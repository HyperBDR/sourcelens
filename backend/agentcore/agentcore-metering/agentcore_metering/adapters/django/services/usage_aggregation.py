"""
LLM usage aggregation for admin cost analysis (summary, by_model, time series).

TIME_ZONE is UTC; date ranges and bucket values are in UTC. Frontend converts.
"""
from datetime import date, datetime, timedelta, timezone as utc_tz
from typing import Any, Optional

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate, TruncHour, TruncMonth
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from agentcore_metering.adapters.django.models import LLMUsage


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = parse_datetime(value)
        if dt:
            return _ensure_aware_datetime(dt)
        return _ensure_aware_datetime(
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        )
    except (ValueError, TypeError):
        return None


def _ensure_aware_datetime(dt: datetime) -> datetime:
    """Normalize to timezone-aware UTC for query range."""
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, utc_tz.utc)
    return dt.astimezone(utc_tz.utc)


def _bucket_key_for_fill(
    bucket: date | datetime | None,
    granularity: str,
) -> str | None:
    """
    Normalize bucket to a string key for fill lookup so DB and expected match.

    We build by_bucket from DB rows and look up by the key from
    _build_expected_buckets. If the two sides use different string formats,
    by_bucket.get(bucket_str) returns None and that bucket is filled with
    zeros, so the whole series can appear as zero.

    Typical scenario (SQLite): the DB returns naive datetime from
    TruncHour/TruncMonth so r["bucket"].isoformat() is "2026-02-21T03:00:00"
    (no timezone). Our expected buckets are timezone-aware UTC, so
    bucket.isoformat() is "2026-02-21T03:00:00+00:00". The strings differ and
    the lookup fails. PostgreSQL with USE_TZ=True usually returns aware
    datetimes so keys may match without this, but normalization keeps behavior
    consistent across backends.

    Other cases: TruncDate (month granularity) may return a date while we
    generate datetime; or microsecond/format differences. This function
    unifies to the same key shape per granularity (hour -> aware UTC no
    microsecond; month -> date iso; year -> first-of-month aware UTC).
    """
    if bucket is None:
        return None
    if granularity == "month":
        d = bucket.date() if isinstance(bucket, datetime) else bucket
        return d.isoformat()
    if granularity == "year":
        if isinstance(bucket, datetime):
            dt = _ensure_aware_datetime(bucket)
        else:
            dt = datetime(
                bucket.year, bucket.month, 1,
                tzinfo=utc_tz.utc,
            )
        dt = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return dt.isoformat()
    if isinstance(bucket, datetime):
        dt = _ensure_aware_datetime(bucket)
    else:
        dt = datetime.combine(
            bucket, datetime.min.time()
        ).replace(tzinfo=utc_tz.utc)
    dt = dt.replace(microsecond=0)
    return dt.isoformat()


def _parse_end_date(value: Optional[str]) -> Optional[datetime]:
    """
    Parse end_date; if value is date-only (no time part), return end of that
    day so that the whole day is included in range filters.
    """
    dt = _parse_date(value)
    if dt is None:
        return None
    value = (value or "").strip()
    if "T" not in value and " " not in value and len(value) <= 10:
        return dt.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
    return dt


def get_summary_stats(start_date=None, end_date=None, user_id=None):
    """
    Return aggregate token and cost stats for the given date range and user.

    Optional filters: start_date, end_date (timezone-aware), user_id.
    Returns dict with total_* tokens, total_calls, successful_calls,
    failed_calls, total_cost, total_cost_currency.
    """
    qs = LLMUsage.objects.all()
    if user_id:
        qs = qs.filter(user_id=user_id)
    if start_date:
        qs = qs.filter(created_at__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__lte=end_date)
    agg = qs.aggregate(
        total_calls=Count("id"),
        total_prompt_tokens=Sum("prompt_tokens"),
        total_completion_tokens=Sum("completion_tokens"),
        total_tokens=Sum("total_tokens"),
        total_cached_tokens=Sum("cached_tokens"),
        total_reasoning_tokens=Sum("reasoning_tokens"),
        total_cost=Sum("cost"),
        successful_calls=Count("id", filter=Q(success=True)),
        failed_calls=Count("id", filter=Q(success=False)),
    )
    total_cost = agg.get("total_cost")
    if total_cost is not None:
        total_cost = float(total_cost)
    else:
        total_cost = 0
    return {
        "total_prompt_tokens": agg["total_prompt_tokens"] or 0,
        "total_completion_tokens": agg["total_completion_tokens"] or 0,
        "total_tokens": agg["total_tokens"] or 0,
        "total_cached_tokens": agg["total_cached_tokens"] or 0,
        "total_reasoning_tokens": agg["total_reasoning_tokens"] or 0,
        "total_cost": total_cost,
        "total_cost_currency": "USD",
        "total_calls": agg["total_calls"] or 0,
        "successful_calls": agg["successful_calls"] or 0,
        "failed_calls": agg["failed_calls"] or 0,
    }


