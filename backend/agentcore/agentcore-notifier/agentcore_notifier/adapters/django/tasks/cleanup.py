"""
Celery beat task: cleanup old notification records.
Uses agentcore_task lock and TaskExecution so runs are serialized and recorded.
"""
import logging
import traceback as tb

from celery import shared_task

from agentcore_notifier.adapters.django.cleanup import (
    cleanup_old_notification_records,
)
from agentcore_notifier.adapters.django.conf import get_cleanup_enabled

logger = logging.getLogger(__name__)

_TASK_NAME = (
    "agentcore_notifier.adapters.django.tasks.cleanup."
    "cleanup_old_notification_records_task"
)

MODULE_AGENTCORE_NOTIFIER = "agentcore_notifier"
TASK_CLEANUP_NOTIFIER = "cleanup_old_notification_records"
LOCK_TIMEOUT_CLEANUP = 86400


def _register_and_run():
    """
    Import task lock and tracker from agentcore_task when defining the task.
    Notifier depends on agentcore-task for lock and TaskExecution recording.
    """
    # NOTE(Ray): Import at runtime to avoid import-time dep on agentcore_task.
    from agentcore_task.adapters.django.services.lock import (
        prevent_duplicate_task,
    )
    from agentcore_task.adapters.django.services.task_tracker import (
        TaskTracker,
        register_task_execution,
    )
    from agentcore_task.constants import TaskStatus

    @shared_task(
        name=_TASK_NAME,
        bind=True,
        autoretry_for=(Exception,),
        retry_backoff=True,
        retry_backoff_max=600,
        retry_kwargs={"max_retries": 3},
    )
    @prevent_duplicate_task(
        TASK_CLEANUP_NOTIFIER,
        timeout=LOCK_TIMEOUT_CLEANUP,
    )
    def cleanup_old_notification_records_task(
        self, retention_days=None, only_completed=None, batch_size=None
    ):
        """
        Celery task for cleanup. No-op if cleanup disabled.
        Registers this run in TaskExecution (module=agentcore_notifier) and
        uses prevent_duplicate_task so only one run executes at a time.
        """
        task_id = self.request.id
        register_task_execution(
            task_id=task_id,
            task_name=TASK_CLEANUP_NOTIFIER,
            module=MODULE_AGENTCORE_NOTIFIER,
            metadata={
                "retention_days": retention_days,
                "only_completed": only_completed,
                "batch_size": batch_size,
            },
            initial_status=TaskStatus.STARTED,
        )
        logger.info(f"Starting {TASK_CLEANUP_NOTIFIER}")
        if not get_cleanup_enabled():
            out = {
                "deleted_count": 0,
                "skipped": True,
                "reason": "cleanup_disabled",
            }
            TaskTracker.update_task_status(
                task_id, TaskStatus.SUCCESS, result=out
            )
            logger.info(
                f"Finished {TASK_CLEANUP_NOTIFIER} skipped=cleanup_disabled"
            )
            return out
        try:
            out = cleanup_old_notification_records(
                retention_days=retention_days,
                only_completed=only_completed,
                batch_size=batch_size,
            )
            TaskTracker.update_task_status(
                task_id, TaskStatus.SUCCESS, result=out
            )
            logger.info(
                f"Finished {TASK_CLEANUP_NOTIFIER} "
                f"deleted={out.get('deleted_count', 0)}"
            )
            return out
        except Exception as e:
            logger.error(f"Failed {TASK_CLEANUP_NOTIFIER}: {e}")
            TaskTracker.update_task_status(
                task_id,
                TaskStatus.FAILURE,
                error=str(e),
                traceback="".join(
                    tb.format_exception(type(e), e, e.__traceback__)
                ),
            )
            raise

    return cleanup_old_notification_records_task


cleanup_old_notification_records_task = _register_and_run()
