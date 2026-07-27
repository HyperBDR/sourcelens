import json
import threading
from types import SimpleNamespace

from langchain_core.messages import ToolMessage

from lensnode import agent_runtime
from lensnode.agent_runtime import (
    _build_initial_messages,
    _emit_new_tool_calls,
    _finalize_runtime_outcome,
    _general_chat_system_prompt,
    _normalize_plan_steps,
    _parse_route_decision,
    _pick_text,
    _run_agent_with_turn_limit,
    _strip_dangling_tool_call,
    _synthesize_wrapup_answer,
)


class _Msg:
    """Minimal stand-in for a LangChain message with a type/content."""

    def __init__(
        self,
        type_,
        content="",
        tool_calls=None,
        response_metadata=None,
    ):
        self.type = type_
        self.content = content
        self.tool_calls = tool_calls
        self.response_metadata = response_metadata or {}


class _FakeStreamAgent:
    """Echoes a message prefix then streams new AI turns, one per state."""

    def __init__(self, prefix, new_ai_turns):
        self._prefix = prefix
        self._new_ai_turns = new_ai_turns

    def stream(self, _inp, stream_mode=None, config=None):
        messages = list(self._prefix)
        for index in range(self._new_ai_turns):
            messages = messages + [_Msg("ai", f"answer {index + 1}")]
            yield {"messages": list(messages)}


def test_build_initial_messages_prepends_and_filters_history():
    history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "system", "content": "ignored"},
        {"role": "assistant", "content": ""},
    ]

    messages = _build_initial_messages(history, "q2")

    assert messages == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
    ]


def test_build_initial_messages_without_history():
    assert _build_initial_messages(None, "q") == [
        {"role": "user", "content": "q"}
    ]


def test_model_event_records_cache_reasoning_and_latency():
    events = []
    message = _Msg(
        "ai",
        "answer",
        response_metadata={
            "usage": {
                "model": "deepseek-v4-flash",
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "cached_tokens": 80,
                "reasoning_tokens": 5,
            },
            "latency_ms": 1234,
        },
    )

    agent_runtime._emit_new_model_calls(
        [message],
        set(),
        lambda name, detail: events.append((name, detail)),
    )

    assert events[0][0] == "llm.response"
    assert events[0][1]["cached_tokens"] == 80
    assert events[0][1]["reasoning_tokens"] == 5
    assert events[0][1]["latency_ms"] == 1234


def test_write_todos_emits_user_visible_normalized_plan():
    events = []
    message = _Msg(
        "ai",
        tool_calls=[
            {
                "id": "call-plan",
                "name": "write_todos",
                "args": {
                    "todos": [
                        {
                            "content": "Inspect the current flow",
                            "status": "completed",
                        },
                        {
                            "content": "Implement the event contract",
                            "status": "in_progress",
                        },
                        {"content": "Verify the UI", "status": "pending"},
                    ]
                },
            }
        ],
    )

    _emit_new_tool_calls(
        [message],
        set(),
        lambda name, detail: events.append((name, detail)),
    )

    assert events == [
        (
            "workflow.plan.updated",
            {
                "event_type": "plan.updated",
                "visibility": "user",
                "payload": {
                    "revision": 1,
                    "steps": [
                        {
                            "id": "step-1",
                            "title": "Inspect the current flow",
                            "status": "completed",
                        },
                        {
                            "id": "step-2",
                            "title": "Implement the event contract",
                            "status": "in_progress",
                        },
                        {
                            "id": "step-3",
                            "title": "Verify the UI",
                            "status": "pending",
                        },
                    ],
                },
            },
        )
    ]


def test_direct_execution_stages_start_with_real_runtime_state():
    events = []
    state = agent_runtime._create_direct_stage_state("English")

    agent_runtime._start_direct_stages(
        state,
        lambda name, detail: events.append((name, detail)),
    )

    assert [detail["payload"]["status"] for _, detail in events] == [
        "completed",
        "in_progress",
        "pending",
    ]
    assert [detail["payload"]["order"] for _, detail in events] == [1, 2, 3]
    assert [detail["payload"]["revision"] for _, detail in events] == [1, 2, 3]
    assert all(name == "workflow.stage.updated" for name, _ in events)


