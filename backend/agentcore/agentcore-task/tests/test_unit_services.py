"""
Unit tests for agentcore_task.adapters.django.services
(lock, log_collector, task_tracker, timeout, cleanup, task_config)
and conf (crontab validation).
"""
import pytest

from agentcore_task.adapters.django.conf import is_valid_crontab_expression
from agentcore_task.adapters.django.services import (
    TaskLogCollector,
    TaskTracker,
    acquire_task_lock,
    cleanup_old_executions,
    is_task_locked,
    prevent_duplicate_task,
    register_task_execution,
    release_task_lock,
)
from agentcore_task.adapters.django.services import (
    task_config as task_config_svc,
)
from agentcore_task.adapters.django.services import (
    task_tracker as task_tracker_svc,
)
from agentcore_task.adapters.django.services.timeout import (
    mark_timed_out_executions,
)
from agentcore_task.constants import TaskStatus


pytestmark = [pytest.mark.unit]


class TestLock:
    def test_acquire_release_and_check(self):
        name = "test_lock_acquire_release"
        assert not is_task_locked(name)
        assert acquire_task_lock(name, timeout=60) is True
        assert is_task_locked(name) is True
        assert acquire_task_lock(name, timeout=60) is False
        assert release_task_lock(name) is True
        assert not is_task_locked(name)

    def test_prevent_duplicate_task_decorator_runs_once(self):
        # Decorator prevents concurrent execution; lock is released after run,
        # so two sequential calls both run (no skip).
        name = "test_prevent_dup_run"
        run_count = 0

        @prevent_duplicate_task(name, timeout=60)
        def counted():
            nonlocal run_count
            run_count += 1
            return {"success": True}

        out1 = counted()
        out2 = counted()
        assert run_count == 2
        assert out1 == {"success": True}
        assert out2 == {"success": True}

    def test_prevent_duplicate_task_with_lock_param(self):
        # Same lock_param yields same lock name; sequential calls both run.
        base = "test_prevent_dup_param"

        @prevent_duplicate_task(base, timeout=60, lock_param="x")
        def with_param(x):
            return {"value": x}

        assert with_param(1) == {"value": 1}
        assert with_param(1) == {"value": 1}
        assert with_param(2) == {"value": 2}

    def test_prevent_duplicate_task_skipped_when_lock_held(self):
        # When lock already held (e.g. another worker), call returns skipped.
        name = "test_prevent_dup_held"
        acquire_task_lock(name, timeout=60)
        try:
            run_count = 0

            @prevent_duplicate_task(name, timeout=60)
            def counted():
                nonlocal run_count
                run_count += 1
                return {"success": True}

            out = counted()
            assert run_count == 0
            assert out.get("status") == "skipped"
            assert out.get("reason") in (
                "task_already_running",
                "lock_acquisition_failed",
            )
        finally:
            release_task_lock(name)


class TestTaskLogCollector:
    def test_info_warning_error_and_get_logs(self):
        c = TaskLogCollector(max_records=10)
        c.info("a")
        c.warning("b")
        c.error("c", exception="e1")
        logs = c.get_logs()
        assert len(logs) == 3
        assert logs[0]["level"] == "INFO" and logs[0]["message"] == "a"
        assert logs[1]["level"] == "WARNING"
        assert logs[2]["level"] == "ERROR" and logs[2].get("exception") == "e1"

    def test_get_warnings_and_errors(self):
        c = TaskLogCollector()
        c.info("i")
        c.warning("w")
        c.error("e")
        we = c.get_warnings_and_errors()
        assert len(we) == 2
        assert we[0]["level"] == "WARNING"
        assert we[1]["level"] == "ERROR"

    def test_get_summary(self):
        c = TaskLogCollector()
        c.info("a")
        c.info("b")
        c.warning("w")
        s = c.get_summary()
        assert s["total"] == 3
        assert s["by_level"]["INFO"] == 2
        assert s["by_level"]["WARNING"] == 1

    def test_clear(self):
        c = TaskLogCollector()
        c.info("x")
        c.clear()
        assert c.get_logs() == []

    def test_max_records_caps(self):
        c = TaskLogCollector(max_records=2)
        c.info("1")
        c.info("2")
        c.info("3")
        assert len(c.get_logs()) == 2
        assert c.get_logs()[0]["message"] == "2"
        assert c.get_logs()[1]["message"] == "3"


