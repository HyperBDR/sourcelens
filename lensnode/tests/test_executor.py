import asyncio
import json
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from lensnode.agent_runtime import _system_prompt
from lensnode.agent_tools import _skill_script_environment, build_agent_tools
from lensnode.executor import LensNodeExecutor, _remaining_run_timeout_seconds
from lensnode.gateway_model import RunCancelledError
from lensnode.main import LensNodeClient
from lensnode.runtime_resources import (
    _expand_mcp_environment,
    cleanup_runtime_resources,
    prepare_runtime_resources,
)


class FakeAgent:
    """Fake agent that emits one streamed content delta."""

    class Config:
        request_timeout_s = 240

    config = Config()

    async def answer(
        self,
        command,
        emit_progress=None,
        emit_output=None,
        on_activity=None,
        cancel_event=None,
        wrapup_event=None,
    ):
        del command, emit_progress, on_activity, cancel_event, wrapup_event
        emit_output("streamed")
        return {
            "answer": "streamed final",
            "samples": [],
            "citations": [
                {
                    "id": "evidence-123",
                    "path": "src/app.py",
                    "start_line": 10,
                    "end_line": 12,
                }
            ],
            "planned_evidence": {"sufficient": True},
            "outcome": "partial",
            "termination_detail": {
                "reason": "capability_unavailable",
                "capability": "skill",
            },
        }


def test_skill_script_environment_isolated_from_lensnode_token(monkeypatch):
    monkeypatch.setenv("LENSNODE_TOKEN", "control-plane-secret")
    monkeypatch.setenv("PATH", "/usr/bin")

    environment = _skill_script_environment({"JIRA_API_TOKEN": "jira-secret"})

    assert environment["JIRA_API_TOKEN"] == "jira-secret"
    assert environment["PATH"] == "/usr/bin"
    assert "LENSNODE_TOKEN" not in environment


def test_executor_emits_streamed_output_delta():
    executor = LensNodeExecutor.__new__(LensNodeExecutor)
    executor.agent = FakeAgent()
    events = []

    asyncio.run(
        executor.execute(
            {
                "run_uuid": "00000000-0000-0000-0000-000000000001",
                "task": "knowledge_qa",
                "target_dirs": [],
            },
            events.append,
        )
    )

    assert any(
        event.get("type") == "run_output"
        and event.get("run_uuid") == "00000000-0000-0000-0000-000000000001"
        and event.get("content_delta") == "streamed"
        and event.get("reset") is False
        for event in events
    )
    final_output = next(
        event
        for event in events
        if event.get("type") == "run_output"
        and event.get("final_content") == "streamed final"
    )
    assert final_output["citations"] == [
        {
            "id": "evidence-123",
            "path": "src/app.py",
            "start_line": 10,
            "end_line": 12,
        }
    ]
    assert final_output["planned_evidence"] == {"sufficient": True}
    done = [event for event in events if event["type"] == "run_done"][-1]
    assert done["outcome"] == "partial"
    assert done["termination_detail"] == {
        "reason": "capability_unavailable",
        "capability": "skill",
    }


def test_terminal_result_retains_checkpoint_until_acknowledged():
    executor = LensNodeExecutor.__new__(LensNodeExecutor)
    executor.agent = FakeAgent()

    with (
        patch(
            "lensnode.executor.cleanup_run_checkpoint"
        ) as checkpoint_cleanup,
        patch(
            "lensnode.executor.cleanup_run_runtime_resources"
        ) as runtime_cleanup,
    ):
        asyncio.run(
            executor.execute(
                {
                    "run_uuid": "00000000-0000-0000-0000-000000000017",
                    "task": "knowledge_qa",
                    "target_dirs": [],
                },
                lambda _payload: None,
            )
        )

    checkpoint_cleanup.assert_not_called()
    runtime_cleanup.assert_not_called()


