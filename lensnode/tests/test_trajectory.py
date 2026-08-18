"""Tests for complete LensNode trajectory event production."""

import threading
from types import SimpleNamespace

from langchain_core.messages import ToolMessage

from lensnode.agent_runtime.tracing import TraceObservationMiddleware
from lensnode.trajectory import RunTrajectory


def test_call_state_transition_is_atomic_with_started_event():
    frames = []
    trajectory = RunTrajectory("run-atomic", frames.append)
    original_record = trajectory.record
    started_record_reached = threading.Event()
    release_started_record = threading.Event()
    concurrent_record_finished = threading.Event()

    def blocking_record(event_type, *args, **kwargs):
        if event_type == "model.started":
            started_record_reached.set()
            assert release_started_record.wait(1)
        return original_record(event_type, *args, **kwargs)

    trajectory.record = blocking_record
    start_thread = threading.Thread(
        target=lambda: trajectory.start_call("model", "agent")
    )

    def record_concurrently():
        trajectory.record("step.event", {"name": "concurrent"})
        concurrent_record_finished.set()

    start_thread.start()
    assert started_record_reached.wait(1)
    concurrent_thread = threading.Thread(target=record_concurrently)
    concurrent_thread.start()

    try:
        assert not concurrent_record_finished.wait(0.05)
    finally:
        release_started_record.set()
        start_thread.join(1)
        concurrent_thread.join(1)

    assert [frame["events"][0]["event_type"] for frame in frames] == [
        "model.started",
        "step.event",
    ]


def test_trajectory_sequences_nested_calls_and_preserves_full_payload():
    frames = []
    snapshots = []
    trajectory = RunTrajectory(
        "run-1",
        frames.append,
        start_sequence=7,
        attempt=2,
        persist_state=snapshots.append,
    )

    model_call = trajectory.start_call(
        "model",
        "agent",
        {
            "messages": [{"role": "user", "content": "full prompt"}],
            "tools": [{"name": "search", "parameters": {"type": "object"}}],
        },
    )
    tool_call = trajectory.start_call(
        "tool",
        "search",
        {"arguments": {"query": "needle"}},
        parent_call_id=model_call,
    )
    trajectory.finish_call(
        tool_call,
        "completed",
        {"result": {"matches": ["complete result"]}, "duration_ms": 12},
    )

    events = [frame["events"][0] for frame in frames]
    assert [event["sequence"] for event in events] == [8, 9, 10]
    assert [event["attempt"] for event in events] == [2, 2, 2]
    assert events[0]["event_type"] == "model.started"
    assert events[0]["payload"]["messages"][0]["content"] == "full prompt"
    assert events[1]["parent_call_id"] == model_call
    assert events[2]["payload"]["result"] == {"matches": ["complete result"]}
    assert snapshots[-1]["last_trace_seq"] == 10
    assert snapshots[-1]["open_call_ids"] == [model_call]
    assert snapshots[-1]["parent_call_map"] == {}


def test_trajectory_restores_open_calls_and_cursor():
    frames = []
    trajectory = RunTrajectory(
        "run-2",
        frames.append,
        trace_state={
            "trace_schema_version": 1,
            "last_trace_seq": 20,
            "current_attempt": 3,
            "open_call_ids": ["model-old"],
            "open_span_ids": ["span-old"],
            "parent_call_map": {"span-old": "model-old"},
        },
    )

    trajectory.record(
        "checkpoint.restored",
        {"checkpoint_id": "checkpoint-1"},
        checkpoint_id="checkpoint-1",
    )

    event = frames[0]["events"][0]
    assert event["sequence"] == 21
    assert event["attempt"] == 3
    assert event["checkpoint_id"] == "checkpoint-1"
    assert trajectory.snapshot()["open_call_ids"] == ["model-old"]


def test_trajectory_marks_resumed_open_calls_as_interrupted():
    frames = []
    trajectory = RunTrajectory(
        "run-resume",
        frames.append,
        trace_state={
            "trace_schema_version": 1,
            "last_trace_seq": 4,
            "current_attempt": 2,
            "open_call_ids": ["model-old", "tool-old"],
            "open_span_ids": ["tool-old"],
            "parent_call_map": {"tool-old": "model-old"},
        },
    )

    trajectory.interrupt_open_calls("checkpoint_resume")

    events = [frame["events"][0] for frame in frames]
    assert [event["event_type"] for event in events] == [
        "interrupted",
        "interrupted",
    ]
    assert events[1]["parent_call_id"] == "model-old"
    assert events[1]["payload"]["category"] == "tool"
    assert trajectory.snapshot()["open_call_ids"] == []


def test_trajectory_serialization_failure_does_not_break_execution():
    frames = []
    trajectory = RunTrajectory("run-circular", frames.append)
    circular = {}
    circular["self"] = circular

    trajectory.record("tool.completed", circular)

    payload = frames[0]["events"][0]["payload"]
    assert payload["serialization_error"] == "dict"


def test_trajectory_handles_objects_with_broken_string_conversion():
    class BrokenString:
        def __str__(self):
            raise RuntimeError("cannot stringify")

    class BrokenPayload(dict):
        def __str__(self):
            raise RuntimeError("cannot stringify payload")

    frames = []
    trajectory = RunTrajectory("run-broken-string", frames.append)

    trajectory.record(
        "tool.completed",
        BrokenPayload(result=BrokenString()),
    )

    payload = frames[0]["events"][0]["payload"]
    assert payload["serialization_error"] == "BrokenPayload"
    assert payload["value"] == "<unserializable BrokenPayload>"


def test_tool_middleware_records_complete_arguments_and_result():
    frames = []
    trajectory = RunTrajectory("run-3", frames.append)
    middleware = TraceObservationMiddleware(None, None, trajectory)
    request = SimpleNamespace(
        tool=SimpleNamespace(name="search"),
        tool_call={
            "id": "tool-1",
            "name": "search",
            "args": {"query": "full input"},
        },
    )

    middleware.wrap_tool_call(
        request,
        lambda _request: ToolMessage(
            content="full result",
            tool_call_id="tool-1",
            name="search",
        ),
    )

    events = [frame["events"][0] for frame in frames]
    assert events[0]["payload"]["arguments"] == {"query": "full input"}
    assert events[1]["payload"]["result"]["content"] == "full result"
