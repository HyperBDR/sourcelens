import json
from types import SimpleNamespace

from lensnode import agent_runtime
from lensnode.checkpoint import ResumeState
from lensnode.planned_evidence import build_evidence_bundle


def _runtime_state(tmp_path, resume_state=None):
    ready_events = []
    state = SimpleNamespace(
        runtime_mode=SimpleNamespace(name="code_analysis"),
        resume_state=resume_state,
        run_uuid="planned-run",
        model=SimpleNamespace(),
        command={
            "run_uuid": "planned-run",
            "task": "code_analysis",
        },
        tools=[],
        mcp_tools=[],
        emit_agent_event=lambda *_args, **_kwargs: None,
        resources=SimpleNamespace(),
        initial_messages=[],
        history_assistant_turns=0,
        checkpoint_ready=resume_state is not None,
        initial_checkpoint_seeded=False,
        notify_checkpoint_ready=lambda: ready_events.append("ready"),
    )
    return state, ready_events


def test_planned_code_analysis_seeds_checkpoint_before_execution(
    monkeypatch,
    tmp_path,
):
    actions = []
    state, ready_events = _runtime_state(tmp_path)
    runtime = agent_runtime.LensDeepAgentRuntime(
        SimpleNamespace(workspace_path=str(tmp_path))
    )

    monkeypatch.setattr(
        runtime,
        "_prepare_runtime",
        lambda *_args, **_kwargs: state,
    )
    monkeypatch.setattr(agent_runtime, "checkpoint_enabled", lambda: True)
    monkeypatch.setattr(
        agent_runtime,
        "get_checkpoint_saver",
        lambda _workspace: actions.append("saver") or object(),
    )
    monkeypatch.setattr(
        agent_runtime,
        "save_resume_metadata",
        lambda *_args, **kwargs: actions.append(("metadata", kwargs["route_decision"])),
    )
    monkeypatch.setattr(
        agent_runtime,
        "save_initial_checkpoint",
        lambda *_args, **_kwargs: actions.append("checkpoint"),
    )
    monkeypatch.setattr(
        agent_runtime,
        "_run_planned_code_analysis",
        lambda **_kwargs: actions.append("planned") or {"answer": "done"},
    )
    monkeypatch.setattr(
        agent_runtime,
        "cleanup_runtime_resources",
        lambda _resources: None,
    )

    result = runtime._answer_sync(state.command)

    assert result == {"answer": "done"}
    assert actions == [
        "saver",
        (
            "metadata",
            {"route": "planned_code_analysis"},
        ),
        "checkpoint",
        "planned",
    ]
    assert ready_events == ["ready"]
    assert state.checkpoint_ready is True
    assert state.initial_checkpoint_seeded is True


def test_planned_code_analysis_resume_replays_planned_pipeline(
    monkeypatch,
    tmp_path,
):
    resume_state = ResumeState(
        messages=(),
        route_decision={"route": "planned_code_analysis"},
        history_assistant_turns=0,
        checkpoint_step=-1,
    )
    state, _ready_events = _runtime_state(tmp_path, resume_state)
    runtime = agent_runtime.LensDeepAgentRuntime(
        SimpleNamespace(workspace_path=str(tmp_path))
    )
    calls = []

    monkeypatch.setattr(
        runtime,
        "_prepare_runtime",
        lambda *_args, **_kwargs: state,
    )
    monkeypatch.setattr(
        runtime,
        "_build_agent",
        lambda _state: calls.append("deep-agent"),
    )
    monkeypatch.setattr(
        agent_runtime,
        "_run_planned_code_analysis",
        lambda **_kwargs: calls.append("planned") or {"answer": "recovered"},
    )
    monkeypatch.setattr(
        agent_runtime,
        "cleanup_runtime_resources",
        lambda _resources: None,
    )

    result = runtime._answer_sync({**state.command, "resume": True})

    assert result == {"answer": "recovered"}
    assert calls == ["planned"]


