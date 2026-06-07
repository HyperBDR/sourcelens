from dataclasses import dataclass
from functools import lru_cache
import json


@dataclass(frozen=True)
class LensLLMResult:
    """LLM completion result plus metering usage."""

    content: str
    usage: dict
    metered: bool


@dataclass(frozen=True)
class QuestionPreflightResult:
    """Question preflight decision."""

    decision: str
    message: str
    rewritten_question: str
    reason: str
    usage: dict
    metered: bool


@lru_cache(maxsize=1)
def _metered_chat_model_class():
    """Build the LangChain adapter only when an LLM call is needed."""

    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    class LensMeteredChatModel(BaseChatModel):
        """LangChain adapter that delegates calls to agentcore metering."""

        model_ref: str
        node_name: str
        user_id: int | None = None

        @property
        def _llm_type(self):
            """Return LangChain model type identifier."""

            return "lens_metered_chat_model"

        @property
        def _identifying_params(self):
            """Return identifying params for LangChain tracing."""

            return {
                "model_ref": self.model_ref,
                "node_name": self.node_name,
            }

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            """Generate one chat response through LLMTracker."""

            del stop, run_manager, kwargs
            from agentcore_metering.adapters.django import LLMTracker

            content, usage = LLMTracker.call_and_track(
                messages=[_message_to_dict(message) for message in messages],
                model_uuid=self.model_ref,
                node_name=self.node_name,
                state={
                    "user_id": self.user_id,
                    "source_type": "lens",
                    "node_name": self.node_name,
                },
            )
            message = AIMessage(
                content=content.strip(),
                response_metadata={"usage": usage},
            )
            return ChatResult(
                generations=[ChatGeneration(message=message)],
                llm_output={"usage": usage},
            )

    return LensMeteredChatModel


def _messages(system, user):
    """Build LangChain chat messages."""

    from langchain_core.messages import HumanMessage, SystemMessage

    return [
        SystemMessage(content=system),
        HumanMessage(content=user),
    ]


def _message_to_dict(message):
    """Convert a LangChain message to the metering tracker shape."""

    role_by_type = {
        "system": "system",
        "human": "user",
        "ai": "assistant",
    }
    return {
        "role": role_by_type.get(message.type, message.type),
        "content": message.content,
    }


def _call_metered_model(*, model_ref, messages, node_name, user_id):
    """Call agentcore metering through the LangChain adapter."""

    chat_model_class = _metered_chat_model_class()
    model = chat_model_class(
        model_ref=str(model_ref),
        node_name=node_name,
        user_id=user_id,
    )
    message = model.invoke(messages)
    usage = message.response_metadata.get("usage", {})
    return LensLLMResult(
        content=str(message.content).strip(),
        usage=usage,
        metered=True,
    )


def rewrite_question(assistant, user, question):
    """Rewrite a question using the assistant preprocess model when set."""

    question = question.strip()
    if not assistant.preprocess_model_ref:
        return LensLLMResult(
            content=question,
            usage={"mode": "fallback"},
            metered=False,
        )

    return _call_metered_model(
        model_ref=assistant.preprocess_model_ref,
        messages=_messages(
            "Rewrite the user question for source retrieval. "
            "Return only the rewritten question.",
            question,
        ),
        node_name="lens_query_rewrite",
        user_id=getattr(user, "pk", None),
    )


def preflight_question(assistant, user, question):
    """Validate and rewrite a question before dispatching to LensNode."""

    question = str(question or "").strip()
    if not question:
        return QuestionPreflightResult(
            decision="clarify",
            message="Please enter a question before submitting.",
            rewritten_question="",
            reason="empty_question",
            usage={"mode": "fallback"},
            metered=False,
        )
    if not assistant.preprocess_model_ref:
        return QuestionPreflightResult(
            decision="allow",
            message="",
            rewritten_question=question,
            reason="fallback_without_preprocess_model",
            usage={"mode": "fallback"},
            metered=False,
        )

    result = _call_metered_model(
        model_ref=assistant.preprocess_model_ref,
        messages=_messages(
            _preflight_system_prompt(assistant),
            question,
        ),
        node_name="lens_query_preflight",
        user_id=getattr(user, "pk", None),
    )
    return _parse_preflight_result(result, question)


