import json
import threading
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import ToolMessage

from lensnode import agent_runtime
from lensnode.agent_runtime import (
    _answer_general_chat_directly,
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


def test_build_initial_messages_contains_current_retry_question_once():
    history = [
        {"role": "user", "content": "context question"},
        {"role": "assistant", "content": "context answer"},
    ]

    messages = _build_initial_messages(history, "retried question")

    assert messages.count(
        {"role": "user", "content": "retried question"}
    ) == 1


def test_build_initial_messages_preserves_intentional_identical_turns():
    history = [
        {"role": "user", "content": "query again"},
        {"role": "assistant", "content": "old fresh result"},
    ]

    messages = _build_initial_messages(history, "query again")

    assert messages.count(
        {"role": "user", "content": "query again"}
    ) == 2


def test_historical_assistant_content_is_not_current_tool_evidence():
    messages = _build_initial_messages(
        [
            {
                "role": "assistant",
                "content": "The previous tool call succeeded.",
            }
        ],
        "Run the operation again",
    )
    middleware = agent_runtime.CapabilityBoundaryMiddleware(
        required_capabilities=["skill"]
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="tool_result",
        required_capabilities=["skill"],
        truncated=False,
        stop_reason=None,
    )

    assert messages[0]["role"] == "assistant"
    assert middleware.successful_capabilities == set()
    assert outcome == "blocked"
    assert termination_detail["reason"] == "evidence_unavailable"


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


def test_write_todos_keeps_the_initial_plan_shape_during_execution():
    events = []
    seen = set()
    plan_state = {"revision": 0}
    initial = _Msg(
        "ai",
        tool_calls=[
            {
                "id": "call-plan-1",
                "name": "write_todos",
                "args": {
                    "todos": [
                        {"content": "Query orders", "status": "in_progress"},
                        {"content": "Summarize results", "status": "pending"},
                    ]
                },
            }
        ],
    )
    appended = _Msg(
        "ai",
        tool_calls=[
            {
                "id": "call-plan-2",
                "name": "write_todos",
                "args": {
                    "todos": [
                        {"content": "Query orders", "status": "completed"},
                        {
                            "content": "Summarize results",
                            "status": "in_progress",
                        },
                        {"content": "Check totals", "status": "pending"},
                    ]
                },
            }
        ],
    )

    for message in (initial, appended):
        _emit_new_tool_calls(
            [message],
            seen,
            lambda name, detail: events.append((name, detail)),
            plan_state=plan_state,
        )

    assert events[-1][1]["payload"]["steps"] == [
        {"id": "step-1", "title": "Query orders", "status": "completed"},
        {
            "id": "step-2",
            "title": "Summarize results",
            "status": "in_progress",
        },
    ]


def test_write_todos_defers_full_completion_until_run_terminal():
    events = []
    seen = set()
    plan_state = {"revision": 0}
    initial = _Msg(
        "ai",
        tool_calls=[
            {
                "id": "call-plan-1",
                "name": "write_todos",
                "args": {
                    "todos": [
                        {"content": "Query orders", "status": "completed"},
                        {"content": "Return answer", "status": "in_progress"},
                    ]
                },
            }
        ],
    )
    completed = _Msg(
        "ai",
        tool_calls=[
            {
                "id": "call-plan-2",
                "name": "write_todos",
                "args": {
                    "todos": [
                        {"content": "Query orders", "status": "completed"},
                        {"content": "Return answer", "status": "completed"},
                    ]
                },
            }
        ],
    )

    for message in (initial, completed):
        _emit_new_tool_calls(
            [message],
            seen,
            lambda name, detail: events.append((name, detail)),
            plan_state=plan_state,
        )

    assert events[-1][1]["payload"]["steps"] == [
        {"id": "step-1", "title": "Query orders", "status": "completed"},
        {"id": "step-2", "title": "Return answer", "status": "in_progress"},
    ]


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


def test_route_decision_can_reject_an_unmatched_capability_before_execution():
    decision = _parse_route_decision(
        '{"intent":"action","complexity":"simple",'
        '"route":"capability_unavailable",'
        '"required_capabilities":["skill"],'
        '"evidence_requirement":"tool_result"}'
    )

    assert decision["route"] == "capability_unavailable"
    assert decision["required_capabilities"] == ["skill"]
    assert decision["evidence_requirement"] == "tool_result"


def test_route_selection_matches_intent_against_skill_and_tool_capabilities():
    class Model:
        def __init__(self):
            self.messages = []

        def invoke(self, messages, **_kwargs):
            self.messages = messages
            return SimpleNamespace(
                content=(
                    '{"intent":"action","complexity":"simple",'
                    '"route":"capability_unavailable",'
                    '"required_capabilities":["skill"],'
                    '"evidence_requirement":"tool_result"}'
                )
            )

    model = Model()
    tool = SimpleNamespace(
        name="run_skill_artifact",
        description="Run an Artifact explicitly allowed by a bound Skill.",
    )

    decision = agent_runtime._select_general_chat_route(
        model,
        "创建一个订单",
        context_skill_contents=[
            "## Income orders\nThis Skill can query existing orders only."
        ],
        available_tools=[tool],
    )

    prompt = model.messages[0].content
    assert decision["route"] == "capability_unavailable"
    assert "query existing orders only" in prompt
    assert "run_skill_artifact" in prompt
    assert "creating an order" in prompt


def test_route_selection_recovers_missing_tool_evidence_capabilities():
    class Model:
        def invoke(self, _messages, **_kwargs):
            return SimpleNamespace(
                content=(
                    '{"intent":"action","complexity":"complex",'
                    '"route":"plan_execute",'
                    '"required_capabilities":[],'
                    '"evidence_requirement":"tool_result"}'
                )
            )

    decision = agent_runtime._select_general_chat_route(
        Model(),
        "查询订单并生成流程图",
        context_skill_contents=["This Skill can query Income orders."],
        available_tools=[
            SimpleNamespace(
                name="run_skill_artifact",
                description="Run a bound Skill Artifact.",
            ),
            SimpleNamespace(
                name="save_deliverable",
                description="Deliver a generated file.",
            ),
        ],
    )

    assert decision["evidence_requirement"] == "tool_result"
    assert decision["required_capabilities"] == ["skill"]


def test_route_selection_requires_delivery_for_artifact_evidence():
    class Model:
        def invoke(self, _messages, **_kwargs):
            return SimpleNamespace(
                content=(
                    '{"intent":"action","complexity":"complex",'
                    '"route":"plan_execute",'
                    '"required_capabilities":["skill"],'
                    '"evidence_requirement":"artifact"}'
                )
            )

    decision = agent_runtime._select_general_chat_route(
        Model(),
        "生成并交付流程图",
        context_skill_contents=["This Skill generates flowcharts."],
        available_tools=[
            SimpleNamespace(
                name="run_skill_artifact",
                description="Run a bound Skill Artifact.",
            ),
            SimpleNamespace(
                name="save_deliverable",
                description="Deliver a generated file.",
            ),
        ],
    )

    assert decision["required_capabilities"] == [
        "skill",
        "artifact_delivery",
    ]


def test_route_selection_uses_history_to_resolve_an_action_follow_up():
    class Model:
        def __init__(self):
            self.messages = []

        def invoke(self, messages, **_kwargs):
            self.messages = messages
            contents = [
                message.get("content", "")
                if isinstance(message, dict)
                else message.content
                for message in messages
            ]
            route = (
                "direct_execute"
                if any("读取全部276条订单" in item for item in contents)
                else "direct_answer"
            )
            evidence = "tool_result" if route == "direct_execute" else "none"
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "intent": "action",
                        "complexity": "simple",
                        "route": route,
                        "required_capabilities": ["skill"],
                        "evidence_requirement": evidence,
                    }
                )
            )

    model = Model()
    decision = agent_runtime._select_general_chat_route(
        model,
        "那就只保留企业用户名和授权数量，继续读取。",
        history=[
            {"role": "user", "content": "读取全部276条订单。"},
            {
                "role": "assistant",
                "content": "详细字段查询达到预算，未能完成。",
            },
        ],
        context_skill_contents=["This Skill can query Income orders."],
        available_tools=[],
    )

    assert decision["route"] == "direct_execute"
    assert decision["evidence_requirement"] == "tool_result"
    assert model.messages[-1]["content"] == (
        "那就只保留企业用户名和授权数量，继续读取。"
    )


