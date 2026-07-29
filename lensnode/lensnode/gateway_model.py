import base64
import json
import logging
import re
import threading
import time
from collections import Counter, deque
from contextlib import nullcontext
from typing import Any, Optional, Sequence

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.messages.tool import invalid_tool_call
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import PrivateAttr

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
TOKEN_BUDGET_WARNING = (
    "[TOKEN BUDGET WARNING] This run is approaching its token budget. "
    "Stop expanding the investigation, avoid new tool calls unless strictly "
    "necessary, and synthesize the final answer from evidence already found."
)
LOOP_WARNING = (
    "[LOOP DETECTED] Tool calls are repeating without a final answer. Stop "
    "calling tools and synthesize the result from evidence already collected."
)
LOOP_STOP = (
    "Repeated tool calls reached the runtime safety limit. New tool calls "
    "were suppressed; this answer must use the results already collected."
)
USER_INPUT_BEGIN = "--- BEGIN USER INPUT ---"
USER_INPUT_END = "--- END USER INPUT ---"
REMOTE_DATA_TOOLS = {
    "analyze_structured_output",
    "call_skill_api",
    "inspect_saved_output",
    "run_skill_artifact",
    "run_skill_transform",
    "tool_search",
}
AUTHORITY_TAG_PATTERN = re.compile(
    r"<\s*/?\s*(?:analysis|ignore|important|instruction|override|prompt|role|"
    r"system(?:-reminder|_reminder)?)\b[^>]*>",
    re.IGNORECASE,
)
USER_INPUT_BOUNDARY_PATTERN = re.compile(
    r"---\s*(BEGIN|END)\s+USER INPUT\s*---",
    re.IGNORECASE,
)


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


def _follows_completed_plan(messages):
    """Return whether the last resolved tool call completed the plan."""

    if not messages or getattr(messages[-1], "type", "") != "tool":
        return False
    tool_call_id = str(getattr(messages[-1], "tool_call_id", "") or "")
    for message in reversed(messages[:-1]):
        if getattr(message, "type", "") != "ai":
            continue
        for call in getattr(message, "tool_calls", None) or []:
            if str(call.get("id") or "") != tool_call_id:
                continue
            if call.get("name") != "write_todos":
                return False
            todos = (call.get("args") or {}).get("todos") or []
            return bool(todos) and all(
                item.get("status") == "completed" for item in todos
            )
        return False
    return False


_COMPLETED_PLAN_FINAL_INSTRUCTION = (
    "The substantive text in your previous write_todos turn was not shown "
    "to the user because that turn also invoked a tool. Repeat the entire "
    "final answer now, including every requested record and verification "
    "result. Do not refer to an answer above, summarize it away, call a "
    "tool, or update the plan again."
)


def _http_client_context(
    http_client,
    *,
    timeout,
    tls_skip_verify=False,
    tls_ca_file=None,
):
    """Return an injected shared client or a compatible owned client."""

    if http_client is not None:
        return nullcontext(http_client)
    return httpx.Client(
        timeout=timeout,
        verify=create_ssl_context(tls_skip_verify, tls_ca_file),
    )