def test_direct_execution_stage_counts_actual_tool_calls():
    events = []
    state = agent_runtime._create_direct_stage_state("English")
    agent_runtime._start_direct_stages(state, lambda *_args: None)
    message = _Msg(
        "ai",
        tool_calls=[
            {"id": "call-orders", "name": "call_skill_api", "args": {}},
        ],
    )

    _emit_new_tool_calls(
        [message],
        set(),
        lambda name, detail: events.append((name, detail)),
        direct_stage_state=state,
    )

    stage_events = [
        detail for name, detail in events if name == "workflow.stage.updated"
    ]
    assert state["tool_count"] == 1
    assert stage_events[-1]["payload"]["id"] == "execute"
    assert stage_events[-1]["payload"]["status"] == "in_progress"
    assert stage_events[-1]["payload"]["summary"] == "Started 1 operation"


def test_direct_execution_stages_record_blocked_outcome():
    events = []
    state = agent_runtime._create_direct_stage_state("English")
    agent_runtime._start_direct_stages(state, lambda *_args: None)

    agent_runtime._finish_direct_stages(
        state,
        lambda name, detail: events.append((name, detail)),
        outcome="blocked",
    )

    payloads = [detail["payload"] for _, detail in events]
    assert payloads[0]["id"] == "execute"
    assert payloads[0]["status"] == "failed"
    assert payloads[1]["id"] == "answer"
    assert payloads[1]["status"] == "completed"


def test_direct_execution_stages_do_not_mark_partial_work_completed():
    events = []
    state = agent_runtime._create_direct_stage_state("English")
    agent_runtime._start_direct_stages(state, lambda *_args: None)

    agent_runtime._finish_direct_stages(
        state,
        lambda name, detail: events.append((name, detail)),
        outcome="partial",
    )

    payloads = [detail["payload"] for _, detail in events]
    assert payloads[0]["id"] == "execute"
    assert payloads[0]["status"] == "failed"
    assert payloads[0]["summary"] == "Execution ended with partial results"
    assert payloads[1]["status"] == "completed"


def test_route_decision_parses_json_and_uses_safe_fallback():
    decision = _parse_route_decision(
        '```json\n{"intent":"action","complexity":"simple",'
        '"route":"direct_execute","required_capabilities":["skill"]}\n```'
    )

    assert decision == {
        "intent": "action",
        "complexity": "simple",
        "route": "direct_execute",
        "required_capabilities": ["skill"],
        "evidence_requirement": "tool_result",
    }
    assert _parse_route_decision("not json")["route"] == "plan_execute"


def test_route_decision_requires_execution_for_external_business_facts():
    decision = _parse_route_decision(
        '{"intent":"informational","complexity":"simple",'
        '"route":"direct_answer","required_capabilities":["skill"],'
        '"evidence_requirement":"tool_result"}'
    )

    assert decision["route"] == "direct_execute"
    assert decision["evidence_requirement"] == "tool_result"


def test_guidance_route_keeps_plan_execution_without_tool_evidence():
    decision = _parse_route_decision(
        '{"intent":"informational","complexity":"complex",'
        '"route":"plan_execute","required_capabilities":["skill"],'
        '"evidence_requirement":"none"}'
    )

    assert decision["route"] == "plan_execute"
    assert decision["evidence_requirement"] == "none"


def test_malformed_route_fails_closed_to_tool_evidence():
    decision = _parse_route_decision("not json")

    assert decision["route"] == "plan_execute"
    assert decision["evidence_requirement"] == "tool_result"


def test_advisory_missing_capability_does_not_override_skill_success():
    middleware = SimpleNamespace(
        success_count=1,
        outcome="completed",
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="tool_result",
        truncated=False,
        stop_reason=None,
    )

    assert outcome == "completed"
    assert termination_detail == {}


def test_advisory_missing_capability_blocks_unverified_answer():
    middleware = SimpleNamespace(
        success_count=0,
        outcome="completed",
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="tool_result",
        truncated=False,
        stop_reason=None,
    )

    assert outcome == "blocked"
    assert termination_detail["reason"] == "evidence_unavailable"


