import base64
import json
import logging
import time
from typing import Any, Optional, Sequence

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

LOGGER = logging.getLogger("lensnode")


class GatewayStreamError(RuntimeError):
    """Raised when the AI gateway stream returns an error event."""

    def __init__(self, code, message):
        self.code = code or "MODEL_STREAM_ERROR"
        super().__init__(message or self.code)


def _in_subagent_context():
    """Return True if the current LLM call originates from a subagent.

    deepagents wraps each subagent run in a langsmith tracing context
    that sets metadata ls_agent_type="subagent". Reading it lets the
    gateway model keep subagent output out of the user-facing stream so
    parallel subagents do not interleave into the answer bubble.
    """

    try:
        from langsmith.run_helpers import get_tracing_context

        metadata = get_tracing_context().get("metadata") or {}
        return metadata.get("ls_agent_type") == "subagent"
    except Exception:
        return False


class LensGatewayChatModel(BaseChatModel):
    """LangChain chat model that delegates calls to the control plane."""

    model_ref: str
    ai_gateway_url: str
    token: str
    request_timeout_s: int = 120
    emit_output: Optional[Any] = None

    @property
    def _llm_type(self):
        """Return LangChain model type identifier."""

        return "lens_gateway_chat_model"

    @property
    def _identifying_params(self):
        """Return identifying params for tracing."""

        return {
            "model_ref": self.model_ref,
            "ai_gateway_url": self.ai_gateway_url,
        }

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs,
    ):
        """Bind OpenAI-compatible tools to the model."""

        formatted = [convert_to_openai_tool(tool) for tool in tools]
        return self.bind(
            tools=formatted,
            tool_choice=tool_choice,
            **kwargs,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop=None,
        run_manager=None,
        **kwargs,
    ):
        """Generate a response through the LensNode AI gateway."""

        del stop, run_manager
        payload = {
            "model_ref": self.model_ref,
            "messages": [_message_to_gateway(message) for message in messages],
        }
        if kwargs.get("tools") is not None:
            payload["tools"] = kwargs["tools"]
        if kwargs.get("tool_choice") is not None:
            payload["tool_choice"] = kwargs["tool_choice"]
        if kwargs.get("temperature") is not None:
            payload["temperature"] = kwargs["temperature"]
        if kwargs.get("max_tokens") is not None:
            payload["max_tokens"] = kwargs["max_tokens"]

        if self.emit_output is not None:
            return self._generate_streaming(payload)

        payload["return_message"] = True
        start = time.monotonic()
        with httpx.Client(timeout=self.request_timeout_s) as client:
            response = client.post(
                self.ai_gateway_url,
                headers={"Authorization": f"Bearer {self.token}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        message = _message_from_gateway(data.get("message") or {})
        message.response_metadata["usage"] = data.get("usage") or {}
        message.response_metadata["latency_ms"] = int(
            (time.monotonic() - start) * 1000
        )
        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output={"usage": data.get("usage") or {}},
        )

    def _generate_streaming(self, payload):
        """Stream tokens from the gateway, emitting each via emit_output."""

        content_parts = []
        tool_calls = []
        usage = {}
        # Subagent output must not reach the user-facing answer/thinking
        # stream. deepagents tags subagent runs via the langsmith tracing
        # context; when set, collect content/tool_calls normally but stay
        # silent (no emit_output) so parallel subagents don't interleave
        # into the main bubble.
        silent = _in_subagent_context()

        start = time.monotonic()
        done_received = False
        with httpx.Client(timeout=self.request_timeout_s) as client:
            with client.stream(
                "POST",
                self.ai_gateway_url,
                headers={"Authorization": f"Bearer {self.token}"},
                json={**payload, "stream": True},
            ) as response:
                response.raise_for_status()
                buffer = ""
                for chunk in response.iter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        event_str, buffer = buffer.split("\n\n", 1)
                        for line in event_str.splitlines():
                            if not line.startswith("data: "):
                                continue
                            try:
                                data = json.loads(line[6:])
                            except ValueError:
                                continue
                            if data.get("type") == "token":
                                kind = data.get("kind") or "content"
                                text = data.get("content") or ""
                                if text and kind == "content":
                                    content_parts.append(text)
                                    if not silent:
                                        self.emit_output(text)
                            elif data.get("type") == "done":
                                done_received = True
                                usage = data.get("usage") or {}
                                tool_calls = data.get("tool_calls") or []
                            elif data.get("type") == "error":
                                error = data.get("error") or {}
                                raise GatewayStreamError(
                                    error.get("code"),
                                    error.get("message"),
                                )

        if not done_received:
            raise GatewayStreamError(
                "MODEL_STREAM_ERROR",
                "AI gateway stream ended before completion.",
            )

        content = "".join(content_parts)

        # If this turn issued tool calls, its streamed text was
        # intermediate reasoning, not the final answer. Reset now so it
        # moves into the thinking panel before the tools run and never
        # lingers in the answer bubble. The final turn issues no tool
        # calls, so its content stays as the answer.
        if self.emit_output is not None and not silent and tool_calls and content:
            self.emit_output("", reset=True)

        gateway_message = {
            "content": content,
            "tool_calls": [
                {
                    "id": tc.get("id"),
                    "type": "function",
                    "function": tc.get("function") or {},
                }
                for tc in tool_calls
            ],
        }
        message = _message_from_gateway(gateway_message)
        message.response_metadata["usage"] = usage
        message.response_metadata["latency_ms"] = int(
            (time.monotonic() - start) * 1000
        )
        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output={"usage": usage},
        )