def test_executor_cancellation_preserves_checkpoint():
    started = asyncio.Event()

    class CancellableAgent:
        class Config:
            request_timeout_s = 240
            workspace_path = "/workspace"

        config = Config()

        async def answer(self, command, **kwargs):
            del command, kwargs
            started.set()
            await asyncio.sleep(3600)

    async def exercise():
        executor = LensNodeExecutor.__new__(LensNodeExecutor)
        executor.agent = CancellableAgent()
        task = asyncio.create_task(
            executor.execute(
                {
                    "run_uuid": "00000000-0000-0000-0000-000000000009",
                    "task": "knowledge_qa",
                    "target_dirs": [],
                },
                lambda payload: None,
            )
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    with patch("lensnode.executor.cleanup_run_checkpoint") as cleanup:
        asyncio.run(exercise())

    cleanup.assert_not_called()


def test_explicit_cancellation_cleans_after_agent_stops():
    started = asyncio.Event()
    stopped = asyncio.Event()
    release = asyncio.Event()

    class CancelAwareAgent:
        class Config:
            request_timeout_s = 240
            workspace_path = "/workspace"

        config = Config()

        async def answer(self, command, cancel_event=None, **kwargs):
            del command, kwargs
            started.set()
            while not cancel_event.is_set():
                await asyncio.sleep(0)
            await release.wait()
            stopped.set()

    cleanup_observations = []

    async def exercise():
        executor = LensNodeExecutor.__new__(LensNodeExecutor)
        executor.agent = CancelAwareAgent()
        command = {
            "run_uuid": "00000000-0000-0000-0000-000000000016",
            "task": "knowledge_qa",
            "target_dirs": [],
            "_explicit_cancel": True,
        }
        task = asyncio.create_task(executor.execute(command, lambda _p: None))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        await asyncio.wait_for(
            asyncio.gather(task, return_exceptions=True),
            timeout=1,
        )
        assert not stopped.is_set()
        release.set()
        await asyncio.wait_for(stopped.wait(), timeout=1)
        while len(cleanup_observations) < 2:
            await asyncio.sleep(0)

    def observe_cleanup(*_args):
        cleanup_observations.append(stopped.is_set())

    with (
        patch(
            "lensnode.executor.cleanup_run_checkpoint",
            side_effect=observe_cleanup,
        ),
        patch(
            "lensnode.executor.cleanup_run_runtime_resources",
            side_effect=observe_cleanup,
        ),
    ):
        asyncio.run(exercise())

    assert cleanup_observations == [True, True]


def test_duplicate_resume_for_active_run_is_idempotent():
    async def exercise():
        config = type(
            "Config",
            (),
            {
                "name": "test-node",
                "request_timeout_s": 240,
                "max_concurrent_runs": 1,
            },
        )()
        client = LensNodeClient(config)
        executor = BlockingExecutor()
        client.executor = executor
        run_uuid = "00000000-0000-0000-0000-000000000010"
        message = {
            "type": "run_start",
            "run_uuid": run_uuid,
            "task": "knowledge_qa",
            "target_dirs": [],
            "resume": True,
        }

        await client._handle_message(json.dumps(message))
        await asyncio.wait_for(executor.started.wait(), timeout=1)
        await client._handle_message(json.dumps(message))

        assert not any(
            frame.get("error") == "LENSNODE_RUN_ACTIVE"
            for frame in client._outbox
        )
        client.running_tasks[run_uuid].cancel()
        await asyncio.gather(
            client.running_tasks[run_uuid],
            return_exceptions=True,
        )

    asyncio.run(exercise())


def test_run_admission_echoes_dispatch_id_and_duplicate_is_idempotent():
    async def exercise():
        config = type(
            "Config",
            (),
            {
                "name": "test-node",
                "request_timeout_s": 240,
                "max_concurrent_runs": 1,
            },
        )()
        client = LensNodeClient(config)
        executor = BlockingExecutor()
        client.executor = executor
        run_uuid = "00000000-0000-0000-0000-000000000018"
        dispatch_id = "00000000-0000-0000-0000-000000000019"
        duplicate_dispatch_id = "00000000-0000-0000-0000-000000000022"
        message = {
            "type": "run_start",
            "run_uuid": run_uuid,
            "dispatch_id": dispatch_id,
            "task": "knowledge_qa",
            "target_dirs": [],
        }

        await client._handle_message(json.dumps(message))
        await asyncio.wait_for(executor.started.wait(), timeout=1)
        await client._handle_message(
            json.dumps(
                {
                    **message,
                    "dispatch_id": duplicate_dispatch_id,
                    "resume": True,
                }
            )
        )

        admissions = [
            frame
            for frame in client._outbox
            if frame.get("type") == "run_admitted"
        ]
        assert admissions == [
            {
                "type": "run_admitted",
                "run_uuid": run_uuid,
                "dispatch_id": dispatch_id,
            },
            {
                "type": "run_admitted",
                "run_uuid": run_uuid,
                "dispatch_id": duplicate_dispatch_id,
            },
        ]
        assert not any(
            frame.get("error") == "LENSNODE_RUN_ACTIVE"
            for frame in client._outbox
        )
        client.running_tasks[run_uuid].cancel()
        await asyncio.gather(
            client.running_tasks[run_uuid],
            return_exceptions=True,
        )

    asyncio.run(exercise())


def test_executor_emits_checkpoint_ready_for_current_dispatch():
    class CheckpointAwareAgent(FakeAgent):
        async def answer(self, command, on_checkpoint_ready=None, **kwargs):
            if on_checkpoint_ready is not None:
                on_checkpoint_ready()
            return await super().answer(command, **kwargs)

    executor = LensNodeExecutor.__new__(LensNodeExecutor)
    executor.agent = CheckpointAwareAgent()
    events = []
    run_uuid = "00000000-0000-0000-0000-000000000020"
    dispatch_id = "00000000-0000-0000-0000-000000000021"

    asyncio.run(
        executor.execute(
            {
                "run_uuid": run_uuid,
                "dispatch_id": dispatch_id,
                "task": "knowledge_qa",
                "target_dirs": [],
            },
            events.append,
        )
    )

    assert {
        "type": "run_checkpoint_ready",
        "run_uuid": run_uuid,
        "dispatch_id": dispatch_id,
    } in events


def test_control_plane_cancel_cleans_idle_checkpoint_and_runtime_files():
    async def exercise():
        config = type(
            "Config",
            (),
            {
                "name": "test-node",
                "request_timeout_s": 240,
                "workspace_path": "/workspace",
            },
        )()
        client = LensNodeClient(config)
        run_uuid = "00000000-0000-0000-0000-000000000011"

        await client._handle_message(
            json.dumps({"type": "run_cancel", "run_uuid": run_uuid})
        )

    with (
        patch("lensnode.main.cleanup_run_checkpoint") as checkpoint_cleanup,
        patch(
            "lensnode.main.cleanup_run_runtime_resources"
        ) as runtime_cleanup,
    ):
        asyncio.run(exercise())

    checkpoint_cleanup.assert_called_once_with(
        "00000000-0000-0000-0000-000000000011",
        "/workspace",
    )
    runtime_cleanup.assert_called_once_with(
        "/workspace",
        "00000000-0000-0000-0000-000000000011",
    )


def test_resume_uses_remaining_original_wall_clock_budget():
    now = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    started_at = now - timedelta(seconds=70)

    remaining = _remaining_run_timeout_seconds(
        {
            "run_timeout_s": 100,
            "remaining_run_timeout_s": 30,
            "run_started_at": started_at.isoformat(),
            "resume": True,
        },
        now=now,
    )

    assert remaining == 30


def test_executor_derives_run_timeout_from_agent_rounds():
    executor = LensNodeExecutor.__new__(LensNodeExecutor)
    executor.agent = FakeAgent()
    events = []

    asyncio.run(
        executor.execute(
            {
                "run_uuid": "00000000-0000-0000-0000-000000000008",
                "task": "general_chat",
                "agent_rounds": "max",
                "target_dirs": [],
            },
            events.append,
        )
    )

    started = next(
        event
        for event in events
        if event.get("type") == "run_event"
        and event.get("detail", {}).get("task") == "general_chat"
    )
    assert started["detail"]["run_timeout_s"] == 3600


class SlowFinishingAgent:
    """Fake agent that outlives the transport request timeout."""

    class Config:
        request_timeout_s = 0.05
        run_idle_timeout_s = 1

    config = Config()

    async def answer(
        self,
        command,
        emit_progress=None,
        emit_output=None,
        on_activity=None,
        cancel_event=None,
        wrapup_event=None,
    ):
        del command, emit_progress, cancel_event, wrapup_event
        await asyncio.sleep(0.1)
        on_activity()
        emit_output("completed")
        return {"answer": "completed", "samples": []}


def test_executor_run_timeout_is_independent_of_transport_timeout(
    monkeypatch,
):
    monkeypatch.setattr("lensnode.executor.WATCHDOG_INTERVAL_S", 0.01)
    executor = LensNodeExecutor.__new__(LensNodeExecutor)
    executor.agent = SlowFinishingAgent()
    events = []

    asyncio.run(
        executor.execute(
            {
                "run_uuid": "00000000-0000-0000-0000-000000000009",
                "task": "general_chat",
                "agent_rounds": "max",
                "run_timeout_s": 0.3,
                "target_dirs": [],
            },
            events.append,
        )
    )

    done = [event for event in events if event["type"] == "run_done"][-1]
    started = next(
        event
        for event in events
        if event.get("type") == "run_event"
        and event.get("detail", {}).get("task") == "general_chat"
    )
    assert done["status"] == "done"
    assert started["detail"]["run_timeout_s"] == 0.3


class StallingAgent:
    """Fake agent that never produces output until cancelled."""

    class Config:
        request_timeout_s = 240
        run_idle_timeout_s = 0.1

    config = Config()

    def __init__(self):
        self.cancel_event = None

    async def answer(
        self,
        command,
        emit_progress=None,
        emit_output=None,
        on_activity=None,
        cancel_event=None,
        wrapup_event=None,
    ):
        del command, emit_progress, on_activity, wrapup_event
        self.cancel_event = cancel_event
        try:
            await asyncio.sleep(3600)
        finally:
            # A cancelled worker thread may still try to emit; the
            # executor must mute it so a settled run stays untouched.
            emit_output("late output")


def test_executor_watchdog_fails_stalled_run_and_mutes_late_emits(
    monkeypatch,
):
    monkeypatch.setattr("lensnode.executor.WATCHDOG_INTERVAL_S", 0.02)
    executor = LensNodeExecutor.__new__(LensNodeExecutor)
    agent = StallingAgent()
    executor.agent = agent
    events = []

    asyncio.run(
        executor.execute(
            {
                "run_uuid": "00000000-0000-0000-0000-000000000004",
                "task": "knowledge_qa",
                "target_dirs": [],
            },
            events.append,
        )
    )

    done = [event for event in events if event["type"] == "run_done"]
    assert done[-1]["status"] == "failed"
    assert done[-1]["error"] == "NO_ACTIVITY_TIMEOUT"
    assert agent.cancel_event is not None
    assert agent.cancel_event.is_set()
    assert not any(
        event.get("content_delta") == "late output" for event in events
    )


class HeartbeatOnlyAgent:
    """Fake agent alive through on_activity only, with no output."""

    class Config:
        request_timeout_s = 240
        run_idle_timeout_s = 0.15

    config = Config()

    async def answer(
        self,
        command,
        emit_progress=None,
        emit_output=None,
        on_activity=None,
        cancel_event=None,
        wrapup_event=None,
    ):
        del command, emit_progress, emit_output, cancel_event, wrapup_event
        for _ in range(10):
            await asyncio.sleep(0.05)
            on_activity()
        return {
            "answer": "quiet but alive",
            "samples": [],
        }


def test_executor_watchdog_survives_on_transport_activity(monkeypatch):
    monkeypatch.setattr("lensnode.executor.WATCHDOG_INTERVAL_S", 0.02)
    executor = LensNodeExecutor.__new__(LensNodeExecutor)
    executor.agent = HeartbeatOnlyAgent()
    events = []

    asyncio.run(
        executor.execute(
            {
                "run_uuid": "00000000-0000-0000-0000-000000000005",
                "task": "knowledge_qa",
                "target_dirs": [],
            },
            events.append,
        )
    )

    done = [event for event in events if event["type"] == "run_done"]
    assert done[-1]["status"] == "done"


class DeadlineAgent:
    """Fake agent that stays active beyond the wall-clock deadline."""

    class Config:
        request_timeout_s = 240
        run_idle_timeout_s = 1

    config = Config()

    def __init__(self):
        self.cancel_event = None

    async def answer(
        self,
        command,
        emit_progress=None,
        emit_output=None,
        on_activity=None,
        cancel_event=None,
        wrapup_event=None,
    ):
        del command, emit_progress, wrapup_event
        self.cancel_event = cancel_event
        try:
            while True:
                await asyncio.sleep(0.02)
                on_activity()
        finally:
            emit_output("late deadline output")


def test_executor_enforces_wall_clock_deadline_and_mutes_late_emits(
    monkeypatch,
):
    monkeypatch.setattr("lensnode.executor.WATCHDOG_INTERVAL_S", 0.02)
    executor = LensNodeExecutor.__new__(LensNodeExecutor)
    agent = DeadlineAgent()
    executor.agent = agent
    events = []

    asyncio.run(
        asyncio.wait_for(
            executor.execute(
                {
                    "run_uuid": "00000000-0000-0000-0000-000000000006",
                    "task": "general_chat",
                    "run_timeout_s": 0.12,
                    "target_dirs": [],
                },
                events.append,
            ),
            timeout=0.5,
        )
    )

    done = [event for event in events if event["type"] == "run_done"]
    assert done[-1]["status"] == "failed"
    assert done[-1]["error"] == "RUN_TIMEOUT"
    assert agent.cancel_event is not None
    assert agent.cancel_event.is_set()
    assert not any(
        event.get("content_delta") == "late deadline output"
        for event in events
    )


class GracefulDeadlineAgent:
    """Fake agent that finishes when the soft deadline requests wrap-up."""

    class Config:
        request_timeout_s = 240
        run_idle_timeout_s = 1

    config = Config()

    def __init__(self):
        self.cancel_event = None
        self.wrapup_event = None

    async def answer(
        self,
        command,
        emit_progress=None,
        emit_output=None,
        on_activity=None,
        cancel_event=None,
        wrapup_event=None,
    ):
        del command, emit_progress, emit_output
        self.cancel_event = cancel_event
        self.wrapup_event = wrapup_event
        while not wrapup_event.is_set():
            await asyncio.sleep(0.01)
            on_activity()
        return {"answer": "best effort before timeout", "samples": []}


def test_executor_requests_wrapup_before_hard_deadline(monkeypatch):
    monkeypatch.setattr("lensnode.executor.WATCHDOG_INTERVAL_S", 0.02)
    executor = LensNodeExecutor.__new__(LensNodeExecutor)
    agent = GracefulDeadlineAgent()
    executor.agent = agent
    events = []

    asyncio.run(
        asyncio.wait_for(
            executor.execute(
                {
                    "run_uuid": "00000000-0000-0000-0000-000000000007",
                    "task": "general_chat",
                    "run_timeout_s": 0.2,
                    "target_dirs": [],
                },
                events.append,
            ),
            timeout=0.5,
        )
    )

    done = [event for event in events if event["type"] == "run_done"]
    assert done[-1]["status"] == "done"
    assert agent.wrapup_event is not None
    assert agent.wrapup_event.is_set()
    assert not agent.cancel_event.is_set()
    assert any(
        event.get("detail", {}).get("agent_event")
        == "deepagents.agent.soft_deadline.requested"
        for event in events
    )


def test_runtime_resources_collect_context_skill_content(tmp_path):
    config = type(
        "Config",
        (),
        {
            "workspace_path": str(tmp_path),
        },
    )()
    command = {
        "run_uuid": "00000000-0000-0000-0000-000000000002",
        "loaded_skills": [
            {
                "skill_uuid": "11111111-1111-1111-1111-111111111111",
                "skill_slug": "repo-guide",
                "skill_name": "Repo Guide",
                "content_hash": "sha256:abc",
                "definition": {
                    "content": (
                        "---\n"
                        "name: repo-guide\n"
                        "description: Repository layout guide\n"
                        "---\n\n"
                        "# Repo Guide\n\n"
                        "Inspect service-api before deployment repos."
                    ),
                    "api": {
                        "base_url_env": "REPO_BASE_URL",
                        "routes": [
                            {
                                "path": "/api/status",
                                "methods": ["GET"],
                            }
                        ],
                    },
                    "transforms": {
                        "summarize": {
                            "entrypoint": "scripts/summarize.py",
                            "input_format": "json",
                            "environment": [],
                            "sha256": "0" * 64,
                        }
                    },
                },
                "load_config": {"mode": "context", "inject": True},
            },
        ],
        "loaded_mcps": [],
    }

    resources = prepare_runtime_resources(config, command)

    try:
        assert len(resources.skill_paths) == 1
        assert len(resources.context_skill_contents) == 1
        assert "Inspect service-api" in resources.context_skill_contents[0]
        assert resources.skill_api_policies["repo-guide"] == {
            "base_url_env": "REPO_BASE_URL",
            "routes": [
                {
                    "path": "/api/status",
                    "methods": ["GET"],
                }
            ],
        }
        assert resources.skill_transforms["repo-guide"] == {
            "summarize": {
                "entrypoint": "scripts/summarize.py",
                "input_format": "json",
                "environment": [],
                "sha256": "0" * 64,
            }
        }
        assert resources.mcp_config_path.exists()
    finally:
        cleanup_runtime_resources(resources)


def test_mcp_credentials_are_materialized_only_in_run_directory(tmp_path):
    config = type(
        "Config",
        (),
        {
            "workspace_path": str(tmp_path),
        },
    )()
    secret = "Bearer runtime-only-secret"
    command = {
        "run_uuid": "00000000-0000-0000-0000-000000000008",
        "loaded_skills": [],
        "loaded_mcps": [
            {
                "mcp_uuid": "22222222-2222-2222-2222-222222222222",
                "mcp_name": "Remote API",
                "content_hash": "sha256:def",
                "transport": "url",
                "endpoint": "https://mcp.example.com/api",
                "config": {"headers": {"Authorization": secret}},
                "load_config": {},
            }
        ],
    }

    resources = prepare_runtime_resources(config, command)

    try:
        assert resources.mcp_configs[0]["config"]["headers"] == {
            "Authorization": secret
        }
        runtime_text = resources.mcp_config_path.read_text(encoding="utf-8")
        assert secret not in runtime_text
        assert "Authorization" not in runtime_text
        cache_root = tmp_path / ".sourcelens" / "cache"
        cached_text = "".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in cache_root.rglob("*")
            if path.is_file()
        )
        assert secret not in cached_text
    finally:
        cleanup_runtime_resources(resources)


