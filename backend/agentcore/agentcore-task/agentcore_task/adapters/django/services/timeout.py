"""
Mark STARTED task executions as FAILURE when they exceed timeout.

Single source of truth for timeout-based failure. Uses global config (conf)
when timeout_minutes is omitted. Call directly or via the Celery task in
adapters.django.tasks (mark_timed_out_task_executions).
"""
from datetime import timedelta
import logging
from typing import Any, Dict, Optional

from django.utils import timezone

from agentcore_task.adapters.django.conf import get_task_timeout_minutes
from agentcore_task.adapters.django.models import TaskExecution
from agentcore_task.constants import TaskStatus

logger = logging.getLogger(__name__)


def mark_timed_out_executions(
    timeout_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Mark task executions that are STARTED and have run longer than
    timeout_minutes as FAILURE (task timeout).

    Uses global config when timeout_minutes is None (TaskConfig or settings).

    Args:
        timeout_minutes: Treat STARTED tasks with started_at older than
            this many minutes as timed out. Must be > 0.

    Returns:
        Dict: updated_count, timeout_minutes, cutoff.
    """
    if timeout_minutes is None:
        timeout_minutes = get_task_timeout_minutes()

    if timeout_minutes <= 0:
        logger.warning(
            f"mark_timed_out_executions: timeout_minutes={timeout_minutes} "
            f"<= 0, skipping"
        )
        now = timezone.now()
        cutoff_str = (
            now.isoformat() if hasattr(now, "isoformat") else str(now)
        )
        return {
            "updated_count": 0,
            "timeout_minutes": timeout_minutes,
            "cutoff": cutoff_str,
            "skipped": True,
            "reason": "invalid_timeout_minutes",
        }

    cutoff = timezone.now() - timedelta(minutes=timeout_minutes)
    error_msg = (
        f"Task timeout (exceeded {timeout_minutes} minutes, "
        f"started before {cutoff!s})"
    )

    qs = TaskExecution.objects.filter(
        status=TaskStatus.STARTED,
        started_at__isnull=False,
        started_at__lt=cutoff,
    )
    updated_count = qs.update(
        status=TaskStatus.FAILURE,
        error=error_msg,
        finished_at=timezone.now(),
    )

    if updated_count:
        logger.info(
            f"mark_timed_out_executions: updated={updated_count} "
            f"timeout_minutes={timeout_minutes} cutoff={cutoff!s}"
        )
    cutoff_str = (
        cutoff.isoformat() if hasattr(cutoff, "isoformat") else str(cutoff)
    )
    return {
        "updated_count": updated_count,
        "timeout_minutes": timeout_minutes,
        "cutoff": cutoff_str,
    }
