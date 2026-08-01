import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from lens.models import (
    Assistant,
    LensNode,
    Run,
    RunExecution,
    RunStep,
    Session,
)
from lens.services import (
    create_execution_run,
    fail_active_runs_for_lensnode,
    reconcile_lensnode_active_runs,
    record_lensnode_run_event,
    touch_run_activity,
)
from lens.tasks import confirm_reconcile_orphan, lensnode_cleanup_task

User = get_user_model()


class RunLifecycleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="rl-user",
            email="rl-user@example.com",
            password="pass12345",
        )
        self.lensnode = LensNode.objects.create(
            name="Local LensNode",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            workspace_path="/workspace",
        )
        self.assistant = Assistant.objects.create(
            name="Code Advisor",
            slug="code-advisor",
            lensnode=self.lensnode,
            selected_task="knowledge_qa",
        )
        self.session = Session.objects.create(
            assistant=self.assistant, user=self.user
        )

    def _run(self, status, started_delta, activity_delta):
        """Create a run with explicit status and timestamps."""

        run = create_execution_run(
            session=self.session, question="q", enqueue=False
        )
        now = timezone.now()
        Run.objects.filter(pk=run.pk).update(
            status=status,
            started_at=now - started_delta,
            last_activity_at=(
                None if activity_delta is None else now - activity_delta
            ),
        )
        run.refresh_from_db()
        return run

    def test_touch_run_activity_throttles(self):
        run = self._run(
            Run.Status.STREAMING,
            timedelta(seconds=60),
            timedelta(seconds=3),
        )
        before = run.last_activity_at
        touch_run_activity(run.pk)
        run.refresh_from_db()
        self.assertEqual(run.last_activity_at, before)  # fresh -> no write

        Run.objects.filter(pk=run.pk).update(
            last_activity_at=timezone.now() - timedelta(seconds=30)
        )
        touch_run_activity(run.pk)
        run.refresh_from_db()
        self.assertLess(
            (timezone.now() - run.last_activity_at).total_seconds(), 5
        )

    def test_record_run_event_drops_late_event_for_terminal_run(self):
        run = self._run(
            Run.Status.FAILED,
            timedelta(minutes=5),
            timedelta(minutes=5),
        )

        step = record_lensnode_run_event(
            run.uuid, "retrieval", "running", {"message": "late"}
        )

        self.assertIsNone(step)
        self.assertEqual(run.steps.count(), 0)

    def test_record_run_event_persists_for_active_run(self):
        run = self._run(
            Run.Status.STREAMING,
            timedelta(seconds=10),
            timedelta(seconds=10),
        )

        step = record_lensnode_run_event(
            run.uuid, "retrieval", "running", {"message": "progress"}
        )

        self.assertIsNotNone(step)
        self.assertEqual(run.steps.count(), 1)

    def test_idle_reaper_fails_silent_run(self):
        run = self._run(
            Run.Status.STREAMING,
            timedelta(minutes=10),
            timedelta(minutes=10),
        )

        lensnode_cleanup_task()

        run.refresh_from_db()
        self.assertEqual(run.status, Run.Status.FAILED)
        self.assertEqual(run.error, "LENS_RUN_TIMEOUT")

    def test_idle_reaper_fails_queued_execution_snapshot(self):
        run = self._run(
            Run.Status.RUNNING,
            timedelta(minutes=10),
            timedelta(minutes=10),
        )
        self.assertEqual(run.execution.status, RunExecution.Status.QUEUED)

        lensnode_cleanup_task()

        run.refresh_from_db()
        run.execution.refresh_from_db()
        self.assertEqual(run.status, Run.Status.FAILED)
        self.assertEqual(run.execution.status, RunExecution.Status.FAILED)
        self.assertIsNotNone(run.execution.finished_at)

    def test_idle_reaper_keeps_long_but_active_run(self):
        # Long-running (90 min, past the old 1h cap) but still streaming
        # output a few seconds ago: it must survive on activity alone.
        run = self._run(
            Run.Status.STREAMING,
            timedelta(minutes=90),
            timedelta(seconds=5),
        )

        lensnode_cleanup_task()

        run.refresh_from_db()
        self.assertEqual(run.status, Run.Status.STREAMING)

    def test_reconcile_schedules_confirmation_instead_of_failing_inline(self):
        # LensNode redelivers run_done at-least-once through a durable
        # outbox, so a run absent from a fresh hello's active list may just
        # be finishing, not dead — reconcile must not fail it on the spot.
        run = self._run(
            Run.Status.STREAMING,
            timedelta(minutes=5),
            timedelta(minutes=5),
        )

        with patch(
            "lens.tasks.confirm_reconcile_orphan.apply_async"
        ) as apply_async:
            count = reconcile_lensnode_active_runs(self.lensnode.uuid, [])

        run.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(run.status, Run.Status.STREAMING)
        self.assertTrue(apply_async.called)
        kwargs = apply_async.call_args.kwargs
        self.assertEqual(kwargs["args"][0], str(run.uuid))
        self.assertIn("countdown", kwargs)

    def test_reconcile_keeps_claimed_and_fresh_runs(self):
        claimed = self._run(
            Run.Status.STREAMING,
            timedelta(minutes=5),
            timedelta(minutes=1),
        )
        fresh = self._run(
            Run.Status.RUNNING,
            timedelta(seconds=10),
            timedelta(seconds=10),
        )

        with patch(
            "lens.tasks.confirm_reconcile_orphan.apply_async"
        ) as apply_async:
            reconcile_lensnode_active_runs(
                self.lensnode.uuid, [str(claimed.uuid)]
            )

        claimed.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(claimed.status, Run.Status.STREAMING)
        self.assertEqual(fresh.status, Run.Status.RUNNING)
        apply_async.assert_not_called()

    def test_confirm_reconcile_orphan_fails_still_running_run(self):
        run = self._run(
            Run.Status.STREAMING,
            timedelta(minutes=5),
            timedelta(minutes=5),
        )

        confirm_reconcile_orphan(str(run.uuid))

        run.refresh_from_db()
        self.assertEqual(run.status, Run.Status.FAILED)
        self.assertEqual(run.error, "LENSNODE_RECONNECT_ORPHANED")

    def test_confirm_reconcile_orphan_finalizes_running_steps(self):
        run = self._run(
            Run.Status.STREAMING,
            timedelta(minutes=5),
            timedelta(minutes=5),
        )
        step = RunStep.objects.create(
            run=run,
            step_type=RunStep.StepType.GENERAL_CHAT,
            sequence=1,
            status=RunStep.Status.RUNNING,
        )

        confirm_reconcile_orphan(str(run.uuid))

        step.refresh_from_db()
        self.assertEqual(step.status, RunStep.Status.FAILED)

    def test_fail_active_runs_for_lensnode_finalizes_steps(self):
        run = self._run(
            Run.Status.RUNNING,
            timedelta(minutes=5),
            timedelta(minutes=5),
        )
        step = RunStep.objects.create(
            run=run,
            step_type=RunStep.StepType.GENERAL_CHAT,
            sequence=1,
            status=RunStep.Status.RUNNING,
        )

        fail_active_runs_for_lensnode(self.lensnode.uuid)

        run.refresh_from_db()
        step.refresh_from_db()
        self.assertEqual(run.status, Run.Status.FAILED)
        self.assertEqual(run.error, "LENSNODE_DISCONNECTED")
        self.assertEqual(step.status, RunStep.Status.FAILED)

    def test_confirm_reconcile_orphan_noops_if_already_terminal(self):
        # The normal completion path (a late but durably-delivered run_done)
        # won the race and finished the run before this fired.
        run = self._run(
            Run.Status.DONE,
            timedelta(minutes=5),
            timedelta(minutes=5),
        )

        confirm_reconcile_orphan(str(run.uuid))

        run.refresh_from_db()
        self.assertEqual(run.status, Run.Status.DONE)
        self.assertEqual(run.error, "")

    def test_confirm_reconcile_orphan_noops_for_unknown_run(self):
        # Must not raise for a run_uuid that no longer exists.
        confirm_reconcile_orphan(str(uuid.uuid4()))