def _preflight_system_prompt(assistant):
    """Build the query preflight system prompt."""

    selected_dirs = "\n".join(
        f"- {item.get('path')}"
        for item in assistant.selected_dirs or []
        if isinstance(item, dict) and item.get("path")
    )
    return (
        "You are SourceLens query preflight. Decide whether a user question "
        "should be dispatched to a code/document LensNode assistant.\n\n"
        "Return strict JSON only with these keys:\n"
        "- decision: allow, clarify, or reject\n"
        "- reason: short snake_case reason\n"
        "- message: user-facing message when decision is clarify or reject\n"
        "- rewritten_question: concise rewritten question when decision is allow\n\n"
        "Decision rules:\n"
        "- allow: one coherent question that can be answered from the selected "
        "workspace or project evidence.\n"
        "- clarify: empty, vague, missing key context, or too many unrelated "
        "questions that should be split before execution.\n"
        "- reject: clearly unrelated to the assistant workspace, requests "
        "outside code/document analysis, or requests that should not use this "
        "assistant.\n\n"
        "Assistant context:\n"
        f"Name: {assistant.name}\n"
        f"Task: {assistant.selected_task}\n"
        f"Selected directories:\n{selected_dirs or '- none'}\n\n"
        "Keep message in the user's language when possible."
    )


def _parse_preflight_result(result, original_question):
    """Parse a metered LLM response into a preflight result."""

    payload = _loads_json_object(result.content)
    if payload is None:
        return QuestionPreflightResult(
            decision="clarify",
            message="Please refine the question before running SourceLens.",
            rewritten_question=original_question,
            reason="invalid_preflight_response",
            usage=result.usage,
            metered=result.metered,
        )
    decision = str(payload.get("decision") or "allow").strip().lower()
    if decision not in {"allow", "clarify", "reject"}:
        decision = "allow"

    rewritten_question = str(
        payload.get("rewritten_question") or original_question
    ).strip()
    message = str(payload.get("message") or "").strip()
    reason = str(payload.get("reason") or "").strip() or "unspecified"
    if decision == "allow" and not rewritten_question:
        rewritten_question = original_question
    if decision in {"clarify", "reject"} and not message:
        message = (
            "Please refine the question before running SourceLens."
            if decision == "clarify"
            else "This question is outside the configured SourceLens scope."
        )
    return QuestionPreflightResult(
        decision=decision,
        message=message,
        rewritten_question=rewritten_question,
        reason=reason,
        usage=result.usage,
        metered=result.metered,
    )


def _loads_json_object(content):
    """Load a JSON object from strict or fenced model output."""

    text = str(content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def compose_answer(assistant, user, question, evidence):
    """Compose the final answer through agentcore metering when configured."""

    fallback_answer = (
        f"[{assistant.name}] 已接收问题：{question}\n\n"
        f"检索证据：{evidence}\n\n"
        "当前 Assistant 未配置 preprocess_model_ref，已返回沙箱证据摘要。"
    )
    if not assistant.preprocess_model_ref:
        return LensLLMResult(
            content=fallback_answer,
            usage={"mode": "fallback"},
            metered=False,
        )

    return _call_metered_model(
        model_ref=assistant.preprocess_model_ref,
        messages=_messages(
            "Answer the user question using the provided retrieval evidence. "
            "Be concise and cite relevant evidence keys when useful.",
            f"Question:\n{question}\n\nEvidence:\n{evidence}",
        ),
        node_name="lens_answer",
        user_id=getattr(user, "pk", None),
    )


def postprocess_answer(assistant, user, question, answer):
    """Post-process a LensNode answer when a postprocess model is set."""

    answer = str(answer or "").strip()
    if not assistant.postprocess_model_ref:
        return LensLLMResult(
            content=answer,
            usage={"mode": "skipped"},
            metered=False,
        )

    return _call_metered_model(
        model_ref=assistant.postprocess_model_ref,
        messages=_messages(
            "Polish the assistant answer without changing factual meaning. "
            "Keep the user's language and preserve file path citations.",
            f"Question:\n{question}\n\nAnswer:\n{answer}",
        ),
        node_name="lens_answer_postprocess",
        user_id=getattr(user, "pk", None),
    )