def test_mcp_environment_expands_runtime_placeholders_only(tmp_path):
    config = type(
        "Config",
        (),
        {
            "workspace_path": str(tmp_path),
        },
    )()
    secret = "runtime-environment-secret"
    command = {
        "run_uuid": "00000000-0000-0000-0000-000000000009",
        "loaded_skills": [],
        "loaded_mcps": [
            {
                "mcp_uuid": "22222222-2222-2222-2222-222222222223",
                "mcp_name": "Environment API",
                "content_hash": "sha256:environment",
                "transport": "url",
                "endpoint": "https://${MCP_HOST}/api",
                "config": {
                    "headers": {
                        "Authorization": "Bearer ${MCP_TOKEN}",
                    }
                },
                "environment": {
                    "MCP_HOST": "mcp.example.com",
                    "MCP_TOKEN": secret,
                },
                "load_config": {},
            }
        ],
    }

    resources = prepare_runtime_resources(config, command)

    try:
        runtime_mcp = resources.mcp_configs[0]
        assert runtime_mcp["endpoint"] == "https://mcp.example.com/api"
        assert runtime_mcp["config"]["headers"] == {
            "Authorization": f"Bearer {secret}"
        }
        runtime_text = resources.mcp_config_path.read_text(encoding="utf-8")
        assert secret not in runtime_text
        assert "MCP_TOKEN" not in runtime_text
    finally:
        cleanup_runtime_resources(resources)