def test_pure_model_request_remains_direct_answer_without_bound_tools():
    class Model:
        def invoke(self, _messages, **_kwargs):
            return SimpleNamespace(
                content=(
                    '{"intent":"informational","complexity":"simple",'
                    '"route":"direct_answer","required_capabilities":[],'
                    '"evidence_requirement":"none"}'
                )
            )

    decision = agent_runtime._select_general_chat_route(
        Model(),
        "请解释什么是订单",
        context_skill_contents=[],
        available_tools=[],
    )

    assert decision["route"] == "direct_answer"
    assert decision["evidence_requirement"] == "none"


def test_direct_answer_recovers_an_unfulfilled_action_promise():
    class Model:
        def __init__(self):
            self.calls = []
            self.responses = iter(
                [
                    (
                        "精简字段会降低数据量。\n\n"
                        "我先完成身份验证，然后拉取全部记录。"
                    ),
                    (
                        "有条件可以。如果必需字段支持列表或批量查询，"
                        "就能读取全部记录；否则仍可能超过预算。"
                    ),
                ]
            )

        def invoke(self, messages, **kwargs):
            self.calls.append((messages, kwargs))
            return SimpleNamespace(content=next(self.responses))

    model = Model()
    events = []
    output = []

    answer = _answer_general_chat_directly(
        model,
        {
            "question": "精简字段后能否读取全部276条记录？",
            "history": [],
        },
        "system prompt",
        emit_event=lambda name, detail: events.append((name, detail)),
        emit_output=output.append,
    )

    assert answer.startswith("有条件可以")
    assert len(model.calls) == 2
    assert all(call[1]["runtime_control_call"] for call in model.calls)
    assert events == [("deepagents.answer.promise_recovery", {})]
    assert output == [answer]


def test_direct_answer_does_not_recover_a_completed_explanation():
    class Model:
        def __init__(self):
            self.calls = 0

        def invoke(self, _messages, **_kwargs):
            self.calls += 1
            return SimpleNamespace(
                content=(
                    "可以。我先说明原因：减少返回字段会降低输出量，"
                    "但是否完整仍取决于接口能否批量返回必需字段。"
                )
            )

    model = Model()

    answer = _answer_general_chat_directly(
        model,
        {"question": "精简字段后是否可行？", "history": []},
        "system prompt",
    )

    assert answer.startswith("可以")
    assert model.calls == 1


