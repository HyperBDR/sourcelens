"""
Celery beat task: cleanup old task execution records.
Registered as agentcore_task.adapters.django.tasks.
cleanup_old_task_executions.
"""
import logging
import traceback as tb

from celery import shared_task

from agentcore_task.adapters.django.cleanup import cleanup_old_executions
from agentcore_task.adapters.django.conf import get_cleanup_enabled
from agentcore_task.adapters.django.services.lock import (
    prevent_duplicate_task,
)
from agentcore_task.adapters.django.services.task_tracker import (
    MODULE_AGENTCORE_TASK,
    TASK_CLEANUP,
    TaskTracker,
    register_task_execution,
)
from agentcore_task.constants import TaskStatus

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_CLEANUP = 86400


@shared_task(
    name="agentcore_task.adapters.django.tasks.cleanup_old_task_executions",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 3},
)
@prevent_duplicate_task(
    "cleanup_old_task_executions",
    timeout=LOCK_TIMEOUT_CLEANUP,
)
def cleanup_old_task_executions(
    self, retention_days=None, only_completed=None
):
    """
    Celery task for cleanup. No-op if AGENTCORE_TASK_CLEANUP_ENABLED is False.
    Registers and updates this run in TaskExecution (module=agentcore_task).
    Uses prevent_duplicate_task so only one run executes at a time.
    """
    task_id = self.request.id
    # Register this run of the cleanup task itself (not the records we delete).
    register_task_execution(
        task_id=task_id,
        task_name=TASK_CLEANUP,
        module=MODULE_AGENTCORE_TASK,
        metadata={
            "retention_days": retention_days,
            "only_completed": only_completed,
        },
        initial_status=TaskStatus.STARTED,
    )

    logger.info(f"Starting {TASK_CLEANUP}")
    if not get_cleanup_enabled():
        out = {
            "deleted_count": 0,
            "skipped": True,
            "reason": "cleanup_disabled",
        }
        TaskTracker.update_task_status(task_id, TaskStatus.SUCCESS, result=out)
        logger.info(f"Finished {TASK_CLEANUP} skipped=cleanup_disabled")
        return out

    # Run cleanup then record this run as SUCCESS or FAILURE
    try:
        out = cleanup_old_executions(
            retention_days=retention_days,
            only_completed=only_completed,
        )
        TaskTracker.update_task_status(task_id, TaskStatus.SUCCESS, result=out)
        logger.info(
            f"Finished {TASK_CLEANUP} deleted={out.get('deleted_count', 0)}"
        )
        return out
    except Exception as e:
        logger.error(f"Failed {TASK_CLEANUP}: {e}")
        TaskTracker.update_task_status(
            task_id,
            TaskStatus.FAILURE,
            error=str(e),
            traceback="".join(
                tb.format_exception(type(e), e, e.__traceback__)
            ),
        )
        raise
