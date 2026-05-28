"""
Celery beat task: cleanup old LLM usage and series records.
Uses agentcore_task TaskTracker so runs are recorded in TaskExecution.
"""
import logging
import traceback as tb

from celery import shared_task

from agentcore_metering.adapters.django.cleanup import cleanup_old_llm_usage
from agentcore_metering.adapters.django.conf import get_cleanup_enabled

logger = logging.getLogger(__name__)

TASK_NAME = (
    "agentcore_metering.adapters.django.tasks.cleanup."
    "cleanup_old_llm_usage_task"
)
MODULE_AGENTCORE_METERING = "agentcore_metering"


@shared_task(
    name=TASK_NAME,
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 3},
)
def cleanup_old_llm_usage_task(
    self,
    retention_days=None,
    batch_size=None,
):
    """
    Celery task for cleanup. No-op if cleanup disabled.
    Registers this run in TaskExecution (module=agentcore_metering).
    """
    from agentcore_task.adapters.django.services.task_tracker import (
        TaskTracker,
        register_task_execution,
    )
    from agentcore_task.constants import TaskStatus

    task_id = self.request.id
    register_task_execution(
        task_id=task_id,
        task_name=TASK_NAME,
        module=MODULE_AGENTCORE_METERING,
        metadata={
            "retention_days": retention_days,
            "batch_size": batch_size,
        },
        initial_status=TaskStatus.STARTED,
    )
    logger.info("Starting cleanup_old_llm_usage_task")
    if not get_cleanup_enabled():
        out = {
            "deleted_usage": 0,
            "deleted_series": 0,
            "skipped": True,
            "reason": "cleanup_disabled",
        }
        TaskTracker.update_task_status(
            task_id, TaskStatus.SUCCESS, result=out
        )
        logger.info(
            "Finished cleanup_old_llm_usage_task (skipped: cleanup_disabled)"
        )
        return out
    try:
        out = cleanup_old_llm_usage(
            retention_days=retention_days,
            batch_size=batch_size,
        )
        TaskTracker.update_task_status(
            task_id, TaskStatus.SUCCESS, result=out
        )
        logger.info(
            f"Finished cleanup_old_llm_usage_task "
            f"deleted_usage={out.get('deleted_usage', 0)} "
            f"deleted_series={out.get('deleted_series', 0)}"
        )
        return out
    except Exception as e:
        logger.exception(f"Failed cleanup_old_llm_usage_task: {e}")
        TaskTracker.update_task_status(
            task_id,
            TaskStatus.FAILURE,
            error=str(e),
            traceback="".join(
                tb.format_exception(type(e), e, e.__traceback__)
            ),
        )
        raise