def test_guidance_skill_does_not_require_tool_execution():
    middleware = SimpleNamespace(
        success_count=0,
        successful_capabilities=set(),
        outcome="completed",
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="none",
        truncated=False,
        stop_reason=None,
    )

    assert outcome == "completed"
    assert termination_detail == {}


def test_artifact_requirement_needs_actual_delivery():
    middleware = SimpleNamespace(
        success_count=1,
        successful_capabilities={"skill"},
        outcome="completed",
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="artifact",
        truncated=False,
        stop_reason=None,
    )

    assert outcome == "blocked"
    assert termination_detail["reason"] == "evidence_unavailable"


def test_artifact_requirement_completes_after_actual_delivery():
    middleware = SimpleNamespace(
        success_count=2,
        successful_capabilities={"skill", "artifact_delivery"},
        outcome="completed",
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="artifact",
        truncated=False,
        stop_reason=None,
    )

    assert outcome == "completed"
    assert termination_detail == {}


def test_blocked_evidence_is_not_downgraded_to_partial_when_truncated():
    middleware = SimpleNamespace(
        success_count=0,
        successful_capabilities=set(),
        outcome="completed",
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="tool_result",
        truncated=True,
        stop_reason="turn_limit",
    )

    assert outcome == "blocked"
    assert termination_detail["reason"] == "evidence_unavailable"


def test_guidance_becomes_partial_when_execution_is_truncated():
    middleware = SimpleNamespace(
        success_count=0,
        successful_capabilities=set(),
        outcome="completed",
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="none",
        truncated=True,
        stop_reason="turn_limit",
    )

    assert outcome == "partial"
    assert termination_detail == {"reason": "turn_limit"}


def test_plan_steps_are_bounded_and_normalized():
    todos = [
        {"content": "x" * 300, "status": "unknown"},
        {"content": "Valid", "status": "completed"},
        {"content": "", "status": "pending"},
        *[
            {"content": f"Step {index}", "status": "pending"}
            for index in range(20)
        ],
    ]

    steps = _normalize_plan_steps(todos)

    assert len(steps) == 11
    assert len(steps[0]["title"]) == 240
    assert steps[0]["status"] == "pending"
    assert steps[1]["status"] == "completed"


def test_general_chat_prompt_forbids_unverified_business_results():
    prompt = _general_chat_system_prompt(
        {
            "question": "查询订单详情",
            "runtime_route": "direct_execute",
        }
    )

    assert "Never claim that a tool was called" in prompt
    assert "Never invent order" in prompt


def test_capability_boundary_stops_configuration_failure_immediately():
    events = []
    stop_event = threading.Event()
    middleware = agent_runtime.CapabilityBoundaryMiddleware(
        emit_event=lambda name, detail: events.append((name, detail)),
        stop_event=stop_event,
    )
    request = SimpleNamespace(
        tool=SimpleNamespace(name="call_skill_api"),
        tool_call={"name": "call_skill_api", "id": "call-1"},
    )

    result = middleware.wrap_tool_call(
        request,
        lambda _request: ToolMessage(
            content='{"ok":false,"error":"AUTH_REQUIRED"}',
            name="call_skill_api",
            tool_call_id="call-1",
            status="error",
        ),
    )

    assert result.status == "error"
    assert stop_event.is_set()
    assert middleware.outcome == "blocked"
    assert middleware.termination_detail["capability"] == "skill"
    assert events[0][0] == "workflow.capability.blocked"


def test_capability_boundary_allows_one_transient_retry():
    stop_event = threading.Event()
    middleware = agent_runtime.CapabilityBoundaryMiddleware(
        stop_event=stop_event
    )
    request = SimpleNamespace(
        tool=SimpleNamespace(name="mcp__orders"),
        tool_call={"name": "mcp__orders", "id": "call-1"},
    )

    def fail(_request):
        return ToolMessage(
            content='{"ok":false,"error":"HTTP_REQUEST_FAILED"}',
            name="mcp__orders",
            tool_call_id="call-1",
            status="error",
        )

    middleware.wrap_tool_call(request, fail)
    assert not stop_event.is_set()
    middleware.wrap_tool_call(request, fail)
    assert stop_event.is_set()
    assert middleware.termination_detail["capability"] == "mcp"


