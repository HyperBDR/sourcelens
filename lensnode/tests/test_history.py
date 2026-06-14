from lensnode.agent_runtime import (
    _build_initial_messages,
    _run_agent_with_turn_limit,
)


class _Msg:
    """Minimal stand-in for a LangChain message with a type/content."""

    def __init__(self, type_, content=""):
        self.type = type_
        self.content = content


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
