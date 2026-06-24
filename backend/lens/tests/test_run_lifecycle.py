import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from lens.models import Assistant, LensNode, Run, Session
from lens.services import (
    create_execution_run,
    reconcile_lensnode_active_runs,
    touch_run_activity,
)
from lens.tasks import lensnode_cleanup_task

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

    def test_reconcile_fails_orphaned_run(self):
        run = self._run(
            Run.Status.STREAMING,
            timedelta(minutes=5),
            timedelta(minutes=5),
        )

        count = reconcile_lensnode_active_runs(self.lensnode.uuid, [])

        run.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(run.status, Run.Status.FAILED)
        self.assertEqual(run.error, "LENSNODE_RECONNECT_ORPHANED")

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

        reconcile_lensnode_active_runs(
            self.lensnode.uuid, [str(claimed.uuid)]
        )

        claimed.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(claimed.status, Run.Status.STREAMING)
        self.assertEqual(fresh.status, Run.Status.RUNNING)