def test_unmatched_capability_returns_before_any_tool_call(monkeypatch):
    tool_calls = {"count": 0}

    class Tool:
        name = "query_orders"
        description = "Query existing orders only."

        def invoke(self, _arguments):
            tool_calls["count"] += 1

    class Model:
        stop_reason = None
        token_usage = {}

        def __init__(self, **_kwargs):
            pass

        def invoke(self, _messages, **_kwargs):
            return SimpleNamespace(
                content=(
                    '{"intent":"action","complexity":"simple",'
                    '"route":"capability_unavailable",'
                    '"required_capabilities":["skill"],'
                    '"evidence_requirement":"tool_result"}'
                )
            )

    resources = SimpleNamespace(
        root=Path("/tmp/sourcelens-route-test"),
        context_skill_contents=[
            "## Orders\nThis Skill can query existing orders only."
        ],
        mcp_configs=[],
        skill_paths=[],
    )
    config = SimpleNamespace(
        ai_gateway_url="http://gateway/ai/",
        token="token",
        request_timeout_s=30,
        offload_tool_tokens=5000,
        offload_human_tokens=None,
    )
    monkeypatch.setattr(
        agent_runtime,
        "_apply_offload_thresholds",
        lambda _: None,
    )
    monkeypatch.setattr(
        agent_runtime,
        "prepare_runtime_resources",
        lambda *_args, **_kwargs: resources,
    )
    monkeypatch.setattr(
        agent_runtime,
        "cleanup_runtime_resources",
        lambda _resources: None,
    )
    monkeypatch.setattr(agent_runtime, "LensGatewayChatModel", Model)
    monkeypatch.setattr(
        agent_runtime,
        "build_general_chat_tools",
        lambda *_args, **_kwargs: [Tool()],
    )
    monkeypatch.setattr(
        agent_runtime,
        "load_mcp_tools",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        agent_runtime,
        "build_deferred_mcp_tools",
        lambda *_args, **_kwargs: ([], None),
    )
    monkeypatch.setattr(
        agent_runtime,
        "create_deep_agent",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("Deep Agent must not be created")
        ),
    )
    runtime = agent_runtime.LensDeepAgentRuntime(config)

    result = runtime._answer_sync(
        {
            "run_uuid": "00000000-0000-0000-0000-000000000001",
            "task": "general_chat",
            "question": "创建一个订单",
            "agent_model_ref": "model-ref",
        }
    )

    assert result["outcome"] == "blocked"
    assert result["termination_detail"]["reason"] == (
        "capability_unavailable"
    )
    assert tool_calls["count"] == 0


def test_successful_skill_evidence_preserves_the_final_answer(
    monkeypatch,
    tmp_path,
):
    captured = {}

    class Model:
        stop_reason = None
        token_usage = {"total_tokens": 1}

        def __init__(self, **_kwargs):
            pass

        def invoke(self, _messages, **_kwargs):
            return SimpleNamespace(
                content=(
                    '{"intent":"action","complexity":"complex",'
                    '"route":"plan_execute",'
                    '"required_capabilities":[],'
                    '"evidence_requirement":"tool_result"}'
                )
            )

    resources = SimpleNamespace(
        root=tmp_path,
        context_skill_contents=["This Skill can query Income orders."],
        mcp_configs=[],
        skill_paths=["skills/income"],
        mcp_config_path=tmp_path / "mcp.json",
    )
    config = SimpleNamespace(
        ai_gateway_url="http://gateway/ai/",
        token="token",
        request_timeout_s=30,
        offload_tool_tokens=5000,
        offload_human_tokens=None,
        summary_trigger_tokens=0,
    )
    monkeypatch.setattr(
        agent_runtime,
        "_apply_offload_thresholds",
        lambda _config: None,
    )
    monkeypatch.setattr(
        agent_runtime,
        "prepare_runtime_resources",
        lambda *_args, **_kwargs: resources,
    )
    monkeypatch.setattr(
        agent_runtime,
        "cleanup_runtime_resources",
        lambda _resources: None,
    )
    monkeypatch.setattr(agent_runtime, "LensGatewayChatModel", Model)
    monkeypatch.setattr(
        agent_runtime,
        "build_general_chat_tools",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                name="run_skill_artifact",
                description="Run a bound Skill Artifact.",
            )
        ],
    )
    monkeypatch.setattr(
        agent_runtime,
        "load_mcp_tools",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        agent_runtime,
        "build_deferred_mcp_tools",
        lambda *_args, **_kwargs: ([], None),
    )
    monkeypatch.setattr(
        agent_runtime,
        "_build_summarization_middleware",
        lambda *_args, **_kwargs: None,
    )

    def middleware(
        _command,
        _summarizer,
        _emit_event,
        capability_middleware=None,
        **_kwargs,
    ):
        captured["boundary"] = capability_middleware
        return [capability_middleware]

    monkeypatch.setattr(agent_runtime, "_agent_middleware", middleware)
    monkeypatch.setattr(
        agent_runtime,
        "create_deep_agent",
        lambda **_kwargs: object(),
    )

    def run_agent(*_args, **_kwargs):
        captured["boundary"].success_count = 2
        captured["boundary"].successful_capabilities = {
            "artifact_delivery",
            "skill",
        }
        return "已生成并交付订单流程图。", True, "token_budget_wrapup"

    monkeypatch.setattr(
        agent_runtime,
        "_run_agent_with_turn_limit",
        run_agent,
    )

    result = agent_runtime.LensDeepAgentRuntime(config)._answer_sync(
        {
            "run_uuid": "00000000-0000-0000-0000-000000000002",
            "task": "general_chat",
            "question": "查询订单并生成流程图",
            "agent_model_ref": "model-ref",
        }
    )

    assert captured["boundary"].required_capabilities == {"skill"}
    assert result["answer"] == "已生成并交付订单流程图。"
    assert result["outcome"] == "completed"
    assert result["termination_detail"] == {}


def test_delivered_artifact_completes_after_token_budget_wrapup():
    middleware = SimpleNamespace(
        successful_capabilities={"skill", "artifact_delivery"},
        failed_capabilities=set(),
        recovered_capabilities=set(),
        exhaustion_details=[],
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="tool_result",
        required_capabilities=["skill"],
        truncated=True,
        stop_reason="token_budget_wrapup",
    )

    assert outcome == "completed"
    assert termination_detail == {}


