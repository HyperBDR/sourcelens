import asyncio
import json
import subprocess

from lensnode.agent_tools import build_agent_tools
from lensnode.agent_runtime import _system_prompt
from lensnode.executor import LensNodeExecutor
from lensnode.main import LensNodeClient
from lensnode.runtime_resources import cleanup_runtime_resources
from lensnode.runtime_resources import prepare_runtime_resources


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
    ):
        del command, emit_progress, on_activity, cancel_event
        emit_output("streamed")
        return {
            "answer": "streamed final",
            "samples": [],
        }


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

    assert {
        "type": "run_output",
        "run_uuid": "00000000-0000-0000-0000-000000000001",
        "content_delta": "streamed",
    } in events
    assert {
        "type": "run_output",
        "run_uuid": "00000000-0000-0000-0000-000000000001",
        "final_content": "streamed final",
    } in events


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
    ):
        del command, emit_progress, on_activity
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
    ):
        del command, emit_progress, emit_output, cancel_event
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
        assert resources.mcp_config_path.exists()
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
