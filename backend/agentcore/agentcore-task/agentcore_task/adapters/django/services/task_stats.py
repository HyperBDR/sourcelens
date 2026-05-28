"""
Task execution: stats (aggregate) and query detail (list) API.

- Stats: get_task_stats() — aggregate counts by status, module, task_name;
  optional series (day=24h, month=30d, year=12mo) with fixed buckets, fill 0.
- Query detail: list_task_executions() — list executions with filters for
  list/my_tasks endpoints; single-task detail remains
  TaskTracker.get_task(task_id, sync=...).
"""
from datetime import datetime, timedelta, timezone as utc_tz
from typing import Any, Dict, List, Optional

from django.db.models import Count
from django.db.models.functions import ExtractHour, ExtractMonth, TruncDate
from django.utils import timezone

from agentcore_task.adapters.django.models import TaskExecution
from agentcore_task.constants import TaskStatus


def _counts_for_queryset(qs) -> Dict[str, int]:
    """
    Return dict of status counts for a TaskExecution queryset.

    Keys: total, pending, started, success, failure, retry, revoked.
    Used by get_task_stats and internal stats by_module / by_task_name.
    """
    # Aggregate counts per status
    return {
        "total": qs.count(),
        "pending": qs.filter(status=TaskStatus.PENDING).count(),
        "started": qs.filter(status=TaskStatus.STARTED).count(),
        "success": qs.filter(status=TaskStatus.SUCCESS).count(),
        "failure": qs.filter(status=TaskStatus.FAILURE).count(),
        "retry": qs.filter(status=TaskStatus.RETRY).count(),
        "revoked": qs.filter(status=TaskStatus.REVOKED).count(),
    }


def _stats_by_module_and_task_name(queryset):
    """
    Build by_module and by_task_name dicts from queryset.

    Each key (module or task_name) maps to a count dict from
    _counts_for_queryset for the filtered subset.
    """
    by_module = {}
    # Group counts by module
    for mod in queryset.values_list("module", flat=True).distinct():
        q = queryset.filter(module=mod)
        by_module[mod] = _counts_for_queryset(q)
    by_task_name = {}
    # Group counts by task_name
    for name in queryset.values_list("task_name", flat=True).distinct():
        q = queryset.filter(task_name=name)
        by_task_name[name] = _counts_for_queryset(q)
    return by_module, by_task_name


def _parse_date(value: Optional[str]):
    """Parse YYYY-MM-DD to timezone-aware (UTC) start-of-day datetime."""
    if not value:
        return None
    try:
        dt = datetime.strptime(value.strip()[:10], "%Y-%m-%d")
        return timezone.make_aware(dt, utc_tz.utc)
    except (ValueError, TypeError):
        return None


def _parse_end_date(value: Optional[str]):
    """Parse YYYY-MM-DD to timezone-aware end-of-day datetime."""
    dt = _parse_date(value)
    if dt is None:
        return None
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)