def test_legacy_runtime_modes_skip_general_chat_execution_gates(
    monkeypatch,
    tmp_path,
):
    model_options = []
    run_options = []

    class Model:
        stop_reason = None
        token_usage = {"total_tokens": 1}

        def __init__(self, **options):
            model_options.append(options)

    resources = SimpleNamespace(
        root=tmp_path,
        context_skill_contents=[],
        mcp_configs=[],
        skill_paths=[],
        mcp_config_path=tmp_path / "mcp.json",
    )
    config = SimpleNamespace(
        ai_gateway_url="http://gateway/ai/",
        token="token",
        request_timeout_s=30,
        offload_tool_tokens=5000,
        offload_human_tokens=None,
        summary_trigger_tokens=0,
    )
    monkeypatch.setattr(
        agent_runtime,
        "_apply_offload_thresholds",
        lambda _config: None,
    )
    monkeypatch.setattr(
        agent_runtime,
        "prepare_runtime_resources",
        lambda *_args, **_kwargs: resources,
    )
    monkeypatch.setattr(
        agent_runtime,
        "cleanup_runtime_resources",
        lambda _resources: None,
    )
    monkeypatch.setattr(agent_runtime, "LensGatewayChatModel", Model)
    monkeypatch.setattr(
        agent_runtime,
        "build_agent_tools",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        agent_runtime,
        "load_mcp_tools",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        agent_runtime,
        "build_deferred_mcp_tools",
        lambda *_args, **_kwargs: ([], None),
    )
    monkeypatch.setattr(
        agent_runtime,
        "create_deep_agent",
        lambda **_kwargs: object(),
    )

    def run_agent(*_args, **options):
        run_options.append(options)
        return "legacy answer", False, None

    monkeypatch.setattr(
        agent_runtime,
        "_run_agent_with_turn_limit",
        run_agent,
    )
    runtime = agent_runtime.LensDeepAgentRuntime(config)
    wrapup_event = threading.Event()

    for task in ("knowledge_qa", "code_analysis"):
        result = runtime._answer_sync(
            {
                "run_uuid": f"legacy-{task}",
                "task": task,
                "question": "Question",
                "agent_model_ref": "model-ref",
            },
            wrapup_event=wrapup_event,
        )

        assert result["answer"] == "legacy answer"
        assert result["outcome"] == "completed"
        assert result["termination_detail"] == {}

    assert all(
        options["general_chat_execution_gates"] is False
        for options in model_options
    )
    for options in run_options:
        assert options["wrapup_event"] is None
        assert options["token_budget_wrapup_event"] is None
        assert "capability_stop_event" not in options


def test_unverified_answer_distinguishes_unavailable_from_execution_failure():
    unavailable = agent_runtime._unverified_execution_answer(
        "创建一个订单",
        {
            "reason": "capability_unavailable",
            "capability": "skill",
            "error_type": "capability",
        },
    )
    failed = agent_runtime._unverified_execution_answer(
        "查询订单",
        {
            "reason": "execution_failed",
            "capability": "skill",
            "error_type": "transient",
        },
    )

    assert "未调用任何业务工具" in unavailable
    assert "上游服务暂时异常" in failed
    assert "能力都无法完成" not in failed


def test_route_decision_requires_execution_for_external_business_facts():
    decision = _parse_route_decision(
        '{"intent":"informational","complexity":"simple",'
        '"route":"direct_answer","required_capabilities":["skill"],'
        '"evidence_requirement":"tool_result"}'
    )

    assert decision["route"] == "direct_execute"
    assert decision["evidence_requirement"] == "tool_result"


def test_direct_execution_cannot_disable_tool_evidence():
    decision = _parse_route_decision(
        '{"intent":"action","complexity":"simple",'
        '"route":"direct_execute","required_capabilities":["skill"],'
        '"evidence_requirement":"none"}'
    )

    assert decision["route"] == "direct_execute"
    assert decision["evidence_requirement"] == "tool_result"


def test_action_plan_cannot_disable_tool_evidence():
    decision = _parse_route_decision(
        '{"intent":"action","complexity":"complex",'
        '"route":"plan_execute","required_capabilities":["skill"],'
        '"evidence_requirement":"none"}'
    )

    assert decision["route"] == "plan_execute"
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
        successful_capabilities={"skill"},
        outcome="completed",
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="tool_result",
        required_capabilities=["skill"],
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


def test_missing_required_capability_fails_closed_despite_global_success():
    middleware = SimpleNamespace(
        success_count=1,
        successful_capabilities={"mcp"},
        outcome="completed",
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="tool_result",
        required_capabilities=[],
        truncated=False,
        stop_reason=None,
    )

    assert outcome == "blocked"
    assert termination_detail["reason"] == "evidence_unavailable"


def test_unrelated_success_does_not_satisfy_required_skill_evidence():
    middleware = SimpleNamespace(
        success_count=1,
        successful_capabilities={"mcp"},
        outcome="completed",
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="tool_result",
        required_capabilities=["skill"],
        truncated=False,
        stop_reason=None,
    )

    assert outcome == "blocked"
    assert termination_detail["reason"] == "evidence_unavailable"
    assert termination_detail["capability"] == "skill"


def test_alternative_required_capability_can_complete_after_failure():
    middleware = SimpleNamespace(
        success_count=1,
        successful_capabilities={"mcp"},
        outcome="partial",
        termination_detail={
            "reason": "execution_failed",
            "capability": "skill",
            "error_type": "configuration",
            "tool": "call_skill_api",
        },
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="tool_result",
        required_capabilities=["skill", "mcp"],
        truncated=False,
        stop_reason=None,
    )

    assert outcome == "completed"
    assert termination_detail == {}


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


def test_artifact_requirement_is_partial_with_relevant_skill_evidence():
    middleware = SimpleNamespace(
        success_count=1,
        successful_capabilities={"skill"},
        outcome="completed",
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="artifact",
        required_capabilities=["skill", "artifact_delivery"],
        truncated=False,
        stop_reason=None,
    )

    assert outcome == "partial"
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
        required_capabilities=["skill"],
        truncated=True,
        stop_reason="soft_deadline",
    )

    assert outcome == "blocked"
    assert termination_detail["reason"] == "evidence_unavailable"
    assert termination_detail["trigger"] == "soft_deadline"