def test_capability_boundary_allows_artifact_argument_correction_after_404():
    stop_event = threading.Event()
    middleware = agent_runtime.CapabilityBoundaryMiddleware(
        stop_event=stop_event
    )
    request = SimpleNamespace(
        tool=SimpleNamespace(name="run_skill_artifact"),
        tool_call={"name": "run_skill_artifact", "id": "call-1"},
    )

    def not_found(_request):
        return ToolMessage(
            content=json.dumps(
                {
                    "ok": False,
                    "returncode": 5,
                    "stderr": (
                        "Income API returned 404: NotFound: "
                        "data does not exist"
                    ),
                }
            ),
            name="run_skill_artifact",
            tool_call_id="call-1",
            status="error",
        )

    middleware.wrap_tool_call(request, not_found)

    assert not stop_event.is_set()
    middleware.wrap_tool_call(request, not_found)
    assert stop_event.is_set()
    assert middleware.termination_detail["error_type"] == "request"


def test_capability_boundary_counts_raw_mcp_success_as_evidence():
    middleware = agent_runtime.CapabilityBoundaryMiddleware()
    request = SimpleNamespace(
        tool=SimpleNamespace(name="mcp__orders__lookup"),
        tool_call={"name": "mcp__orders__lookup", "id": "call-1"},
    )

    middleware.wrap_tool_call(
        request,
        lambda _request: ToolMessage(
            content='{"order_id":"HWINSTAD2025071509"}',
            name="mcp__orders__lookup",
            tool_call_id="call-1",
        ),
    )

    assert middleware.success_count == 1
    assert middleware.successful_capabilities == {"mcp"}


def test_capability_boundary_rejects_raw_mcp_error_as_evidence():
    middleware = agent_runtime.CapabilityBoundaryMiddleware()
    request = SimpleNamespace(
        tool=SimpleNamespace(name="mcp__orders__lookup"),
        tool_call={"name": "mcp__orders__lookup", "id": "call-1"},
    )

    middleware.wrap_tool_call(
        request,
        lambda _request: ToolMessage(
            content="remote order service failed",
            name="mcp__orders__lookup",
            tool_call_id="call-1",
            status="error",
        ),
    )

    assert middleware.success_count == 0
    assert middleware.termination_detail["capability"] == "mcp"


def test_capability_boundary_does_not_count_auxiliary_tools_as_evidence():
    middleware = agent_runtime.CapabilityBoundaryMiddleware()

    for index, tool_name in enumerate(
        ("write_todos", "tool_search", "read_file"),
        start=1,
    ):
        request = SimpleNamespace(
            tool=SimpleNamespace(name=tool_name),
            tool_call={"name": tool_name, "id": f"call-{index}"},
        )
        middleware.wrap_tool_call(
            request,
            lambda _request, name=tool_name, call_id=f"call-{index}": (
                ToolMessage(
                    content='{"ok":true}',
                    name=name,
                    tool_call_id=call_id,
                )
            ),
        )

    assert middleware.success_count == 0
    assert middleware.successful_capabilities == set()


def test_capability_boundary_counts_workspace_summary_as_evidence():
    middleware = agent_runtime.CapabilityBoundaryMiddleware()
    request = SimpleNamespace(
        tool=SimpleNamespace(name="summarize_recent_changes"),
        tool_call={"name": "summarize_recent_changes", "id": "call-1"},
    )

    middleware.wrap_tool_call(
        request,
        lambda _request: ToolMessage(
            content='{"ok":true,"repositories":[]}',
            name="summarize_recent_changes",
            tool_call_id="call-1",
        ),
    )

    assert middleware.success_count == 1
    assert middleware.successful_capabilities == {"workspace"}