def _build_task_series(
    qs,
    granularity: str,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
) -> List[Dict[str, Any]]:
    """
    Build series with fixed buckets; fill 0 for missing.
    day -> 24 hours; month -> 30 days; year -> 12 months.
    """
    if not start_date and end_date:
        start_date = end_date
    if not end_date and start_date:
        end_date = start_date
    if not end_date:
        end_date = timezone.now()
    if not start_date:
        start_date = end_date

    if granularity == "day":
        day_start = start_date.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        if timezone.is_naive(day_start):
            day_start = timezone.make_aware(day_start, utc_tz.utc)
        hour_counts = dict(
            qs.filter(
                created_at__gte=day_start,
                created_at__lt=day_start + timedelta(days=1),
            )
            .annotate(hour=ExtractHour("created_at"))
            .values("hour")
            .annotate(count=Count("id"))
            .values_list("hour", "count")
        )
        return [
            {"bucket": f"{h:02d}:00", "count": hour_counts.get(h, 0)}
            for h in range(24)
        ]

    if granularity == "month":
        end_d = end_date.date() if hasattr(end_date, "date") else end_date
        start_d = end_d - timedelta(days=29)
        day_list = [start_d + timedelta(days=i) for i in range(30)]
        rows = list(
            qs.annotate(d=TruncDate("created_at"))
            .values("d")
            .annotate(count=Count("id"))
            .values_list("d", "count")
        )
        date_counts = {}
        for d_val, cnt in rows:
            if d_val is None:
                continue
            d_date = d_val.date() if hasattr(d_val, "date") else d_val
            date_counts[d_date] = cnt
        return [
            {"bucket": d.isoformat(), "count": date_counts.get(d, 0)}
            for d in day_list
        ]

    if granularity == "year":
        year = (
            end_date.year
            if hasattr(end_date, "year")
            else timezone.now().year
        )
        month_counts = dict(
            qs.annotate(month=ExtractMonth("created_at"))
            .values("month")
            .annotate(count=Count("id"))
            .values_list("month", "count")
        )
        month_labels = [
            "01", "02", "03", "04", "05", "06",
            "07", "08", "09", "10", "11", "12",
        ]
        return [
            {
                "bucket": f"{year}-{month_labels[m-1]}",
                "count": month_counts.get(m, 0),
            }
            for m in range(1, 13)
        ]

    return []


def get_task_stats(
    module: Optional[str] = None,
    task_name: Optional[str] = None,
    created_by=None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    granularity: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Aggregate counts by status and by module/task_name.

    Optional filters: module, task_name, created_by, start_date, end_date
    (YYYY-MM-DD; filter by created_at date). Returns total and per-status
    counts plus by_module and by_task_name breakdowns.
    When granularity is day/month/year, adds series (24h/30d/12mo) with fill 0.
    """
    queryset = TaskExecution.objects.all()
    if module:
        queryset = queryset.filter(module=module)
    if task_name:
        queryset = queryset.filter(task_name=task_name)
    if created_by is not None:
        queryset = queryset.filter(created_by=created_by)
    if start_date:
        queryset = queryset.filter(created_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(created_at__date__lte=end_date)

    summary = _counts_for_queryset(queryset)
    by_module, by_task_name = _stats_by_module_and_task_name(queryset)
    result = {
        **summary,
        "by_module": by_module,
        "by_task_name": by_task_name,
    }

    g = (granularity or "").strip().lower()
    if g in ("day", "month", "year"):
        start_dt = _parse_date(start_date)
        end_dt = _parse_end_date(end_date)
        result["series"] = _build_task_series(queryset, g, start_dt, end_dt)

    return result


def list_task_executions(
    *,
    module: Optional[str] = None,
    task_name: Optional[str] = None,
    status: Optional[str] = None,
    created_by=None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: Optional[str] = None,
    config_platform: Optional[str] = None,
    config_key: Optional[str] = None,
    order_by: str = "-created_at",
):
    """
    Query task execution list (query detail API).

    Optional filters: module, task_name, status, created_by, start_date,
    end_date, search (task_name icontains), config_platform (exact on
    metadata.config_platform), config_key (icontains on metadata.config_key).
    Returns a QuerySet with select_related("created_by") for list/detail
    views; caller may paginate or slice.
    """
    queryset = TaskExecution.objects.select_related("created_by").all()
    # Apply optional filters
    if module:
        queryset = queryset.filter(module=module)
    if task_name:
        queryset = queryset.filter(task_name=task_name)
    if status:
        queryset = queryset.filter(status=status)
    if created_by is not None:
        queryset = queryset.filter(created_by=created_by)
    if start_date:
        queryset = queryset.filter(created_at__gte=start_date)
    if end_date:
        queryset = queryset.filter(created_at__lte=end_date)
    if search and search.strip():
        queryset = queryset.filter(task_name__icontains=search.strip())
    if config_platform and config_platform.strip():
        queryset = queryset.filter(
            metadata__config_platform=config_platform.strip()
        )
    if config_key and config_key.strip():
        queryset = queryset.filter(
            metadata__config_key__icontains=config_key.strip()
        )
    return queryset.order_by(order_by)