def test_relevant_evidence_is_partial_at_soft_deadline():
    middleware = SimpleNamespace(
        success_count=1,
        successful_capabilities={"skill"},
        outcome="completed",
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="tool_result",
        required_capabilities=["skill"],
        truncated=True,
        stop_reason="soft_deadline",
    )

    assert outcome == "partial"
    assert termination_detail == {"reason": "soft_deadline"}


def test_relevant_evidence_is_partial_after_unrecovered_failure():
    middleware = agent_runtime.CapabilityBoundaryMiddleware(
        required_capabilities=["skill"],
    )
    request = SimpleNamespace(
        tool=SimpleNamespace(name="run_skill_artifact"),
        tool_call={
            "name": "run_skill_artifact",
            "id": "call-1",
            "args": {"query": "orders"},
        },
    )
    middleware.wrap_tool_call(
        request,
        lambda _request: ToolMessage(
            content='{"ok":true,"orders":[]}',
            name="run_skill_artifact",
            tool_call_id="call-1",
        ),
    )
    middleware.wrap_tool_call(
        request,
        lambda _request: ToolMessage(
            content='{"ok":false,"error":"TIMEOUT"}',
            name="run_skill_artifact",
            tool_call_id="call-2",
            status="error",
        ),
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="tool_result",
        required_capabilities=["skill"],
        truncated=False,
        stop_reason=None,
    )

    assert outcome == "partial"
    assert termination_detail["reason"] == "execution_failed"
    assert termination_detail["capability"] == "skill"


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


def test_validated_bulk_result_completes_after_token_budget_wrapup():
    middleware = SimpleNamespace(
        success_count=1,
        successful_capabilities={"skill"},
        outcome="completed",
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="tool_result",
        required_capabilities=["skill"],
        truncated=True,
        stop_reason="token_capped",
        runtime_evidence={
            "record_validation": {
                "valid": True,
                "total_count": 38,
                "expected_count": 38,
                "count_matches": True,
                "unique_by": ["code"],
            }
        },
    )

    assert outcome == "completed"
    assert termination_detail == {}


def test_legacy_runtime_ignores_general_chat_outcome_gates():
    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=None,
        evidence_requirement="none",
        truncated=True,
        stop_reason="turn_limit",
        execution_gate_enabled=False,
    )

    assert outcome == "completed"
    assert termination_detail == {}


def test_validation_without_expected_count_remains_partial_after_wrapup():
    middleware = SimpleNamespace(
        success_count=1,
        successful_capabilities={"skill"},
        outcome="completed",
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="tool_result",
        required_capabilities=["skill"],
        truncated=True,
        stop_reason="token_capped",
        runtime_evidence={
            "record_validation": {
                "valid": True,
                "total_count": 38,
                "expected_count": None,
                "count_matches": None,
                "unique_by": ["code"],
            }
        },
    )

    assert outcome == "partial"
    assert termination_detail == {"reason": "token_capped"}


def test_invalid_bulk_result_remains_partial_after_token_budget_wrapup():
    middleware = SimpleNamespace(
        success_count=1,
        successful_capabilities={"skill"},
        outcome="completed",
        termination_detail={},
    )

    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="tool_result",
        required_capabilities=["skill"],
        truncated=True,
        stop_reason="token_capped",
        runtime_evidence={"record_validation": {"valid": False}},
    )

    assert outcome == "partial"
    assert termination_detail == {"reason": "token_capped"}
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
    assert "Never invent flags" in prompt
    assert "validate_records" in prompt
    assert "Do not fan out per-record detail calls" in prompt


def test_plan_execute_prompt_requires_a_stable_initial_plan():
    prompt = _general_chat_system_prompt(
        {
            "question": "Query and summarize orders",
            "runtime_route": "plan_execute",
        }
    )

    assert "complete concise high-level plan" in prompt
    assert "task count, order, and wording fixed" in prompt
    assert "may only update statuses" in prompt