def get_stats_by_model(start_date=None, end_date=None, user_id=None):
    """
    Return per-model aggregate stats (calls, tokens, cost) for the given range.

    Optional filters: start_date, end_date, user_id.
    Ordered by total_tokens desc.
    """
    qs = LLMUsage.objects.values("model").annotate(
        total_calls=Count("id"),
        total_prompt_tokens=Sum("prompt_tokens"),
        total_completion_tokens=Sum("completion_tokens"),
        total_tokens=Sum("total_tokens"),
        total_cached_tokens=Sum("cached_tokens"),
        total_reasoning_tokens=Sum("reasoning_tokens"),
        total_cost=Sum("cost"),
    ).order_by("-total_tokens")
    if user_id:
        qs = qs.filter(user_id=user_id)
    if start_date:
        qs = qs.filter(created_at__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__lte=end_date)
    return list(qs)


def get_time_series_stats(
    granularity: str,
    start_date=None,
    end_date=None,
    user_id=None,
):
    """
    Returns time-series token usage points for charting.

    Supported granularity:
    - day: points bucketed by hour
    - month: points bucketed by day
    - year: points bucketed by month
    """
    granularity = (granularity or "").strip().lower()
    if granularity == "day":
        trunc = TruncHour("created_at")
    elif granularity == "month":
        trunc = TruncDate("created_at")
    elif granularity == "year":
        trunc = TruncMonth("created_at")
    else:
        raise ValueError(
            "Unsupported granularity. Use one of: day, month, year."
        )

    qs = (
        LLMUsage.objects.annotate(bucket=trunc)
        .values("bucket")
        .annotate(
            total_calls=Count("id"),
            total_prompt_tokens=Sum("prompt_tokens"),
            total_completion_tokens=Sum("completion_tokens"),
            total_tokens=Sum("total_tokens"),
            total_cached_tokens=Sum("cached_tokens"),
            total_reasoning_tokens=Sum("reasoning_tokens"),
            total_cost=Sum("cost"),
        )
        .order_by("bucket")
    )
    if user_id:
        qs = qs.filter(user_id=user_id)
    if start_date:
        qs = qs.filter(created_at__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__lte=end_date)

    def _row(i):
        bucket = i["bucket"]
        bucket_str = bucket.isoformat() if bucket is not None else None
        cost = i.get("total_cost")
        cost = float(cost) if cost is not None else 0
        return {
            "bucket": bucket_str,
            "total_calls": i["total_calls"],
            "total_prompt_tokens": i["total_prompt_tokens"] or 0,
            "total_completion_tokens": i["total_completion_tokens"] or 0,
            "total_tokens": i["total_tokens"] or 0,
            "total_cached_tokens": i["total_cached_tokens"] or 0,
            "total_reasoning_tokens": i["total_reasoning_tokens"] or 0,
            "total_cost": cost,
        }

    rows_list = list(qs)
    rows = [_row(r) for r in rows_list]
    if not start_date or not end_date:
        return rows

    filled = []
    by_bucket = {
        _bucket_key_for_fill(r["bucket"], granularity): _row(r)
        for r in rows_list
    }
    for bucket in _build_expected_buckets(
        granularity=granularity,
        start_date=start_date,
        end_date=end_date,
    ):
        bucket_str = _bucket_key_for_fill(bucket, granularity)
        filled.append(
            by_bucket.get(bucket_str)
            or {
                "bucket": bucket_str,
                "total_calls": 0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "total_cached_tokens": 0,
                "total_reasoning_tokens": 0,
                "total_cost": 0,
            }
        )
    return filled