def test_capability_boundary_marks_partial_after_prior_success():
    stop_event = threading.Event()
    middleware = agent_runtime.CapabilityBoundaryMiddleware(
        stop_event=stop_event
    )
    success_request = SimpleNamespace(
        tool=SimpleNamespace(name="run_skill_artifact"),
        tool_call={"name": "run_skill_artifact", "id": "call-success"},
    )
    failed_request = SimpleNamespace(
        tool=SimpleNamespace(name="save_deliverable"),
        tool_call={"name": "save_deliverable", "id": "call-failed"},
    )

    middleware.wrap_tool_call(
        success_request,
        lambda _request: ToolMessage(
            content='{"ok":true}',
            name="run_skill_artifact",
            tool_call_id="call-success",
        ),
    )
    middleware.wrap_tool_call(
        failed_request,
        lambda _request: ToolMessage(
            content='{"ok":false,"error":"DELIVERY_FAILED"}',
            name="save_deliverable",
            tool_call_id="call-failed",
            status="error",
        ),
    )

    assert stop_event.is_set()
    assert middleware.outcome == "partial"
    assert middleware.successful_capabilities == {"skill"}
    assert middleware.termination_detail["capability"] == "artifact_delivery"


def test_general_chat_middleware_removes_task_tool():
    class Request:
        tools = [
            SimpleNamespace(name="run_skill_artifact"),
            SimpleNamespace(name="task"),
        ]

        def override(self, **changes):
            return SimpleNamespace(**changes)

    middleware = agent_runtime._NoTaskMiddleware()
    result = middleware.wrap_model_call(
        Request(),
        lambda request: [tool.name for tool in request.tools],
    )

    assert result == ["run_skill_artifact"]


def test_general_chat_middleware_denies_task_execution():
    events = []
    handler_called = []
    middleware = agent_runtime._NoTaskMiddleware(
        lambda name, detail: events.append((name, detail))
    )
    request = SimpleNamespace(
        tool=SimpleNamespace(name="task"),
        tool_call={"name": "task", "id": "call-1", "args": {}},
    )

    result = middleware.wrap_tool_call(
        request,
        lambda _request: handler_called.append(True),
    )

    assert handler_called == []
    assert result.status == "error"
    assert result.tool_call_id == "call-1"
    assert "SUBAGENT_DISABLED" in result.content
    assert events[0][0] == "tool.task.denied"


def test_general_chat_uses_no_task_middleware():
    middleware = agent_runtime._agent_middleware(
        {"task": "general_chat"},
        summarizer=None,
    )

    assert any(
        isinstance(item, agent_runtime._NoTaskMiddleware)
        for item in middleware
    )


def test_general_chat_prompt_prefers_bounded_large_result_tools():
    prompt = agent_runtime._general_chat_system_prompt(
        {"question": "Summarize all orders."},
        [],
    )

    assert "analyze_structured_output" in prompt
    assert "inspect_saved_output" in prompt
    assert "run_skill_transform" in prompt
    assert "Never use read_file or grep" in prompt
    assert "/large_tool_results/" in prompt


def test_knowledge_qa_keeps_task_tool_available():
    middleware = agent_runtime._agent_middleware(
        {"task": "knowledge_qa"},
        summarizer=None,
    )

    assert not any(
        isinstance(item, agent_runtime._NoTaskMiddleware)
        for item in middleware
    )


def test_agent_middleware_includes_deferred_mcp_filter():
    deferred = object()

    middleware = agent_runtime._agent_middleware(
        {"task": "knowledge_qa"},
        summarizer=None,
        mcp_middleware=deferred,
    )

    assert middleware == [deferred]


def test_fast_subagent_inherits_deferred_mcp_filter():
    deferred = object()

    subagent = agent_runtime._fast_subagent(deferred)

    assert subagent["middleware"] == [deferred]


def test_summarization_middleware_forwards_run_uuid(monkeypatch):
    captured = {}

    class CapturingMiddleware:
        """Capture the model configured for compaction."""

        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        agent_runtime,
        "LensSummarizationMiddleware",
        CapturingMiddleware,
    )
    config = SimpleNamespace(
        ai_gateway_url="http://gateway/ai/",
        request_timeout_s=120,
        summary_keep_tokens=8000,
        summary_trigger_tokens=48000,
        token="token",
    )
    run_uuid = "00000000-0000-0000-0000-000000000009"

    middleware = agent_runtime._build_summarization_middleware(
        config,
        "model-ref",
        lambda *_args, **_kwargs: None,
        run_uuid=run_uuid,
    )

    assert isinstance(middleware, CapturingMiddleware)
    assert captured["model"].run_uuid == run_uuid