class TestTaskTrackerAndRegister:
    def test_register_task_execution(self, user, db):
        task_id = "celery-id-001"
        te = register_task_execution(
            task_id=task_id,
            task_name="myapp.tasks.job",
            module="myapp",
            task_kwargs={"a": 1},
            created_by=user,
            metadata={"source": "test"},
        )
        assert te.task_id == task_id
        assert te.task_name == "myapp.tasks.job"
        assert te.module == "myapp"
        assert te.status == TaskStatus.PENDING
        assert te.created_by_id == user.id
        assert te.metadata == {"source": "test"}
        te2 = register_task_execution(
            task_id=task_id,
            task_name="other",
            module="other",
        )
        assert te2.pk == te.pk
        assert te2.task_name == "myapp.tasks.job"

    def test_update_task_status(self, user, db):
        te = register_task_execution(
            task_id="tid-update",
            task_name="t",
            module="m",
            created_by=user,
        )
        updated = TaskTracker.update_task_status(
            te.task_id,
            status=TaskStatus.STARTED,
            metadata={"step": "running"},
        )
        assert updated is not None
        updated.refresh_from_db()
        assert updated.status == TaskStatus.STARTED
        assert updated.started_at is not None
        assert updated.metadata.get("step") == "running"

        TaskTracker.update_task_status(
            te.task_id,
            status=TaskStatus.SUCCESS,
            result={"done": True},
        )
        te.refresh_from_db()
        assert te.status == TaskStatus.SUCCESS
        assert te.finished_at is not None
        assert te.result == {"done": True}

    def test_get_task_not_found(self, db):
        assert TaskTracker.get_task("nonexistent-id", sync=False) is None

    def test_get_task_found(self, user, db):
        register_task_execution(
            task_id="tid-get",
            task_name="t",
            module="m",
            created_by=user,
        )
        found = TaskTracker.get_task("tid-get", sync=False)
        assert found is not None
        assert found.task_id == "tid-get"

    def test_get_task_stats(self, user, db):
        register_task_execution(
            task_id="s1",
            task_name="task_a",
            module="mod1",
            created_by=user,
        )
        register_task_execution(
            task_id="s2",
            task_name="task_a",
            module="mod1",
            created_by=user,
        )
        register_task_execution(
            task_id="s3",
            task_name="task_b",
            module="mod2",
            created_by=user,
        )
        stats = TaskTracker.get_task_stats()
        assert stats["total"] == 3
        assert stats["pending"] == 3
        assert "mod1" in stats["by_module"]
        assert stats["by_module"]["mod1"]["total"] == 2
        assert "task_a" in stats["by_task_name"]
        assert stats["by_task_name"]["task_a"]["total"] == 2

        stats_m1 = TaskTracker.get_task_stats(module="mod1")
        assert stats_m1["total"] == 2

        stats_user = TaskTracker.get_task_stats(created_by=user)
        assert stats_user["total"] == 3

    def test_register_task_execution_with_initial_status_started(
        self, user, db
    ):
        task_id = "celery-id-started"
        te = register_task_execution(
            task_id=task_id,
            task_name="periodic.task",
            module="myapp",
            created_by=user,
            initial_status=TaskStatus.STARTED,
        )
        assert te.status == TaskStatus.STARTED
        assert te.started_at is not None

    def test_update_task_status_not_found_returns_none(self, db):
        out = TaskTracker.update_task_status(
            "nonexistent-task-id",
            status=TaskStatus.SUCCESS,
        )
        assert out is None

    def test_sync_task_from_celery_does_not_override_completed_with_pending(
        self, user, db, monkeypatch
    ):
        register_task_execution(
            task_id="tid-sync-completed",
            task_name="t",
            module="m",
            created_by=user,
        )
        TaskTracker.update_task_status(
            task_id="tid-sync-completed",
            status=TaskStatus.SUCCESS,
            result={"ok": True},
        )

        class FakePendingResult:
            status = "PENDING"
            result = None
            traceback = None

            @staticmethod
            def ready():
                return False

        monkeypatch.setattr(
            task_tracker_svc,
            "AsyncResult",
            lambda _: FakePendingResult(),
        )

        synced = TaskTracker.sync_task_from_celery("tid-sync-completed")
        assert synced is not None
        assert synced.status == TaskStatus.SUCCESS
        synced.refresh_from_db()
        assert synced.status == TaskStatus.SUCCESS

    def test_sync_task_from_celery_updates_pending_to_success(
        self, user, db, monkeypatch
    ):
        register_task_execution(
            task_id="tid-sync-pending",
            task_name="t",
            module="m",
            created_by=user,
        )

        class FakeSuccessResult:
            status = "SUCCESS"
            result = {"count": 1}
            traceback = None

            @staticmethod
            def ready():
                return True

        monkeypatch.setattr(
            task_tracker_svc,
            "AsyncResult",
            lambda _: FakeSuccessResult(),
        )

        synced = TaskTracker.sync_task_from_celery("tid-sync-pending")
        assert synced is not None
        synced.refresh_from_db()
        assert synced.status == TaskStatus.SUCCESS
        assert synced.result == {"count": 1}

    @pytest.mark.parametrize(
        "completed_status",
        [TaskStatus.FAILURE, TaskStatus.REVOKED],
    )
    def test_sync_task_from_celery_keeps_completed_on_pending(
        self,
        user,
        db,
        monkeypatch,
        completed_status,
    ):
        register_task_execution(
            task_id=f"tid-sync-completed-{completed_status.lower()}",
            task_name="t",
            module="m",
            created_by=user,
        )
        TaskTracker.update_task_status(
            task_id=f"tid-sync-completed-{completed_status.lower()}",
            status=completed_status,
            error="done",
        )

        class FakePendingResult:
            status = "PENDING"
            result = None
            traceback = None

            @staticmethod
            def ready():
                return False

        monkeypatch.setattr(
            task_tracker_svc,
            "AsyncResult",
            lambda _: FakePendingResult(),
        )

        task_id = f"tid-sync-completed-{completed_status.lower()}"
        synced = TaskTracker.sync_task_from_celery(task_id)
        assert synced is not None
        synced.refresh_from_db()
        assert synced.status == completed_status

    def test_sync_task_from_celery_failure_uses_celery_traceback_fallback(
        self, user, db, monkeypatch
    ):
        register_task_execution(
            task_id="tid-sync-failure-fallback",
            task_name="t",
            module="m",
            created_by=user,
        )

        class FakeFailureResult:
            status = "FAILURE"
            result = Exception("boom")
            traceback = "celery-traceback-text"

            @staticmethod
            def ready():
                return True

        monkeypatch.setattr(
            task_tracker_svc,
            "AsyncResult",
            lambda _: FakeFailureResult(),
        )

        synced = TaskTracker.sync_task_from_celery("tid-sync-failure-fallback")
        assert synced is not None
        synced.refresh_from_db()
        assert synced.status == TaskStatus.FAILURE
        assert synced.error == "boom"
        assert synced.traceback == "celery-traceback-text"

    def test_sync_task_from_celery_same_status_does_not_overwrite_result(
        self, user, db, monkeypatch
    ):
        register_task_execution(
            task_id="tid-sync-same-status",
            task_name="t",
            module="m",
            created_by=user,
        )
        TaskTracker.update_task_status(
            task_id="tid-sync-same-status",
            status=TaskStatus.SUCCESS,
            result={"from_db": True},
        )

        class FakeSuccessResult:
            status = "SUCCESS"
            result = {"from_celery": True}
            traceback = None

            @staticmethod
            def ready():
                return True

        monkeypatch.setattr(
            task_tracker_svc,
            "AsyncResult",
            lambda _: FakeSuccessResult(),
        )

        synced = TaskTracker.sync_task_from_celery("tid-sync-same-status")
        assert synced is not None
        synced.refresh_from_db()
        assert synced.status == TaskStatus.SUCCESS
        assert synced.result == {"from_db": True}

    def test_get_task_with_sync_refreshes_from_sync_service(
        self, user, db, monkeypatch
    ):
        register_task_execution(
            task_id="tid-get-sync",
            task_name="t",
            module="m",
            created_by=user,
        )

        def fake_sync(task_id):
            TaskTracker.update_task_status(
                task_id=task_id,
                status=TaskStatus.SUCCESS,
                result={"synced": True},
            )
            return TaskTracker.get_task(task_id, sync=False)

        monkeypatch.setattr(
            TaskTracker,
            "sync_task_from_celery",
            staticmethod(fake_sync),
        )

        found = TaskTracker.get_task("tid-get-sync", sync=True)
        assert found is not None
        assert found.status == TaskStatus.SUCCESS
        assert found.result == {"synced": True}

    def test_sync_all_unfinished_executions_counts_only_real_updates(
        self, user, db, monkeypatch
    ):
        register_task_execution(
            task_id="tid-sync-all-pending",
            task_name="t",
            module="m",
            created_by=user,
        )
        register_task_execution(
            task_id="tid-sync-all-to-success",
            task_name="t",
            module="m",
            created_by=user,
            initial_status=TaskStatus.STARTED,
        )
        register_task_execution(
            task_id="tid-sync-all-no-change",
            task_name="t",
            module="m",
            created_by=user,
            initial_status=TaskStatus.STARTED,
        )

        result_map = {
            "tid-sync-all-pending": {
                "status": "PENDING",
                "ready": False,
                "result": None,
                "traceback": None,
            },
            "tid-sync-all-to-success": {
                "status": "SUCCESS",
                "ready": True,
                "result": {"ok": 1},
                "traceback": None,
            },
            "tid-sync-all-no-change": {
                "status": "STARTED",
                "ready": False,
                "result": None,
                "traceback": None,
            },
        }

        class FakeAsyncResult:
            def __init__(self, task_id):
                payload = result_map[task_id]
                self.status = payload["status"]
                self.result = payload["result"]
                self.traceback = payload["traceback"]
                self._ready = payload["ready"]

            def ready(self):
                return self._ready

        monkeypatch.setattr(task_tracker_svc, "AsyncResult", FakeAsyncResult)

        out = TaskTracker.sync_all_unfinished_executions()
        assert out["synced_count"] == 3
        assert out["updated_count"] == 1


