import base64
import json
import logging
import time
from typing import Any, Optional, Sequence

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.messages.tool import invalid_tool_call
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from .tls import create_ssl_context

LOGGER = logging.getLogger("lensnode")

SAFETY_FINISH_REASONS = {
    "blocked",
    "content_filter",
    "prohibited_content",
    "refusal",
    "safety",
}
LENGTH_FINISH_REASONS = {
    "length",
    "max_completion_tokens",
    "max_output_tokens",
    "max_tokens",
    "max_tokens_reached",
}
INVALID_TOOL_ARGUMENT_PREVIEW_CHARS = 1024


class GatewayStreamError(RuntimeError):
    """Raised when the AI gateway stream returns an error event."""

    def __init__(self, code, message):
        self.code = code or "MODEL_STREAM_ERROR"
        super().__init__(message or self.code)


class RunCancelledError(RuntimeError):
    """Raised inside a worker thread once its run has been cancelled.

    Cancelling the asyncio task cannot interrupt the synchronous agent
    thread, so the thread checks a shared cancel event at every stream
    chunk and before every model call, and unwinds itself with this
    error instead of issuing further model calls for a dead run.
    """

    code = "RUN_CANCELLED"


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
    tls_skip_verify: bool = False
    tls_ca_file: str | None = None
    emit_output: Optional[Any] = None
    # Called on EVERY gateway SSE event (reasoning/tool-call tokens,
    # heartbeats, done) to prove transport liveness to the run watchdog.
    # emit_output stays content-only for the user-facing stream.
    on_activity: Optional[Any] = None
    cancel_event: Optional[Any] = None
    run_uuid: str = ""

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

    def _check_cancelled(self):
        """Abort the current call when the run has been cancelled."""

        if self.cancel_event is not None and self.cancel_event.is_set():
            raise RunCancelledError(
                "Run was cancelled; aborting in-flight model call."
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
        self._check_cancelled()
        payload = {
            "model_ref": self.model_ref,
            "messages": [_message_to_gateway(message) for message in messages],
        }
        if self.run_uuid:
            payload["run_uuid"] = self.run_uuid
            payload["is_subagent"] = _in_subagent_context()
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
        with httpx.Client(
            timeout=self.request_timeout_s,
            verify=create_ssl_context(
                self.tls_skip_verify,
                self.tls_ca_file,
            ),
        ) as client:
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
        finish_reason = None
        # Subagent output must not reach the user-facing answer/thinking
        # stream. deepagents tags subagent runs via the langsmith tracing
        # context; when set, collect content/tool_calls normally but stay
        # silent (no emit_output) so parallel subagents don't interleave
        # into the main bubble.
        silent = _in_subagent_context()

        start = time.monotonic()
        done_received = False
        with httpx.Client(
            timeout=self.request_timeout_s,
            verify=create_ssl_context(
                self.tls_skip_verify,
                self.tls_ca_file,
            ),
        ) as client:
            with client.stream(
                "POST",
                self.ai_gateway_url,
                headers={"Authorization": f"Bearer {self.token}"},
                json={**payload, "stream": True},
            ) as response:
                response.raise_for_status()
                buffer = ""
                for chunk in response.iter_text():
                    self._check_cancelled()
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
                            # Any decoded event — heartbeat, reasoning or
                            # tool-call token, done — proves the gateway
                            # stream is alive, even when nothing is
                            # user-visible.
                            if self.on_activity is not None:
                                self.on_activity()
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
                                finish_reason = data.get("finish_reason")
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
            "finish_reason": finish_reason,
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
    invalid_calls = []
    raw_valid_calls = []
    for raw_call in payload.get("tool_calls") or []:
        function = raw_call.get("function") or {}
        name = str(function.get("name") or "").strip()
        call_id = str(raw_call.get("id") or "").strip()
        arguments = function.get("arguments")
        error = None
        if isinstance(arguments, dict):
            args = arguments
        elif isinstance(arguments, str):
            try:
                args = json.loads(arguments or "{}")
            except json.JSONDecodeError as exc:
                args = None
                error = f"Invalid JSON arguments: {exc.msg}"
        else:
            args = None
            error = "Tool arguments must be a JSON object."
        if args is not None and not isinstance(args, dict):
            args = None
            error = "Tool arguments must decode to a JSON object."
        if not name:
            error = "Tool call name is missing."
        if not call_id:
            error = "Tool call id is missing."
        if error is not None:
            preview = (
                arguments
                if isinstance(arguments, str)
                else json.dumps(arguments, ensure_ascii=False, default=str)
            )
            invalid_calls.append(
                invalid_tool_call(
                    name=name or None,
                    args=preview[:INVALID_TOOL_ARGUMENT_PREVIEW_CHARS],
                    id=call_id or None,
                    error=error,
                )
            )
            continue
        tool_calls.append(
            {
                "name": name,
                "args": args,
                "id": call_id,
            }
        )
        raw_valid_calls.append(raw_call)

    finish_reason = payload.get("finish_reason")
    normalized_reason = str(finish_reason or "").strip().lower()
    response_metadata = {}
    if finish_reason is not None:
        response_metadata["finish_reason"] = str(finish_reason)

    content = payload.get("content") or ""
    if normalized_reason in SAFETY_FINISH_REASONS:
        suppressed = len(tool_calls)
        invalid_calls.extend(
            _suppressed_tool_calls(tool_calls, "Provider safety termination")
        )
        tool_calls = []
        raw_valid_calls = []
        response_metadata.update(
            {
                "safety_terminated": True,
                "suppressed_tool_call_count": suppressed,
            }
        )
        content = _append_runtime_notice(
            content,
            "The provider stopped this response for safety reasons. "
            "Any tool calls from this response were suppressed.",
        )
    elif normalized_reason in LENGTH_FINISH_REASONS:
        suppressed = len(tool_calls)
        invalid_calls.extend(
            _suppressed_tool_calls(tool_calls, "Provider length termination")
        )
        tool_calls = []
        raw_valid_calls = []
        response_metadata.update(
            {
                "model_length_capped": True,
                "suppressed_tool_call_count": suppressed,
            }
        )
        content = _append_runtime_notice(
            content,
            "This response is incomplete because the provider reached its "
            "output length limit. Any unfinished tool calls were suppressed.",
        )

    additional_kwargs = {}
    if raw_valid_calls:
        additional_kwargs["tool_calls"] = raw_valid_calls
    return AIMessage(
        content=content,
        tool_calls=tool_calls,
        invalid_tool_calls=invalid_calls,
        additional_kwargs=additional_kwargs,
        response_metadata=response_metadata,
    )


def _suppressed_tool_calls(tool_calls, error):
    """Return invalid call records for provider-suppressed tool calls."""

    return [
        invalid_tool_call(
            name=call.get("name"),
            args=json.dumps(call.get("args") or {}, ensure_ascii=False),
            id=call.get("id"),
            error=error,
        )
        for call in tool_calls
    ]


def _append_runtime_notice(content, notice):
    """Append a provider termination notice to visible response content."""

    text = str(content or "").strip()
    if not text:
        return notice
    return f"{text}\n\n{notice}"


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
    tls_skip_verify=False,
    tls_ca_file=None,
):
    """Describe one image through the AI gateway."""

    result = describe_image_result(
        image_bytes,
        prompt,
        mime_type,
        model_ref=model_ref,
        ai_gateway_url=ai_gateway_url,
        token=token,
        tls_skip_verify=tls_skip_verify,
        tls_ca_file=tls_ca_file,
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
    tls_skip_verify=False,
    tls_ca_file=None,
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
    with httpx.Client(
        timeout=120,
        verify=create_ssl_context(tls_skip_verify, tls_ca_file),
    ) as client:
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