def test_turn_limit_excludes_historical_assistant_turns():
    # one prior assistant turn -> baseline_ai = 1, must not count
    messages = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
    ]
    prefix = [_Msg("human", "q1"), _Msg("ai", "a1"), _Msg("human", "q2")]
    agent = _FakeStreamAgent(prefix, new_ai_turns=5)

    answer, truncated = _run_agent_with_turn_limit(agent, messages, max_turns=3)

    assert truncated is True
    # stops at the 3rd NEW turn; without baseline it would stop at the 2nd
    assert "answer 3" in answer


def test_turn_limit_no_history_runs_to_completion():
    messages = [{"role": "user", "content": "q"}]
    prefix = [_Msg("human", "q")]
    agent = _FakeStreamAgent(prefix, new_ai_turns=2)

    answer, truncated = _run_agent_with_turn_limit(agent, messages, max_turns=5)

    assert truncated is False
    assert "answer 2" in answer


def test_pick_text_picks_chinese_only_for_chinese():
    assert _pick_text("zh", "en", "Chinese") == "zh"
    assert _pick_text("zh", "en", "English") == "en"
    # every other detected language falls back to English text too
    assert _pick_text("zh", "en", "Japanese") == "en"
    assert _pick_text("zh", "en", "Korean") == "en"


def test_strip_dangling_tool_call_drops_trailing_pending_call():
    messages = [
        _Msg("human", "q"),
        _Msg("ai", "", tool_calls=[{"id": "1", "name": "grep"}]),
    ]

    result = _strip_dangling_tool_call(messages)

    assert result == messages[:-1]


def test_strip_dangling_tool_call_keeps_resolved_history():
    messages = [_Msg("human", "q"), _Msg("ai", "some findings")]

    result = _strip_dangling_tool_call(messages)

    assert result == messages


class _FakeWrapupModel:
    """Records the messages it was invoked with and returns a fixed reply."""

    def __init__(self, content="synthesized answer"):
        self.content = content
        self.invoked_with = None
        self.invoked_kwargs = None
        self.call_count = 0

    def invoke(self, messages, **kwargs):
        self.call_count += 1
        self.invoked_with = list(messages)
        self.invoked_kwargs = kwargs
        return _Msg("ai", self.content)


class _FailingModel:
    def invoke(self, _messages, **_kwargs):
        raise RuntimeError("gateway unreachable")


class _CancelledModel:
    """Mimics LensGatewayChatModel raising RunCancelledError mid-call."""

    def invoke(self, _messages, **_kwargs):
        raise agent_runtime.RunCancelledError("cancelled")


def test_synthesize_wrapup_answer_strips_dangling_call_and_returns_content():
    model = _FakeWrapupModel("here is what I found")
    current = [
        _Msg("human", "q"),
        _Msg("ai", "partial reasoning"),
        _Msg("ai", "", tool_calls=[{"id": "1", "name": "grep"}]),
    ]

    answer = _synthesize_wrapup_answer(model, current, "English", None)

    assert answer == "here is what I found"
    # dangling tool-call turn dropped, wrap-up instruction appended
    assert len(model.invoked_with) == 3
    assert model.invoked_with[-2].content == "partial reasoning"
    assert model.invoked_with[-1].type == "human"


def test_synthesize_wrapup_answer_returns_empty_on_failure():
    answer = _synthesize_wrapup_answer(
        _FailingModel(), [_Msg("human", "q")], "English", None
    )

    assert answer == ""


def test_synthesize_wrapup_answer_propagates_cancellation():
    # A cancellation landing during the wrap-up call must stop the run,
    # not be swallowed into an empty "wrap-up failed" result.
    try:
        _synthesize_wrapup_answer(
            _CancelledModel(), [_Msg("human", "q")], "English", None
        )
        raised = False
    except agent_runtime.RunCancelledError:
        raised = True

    assert raised is True