def test_planned_answer_extracts_json_after_explanatory_prefix(tmp_path):
    bundle = build_evidence_bundle([], max_tokens=100)
    response = SimpleNamespace(
        content=(
            "Here is the structured result:\n"
            "```json\n"
            '{"answer":"Readable answer","citations":[],'
            '"unsupported_claims":[]}\n'
            "```"
        )
    )

    answer, citations, unsupported = agent_runtime._validated_planned_answer(
        response,
        bundle,
        tmp_path,
    )

    assert answer == (
        "## Conclusion\n\nReadable answer\n\n"
        "No verified citations were returned."
    )
    assert citations == ()
    assert unsupported == 0
    assert "structured result" not in answer
    assert '"citations"' not in answer


def test_invalid_planned_envelope_is_not_exposed(tmp_path):
    bundle = build_evidence_bundle([], max_tokens=100)
    response = SimpleNamespace(
        content=(
            '{"answer":"Internal answer","citations":['
            '{"path":"private.py","supports":"internal rationale"}]'
        )
    )

    answer, citations, unsupported = agent_runtime._validated_planned_answer(
        response,
        bundle,
        tmp_path,
    )

    assert "Internal answer" not in answer
    assert "private.py" not in answer
    assert "supports" not in answer
    assert "could not be validated" in answer
    assert citations == ()
    assert unsupported == 1


def test_planned_answer_leads_with_conclusion_and_limits_evidence(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("\n".join(f"line {index}" for index in range(1, 8)))
    bundle = build_evidence_bundle(
        [
            {
                "evidence_type": "source",
                "path": "app.py",
                "symbol": "analyze",
                "start_line": 1,
                "end_line": 7,
                "content": source.read_text(),
            }
        ],
        max_tokens=100,
    )
    citations = [
        {
            "project": "SourceLens",
            "repository": "SourceLens",
            "revision": "workspace",
            "path": "app.py",
            "symbol": f"analyze_{index}",
            "start_line": index,
            "end_line": index,
            "evidence_type": "source",
            "supports": f"finding {index}",
        }
        for index in range(1, 8)
    ]
    response = SimpleNamespace(
        content=json.dumps(
            {
                "answer": "The implementation has one root cause.",
                "citations": citations,
                "unsupported_claims": [],
            }
        )
    )

    answer, valid, unsupported = agent_runtime._validated_planned_answer(
        response,
        bundle,
        tmp_path,
    )

    assert answer.startswith(
        "## Conclusion\n\nThe implementation has one root cause."
    )
    assert answer.count("- SourceLens / SourceLens") == 5
    assert len(valid) == 5
    assert unsupported == 0


def test_planned_code_analysis_retries_truncated_final_concisely(tmp_path):
    plan = {
        "objective": "Find the root cause",
        "project": "SourceLens",
        "repository": "SourceLens",
        "revision": "workspace",
        "question_type": "implementation",
        "evidence_requirements": [],
        "codegraph_queries": [],
        "literal_queries": [],
        "source_windows": [],
        "max_files": 3,
        "max_fallback_rounds": 0,
        "budgets": {"max_evidence_tokens": 100},
    }
    responses = [
        SimpleNamespace(content=json.dumps(plan)),
        SimpleNamespace(
            content='{"answer":"An incomplete result",',
            response_metadata={"model_length_capped": True},
        ),
        SimpleNamespace(
            content=json.dumps(
                {
                    "answer": "The retry produced a complete conclusion.",
                    "citations": [],
                    "unsupported_claims": [],
                }
            ),
            response_metadata={},
        ),
    ]

    class Model:
        stop_reason = "model_length_capped"
        token_usage = {}

        def __init__(self):
            self.calls = []

        def invoke(self, messages, **kwargs):
            self.calls.append((messages, kwargs))
            return responses[len(self.calls) - 1]

    model = Model()
    result = agent_runtime._run_planned_code_analysis(
        model=model,
        command={"question": "Why is the output incomplete?"},
        tools=[],
        mcp_tools=[],
        emit_agent_event=lambda *_args: None,
        workspace_root=tmp_path,
    )

    assert result["answer"].startswith(
        "## Conclusion\n\nThe retry produced a complete conclusion."
    )
    assert result["planned_evidence"]["final_retry_count"] == 1
    assert result["planned_evidence"]["model_call_count"] == 3
    assert len(model.calls) == 3
    assert model.calls[1][1]["runtime_structured_output"] is True
    assert model.calls[2][1]["runtime_structured_output"] is True
