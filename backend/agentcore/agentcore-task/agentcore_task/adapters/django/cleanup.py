"""
Cleanup of old task execution records.

Single source of truth for retention-based cleanup. Uses global config (conf)
when arguments are omitted. Call directly or via the Celery task in
adapters.django.tasks (cleanup_old_task_executions).
"""
from datetime import timedelta
import logging
from typing import Any, Dict, Optional

from django.utils import timezone

from agentcore_task.adapters.django.conf import (
    get_cleanup_only_completed,
    get_retention_days,
)
from agentcore_task.adapters.django.models import TaskExecution
from agentcore_task.constants import TaskStatus

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5000


def cleanup_old_executions(
    retention_days: Optional[int] = None,
    only_completed: Optional[bool] = None,
    batch_size: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Delete task execution records older than retention_days.

    Uses global config when retention_days or only_completed is None.
    When batch_size is set, deletes in chunks to avoid long transactions.

    Args:
        retention_days: Delete records with created_at older than this
            many days.
        only_completed: If True, only delete SUCCESS/FAILURE/REVOKED.
        batch_size: If set, delete in batches; otherwise one query.

    Returns:
        Dict: deleted_count, cutoff, retention_days, only_completed.
    """
    # Resolve params from config when omitted
    if retention_days is None:
        retention_days = get_retention_days()
    if only_completed is None:
        only_completed = get_cleanup_only_completed()

    if retention_days <= 0:
        logger.warning(
            f"cleanup_old_executions: retention_days={retention_days} <= 0, "
            "skipping"
        )
        return {
            "deleted_count": 0,
            "cutoff": timezone.now(),
            "retention_days": retention_days,
            "only_completed": only_completed,
            "skipped": True,
            "reason": "invalid_retention_days",
        }

    # Build queryset: older than cutoff, optionally completed-only
    cutoff = timezone.now() - timedelta(days=retention_days)
    base_qs = TaskExecution.objects.filter(created_at__lt=cutoff)
    if only_completed:
        base_qs = base_qs.filter(
            status__in=TaskStatus.get_completed_statuses()
        )

    # Delete in one go or in batches
    if batch_size is None or batch_size <= 0:
        deleted_count, _ = base_qs.delete()
        total_deleted = deleted_count
    else:
        total_deleted = 0
        while True:
            batch = list(
                base_qs.values_list("pk", flat=True)[:batch_size]
            )
            if not batch:
                break
            batch_deleted, _ = TaskExecution.objects.filter(
                pk__in=batch
            ).delete()
            total_deleted += batch_deleted

    logger.info(
        f"cleanup_old_executions: deleted={total_deleted} retention_days="
        f"{retention_days} only_completed={only_completed} cutoff={cutoff!s}"
    )
    return {
        "deleted_count": total_deleted,
        "cutoff": cutoff,
        "retention_days": retention_days,
        "only_completed": only_completed,
    }