def test_truncated_run_falls_back_to_wrapup_when_no_answer_text():
    # last streamed turn is a bare tool call with no text -> nothing to
    # extract; the wrap-up model call must supply the final answer.
    messages = [{"role": "user", "content": "q"}]
    prefix = [_Msg("human", "q")]

    class _ToolCallEndingAgent:
        def stream(self, _inp, stream_mode=None, config=None):
            state = list(prefix)
            for index in range(2):
                state = state + [_Msg("ai", f"finding {index + 1}")]
                yield {"messages": list(state)}
            # 3rd (budget-exhausting) turn is a bare tool call, no text.
            state = state + [
                _Msg("ai", "", tool_calls=[{"id": "1", "name": "grep"}])
            ]
            yield {"messages": list(state)}

    model = _FakeWrapupModel("best-effort synthesis")

    answer, truncated = _run_agent_with_turn_limit(
        _ToolCallEndingAgent(),
        messages,
        max_turns=3,
        model=model,
        answer_language="English",
    )

    assert truncated is True
    assert "best-effort synthesis" in answer
    assert "Reached the current analysis-depth limit" in answer
    assert model.invoked_with is not None


def test_soft_deadline_forces_wrapup_from_current_evidence():
    messages = [{"role": "user", "content": "q"}]
    prefix = [_Msg("human", "q")]
    agent = _FakeStreamAgent(prefix, new_ai_turns=3)
    model = _FakeWrapupModel("deadline synthesis")
    wrapup_event = threading.Event()
    wrapup_event.set()

    answer, truncated = _run_agent_with_turn_limit(
        agent,
        messages,
        max_turns=5,
        model=model,
        answer_language="English",
        wrapup_event=wrapup_event,
    )

    assert truncated is True
    assert "deadline synthesis" in answer
    assert "hard deadline" in answer
    assert model.invoked_with is not None


def test_token_budget_forces_tool_free_wrapup_from_current_evidence():
    messages = [{"role": "user", "content": "q"}]
    prefix = [_Msg("human", "q")]
    agent = _FakeStreamAgent(prefix, new_ai_turns=3)
    model = _FakeWrapupModel("budget synthesis")
    token_budget_wrapup_event = threading.Event()
    token_budget_wrapup_event.set()

    answer, truncated = _run_agent_with_turn_limit(
        agent,
        messages,
        max_turns=5,
        model=model,
        answer_language="English",
        token_budget_wrapup_event=token_budget_wrapup_event,
    )

    assert truncated is True
    assert "budget synthesis" in answer
    assert "token budget" in answer
    assert model.invoked_kwargs == {"runtime_final_synthesis": True}


def test_empty_terminal_response_recovers_once_without_tools():
    class _EmptyEndingAgent:
        def stream(self, _inp, stream_mode=None, config=None):
            yield {
                "messages": [
                    _Msg("human", "q"),
                    _Msg("ai", ""),
                ]
            }

    model = _FakeWrapupModel("recovered answer")
    events = []

    answer, truncated = _run_agent_with_turn_limit(
        _EmptyEndingAgent(),
        [{"role": "user", "content": "q"}],
        max_turns=5,
        model=model,
        emit_event=lambda name, detail: events.append((name, detail)),
    )

    assert answer == "recovered answer"
    assert truncated is False
    assert model.call_count == 1
    assert any(name == "deepagents.answer.recovery" for name, _ in events)


def test_empty_terminal_response_raises_after_one_failed_recovery():
    class _EmptyEndingAgent:
        def stream(self, _inp, stream_mode=None, config=None):
            yield {"messages": [_Msg("human", "q"), _Msg("ai", "")]}

    model = _FakeWrapupModel("")

    try:
        _run_agent_with_turn_limit(
            _EmptyEndingAgent(),
            [{"role": "user", "content": "q"}],
            max_turns=5,
            model=model,
        )
        raised = None
    except agent_runtime.EmptyAgentResponseError as exc:
        raised = exc

    assert raised is not None
    assert raised.code == "EMPTY_AGENT_RESPONSE"
    assert model.call_count == 1
