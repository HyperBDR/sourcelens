"""
Cleanup of old LLM usage and series records.

Uses conf when arguments are omitted. Call directly or via Celery task.
Default retention: 365 days (configurable via MeteringConfig or settings).
"""
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from django.utils import timezone

from agentcore_metering.adapters.django.conf import get_retention_days
from agentcore_metering.adapters.django.models import LLMUsage, LLMUsageSeries

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5000


def cleanup_old_llm_usage(
    retention_days: Optional[int] = None,
    batch_size: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Delete LLMUsage and LLMUsageSeries older than retention_days.

    Returns dict with deleted_usage, deleted_series, cutoff, retention_days.
    """
    if retention_days is None:
        retention_days = get_retention_days()

    if retention_days <= 0:
        logger.warning(
            f"cleanup_old_llm_usage: retention_days={retention_days} <= 0, "
            "skipping"
        )
        return {
            "deleted_usage": 0,
            "deleted_series": 0,
            "cutoff": timezone.now(),
            "retention_days": retention_days,
            "skipped": True,
            "reason": "invalid_retention_days",
        }

    cutoff = timezone.now() - timedelta(days=retention_days)
    batch_size = batch_size or DEFAULT_BATCH_SIZE

    deleted_usage = 0
    if batch_size <= 0:
        deleted_usage, _ = (
            LLMUsage.objects.filter(created_at__lt=cutoff).delete()
        )
    else:
        while True:
            batch = list(
                LLMUsage.objects.filter(created_at__lt=cutoff)
                .values_list("pk", flat=True)[:batch_size]
            )
            if not batch:
                break
            n, _ = LLMUsage.objects.filter(pk__in=batch).delete()
            deleted_usage += n

    deleted_series = 0
    if batch_size <= 0:
        deleted_series, _ = (
            LLMUsageSeries.objects.filter(bucket__lt=cutoff).delete()
        )
    else:
        while True:
            batch = list(
                LLMUsageSeries.objects.filter(bucket__lt=cutoff)
                .values_list("pk", flat=True)[:batch_size]
            )
            if not batch:
                break
            n, _ = LLMUsageSeries.objects.filter(pk__in=batch).delete()
            deleted_series += n

    logger.info(
        f"cleanup_old_llm_usage: deleted_usage={deleted_usage} "
        f"deleted_series={deleted_series} retention_days={retention_days}"
    )
    return {
        "deleted_usage": deleted_usage,
        "deleted_series": deleted_series,
        "cutoff": cutoff,
        "retention_days": retention_days,
    }