def test_mcp_environment_rejects_unresolved_placeholders():
    with pytest.raises(
        ValueError,
        match="Missing MCP environment variable: MCP_TOKEN",
    ):
        _expand_mcp_environment(
            {
                "headers": {
                    "Authorization": "Bearer ${MCP_TOKEN}",
                }
            },
            {},
        )


def test_mcp_environment_preserves_preexpanded_values(tmp_path):
    config = type(
        "Config",
        (),
        {
            "workspace_path": str(tmp_path),
        },
    )()
    secret = "runtime-${HOME}-secret"
    command = {
        "run_uuid": "00000000-0000-0000-0000-000000000010",
        "loaded_skills": [],
        "loaded_mcps": [
            {
                "mcp_uuid": "22222222-2222-2222-2222-222222222224",
                "mcp_name": "Resolved Environment API",
                "content_hash": "sha256:resolved-environment",
                "transport": "url",
                "endpoint": "https://mcp.example.com/api",
                "config": {
                    "headers": {
                        "Authorization": f"Bearer {secret}",
                    }
                },
                "environment": {"MCP_TOKEN": secret},
                "environment_resolved": True,
                "load_config": {},
            }
        ],
    }

    resources = prepare_runtime_resources(config, command)

    try:
        assert resources.mcp_configs[0]["config"]["headers"] == {
            "Authorization": f"Bearer {secret}"
        }
    finally:
        cleanup_runtime_resources(resources)