class LensGatewayChatModel(BaseChatModel):
    """LangChain chat model that delegates calls to the control plane."""

    model_ref: str
    ai_gateway_url: str
    token: str
    request_timeout_s: int = 120
    tls_skip_verify: bool = False
    tls_ca_file: str | None = None
    http_client: Optional[Any] = None
    emit_output: Optional[Any] = None
    # Called on EVERY gateway SSE event (reasoning/tool-call tokens,
    # heartbeats, done) to prove transport liveness to the run watchdog.
    # emit_output stays content-only for the user-facing stream.
    on_activity: Optional[Any] = None
    cancel_event: Optional[Any] = None
    run_uuid: str = ""
    general_chat_execution_gates: bool = False
    token_budget_max_tokens: int = 200000
    token_budget_final_reserve_tokens: int = 40000
    token_budget_warn_ratio: float = 0.8
    token_budget_wrapup_event: Optional[Any] = None
    loop_repeat_warn: int = 3
    loop_repeat_hard: int = 5
    loop_tool_warn: int = 30
    loop_tool_hard: int = 50
    _usage_lock: Any = PrivateAttr(default_factory=threading.Lock)
    _run_token_usage: dict[str, int] = PrivateAttr(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    )
    _budget_warning_pending: bool = PrivateAttr(default=False)
    _budget_warned: bool = PrivateAttr(default=False)
    _loop_warnings_pending: list[str] = PrivateAttr(default_factory=list)
    _tool_call_history: Any = PrivateAttr(
        default_factory=lambda: deque(maxlen=20)
    )
    _tool_name_history: Any = PrivateAttr(
        default_factory=lambda: deque(maxlen=50)
    )
    _loop_warned: set[str] = PrivateAttr(default_factory=set)
    _tool_warned: set[str] = PrivateAttr(default_factory=set)
    _stop_reason: str | None = PrivateAttr(default=None)

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

    @property
    def token_usage(self):
        """Return cumulative model usage for this run."""

        with self._usage_lock:
            return dict(self._run_token_usage)

    @property
    def stop_reason(self):
        """Return the runtime stop reason, when a guardrail fired."""

        with self._usage_lock:
            return self._stop_reason

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
        control_call = bool(kwargs.get("runtime_control_call"))
        gateway_messages = [
            _message_to_gateway(
                message,
                include_recovery_metadata=(
                    self.general_chat_execution_gates
                ),
            )
            for message in messages
        ]
        warnings = [] if control_call else self._consume_runtime_warnings()
        if warnings:
            gateway_messages.append(
                {"role": "user", "content": "\n\n".join(warnings)}
            )
        payload = {
            "model_ref": self.model_ref,
            "messages": gateway_messages,
        }
        if self.run_uuid:
            payload["run_uuid"] = self.run_uuid
            payload["is_subagent"] = _in_subagent_context()
        if not control_call and kwargs.get("tools") is not None:
            payload["tools"] = kwargs["tools"]
        if not control_call and kwargs.get("tool_choice") is not None:
            payload["tool_choice"] = kwargs["tool_choice"]
        completed_plan_followup = _follows_completed_plan(messages)
        if completed_plan_followup:
            payload.pop("tools", None)
            payload.pop("tool_choice", None)
            payload["messages"].append(
                {
                    "role": "user",
                    "content": _COMPLETED_PLAN_FINAL_INSTRUCTION,
                }
            )
        if kwargs.get("temperature") is not None:
            payload["temperature"] = kwargs["temperature"]
        if kwargs.get("max_tokens") is not None:
            payload["max_tokens"] = kwargs["max_tokens"]

        if self.emit_output is not None and not control_call:
            return self._generate_streaming(
                payload,
                publish_tokens=(
                    bool(kwargs.get("runtime_final_synthesis"))
                    or completed_plan_followup
                ),
            )

        payload["return_message"] = True
        start = time.monotonic()
        with _http_client_context(
            self.http_client,
            timeout=self.request_timeout_s,
            tls_skip_verify=self.tls_skip_verify,
            tls_ca_file=self.tls_ca_file,
        ) as client:
            response = client.post(
                self.ai_gateway_url,
                headers={"Authorization": f"Bearer {self.token}"},
                json=payload,
                timeout=self.request_timeout_s,
            )
            response.raise_for_status()
            data = response.json()

        message = _message_from_gateway(data.get("message") or {})
        message.response_metadata["usage"] = data.get("usage") or {}
        message.response_metadata["latency_ms"] = int(
            (time.monotonic() - start) * 1000
        )
        message = self._apply_token_budget(message, data.get("usage") or {})
        message = self._apply_loop_detection(message)
        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output={"usage": data.get("usage") or {}},
        )

    def _generate_streaming(self, payload, *, publish_tokens=False):
        """Consume a gateway stream and publish only a final answer turn."""

        content_parts = []
        tool_calls = []
        usage = {}
        finish_reason = None
        # Subagent output must not reach the user-facing answer stream.
        # deepagents tags subagent runs via the langsmith tracing context;
        # when set, collect content and tool calls normally but stay silent.
        silent = _in_subagent_context()

        start = time.monotonic()
        done_received = False
        with _http_client_context(
            self.http_client,
            timeout=self.request_timeout_s,
            tls_skip_verify=self.tls_skip_verify,
            tls_ca_file=self.tls_ca_file,
        ) as client:
            with client.stream(
                "POST",
                self.ai_gateway_url,
                headers={"Authorization": f"Bearer {self.token}"},
                json={**payload, "stream": True},
                timeout=self.request_timeout_s,
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
                                    if (
                                        publish_tokens
                                        and self.emit_output is not None
                                        and not silent
                                    ):
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

        # A turn that issues tool calls contains intermediate reasoning, not
        # the final answer. Buffer the turn until its terminal event reveals
        # whether tools were requested, then publish only answer turns. This
        # prevents answer-like text from appearing and suddenly disappearing
        # when the agent continues with a tool call.
        if (
            self.emit_output is not None
            and not silent
            and content
            and not tool_calls
            and not publish_tokens
        ):
            self.emit_output(content)

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
        message = self._apply_token_budget(message, usage)
        message = self._apply_loop_detection(message)
        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output={"usage": usage},
        )

    def _consume_runtime_warnings(self):
        """Consume pending guardrail warnings for one model request."""

        with self._usage_lock:
            warnings = []
            if self._budget_warning_pending:
                warnings.append(TOKEN_BUDGET_WARNING)
            self._budget_warning_pending = False
            warnings.extend(self._loop_warnings_pending)
            self._loop_warnings_pending.clear()
            return warnings

    def _apply_token_budget(self, message, usage):
        """Accumulate usage and fail closed when the run budget is reached."""

        source_metadata = dict(message.response_metadata or {})
        prompt_tokens = _usage_int(
            usage,
            "prompt_tokens",
            fallback_key="input_tokens",
        )
        completion_tokens = _usage_int(
            usage,
            "completion_tokens",
            fallback_key="output_tokens",
        )
        total_tokens = _usage_int(usage, "total_tokens")
        if total_tokens <= 0:
            total_tokens = prompt_tokens + completion_tokens

        with self._usage_lock:
            if source_metadata.get("safety_terminated"):
                self._stop_reason = "safety_terminated"
            elif source_metadata.get("model_length_capped"):
                self._stop_reason = "model_length_capped"
            self._run_token_usage["prompt_tokens"] += prompt_tokens
            self._run_token_usage["completion_tokens"] += completion_tokens
            self._run_token_usage["total_tokens"] += total_tokens
            cumulative = dict(self._run_token_usage)
            limit = (
                max(int(self.token_budget_max_tokens or 0), 0)
                if self.general_chat_execution_gates
                else 0
            )
            warn_ratio = min(
                max(float(self.token_budget_warn_ratio or 0), 0.0),
                1.0,
            )
            reserve = min(
                max(int(self.token_budget_final_reserve_tokens or 0), 0),
                limit,
            )
            work_limit = max(limit - reserve, 0)
            wrapup_needed = bool(
                limit
                and reserve
                and cumulative["total_tokens"] >= work_limit
            )
            hard_stop = bool(limit and cumulative["total_tokens"] >= limit)
            if wrapup_needed and self.token_budget_wrapup_event is not None:
                self.token_budget_wrapup_event.set()
            if hard_stop:
                self._stop_reason = "token_capped"
                self._budget_warning_pending = False
            elif wrapup_needed:
                self._stop_reason = "token_budget_wrapup"
            elif (
                limit
                and not self._budget_warned
                and cumulative["total_tokens"] >= limit * warn_ratio
            ):
                self._budget_warned = True
                self._budget_warning_pending = True

        metadata = source_metadata
        metadata["run_token_usage"] = cumulative
        if wrapup_needed:
            metadata["token_budget_wrapup"] = True
        if not hard_stop:
            return message.model_copy(
                update={"response_metadata": metadata}
            )

        metadata["token_capped"] = True
        if not message.tool_calls:
            return message.model_copy(
                update={"response_metadata": metadata}
            )

        return _stop_tool_calls(
            message,
            "",
            "Run token budget reached",
            {"token_capped": True},
        )

    def _apply_loop_detection(self, message):
        """Warn on repeated tool activity and stop persistent loops."""

        if not self.general_chat_execution_gates:
            return message
        calls = list(message.tool_calls or [])
        if not calls:
            return message
        fingerprint = _tool_call_fingerprint(calls)
        names = [str(call.get("name") or "") for call in calls]

        with self._usage_lock:
            self._tool_call_history.append(fingerprint)
            repeat_count = self._tool_call_history.count(fingerprint)
            for name in names:
                self._tool_name_history.append(name)
            frequencies = Counter(self._tool_name_history)

            repeat_warn = max(int(self.loop_repeat_warn or 1), 1)
            repeat_hard = max(
                int(self.loop_repeat_hard or repeat_warn),
                repeat_warn,
            )
            tool_warn = max(int(self.loop_tool_warn or 1), 1)
            tool_hard = max(
                int(self.loop_tool_hard or tool_warn),
                tool_warn,
            )
            loop_tool = next(
                (
                    name
                    for name in names
                    if frequencies[name] >= tool_hard
                ),
                None,
            )
            hard_stop = repeat_count >= repeat_hard or loop_tool is not None

            if hard_stop:
                self._stop_reason = "loop_capped"
                self._loop_warnings_pending.clear()
            else:
                if (
                    repeat_count >= repeat_warn
                    and fingerprint not in self._loop_warned
                ):
                    self._loop_warned.add(fingerprint)
                    self._loop_warnings_pending.append(LOOP_WARNING)
                for name in names:
                    if (
                        frequencies[name] >= tool_warn
                        and name not in self._tool_warned
                    ):
                        self._tool_warned.add(name)
                        self._loop_warnings_pending.append(LOOP_WARNING)

        if not hard_stop:
            return message
        updates = {"loop_capped": True}
        if loop_tool is not None:
            updates["loop_tool"] = loop_tool
        return _stop_tool_calls(
            message,
            LOOP_STOP,
            "Tool-call loop safety limit reached",
            updates,
        )


