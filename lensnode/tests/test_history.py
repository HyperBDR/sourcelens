from types import SimpleNamespace

from lensnode import agent_runtime
from lensnode.agent_runtime import (
    _build_initial_messages,
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

    def invoke(self, messages):
        self.invoked_with = list(messages)
        return _Msg("ai", self.content)


class _FailingModel:
    def invoke(self, _messages):
        raise RuntimeError("gateway unreachable")


class _CancelledModel:
    """Mimics LensGatewayChatModel raising RunCancelledError mid-call."""

    def invoke(self, _messages):
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