def test_mcp_environment_preserves_legacy_placeholder_literals(tmp_path):
    config = type(
        "Config",
        (),
        {
            "workspace_path": str(tmp_path),
        },
    )()
    command = {
        "run_uuid": "00000000-0000-0000-0000-000000000011",
        "loaded_skills": [],
        "loaded_mcps": [
            {
                "mcp_uuid": "22222222-2222-2222-2222-222222222225",
                "mcp_name": "Legacy Placeholder API",
                "content_hash": "sha256:legacy-placeholder",
                "transport": "url",
                "endpoint": "https://mcp.example.com/${API_VERSION}",
                "config": {"template": "${LITERAL}"},
                "load_config": {},
            }
        ],
    }

    resources = prepare_runtime_resources(config, command)

    try:
        assert resources.mcp_configs[0]["endpoint"] == (
            "https://mcp.example.com/${API_VERSION}"
        )
        assert resources.mcp_configs[0]["config"] == {
            "template": "${LITERAL}"
        }
    finally:
        cleanup_runtime_resources(resources)


def test_system_prompt_includes_context_skill_guidance():
    prompt = _system_prompt(
        {
            "prompt": "Analyze code.",
        },
        {
            "target_dirs": [{"path": "/workspace/product"}],
        },
        ["## Repo Guide\n\nInspect service-api first."],
    )

    assert "Workspace Guidance from bound context skills" in prompt
    assert "Inspect service-api first" in prompt
    assert "/workspace/product" in prompt