def _message_to_gateway(message, *, include_recovery_metadata=False):
    """Convert a LangChain message to OpenAI-compatible payload."""

    if message.type == "system":
        return {"role": "system", "content": _content_to_text(message.content)}
    if message.type == "human":
        content = _content_to_text(message.content)
        if not (message.additional_kwargs or {}).get("hide_from_ui"):
            content = _wrap_user_input(content)
        return {"role": "user", "content": content}
    if message.type == "tool":
        tool_name = str(getattr(message, "name", "") or "")
        content = _tool_result_for_gateway(
            message.content,
            tool_name,
            include_recovery_metadata=include_recovery_metadata,
        )
        return {
            "role": "tool",
            "content": content,
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


def _wrap_user_input(content):
    """Return a neutralized user-input view without mutating the message."""

    if isinstance(content, str):
        text = neutralize_untrusted_text(content, neutralize_boundaries=True)
        return f"{USER_INPUT_BEGIN}\n{text}\n{USER_INPUT_END}"
    if not isinstance(content, list):
        return content

    wrapped = [{"type": "text", "text": USER_INPUT_BEGIN}]
    for item in content:
        if isinstance(item, str):
            wrapped.append(
                neutralize_untrusted_text(
                    item,
                    neutralize_boundaries=True,
                )
            )
            continue
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            item = dict(item)
            item["text"] = neutralize_untrusted_text(
                item["text"],
                neutralize_boundaries=True,
            )
        wrapped.append(item)
    wrapped.append({"type": "text", "text": USER_INPUT_END})
    return wrapped


def neutralize_untrusted_text(text, *, neutralize_boundaries=False):
    """Escape prompt-like markup in an untrusted model-facing view."""

    value = str(text)
    if neutralize_boundaries:
        value = USER_INPUT_BOUNDARY_PATTERN.sub(
            lambda match: f"[{match.group(1).upper()} USER INPUT]",
            value,
        )
    return AUTHORITY_TAG_PATTERN.sub(
        lambda match: match.group(0).replace("<", "&lt;").replace(
            ">", "&gt;"
        ),
        value,
    )


def _tool_result_for_gateway(
    content,
    tool_name,
    *,
    include_recovery_metadata=False,
):
    """Return a mode-scoped, neutralized tool-result view."""

    text = _content_to_text(content)
    if not isinstance(text, str):
        return text

    try:
        result = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        result = None
    if (
        include_recovery_metadata
        and isinstance(result, dict)
        and "ok" in result
    ):
        result = dict(result)
        result["result_meta"] = _tool_result_metadata(result, tool_name)
        text = json.dumps(result, ensure_ascii=False)
    if tool_name in REMOTE_DATA_TOOLS or tool_name.startswith("mcp__"):
        text = neutralize_untrusted_text(text)
    return text


def _tool_result_metadata(result, tool_name):
    """Classify a structured tool result for consistent model recovery."""

    if result.get("ok") is True:
        return {
            "status": "success",
            "source": tool_name,
        }

    error_code = _tool_error_code(result)
    artifact_diagnostic = (
        str(result.get("stderr") or "").upper()
        if tool_name == "run_skill_artifact"
        else ""
    )
    diagnostic = " ".join(
        str(result.get(key) or "")
        for key in ("error", "code", "message", "detail", "stderr")
    ).upper()
    artifact_request_failure = any(
        marker in artifact_diagnostic
        for marker in (
            "404",
            "NOTFOUND",
            "NOT FOUND",
            "UNKNOWN FLAG",
            "INVALID ARGUMENT",
            "USAGE:",
            "数据不存在",
        )
    )
    artifact_server_failure = bool(
        re.search(r"\b(?:HTTP\s*)?5\d{2}\b", artifact_diagnostic)
    )
    try:
        status_code = int(result.get("status_code") or 0)
    except (TypeError, ValueError):
        status_code = 0
    upstream_server_failure = 500 <= status_code < 600
    if any(
        marker in error_code
        for marker in ("AUTH", "CONFIG", "CREDENTIAL", "PERMISSION")
    ):
        error_type = "configuration"
        recoverable = False
        action = (
            "Stop retrying this tool and report the configuration or "
            "authorization requirement."
        )
    elif artifact_server_failure or upstream_server_failure or any(
        marker in error_code
        for marker in ("HTTP_REQUEST_FAILED", "RATE_LIMIT", "TIMEOUT")
    ):
        error_type = "transient"
        recoverable = True
        action = (
            "Retry this tool at most once, then report the failure if it "
            "persists."
        )
    elif any(
        marker in error_code
        for marker in (
            "BUDGET",
            "LOOP",
            "POLICY",
            "REPEATED",
            "STALLED",
        )
    ):
        error_type = "policy"
        recoverable = False
        action = (
            "Stop calling this tool and synthesize the answer from evidence "
            "already collected."
        )
    elif artifact_request_failure or any(
        marker in error_code
        for marker in (
            "INVALID",
            "MALFORMED",
            "NOT_FOUND",
            "PARSE",
            "PATH",
            "SCHEMA",
            "SYNTAX",
            "VALIDATION",
        )
    ) or any(
        marker in diagnostic
        for marker in (
            "INVALID QUERY",
            "INVALID EXPRESSION",
            "SQL SYNTAX",
            "SYNTAX ERROR",
            "UNKNOWN FLAG",
            "USAGE:",
            "VALIDATION ERROR",
            "RESPONSE VALIDATION",
        )
    ):
        error_type = "request"
        recoverable = True
        action = "Correct the tool arguments before retrying."
    else:
        error_type = "tool"
        recoverable = True
        action = (
            "Correct the request once or use another available capability; "
            "do not repeat the same failing call beyond that."
        )
    return {
        "status": "error",
        "error_type": error_type,
        "recoverable_by_model": recoverable,
        "recommended_next_action": action,
        "source": tool_name,
    }


def _tool_error_code(result):
    """Return an uppercase error code from common tool-result shapes."""

    error = result.get("error")
    if isinstance(error, dict):
        error = error.get("code") or error.get("type") or error.get("message")
    return str(error or result.get("code") or "").upper()


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


def _usage_int(usage, key, fallback_key=None):
    """Return a non-negative integer usage field."""

    value = usage.get(key)
    if value is None and fallback_key is not None:
        value = usage.get(fallback_key)
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _tool_call_fingerprint(tool_calls):
    """Return a stable fingerprint for one model tool-call set."""

    normalized = [
        {
            "name": str(call.get("name") or ""),
            "args": call.get("args") or {},
        }
        for call in tool_calls
    ]
    normalized.sort(
        key=lambda item: json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    )
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _stop_tool_calls(message, notice, error, metadata_updates):
    """Return a copy whose tool calls are retained only as invalid records."""

    suppressed = list(message.tool_calls or [])
    invalid_calls = list(message.invalid_tool_calls or [])
    invalid_calls.extend(_suppressed_tool_calls(suppressed, error))
    additional_kwargs = dict(message.additional_kwargs or {})
    additional_kwargs.pop("tool_calls", None)
    additional_kwargs.pop("function_call", None)
    metadata = dict(message.response_metadata or {})
    metadata.update(metadata_updates)
    metadata["suppressed_tool_call_count"] = len(suppressed)
    if metadata.get("finish_reason") in {
        "function_call",
        "tool_calls",
    }:
        metadata["finish_reason"] = "stop"
    return message.model_copy(
        update={
            "content": (
                _append_runtime_notice(message.content, notice)
                if notice
                else message.content
            ),
            "tool_calls": [],
            "invalid_tool_calls": invalid_calls,
            "additional_kwargs": additional_kwargs,
            "response_metadata": metadata,
        }
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
    http_client=None,
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
    with _http_client_context(
        http_client,
        timeout=120,
        tls_skip_verify=tls_skip_verify,
        tls_ca_file=tls_ca_file,
    ) as client:
        response = client.post(
            ai_gateway_url,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
    message = data.get("message") or {}
    return {
        "content": message.get("content") or "",
        "usage": data.get("usage") or {},
    }