def _message_to_gateway(message):
    """Convert a LangChain message to OpenAI-compatible payload."""

    if message.type == "system":
        return {"role": "system", "content": _content_to_text(message.content)}
    if message.type == "human":
        return {"role": "user", "content": _content_to_text(message.content)}
    if message.type == "tool":
        return {
            "role": "tool",
            "content": _content_to_text(message.content),
            "tool_call_id": getattr(message, "tool_call_id", ""),
        }
    if message.type == "ai":
        payload = {
            "role": "assistant",
            "content": _content_to_text(message.content),
        }
        tool_calls = _tool_calls_to_gateway(getattr(message, "tool_calls", []))
        if tool_calls:
            payload["tool_calls"] = tool_calls
        return payload
    return {
        "role": message.type,
        "content": _content_to_text(message.content),
    }


def _tool_calls_to_gateway(tool_calls):
    """Convert LangChain tool calls to OpenAI-compatible tool calls."""

    output = []
    for call in tool_calls or []:
        name = call.get("name")
        if not name:
            continue
        output.append(
            {
                "id": call.get("id"),
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(
                        call.get("args") or {},
                        ensure_ascii=False,
                    ),
                },
            }
        )
    return output


def _message_from_gateway(payload):
    """Convert gateway assistant payload to AIMessage."""

    tool_calls = []
    for raw_call in payload.get("tool_calls") or []:
        function = raw_call.get("function") or {}
        arguments = function.get("arguments") or "{}"
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            args = {}
        tool_calls.append(
            {
                "name": function.get("name", ""),
                "args": args,
                "id": raw_call.get("id"),
            }
        )
    return AIMessage(
        content=payload.get("content") or "",
        tool_calls=tool_calls,
        additional_kwargs={
            "tool_calls": payload.get("tool_calls") or [],
        },
    )


def _content_to_text(content):
    """Return string content for gateway calls."""

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return content
    return json.dumps(content, ensure_ascii=False)


def describe_image(
    image_bytes,
    prompt,
    mime_type,
    *,
    model_ref,
    ai_gateway_url,
    token,
):
    """Describe one image through the AI gateway."""

    result = describe_image_result(
        image_bytes,
        prompt,
        mime_type,
        model_ref=model_ref,
        ai_gateway_url=ai_gateway_url,
        token=token,
    )
    return result.get("content") or ""


def describe_image_result(
    image_bytes,
    prompt,
    mime_type,
    *,
    model_ref,
    ai_gateway_url,
    token,
):
    """Describe one image and return content plus usage."""

    encoded = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model_ref": model_ref,
        "return_message": True,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{encoded}",
                        },
                    },
                ],
            }
        ],
    }
    with httpx.Client(timeout=120) as client:
        response = client.post(
            ai_gateway_url,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    message = data.get("message") or {}
    return {
        "content": message.get("content") or "",
        "usage": data.get("usage") or {},
    }