def test_system_prompt_omits_codegraph_guidance_by_default():
    prompt = _system_prompt(
        {"prompt": "Analyze code."},
        {"target_dirs": [{"path": "/workspace/product"}]},
    )

    assert "CodeGraph is available" not in prompt


def test_system_prompt_injects_codegraph_guidance_when_available():
    prompt = _system_prompt(
        {"prompt": "Analyze code."},
        {"target_dirs": [{"path": "/workspace/product"}]},
        runtime_guidance=(
            "CodeGraph is available through exactly one MCP tool: "
            "mcp__codegraph__codegraph_explore. MUST call "
            "mcp__codegraph__codegraph_explore before any workspace tool.",
        ),
    )

    assert "CodeGraph is available" in prompt
    assert "mcp__codegraph__codegraph_explore" in prompt
    assert (
        "MUST call mcp__codegraph__codegraph_explore before any"
        in prompt
    )
    assert "mcp__codegraph__codegraph_trace" not in prompt


def test_system_prompt_prioritizes_codegraph_over_workspace_search():
    prompt = _system_prompt(
        {"prompt": "Analyze code."},
        {"target_dirs": [{"path": "/workspace/product"}]},
        runtime_guidance=(
            "CodeGraph is available through exactly one MCP tool: "
            "mcp__codegraph__codegraph_explore. MUST call "
            "mcp__codegraph__codegraph_explore before any workspace tool.",
        ),
    )

    codegraph_position = prompt.index("CodeGraph is available")
    search_position = prompt.index("FIRST workspace action")

    assert codegraph_position < search_position


