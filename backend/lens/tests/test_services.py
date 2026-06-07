from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from core.asgi import application
from core.management.commands.register_periodic_tasks import (
    discover_and_register,
)
from core.periodic_registry import TASK_REGISTRY
from lens.execution import execute_answer_run
from lens.lensnode_auth import issue_lensnode_token
from lens.llm import LensLLMResult, QuestionPreflightResult
from lens.llm import _parse_preflight_result
from lens.models import (
    Assistant,
    DataSource,
    LensNode,
    Message,
    Run,
    RunStep,
    ScheduledTask,
    Session,
)
from lens.periodic_tasks import register_periodic_tasks
from lens.services import (
    append_lensnode_output,
    create_execution_run,
    finish_lensnode_run,
)
from lens.source_sync import reset_cache_path
from lens.tasks import (
    SourceSyncBusy,
    datasource_lock,
    lensnode_health_task,
    source_sync_task,
)

User = get_user_model()

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
}

TEST_CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}


@override_settings(CACHES=TEST_CACHES, CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class LensServiceTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="lens-user",
            email="lens-user@example.com",
            password="pass12345",
        )
        self.lensnode = LensNode.objects.create(
            name="Local LensNode",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            workspace_path="/workspace",
            available_dirs=[{"path": "/workspace/repo"}],
            tasks=[{"name": "knowledge_qa", "description": "Answer code questions"}],
        )
        self.assistant = Assistant.objects.create(
            name="Code Advisor",
            slug="code-advisor",
            lensnode=self.lensnode,
            selected_task="knowledge_qa",
            selected_dirs=[{"path": "/workspace/repo"}],
        )
        self.datasource = DataSource.objects.create(
            name="Repo Cache",
            source_type="git",
            config={"repo_url": "https://example.com/repo.git"},
            sync_policy={"interval_seconds": 3600},
            target_path="/opt/storage/repo-cache",
        )
        self.session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
            title="",
        )

    def test_create_execution_run_creates_queued_run_with_lensnode(self):
        run = create_execution_run(
            session=self.session,
            question="How does SSE work?",
            idempotency_key="real-run",
            enqueue=False,
        )

        self.assertEqual(run.status, "queued")
        self.assertEqual(run.lensnode, self.lensnode)
        self.assertEqual(run.input_message.role, Message.Role.USER)
        self.assertEqual(run.output_message.role, Message.Role.ASSISTANT)
        self.assertEqual(self.session.message_set.count(), 2)

    def test_lens_smoke_test_command_passes(self):
        call_command("lens_smoke_test")

    def test_create_execution_run_reuses_idempotent_run(self):
        first = create_execution_run(
            session=self.session,
            question="How does SSE work?",
            idempotency_key="real-run",
            enqueue=False,
        )
        second = create_execution_run(
            session=self.session,
            question="How does SSE work?",
            idempotency_key="real-run",
            enqueue=False,
        )

        self.assertEqual(first.uuid, second.uuid)
        self.assertEqual(self.session.message_set.count(), 2)

    def test_execute_answer_run_creates_execution_snapshot(self):
        run = create_execution_run(
            session=self.session,
            question="How does SSE work?",
            idempotency_key="real-run",
            enqueue=False,
        )

        execute_answer_run(run, dispatch=False)
        run.refresh_from_db()

        self.assertEqual(run.status, "done")
        self.assertEqual(run.steps.count(), 4)
        self.assertTrue(run.output_message.content)
        self.assertEqual(run.execution.task, "knowledge_qa")
        self.assertEqual(run.execution.target_dirs, [{"path": "/workspace/repo"}])

    def test_execute_answer_run_allows_preflight_and_dispatches(self):
        run = create_execution_run(
            session=self.session,
            question="How does SSE work?",
            enqueue=False,
        )
        preflight = QuestionPreflightResult(
            decision="allow",
            message="",
            rewritten_question="Explain SSE in this repo.",
            reason="single_workspace_question",
            usage={"total_tokens": 9},
            metered=True,
        )

        with patch("lens.llm.preflight_question", return_value=preflight):
            execute_answer_run(run, dispatch=False)

        run.refresh_from_db()
        step = run.steps.get(sequence=1)
        self.assertEqual(step.detail["decision"], "allow")
        self.assertEqual(
            step.detail["rewritten_question"],
            "Explain SSE in this repo.",
        )
        self.assertTrue(hasattr(run, "execution"))
        self.assertEqual(run.execution.task, "knowledge_qa")

    def test_execute_answer_run_clarify_preflight_does_not_dispatch(self):
        run = create_execution_run(
            session=self.session,
            question="A lot of unrelated questions",
            enqueue=False,
        )
        preflight = QuestionPreflightResult(
            decision="clarify",
            message="Please split this into one question at a time.",
            rewritten_question="",
            reason="too_many_unrelated_questions",
            usage={"total_tokens": 11},
            metered=True,
        )

        with patch("lens.llm.preflight_question", return_value=preflight):
            execute_answer_run(run, dispatch=True)

        run.refresh_from_db()
        self.assertEqual(run.status, Run.Status.DONE)
        self.assertEqual(
            run.output_message.content,
            "Please split this into one question at a time.",
        )
        self.assertFalse(hasattr(run, "execution"))
        self.assertEqual(run.steps.count(), 2)
        self.assertEqual(
            run.steps.get(sequence=1).detail["decision"],
            "clarify",
        )

    def test_execute_answer_run_reject_preflight_does_not_dispatch(self):
        run = create_execution_run(
            session=self.session,
            question="What is the weather today?",
            enqueue=False,
        )
        preflight = QuestionPreflightResult(
            decision="reject",
            message="This assistant only answers workspace questions.",
            rewritten_question="",
            reason="outside_workspace_scope",
            usage={"total_tokens": 12},
            metered=True,
        )

        with patch("lens.llm.preflight_question", return_value=preflight):
            execute_answer_run(run, dispatch=True)

        run.refresh_from_db()
        self.assertEqual(run.status, Run.Status.DONE)
        self.assertEqual(
            run.output_message.content,
            "This assistant only answers workspace questions.",
        )
        self.assertFalse(hasattr(run, "execution"))
        self.assertEqual(
            run.steps.get(sequence=1).detail["reason"],
            "outside_workspace_scope",
        )

    def test_execute_answer_run_fails_when_lensnode_offline(self):
        self.lensnode.status = LensNode.Status.OFFLINE
        self.lensnode.save(update_fields=["status"])
        run = create_execution_run(
            session=self.session,
            question="How does SSE work?",
            enqueue=False,
        )

        with self.assertRaises(Exception):
            execute_answer_run(run, dispatch=False)

        run.refresh_from_db()
        self.assertEqual(run.status, Run.Status.FAILED)
        self.assertEqual(run.error, "LENSNODE_OFFLINE")

    def test_finish_lensnode_run_applies_optional_postprocess_model(self):
        self.assistant.postprocess_model_ref = (
            "016d5cf7-2245-4015-b242-d6323e795b58"
        )
        self.assistant.save(update_fields=["postprocess_model_ref"])
        run = create_execution_run(
            session=self.session,
            question="What does this project do?",
            enqueue=False,
        )
        run.output_message.content = "raw answer"
        run.output_message.save(update_fields=["content"])
        postprocess_result = type(
            "PostprocessResult",
            (),
            {
                "content": "polished answer",
                "usage": {"total_tokens": 8},
                "metered": True,
            },
        )()

        with patch(
            "lens.llm.postprocess_answer",
            return_value=postprocess_result,
        ):
            finish_lensnode_run(run.uuid, Run.Status.DONE)

        run.refresh_from_db()
        self.assertEqual(run.status, Run.Status.DONE)
        self.assertEqual(run.output_message.content, "polished answer")
        answer_step = run.steps.get(sequence=3)
        self.assertEqual(answer_step.step_type, RunStep.StepType.ANSWER)
        self.assertEqual(answer_step.status, RunStep.Status.DONE)
        self.assertEqual(
            answer_step.detail["postprocessed_answer_length"],
            len("polished answer"),
        )

    def test_finish_lensnode_run_does_not_overwrite_cancelled_run(self):
        run = create_execution_run(
            session=self.session,
            question="What does this project do?",
            enqueue=False,
        )
        run.status = Run.Status.CANCELLED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])

        finish_lensnode_run(run.uuid, Run.Status.DONE)

        run.refresh_from_db()
        self.assertEqual(run.status, Run.Status.CANCELLED)
        self.assertEqual(run.output_message.content, "")

    def test_append_lensnode_output_ignores_terminal_run(self):
        run = create_execution_run(
            session=self.session,
            question="What does this project do?",
            enqueue=False,
        )
        run.status = Run.Status.CANCELLED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])

        append_lensnode_output(run.uuid, content_delta="late answer")

        run.refresh_from_db()
        self.assertEqual(run.output_message.content, "")

    def test_preflight_invalid_json_clarifies_instead_of_allowing(self):
        result = LensLLMResult(
            content="not json",
            usage={"total_tokens": 3},
            metered=True,
        )

        parsed = _parse_preflight_result(result, "Question?")

        self.assertEqual(parsed.decision, "clarify")
        self.assertEqual(parsed.reason, "invalid_preflight_response")
        self.assertTrue(parsed.message)

    def test_lensnode_websocket_hello_output_and_done(self):
        token = issue_lensnode_token(self.lensnode)

        async_to_sync(self._exercise_lensnode_websocket)(token)

        self.lensnode.refresh_from_db()
        self.assertEqual(self.lensnode.protocol_version, "v1")
        self.lensnode.status = LensNode.Status.ONLINE
        self.lensnode.save(update_fields=["status"])

        run = create_execution_run(
            session=self.session,
            question="How does SSE work?",
            enqueue=False,
        )
        execute_answer_run(run, dispatch=True)

        async_to_sync(self._exercise_lensnode_run_frames)(token, run)

        run.refresh_from_db()
        self.assertEqual(run.status, Run.Status.DONE)
        self.assertEqual(run.output_message.content, "answer")

    def test_lensnode_websocket_rejects_revoked_token(self):
        token = issue_lensnode_token(self.lensnode)
        self.lensnode.token_revoked = True
        self.lensnode.save(update_fields=["token_revoked"])
        communicator = WebsocketCommunicator(
            application,
            f"/ws/lens/lensnodes/?token={token}",
        )

        connected, _ = async_to_sync(communicator.connect)()

        self.assertFalse(connected)

    async def _exercise_lensnode_websocket(self, token):
        """Connect a LensNode and send a hello frame in one event loop."""

        communicator = WebsocketCommunicator(
            application,
            f"/ws/lens/lensnodes/?token={token}",
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_json_from()
        await communicator.send_json_to(
            {
                "type": "hello",
                "protocol_version": "v1",
                "agent_version": "1.0.0",
                "workspace_path": "/workspace",
                "available_dirs": [{"path": "/workspace/repo"}],
                "tasks": [{"name": "knowledge_qa"}],
                "labels": {"region": "local"},
            }
        )
        self.assertEqual(
            (await communicator.receive_json_from())["type"],
            "hello_ack",
        )
        await communicator.disconnect()

    async def _exercise_lensnode_run_frames(self, token, run):
        """Connect a LensNode and send run result frames in one event loop."""

        communicator = WebsocketCommunicator(
            application,
            f"/ws/lens/lensnodes/?token={token}",
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_json_from()
        await communicator.send_json_to(
            {
                "type": "run_event",
                "run_uuid": str(run.uuid),
                "step_type": "retrieval",
                "status": "done",
                "detail": {"hits": 2},
            }
        )
        await communicator.send_json_to(
            {
                "type": "run_output",
                "run_uuid": str(run.uuid),
                "content_delta": "answer",
            }
        )
        await communicator.send_json_to(
            {
                "type": "run_done",
                "run_uuid": str(run.uuid),
                "status": "done",
            }
        )
        await communicator.disconnect()

    def test_source_sync_task_updates_datasource_and_scheduled_task(self):
        with self._local_git_repo() as repo_path:
            with self._target_path() as target_path:
                self.datasource.config = {
                    "repo_url": repo_path,
                    "branch": "main",
                }
                self.datasource.target_path = target_path
                self.datasource.save(update_fields=["config", "target_path"])

                synced = source_sync_task(str(self.datasource.uuid))
                self.datasource.refresh_from_db()

                record = ScheduledTask.objects.get(
                    task_type="source_sync",
                    target_type="datasource",
                    target_id=self.datasource.uuid,
                )
                self.assertEqual(synced, 1)
                self.assertEqual(self.datasource.status, "active")
                self.assertIsNotNone(self.datasource.last_synced_at)
                self.assertTrue(Path(self.datasource.target_path).exists())
                self.assertEqual(record.last_status, "success")
                self.assertEqual(record.last_metrics, {"synced": 1})

                reset_cache_path(self.datasource.target_path)

    def test_source_sync_task_marks_invalid_source_failed(self):
        self.datasource.config = {}
        self.datasource.save(update_fields=["config"])

        with self.assertRaises(ValueError):
            source_sync_task(str(self.datasource.uuid))

        self.datasource.refresh_from_db()
        record = ScheduledTask.objects.get(
            task_type="source_sync",
            target_type="datasource",
            target_id=self.datasource.uuid,
        )
        self.assertEqual(self.datasource.status, "error")
        self.assertEqual(record.last_status, "failed")

    def test_source_sync_task_rejects_concurrent_sync_without_source_error(self):
        with datasource_lock(self.datasource.uuid):
            with self.assertRaises(SourceSyncBusy):
                source_sync_task(str(self.datasource.uuid))

        self.datasource.refresh_from_db()
        record = ScheduledTask.objects.get(
            task_type="source_sync",
            target_type="datasource",
            target_id=self.datasource.uuid,
        )
        self.assertEqual(self.datasource.status, "active")
        self.assertEqual(record.last_status, "failed")
        self.assertEqual(record.last_error, "LENS_SOURCE_SYNC_BUSY")

    def test_source_sync_task_writes_jira_cache(self):
        with self._target_path() as target_path:
            self.datasource.source_type = DataSource.SourceType.JIRA
            self.datasource.config = {
                "base_url": "https://jira.example.com",
                "query_rules": {"jql": "project = SRC", "max_results": 2},
            }
            self.datasource.target_path = target_path
            self.datasource.save(
                update_fields=["source_type", "config", "target_path"]
            )

            with patch("lens.source_sync._http_get_json") as get_json:
                get_json.return_value = {
                    "issues": [
                        {"key": "SRC-1", "fields": {"summary": "One"}},
                        {"key": "SRC-2", "fields": {"summary": "Two"}},
                    ]
                }
                synced = source_sync_task(str(self.datasource.uuid))

            cache_file = Path(self.datasource.target_path) / "jira" / "issues.json"
            self.assertEqual(synced, 2)
            self.assertTrue(cache_file.exists())
            self.assertIn("SRC-1", cache_file.read_text())
            reset_cache_path(self.datasource.target_path)

    def test_source_sync_task_writes_feishu_cache(self):
        with self._target_path() as target_path:
            self.datasource.source_type = DataSource.SourceType.FEISHU
            self.datasource.config = {
                "app_token": "app-token",
                "doc_ids": ["doc-1", "doc-2"],
            }
            self.datasource.target_path = target_path
            self.datasource.save(
                update_fields=["source_type", "config", "target_path"]
            )

            with patch("lens.source_sync._http_get_json") as get_json:
                get_json.side_effect = [
                    {"data": {"name": "Doc 1"}},
                    {"data": {"name": "Doc 2"}},
                ]
                synced = source_sync_task(str(self.datasource.uuid))

            cache_file = (
                Path(self.datasource.target_path) / "feishu" / "documents.json"
            )
            self.assertEqual(synced, 2)
            self.assertTrue(cache_file.exists())
            self.assertIn("Doc 1", cache_file.read_text())
            reset_cache_path(self.datasource.target_path)

    def test_lensnode_health_marks_stale_lensnodes_offline(self):
        self.lensnode.status = LensNode.Status.ONLINE
        self.lensnode.last_heartbeat_at = timezone.now() - timedelta(seconds=120)
        self.lensnode.save(update_fields=["status", "last_heartbeat_at"])

        marked = lensnode_health_task()

        self.lensnode.refresh_from_db()
        self.assertEqual(marked, 1)
        self.assertEqual(self.lensnode.status, LensNode.Status.OFFLINE)

    def test_register_periodic_tasks_adds_lens_entries(self):
        TASK_REGISTRY.clear()

        register_periodic_tasks()

        self.assertEqual(
            ScheduledTask.objects.filter(
                task_type="lensnode_cleanup",
                target_type=None,
            ).count(),
            1,
        )
        self.assertEqual(
            ScheduledTask.objects.filter(
                task_type="lensnode_health",
                target_type=None,
            ).count(),
            1,
        )
        self.assertGreaterEqual(len(TASK_REGISTRY), 4)

    def test_discover_and_register_backfills_periodic_task_refs(self):
        discover_and_register()

        task_types = {
            "lensnode_cleanup",
            "lensnode_health",
            "run_retention",
            "source_sync",
        }
        tasks = ScheduledTask.objects.filter(task_type__in=task_types)
        self.assertTrue(tasks.exists())
        self.assertFalse(tasks.filter(periodic_task_ref__isnull=True).exists())

    def _local_git_repo(self):
        """Create a temporary git repo for source sync tests."""

        import shutil
        import subprocess
        import tempfile

        @contextmanager
        def repo_context():
            root = Path(tempfile.mkdtemp(prefix="lens-git-source-"))
            try:
                subprocess.run(
                    ["git", "init", "-b", "main"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "config", "user.email", "lens@example.com"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "config", "user.name", "Lens Test"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                (root / "README.md").write_text("hello lens\n")
                subprocess.run(
                    ["git", "add", "README.md"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "commit", "-m", "Initial commit"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                yield str(root)
            finally:
                shutil.rmtree(root, ignore_errors=True)

        return repo_context()

    def _target_path(self):
        """Create an empty target path value for source sync tests."""

        import shutil
        import tempfile

        @contextmanager
        def target_context():
            root = Path(tempfile.mkdtemp(prefix="lens-target-"))
            target = root / "cache"
            try:
                yield str(target)
            finally:
                shutil.rmtree(root, ignore_errors=True)

        return target_context()