class TestConfCrontab:
    def test_is_valid_crontab_expression_valid(self):
        assert is_valid_crontab_expression("0 2 * * *") is True
        assert is_valid_crontab_expression("*/30 * * * *") is True
        assert is_valid_crontab_expression("0 0 1 * *") is True

    def test_is_valid_crontab_expression_invalid(self):
        assert is_valid_crontab_expression("") is False
        assert is_valid_crontab_expression("   ") is False
        assert is_valid_crontab_expression("1 2") is False
        assert is_valid_crontab_expression("0 0 0 0 0") is False


class TestTimeoutService:
    def test_mark_timed_out_executions_invalid_timeout_returns_skipped(self):
        out = mark_timed_out_executions(timeout_minutes=0)
        assert out["updated_count"] == 0
        assert out.get("skipped") is True
        assert out.get("reason") == "invalid_timeout_minutes"

        out_neg = mark_timed_out_executions(timeout_minutes=-1)
        assert out_neg["updated_count"] == 0
        assert out_neg.get("skipped") is True


class TestCleanupService:
    def test_cleanup_old_executions_invalid_retention_returns_skipped(self):
        out = cleanup_old_executions(retention_days=0)
        assert out["deleted_count"] == 0
        assert out.get("skipped") is True
        assert out.get("reason") == "invalid_retention_days"

        out_neg = cleanup_old_executions(retention_days=-1)
        assert out_neg["deleted_count"] == 0
        assert out_neg.get("skipped") is True


class TestTaskConfigService:
    def test_set_and_get_global_task_config(self, db):
        task_config_svc.set_global_task_config("test_key", 42)
        val = task_config_svc.get_global_task_config("test_key")
        assert val == 42

        task_config_svc.set_global_task_config("test_key", {"nested": 1})
        val2 = task_config_svc.get_global_task_config("test_key")
        assert val2 == {"nested": 1}

    def test_get_global_task_config_missing_returns_none(self, db):
        val = task_config_svc.get_global_task_config("nonexistent_key_xyz")
        assert val is None