def test_git_log_accepts_non_integer_max_count(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
    )
    (repo / "README.md").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True)

    tools = {
        tool.name: tool
        for tool in build_agent_tools(
            {
                "target_dirs": [{"path": str(repo)}],
                "settings": {},
            }
        )
    }

    payload = tools["git_log"].invoke(
        {
            "path": str(repo),
            "max_count": "many",
        }
    )

    assert json.loads(payload)["ok"] is True


def test_recent_changes_returns_no_match_instead_of_fallback_repo(tmp_path):
    root = tmp_path / "workspace"
    repo = root / "unrelated"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    tools = {
        tool.name: tool
        for tool in build_agent_tools(
            {
                "target_dirs": [{"path": str(root)}],
                "settings": {},
            }
        )
    }

    payload = tools["summarize_recent_changes"].invoke(
        {
            "query": "porter recent changes",
            "max_commits": 20,
        }
    )
    data = json.loads(payload)

    assert data["error"] == "NO_MATCHING_REPOSITORY"
    assert str(repo) in data["candidate_repositories"]


class BlockingExecutor:
    """Executor that blocks until cancelled."""

    def __init__(self):
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def execute(self, command, emit):
        del command, emit
        self.started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


def test_lensnode_run_cancel_cancels_running_task():
    async def exercise():
        config = type(
            "Config",
            (),
            {
                "name": "test-node",
                "request_timeout_s": 240,
                "max_concurrent_runs": 1,
            },
        )()
        client = LensNodeClient(config)
        executor = BlockingExecutor()
        client.executor = executor
        run_uuid = "00000000-0000-0000-0000-000000000003"

        await client._handle_message(
            json.dumps(
                {
                    "type": "run_start",
                    "run_uuid": run_uuid,
                    "task": "knowledge_qa",
                    "target_dirs": [],
                }
            )
        )
        await asyncio.wait_for(executor.started.wait(), timeout=1)

        await client._handle_message(
            json.dumps(
                {
                    "type": "run_cancel",
                    "run_uuid": run_uuid,
                }
            )
        )

        await asyncio.wait_for(executor.cancelled.wait(), timeout=1)
        assert run_uuid not in client.running_tasks

    asyncio.run(exercise())