def test_execution_boundary_disables_configuration_failure_capability():
    events = []
    middleware = agent_runtime.CapabilityBoundaryMiddleware(
        emit_event=lambda name, detail: events.append((name, detail)),
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
    assert middleware.outcome == "blocked"
    assert middleware.blocked_capabilities == {"skill"}
    remaining = middleware._filter_tools(
        [
            SimpleNamespace(name="call_skill_api"),
            SimpleNamespace(name="mcp__orders"),
        ]
    )
    assert [tool.name for tool in remaining] == ["mcp__orders"]
    assert middleware.termination_detail["capability"] == "skill"
    assert middleware.termination_detail["reason"] == "execution_failed"
    assert events[0][0] == "deepagents.capability.exhausted"


def test_capability_boundary_allows_one_transient_retry():
    middleware = agent_runtime.CapabilityBoundaryMiddleware()
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
    middleware.wrap_tool_call(request, fail)
    assert middleware.blocked_tools == {"mcp__orders"}
    assert middleware.termination_detail["capability"] == "mcp"


def test_structured_analysis_limit_blocks_only_the_exhausted_tool():
    middleware = agent_runtime.CapabilityBoundaryMiddleware()
    request = SimpleNamespace(
        tool=SimpleNamespace(name="analyze_structured_output"),
        tool_call={
            "name": "analyze_structured_output",
            "id": "call-1",
        },
    )

    result = middleware.wrap_tool_call(
        request,
        lambda _request: ToolMessage(
            content=json.dumps(
                {
                    "ok": False,
                    "error": "STRUCTURED_ANALYSIS_CALL_LIMIT",
                    "instruction": (
                        "Use existing bounded results and finish the answer."
                    ),
                }
            ),
            name="analyze_structured_output",
            tool_call_id="call-1",
            status="error",
        ),
    )

    assert json.loads(result.content)["error"] == (
        "STRUCTURED_ANALYSIS_CALL_LIMIT"
    )
    assert middleware.blocked_tools == {"analyze_structured_output"}
    assert middleware.termination_detail == {}
    assert middleware.failed_capabilities == set()

    denied = middleware.wrap_tool_call(
        request,
        lambda _request: (_ for _ in ()).throw(
            AssertionError("The blocked tool must not execute again")
        ),
    )

    assert json.loads(denied.content)["error"] == "CAPABILITY_BLOCKED"


def test_last_structured_analysis_call_prevents_an_over_limit_attempt():
    middleware = agent_runtime.CapabilityBoundaryMiddleware()
    request = SimpleNamespace(
        tool=SimpleNamespace(name="analyze_structured_output"),
        tool_call={
            "name": "analyze_structured_output",
            "id": "call-1",
        },
    )

    result = middleware.wrap_tool_call(
        request,
        lambda _request: ToolMessage(
            content=json.dumps(
                {
                    "ok": True,
                    "call_budget_exhausted": True,
                    "instruction": (
                        "Use existing bounded results and finish the answer."
                    ),
                }
            ),
            name="analyze_structured_output",
            tool_call_id="call-1",
        ),
    )

    assert json.loads(result.content)["ok"] is True
    assert middleware.blocked_tools == {"analyze_structured_output"}
    assert middleware.termination_detail == {}


def test_request_failures_are_isolated_by_normalized_arguments():
    middleware = agent_runtime.CapabilityBoundaryMiddleware()

    def fail(request):
        return ToolMessage(
            content='{"ok":false,"error":"INVALID_QUERY"}',
            name="mcp__orders",
            tool_call_id=request.tool_call["id"],
            status="error",
        )

    first = SimpleNamespace(
        tool=SimpleNamespace(name="mcp__orders"),
        tool_call={
            "name": "mcp__orders",
            "id": "call-1",
            "args": {"filters": {"status": "open", "year": 2025}},
        },
    )
    reordered = SimpleNamespace(
        tool=SimpleNamespace(name="mcp__orders"),
        tool_call={
            "name": "mcp__orders",
            "id": "call-2",
            "args": {"filters": {"year": 2025, "status": "open"}},
        },
    )
    corrected = SimpleNamespace(
        tool=SimpleNamespace(name="mcp__orders"),
        tool_call={
            "name": "mcp__orders",
            "id": "call-3",
            "args": {"filters": {"year": 2024, "status": "open"}},
        },
    )

    middleware.wrap_tool_call(first, fail)
    middleware.wrap_tool_call(corrected, fail)

    assert middleware.blocked_tools == set()

    middleware.wrap_tool_call(reordered, fail)

    assert middleware.blocked_tools == {"mcp__orders"}


def test_request_corrections_have_a_separate_capability_failure_cap():
    middleware = agent_runtime.CapabilityBoundaryMiddleware()

    for index in range(4):
        request = SimpleNamespace(
            tool=SimpleNamespace(name="mcp__orders"),
            tool_call={
                "name": "mcp__orders",
                "id": f"call-{index}",
                "args": {"query": f"invalid query {index}"},
            },
        )
        middleware.wrap_tool_call(
            request,
            lambda current: ToolMessage(
                content='{"ok":false,"error":"INVALID_QUERY"}',
                name="mcp__orders",
                tool_call_id=current.tool_call["id"],
                status="error",
            ),
        )

    assert middleware.blocked_capabilities == {"mcp"}
    assert middleware.capability_failure_counts["mcp"] == 4


def test_unclassified_tool_failure_allows_one_correction_attempt():
    middleware = agent_runtime.CapabilityBoundaryMiddleware()
    request = SimpleNamespace(
        tool=SimpleNamespace(name="mcp__orders"),
        tool_call={"name": "mcp__orders", "id": "call-1", "args": {}},
    )

    def fail(_request):
        return ToolMessage(
            content='{"ok":false,"error":"REMOTE_BROKEN"}',
            name="mcp__orders",
            tool_call_id="call-1",
            status="error",
        )

    middleware.wrap_tool_call(request, fail)
    assert middleware.blocked_tools == set()

    middleware.wrap_tool_call(request, fail)
    assert middleware.blocked_tools == {"mcp__orders"}


def test_non_idempotent_write_does_not_receive_transient_retry():
    middleware = agent_runtime.CapabilityBoundaryMiddleware()
    request = SimpleNamespace(
        tool=SimpleNamespace(
            name="mcp__orders__create",
            metadata={"operation": "write", "idempotent": False},
        ),
        tool_call={
            "name": "mcp__orders__create",
            "id": "call-1",
            "args": {"amount": 100},
        },
    )

    middleware.wrap_tool_call(
        request,
        lambda _request: ToolMessage(
            content='{"ok":false,"error":"TIMEOUT"}',
            name="mcp__orders__create",
            tool_call_id="call-1",
            status="error",
        ),
    )

    assert middleware.blocked_tools == {"mcp__orders__create"}


def test_alternative_capability_recovery_is_counted_without_arguments():
    events = []
    middleware = agent_runtime.CapabilityBoundaryMiddleware(
        emit_event=lambda name, detail: events.append((name, detail)),
        required_capabilities=["skill", "mcp"],
    )
    skill_request = SimpleNamespace(
        tool=SimpleNamespace(name="call_skill_api"),
        tool_call={
            "name": "call_skill_api",
            "id": "call-1",
            "args": {"authorization": "must-not-be-emitted"},
        },
    )
    mcp_request = SimpleNamespace(
        tool=SimpleNamespace(name="mcp__orders"),
        tool_call={
            "name": "mcp__orders",
            "id": "call-2",
            "args": {"query": "orders"},
        },
    )

    middleware.wrap_tool_call(
        skill_request,
        lambda _request: ToolMessage(
            content='{"ok":false,"error":"AUTH_REQUIRED"}',
            name="call_skill_api",
            tool_call_id="call-1",
            status="error",
        ),
    )
    middleware.wrap_tool_call(
        mcp_request,
        lambda _request: ToolMessage(
            content='{"ok":true,"orders":[]}',
            name="mcp__orders",
            tool_call_id="call-2",
        ),
    )

    recovered = [
        detail
        for name, detail in events
        if name == "deepagents.capability.recovered"
    ]
    outcome, termination_detail = _finalize_runtime_outcome(
        capability_middleware=middleware,
        evidence_requirement="tool_result",
        required_capabilities=["skill", "mcp"],
        truncated=False,
        stop_reason=None,
    )

    assert middleware.alternative_recovery_count == 1
    assert recovered[0]["recovery_type"] == "alternative_capability"
    assert "must-not-be-emitted" not in str(recovered)
    assert outcome == "completed"
    assert termination_detail == {}


def test_corrected_request_recovery_is_counted():
    events = []
    middleware = agent_runtime.CapabilityBoundaryMiddleware(
        emit_event=lambda name, detail: events.append((name, detail)),
        required_capabilities=["mcp"],
    )
    failed_request = SimpleNamespace(
        tool=SimpleNamespace(name="mcp__orders"),
        tool_call={
            "name": "mcp__orders",
            "id": "call-1",
            "args": {"query": "invalid"},
        },
    )
    corrected_request = SimpleNamespace(
        tool=SimpleNamespace(name="mcp__orders"),
        tool_call={
            "name": "mcp__orders",
            "id": "call-2",
            "args": {"query": "valid"},
        },
    )

    middleware.wrap_tool_call(
        failed_request,
        lambda _request: ToolMessage(
            content='{"ok":false,"error":"INVALID_QUERY"}',
            name="mcp__orders",
            tool_call_id="call-1",
            status="error",
        ),
    )
    middleware.wrap_tool_call(
        corrected_request,
        lambda _request: ToolMessage(
            content='{"ok":true,"orders":[]}',
            name="mcp__orders",
            tool_call_id="call-2",
        ),
    )

    assert middleware.correction_recovery_count == 1
    assert any(
        name == "deepagents.capability.recovered"
        and detail["recovery_type"] == "corrected_request"
        for name, detail in events
    )


def test_capability_boundary_allows_artifact_argument_correction_after_404():
    middleware = agent_runtime.CapabilityBoundaryMiddleware()
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

    middleware.wrap_tool_call(request, not_found)
    assert middleware.blocked_tools == {"run_skill_artifact"}
    assert middleware.termination_detail["error_type"] == "request"


def test_capability_boundary_tracks_distinct_artifact_requests_separately():
    middleware = agent_runtime.CapabilityBoundaryMiddleware()
    get_request = SimpleNamespace(
        tool=SimpleNamespace(name="run_skill_artifact"),
        tool_call={
            "name": "run_skill_artifact",
            "id": "call-1",
            "args": {
                "artifact": "income",
                "args": ["order", "get", "ORDER-CODE"],
            },
        },
    )
    list_request = SimpleNamespace(
        tool=SimpleNamespace(name="run_skill_artifact"),
        tool_call={
            "name": "run_skill_artifact",
            "id": "call-2",
            "args": {
                "artifact": "income",
                "args": ["order", "list", "--code", "ORDER-CODE"],
            },
        },
    )

    def not_found(request):
        return ToolMessage(
            content=json.dumps(
                {
                    "ok": False,
                    "returncode": 5,
                    "stderr": "Income API returned 404: NotFound",
                }
            ),
            name="run_skill_artifact",
            tool_call_id=request.tool_call["id"],
            status="error",
        )

    middleware.wrap_tool_call(get_request, not_found)
    middleware.wrap_tool_call(list_request, not_found)

    assert middleware.blocked_tools == set()
    assert middleware.termination_detail == {}


def test_execution_boundary_classifies_artifact_http_500_as_transient():
    events = []
    middleware = agent_runtime.CapabilityBoundaryMiddleware(
        emit_event=lambda name, detail: events.append((name, detail)),
    )
    request = SimpleNamespace(
        tool=SimpleNamespace(name="run_skill_artifact"),
        tool_call={"name": "run_skill_artifact", "id": "call-1"},
    )

    def fail(_request):
        return ToolMessage(
            content=json.dumps(
                {
                    "ok": False,
                    "returncode": 1,
                    "stderr": "Income API returned HTTP 500",
                }
            ),
            name="run_skill_artifact",
            tool_call_id="call-1",
            status="error",
        )

    middleware.wrap_tool_call(request, fail)
    middleware.wrap_tool_call(request, fail)

    assert middleware.blocked_tools == {"run_skill_artifact"}
    assert middleware.termination_detail["reason"] == "execution_failed"
    assert middleware.termination_detail["error_type"] == "transient"
    assert events[0][0] == "deepagents.capability.exhausted"


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
    assert middleware.termination_detail == {}

    middleware.wrap_tool_call(
        request,
        lambda _request: ToolMessage(
            content="remote order service failed",
            name="mcp__orders__lookup",
            tool_call_id="call-1",
            status="error",
        ),
    )

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
    middleware = agent_runtime.CapabilityBoundaryMiddleware()
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
    middleware.wrap_tool_call(
        failed_request,
        lambda _request: ToolMessage(
            content='{"ok":false,"error":"DELIVERY_FAILED"}',
            name="save_deliverable",
            tool_call_id="call-failed",
            status="error",
        ),
    )

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


def test_general_chat_middleware_emits_each_model_round_as_one_step():
    class Request:
        tools = []

        def override(self, **changes):
            return SimpleNamespace(**changes)

    events = []
    middleware = agent_runtime._NoTaskMiddleware(
        lambda name, detail: events.append((name, detail))
    )

    result = middleware.wrap_model_call(Request(), lambda _request: "answer")

    assert result == "answer"
    assert events == [
        (
            "model.round.start",
            {"invocation_id": "model-round-1", "round": 1},
        ),
        (
            "model.round.done",
            {"invocation_id": "model-round-1", "round": 1},
        ),
    ]


def test_trace_observation_middleware_wraps_tool_lifecycle():
    observations = []
    middleware = agent_runtime.TraceObservationMiddleware(
        observations.append,
        "c" * 32,
    )
    request = SimpleNamespace(
        tool=SimpleNamespace(name="search_workspace"),
        tool_call={
            "name": "search_workspace",
            "id": "call-1",
            "args": {"query": "secret input is not traced"},
        },
    )

    result = middleware.wrap_tool_call(
        request,
        lambda _request: ToolMessage(
            content="result is not traced",
            name="search_workspace",
            tool_call_id="call-1",
        ),
    )

    assert result.content == "result is not traced"
    assert [item["action"] for item in observations] == ["start", "end"]
    assert observations[0]["id"] == observations[1]["id"]
    assert observations[0]["parent_observation_id"] == "c" * 32
    assert observations[0]["name"] == "tool.search_workspace"
    assert observations[1]["status"] == "done"
    assert "secret input" not in str(observations)
    assert "result is not traced" not in str(observations)


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


def test_general_chat_middleware_denies_direct_large_result_access():
    events = []
    handler_calls = []
    middleware = agent_runtime._NoTaskMiddleware(
        lambda name, detail: events.append((name, detail))
    )
    requests = [
        SimpleNamespace(
            tool=SimpleNamespace(name="read_file"),
            tool_call={
                "name": "read_file",
                "id": "call-read",
                "args": {
                    "file_path": "/large_tool_results/orders.json"
                },
            },
        ),
        SimpleNamespace(
            tool=SimpleNamespace(name="grep"),
            tool_call={
                "name": "grep",
                "id": "call-grep",
                "args": {"path": "/large_tool_results"},
            },
        ),
    ]

    results = [
        middleware.wrap_tool_call(
            request,
            lambda _request: handler_calls.append(True),
        )
        for request in requests
    ]

    assert handler_calls == []
    assert all(result.status == "error" for result in results)
    assert all(
        "LARGE_RESULT_DIRECT_ACCESS_DENIED" in result.content
        for result in results
    )
    assert [name for name, _detail in events] == [
        "tool.read_file.denied",
        "tool.grep.denied",
    ]


def test_general_chat_middleware_allows_skill_reference_reads():
    middleware = agent_runtime._NoTaskMiddleware()
    request = SimpleNamespace(
        tool=SimpleNamespace(name="read_file"),
        tool_call={
            "name": "read_file",
            "id": "call-read",
            "args": {"file_path": "/skills/orders/SKILL.md"},
        },
    )

    result = middleware.wrap_tool_call(
        request,
        lambda _request: "allowed",
    )

    assert result == "allowed"


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

    answer, truncated, termination_reason = _run_agent_with_turn_limit(
        agent,
        messages,
        max_turns=3,
    )

    assert truncated is True
    assert termination_reason == "turn_limit"
    # stops at the 3rd NEW turn; without baseline it would stop at the 2nd
    assert "answer 3" in answer


def test_turn_limit_no_history_runs_to_completion():
    messages = [{"role": "user", "content": "q"}]
    prefix = [_Msg("human", "q")]
    agent = _FakeStreamAgent(prefix, new_ai_turns=2)

    answer, truncated, termination_reason = _run_agent_with_turn_limit(
        agent,
        messages,
        max_turns=5,
    )

    assert truncated is False
    assert termination_reason is None
    assert "answer 2" in answer


def test_provider_loop_gate_is_preserved_after_natural_agent_finish():
    messages = [{"role": "user", "content": "q"}]
    prefix = [_Msg("human", "q")]
    agent = _FakeStreamAgent(prefix, new_ai_turns=1)
    model = SimpleNamespace(stop_reason="loop_capped")

    answer, truncated, termination_reason = _run_agent_with_turn_limit(
        agent,
        messages,
        max_turns=5,
        model=model,
    )

    assert answer == "answer 1"
    assert truncated is False
    assert termination_reason == "loop_capped"


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

    answer, truncated, termination_reason = _run_agent_with_turn_limit(
        _ToolCallEndingAgent(),
        messages,
        max_turns=3,
        model=model,
        answer_language="English",
    )

    assert truncated is True
    assert termination_reason == "turn_limit"
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

    answer, truncated, termination_reason = _run_agent_with_turn_limit(
        agent,
        messages,
        max_turns=5,
        model=model,
        answer_language="English",
        wrapup_event=wrapup_event,
    )

    assert truncated is True
    assert termination_reason == "soft_deadline"
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

    answer, truncated, termination_reason = _run_agent_with_turn_limit(
        agent,
        messages,
        max_turns=5,
        model=model,
        answer_language="English",
        token_budget_wrapup_event=token_budget_wrapup_event,
    )

    assert truncated is True
    assert termination_reason == "token_budget_wrapup"
    assert "budget synthesis" in answer
    assert "token budget" not in answer.lower()
    assert "Token 调查预算" not in answer
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

    answer, truncated, termination_reason = _run_agent_with_turn_limit(
        _EmptyEndingAgent(),
        [{"role": "user", "content": "q"}],
        max_turns=5,
        model=model,
        emit_event=lambda name, detail: events.append((name, detail)),
    )

    assert answer == "recovered answer"
    assert truncated is False
    assert termination_reason is None
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
