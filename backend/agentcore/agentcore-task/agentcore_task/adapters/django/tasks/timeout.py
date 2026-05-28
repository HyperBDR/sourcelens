"""
Celery beat task: mark timed-out STARTED tasks as FAILURE.
Registered as agentcore_task.adapters.django.tasks.
mark_timed_out_task_executions.
"""
import logging
import traceback as tb

from celery import shared_task

from agentcore_task.adapters.django.conf import get_mark_timeout_enabled
from agentcore_task.adapters.django.services.lock import (
    prevent_duplicate_task,
)
from agentcore_task.adapters.django.services.task_tracker import (
    MODULE_AGENTCORE_TASK,
    TASK_MARK_TIMEOUT,
    TaskTracker,
    register_task_execution,
)
from agentcore_task.adapters.django.services.timeout import (
    mark_timed_out_executions,
)
from agentcore_task.constants import TaskStatus

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_MARK_TIMEOUT = 3600


@shared_task(
    name="agentcore_task.adapters.django.tasks.mark_timed_out_task_executions",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 3},
)
@prevent_duplicate_task(
    "mark_timed_out_task_executions",
    timeout=LOCK_TIMEOUT_MARK_TIMEOUT,
)
def mark_timed_out_task_executions(self, timeout_minutes=None):
    """
    Celery task: mark STARTED tasks that exceeded timeout as FAILURE.
    No-op if AGENTCORE_TASK_MARK_TIMEOUT_ENABLED is False.
    Registers and updates this run in TaskExecution (module=agentcore_task).
    Uses prevent_duplicate_task so only one run executes at a time.
    """
    task_id = self.request.id
    # Register this run of the timeout checker itself (not the tasks we
    # will mark as timed out).
    register_task_execution(
        task_id=task_id,
        task_name=TASK_MARK_TIMEOUT,
        module=MODULE_AGENTCORE_TASK,
        metadata={"timeout_minutes": timeout_minutes},
        initial_status=TaskStatus.STARTED,
    )

    logger.info(f"Starting {TASK_MARK_TIMEOUT}")
    # Skip if timeout marking is disabled
    if not get_mark_timeout_enabled():
        out = {
            "updated_count": 0,
            "skipped": True,
            "reason": "mark_timeout_disabled",
        }
        TaskTracker.update_task_status(task_id, TaskStatus.SUCCESS, result=out)
        logger.info(
            f"Finished {TASK_MARK_TIMEOUT} skipped=mark_timeout_disabled"
        )
        return out

    # Sync from Celery then mark timed-out STARTED tasks
    try:
        sync_result = TaskTracker.sync_all_unfinished_executions()
        out = mark_timed_out_executions(timeout_minutes=timeout_minutes)
        out["synced_count"] = sync_result.get("synced_count", 0)
        out["synced_updated_count"] = sync_result.get("updated_count", 0)
        TaskTracker.update_task_status(
            task_id, TaskStatus.SUCCESS, result=out
        )
        logger.info(
            f"Finished {TASK_MARK_TIMEOUT} "
            f"synced={out.get('synced_count', 0)} "
            f"timeout_updated={out.get('updated_count', 0)}"
        )
        return out
    except Exception as e:
        # Record this run as FAILURE and re-raise
        logger.error(f"Failed {TASK_MARK_TIMEOUT}: {e}")
        TaskTracker.update_task_status(
            task_id,
            TaskStatus.FAILURE,
            error=str(e),
            traceback="".join(
                tb.format_exception(type(e), e, e.__traceback__)
            ),
        )
        raise