def _build_expected_buckets(
    granularity: str,
    start_date: datetime,
    end_date: datetime,
) -> list[date | datetime]:
    """
    Build ordered bucket values for fill. Return type matches the annotation:
    day -> datetime (TruncHour), month -> date (TruncDate),
    year -> datetime first-of-month (TruncMonth).
    """
    if granularity == "day":
        return _hour_buckets(start_date, end_date)
    if granularity == "month":
        return _day_buckets(start_date, end_date)
    if granularity == "year":
        return _month_buckets(start_date, end_date)
    return []


def _hour_buckets(start_date: datetime, end_date: datetime) -> list[datetime]:
    start_date = _ensure_aware_datetime(start_date)
    end_date = _ensure_aware_datetime(end_date)
    current = start_date.replace(minute=0, second=0, microsecond=0)
    end = end_date.replace(minute=0, second=0, microsecond=0)
    out = []
    while current <= end:
        out.append(current)
        current = current + timedelta(hours=1)
    return out


def _day_buckets(start_date: datetime, end_date: datetime) -> list[date]:
    current = start_date.date()
    end = end_date.date()
    out = []
    while current <= end:
        out.append(current)
        current = current + timedelta(days=1)
    return out


def _month_buckets(start_date: datetime, end_date: datetime) -> list[datetime]:
    start_date = _ensure_aware_datetime(start_date)
    end_year = end_date.year
    end_month = end_date.month
    end = datetime(
        end_year, end_month, 1,
        hour=0, minute=0, second=0, microsecond=0,
        tzinfo=utc_tz.utc,
    )
    current = start_date.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    out = []
    while current <= end:
        out.append(current)
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return out


def get_token_stats_from_query(params: Any) -> dict:
    """
    Build token stats dict from query params (e.g. request.query_params).
    Raises ValueError for unsupported granularity.
    When use_series=1 and granularity and date range are set, also returns
    series_by_model from the pre-aggregated LLMUsageSeries table.
    """
    # NOTE(Ray): Lazy import to avoid circular import (usage_chart_series
    # imports usage_aggregation._ensure_aware_datetime).
    from agentcore_metering.adapters.django.services import (
        usage_chart_series,
    )

    start_date = _parse_date(params.get("start_date"))
    end_date = _parse_end_date(params.get("end_date"))
    user_id = params.get("user_id") or None
    if user_id is not None and str(user_id).strip() == "":
        user_id = None
    granularity = params.get("granularity")
    use_series = (
        str(params.get("use_series") or "").strip() in ("1", "true", "yes")
    )

    summary = get_summary_stats(
        start_date=start_date, end_date=end_date, user_id=user_id
    )
    by_model = get_stats_by_model(
        start_date=start_date, end_date=end_date, user_id=user_id
    )
    for i in by_model:
        cost = i.get("total_cost")
        i["total_cost"] = float(cost) if cost is not None else 0
        i["total_cost_currency"] = "USD"
    series = None
    expected_buckets = None
    if granularity and start_date and end_date:
        expected_buckets = [
            b.isoformat() if b is not None else None
            for b in _build_expected_buckets(
                granularity=granularity,
                start_date=start_date,
                end_date=end_date,
            )
        ]
    if granularity:
        series_items = get_time_series_stats(
            granularity=granularity,
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
        )
        series = {
            "granularity": (granularity or "").strip().lower(),
            "items": series_items,
        }
    result = {
        "summary": summary,
        "by_model": by_model,
        "series": series,
        "expected_buckets": expected_buckets,
    }
    if use_series and granularity and start_date and end_date:
        try:
            result["series_by_model"] = (
                usage_chart_series.get_series_for_charts_with_fallback(
                    granularity=granularity,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            series_total_calls = sum(
                r.get("call_count") or 0 for r in result["series_by_model"]
            )
            if (
                summary["total_calls"] > 0
                and series_total_calls < summary["total_calls"] * 0.5
            ):
                series_gran = (
                    usage_chart_series.VIEW_TO_SERIES_GRANULARITY.get(
                        (granularity or "").strip().lower()
                    )
                )
                if series_gran:
                    result["series_by_model"] = (
                        usage_chart_series._compute_series_from_usage(
                            granularity=series_gran,
                            start_date=start_date,
                            end_date=end_date,
                        )
                    )
        except ValueError:
            result["series_by_model"] = []
    return result
