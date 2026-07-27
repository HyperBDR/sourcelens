from lensnode.runtime_modes import (
    CodeAnalysisMode,
    DocumentQAMode,
    GeneralChatMode,
    runtime_mode_for,
)


def test_runtime_modes_keep_general_chat_features_isolated():
    general = runtime_mode_for({"task": "general_chat"})
    document = runtime_mode_for({"task": "knowledge_qa"})
    code = runtime_mode_for({"task": "code_analysis"})

    assert isinstance(general, GeneralChatMode)
    assert general.decorate_event({"value": 1}) == {
        "value": 1,
        "runtime_scope": "general_chat",
    }
    events = []
    general.emit_model_round(
        lambda name, detail: events.append((name, detail)),
        "start",
        1,
    )
    assert events == [
        (
            "model.round.start",
            {"invocation_id": "model-round-1", "round": 1},
        )
    ]

    assert isinstance(document, DocumentQAMode)
    assert isinstance(code, CodeAnalysisMode)
    for legacy in (document, code):
        assert legacy.decorate_event({"value": 1}) == {"value": 1}
        legacy.emit_model_round(
            lambda name, detail: events.append((name, detail)),
            "start",
            1,
        )
    assert len(events) == 1