def test_lensnode_datasource_conversion_reports_safe_cancellation(
    monkeypatch,
):
    """Managed conversion cancellation stops at a cooperative boundary."""

    started = threading.Event()

    def convert_managed_workspace(command, workspace_path, emit):
        del workspace_path, emit
        started.set()
        while not command["cancel_event"].is_set():
            time.sleep(0.01)
        raise RunCancelledError("cancelled")

    monkeypatch.setattr(
        "lensnode.main.convert_managed_workspace",
        convert_managed_workspace,
    )

    async def exercise():
        config = type(
            "Config",
            (),
            {
                "name": "test-node",
                "request_timeout_s": 240,
                "max_concurrent_runs": 1,
                "workspace_path": "/workspace",
                "ai_gateway_url": "http://gateway",
                "token": "node-token",
            },
        )()
        client = LensNodeClient(config)
        task_id = "conversion-task"

        await client._handle_message(
            json.dumps(
                {
                    "type": "datasource_convert",
                    "request_id": "conversion-request",
                    "task_id": task_id,
                    "source_type": "managed_workspace",
                    "target_path": "/workspace/documents",
                    "conversion": {"document": True},
                }
            )
        )
        await asyncio.wait_for(
            asyncio.to_thread(started.wait),
            timeout=1,
        )

        await client._handle_message(
            json.dumps(
                {
                    "type": "datasource_convert_cancel",
                    "task_id": task_id,
                }
            )
        )
        task = client.running_tasks[f"datasource-convert:{task_id}"]
        await asyncio.wait_for(task, timeout=1)

        done = [
            item
            for item in client._outbox
            if item.get("type") == "datasource_convert_done"
        ]
        assert done[-1]["status"] == "cancelled"
        assert done[-1]["error"] == "DATASOURCE_CONVERSION_CANCELLED"
        assert f"datasource-convert:{task_id}" not in client.running_tasks

    asyncio.run(exercise())
