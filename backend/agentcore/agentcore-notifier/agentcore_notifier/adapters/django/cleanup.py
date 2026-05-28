"""
Cleanup of old notification records.
Uses conf when arguments are omitted. Call directly or via Celery task.
"""
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from django.utils import timezone

from agentcore_notifier.adapters.django.conf import (
    get_cleanup_only_completed,
    get_retention_days,
)
from agentcore_notifier.adapters.django.models import NotificationRecord
from agentcore_notifier.constants import Status

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5000


def cleanup_old_notification_records(
    retention_days: Optional[int] = None,
    only_completed: Optional[bool] = None,
    batch_size: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Delete notification records older than retention_days.
    only_completed=True: only delete status in (success, failed).
    """
    if retention_days is None:
        retention_days = get_retention_days()
    if only_completed is None:
        only_completed = get_cleanup_only_completed()

    if retention_days <= 0:
        logger.warning(
            f"cleanup_old_notification_records: retention_days="
            f"{retention_days} <= 0, skipping"
        )
        return {
            "deleted_count": 0,
            "cutoff": timezone.now(),
            "retention_days": retention_days,
            "only_completed": only_completed,
            "skipped": True,
            "reason": "invalid_retention_days",
        }

    cutoff = timezone.now() - timedelta(days=retention_days)
    base_qs = NotificationRecord.objects.filter(created_at__lt=cutoff)
    if only_completed:
        base_qs = base_qs.filter(status__in=(Status.SUCCESS, Status.FAILED))

    # Delete in one go or in batches
    if batch_size is None or batch_size <= 0:
        deleted_count, _ = base_qs.delete()
        total_deleted = deleted_count
    else:
        total_deleted = 0
        while True:
            batch = list(base_qs.values_list("pk", flat=True)[:batch_size])
            if not batch:
                break
            batch_deleted, _ = (
                NotificationRecord.objects.filter(pk__in=batch).delete()
            )
            total_deleted += batch_deleted

    logger.info(
        f"cleanup_old_notification_records: deleted={total_deleted} "
        f"retention_days={retention_days} only_completed={only_completed}"
    )
    return {
        "deleted_count": total_deleted,
        "cutoff": cutoff,
        "retention_days": retention_days,
        "only_completed": only_completed,
    }
