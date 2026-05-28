"""
Pre-aggregated LLM usage series for chart API (by-model curves).

Granularity: hour (day view), day (month view), month (year view).
"""
import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db import transaction

from agentcore_metering.adapters.django.models import LLMUsage, LLMUsageSeries
from agentcore_metering.adapters.django.services.usage_aggregation import (
    _ensure_aware_datetime,
)

logger = logging.getLogger(__name__)

SERIES_GRANULARITY_HOUR = "hour"
SERIES_GRANULARITY_DAY = "day"
SERIES_GRANULARITY_MONTH = "month"

VIEW_TO_SERIES_GRANULARITY = {
    "day": SERIES_GRANULARITY_HOUR,
    "month": SERIES_GRANULARITY_DAY,
    "year": SERIES_GRANULARITY_MONTH,
}


def _truncate_bucket(dt: datetime, granularity: str) -> datetime:
    dt = _ensure_aware_datetime(dt)
    if granularity == SERIES_GRANULARITY_HOUR:
        return dt.replace(minute=0, second=0, microsecond=0)
    if granularity == SERIES_GRANULARITY_DAY:
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == SERIES_GRANULARITY_MONTH:
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return dt


def aggregate_usage_to_series(
    granularity: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> int:
    """
    Aggregate LLMUsage into LLMUsageSeries for the given granularity and range.

    Series is global (no per-user); granularity: hour, day, or month.
    Returns number of (bucket, model) rows upserted.
    """
    if granularity not in (
        SERIES_GRANULARITY_HOUR,
        SERIES_GRANULARITY_DAY,
        SERIES_GRANULARITY_MONTH,
    ):
        raise ValueError(
            f"granularity must be one of: hour, day, month; "
            f"got {granularity!r}"
        )
    start_date = _ensure_aware_datetime(start_date) if start_date else None
    end_date = _ensure_aware_datetime(end_date) if end_date else None
    if not start_date or not end_date:
        raise ValueError("start_date and end_date are required")

    qs = LLMUsage.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date,
    ).only(
        "created_at",
        "started_at",
        "first_chunk_at",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cached_tokens",
        "reasoning_tokens",
        "cost",
        "cost_currency",
        "success",
        "is_streaming",
    )
    groups: Dict[tuple, Dict[str, Any]] = defaultdict(
        lambda: {
            "e2e_secs": [],
            "ttft_secs": [],
            "output_tps_list": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
            "cost": Decimal("0"),
            "cost_currency": "USD",
            "call_count": 0,
            "success_count": 0,
        }
    )

    for row in qs.iterator(chunk_size=2000):
        bucket = _truncate_bucket(row.created_at, granularity)
        key = (bucket, row.model or "")
        g = groups[key]
        g["call_count"] += 1
        if row.success:
            g["success_count"] += 1
        g["prompt_tokens"] += row.prompt_tokens or 0
        g["completion_tokens"] += row.completion_tokens or 0
        g["total_tokens"] += row.total_tokens or 0
        g["cached_tokens"] += row.cached_tokens or 0
        g["reasoning_tokens"] += row.reasoning_tokens or 0
        if row.cost is not None:
            g["cost"] += row.cost
        if row.cost_currency:
            g["cost_currency"] = row.cost_currency

        e2e_sec = None
        if row.started_at and row.created_at:
            delta = row.created_at - row.started_at
            e2e_sec = max(0.0, delta.total_seconds())
            g["e2e_secs"].append(e2e_sec)
        ttft_sec = None
        if (
            row.is_streaming
            and row.first_chunk_at is not None
            and row.started_at is not None
        ):
            ttft_delta = row.first_chunk_at - row.started_at
            ttft_sec = max(0.0, ttft_delta.total_seconds())
            g["ttft_secs"].append(ttft_sec)
        if (
            e2e_sec is not None
            and e2e_sec > 0
            and row.completion_tokens is not None
        ):
            g["output_tps_list"].append(
                float(row.completion_tokens) / e2e_sec
            )

    rows_to_upsert: List[Dict[str, Any]] = []
    for (bucket, model), g in groups.items():
        avg_e2e = (
            sum(g["e2e_secs"]) / len(g["e2e_secs"])
            if g["e2e_secs"]
            else None
        )
        avg_ttft = (
            sum(g["ttft_secs"]) / len(g["ttft_secs"])
            if g["ttft_secs"]
            else None
        )
        avg_tps = (
            sum(g["output_tps_list"]) / len(g["output_tps_list"])
            if g["output_tps_list"]
            else None
        )
        cost_val = g["cost"]
        if cost_val == Decimal("0"):
            cost_val = None
        rows_to_upsert.append({
            "granularity": granularity,
            "bucket": bucket,
            "model": model or "unknown",
            "call_count": g["call_count"],
            "success_count": g["success_count"],
            "avg_e2e_latency_sec": (
                round(avg_e2e, 4) if avg_e2e is not None else None
            ),
            "avg_ttft_sec": (
                round(avg_ttft, 4) if avg_ttft is not None else None
            ),
            "avg_output_tps": (
                round(avg_tps, 2) if avg_tps is not None else None
            ),
            "total_prompt_tokens": g["prompt_tokens"],
            "total_completion_tokens": g["completion_tokens"],
            "total_tokens": g["total_tokens"],
            "total_cached_tokens": g["cached_tokens"],
            "total_reasoning_tokens": g["reasoning_tokens"],
            "total_cost": cost_val,
            "cost_currency": g["cost_currency"] or "USD",
        })

    with transaction.atomic():
        for r in rows_to_upsert:
            LLMUsageSeries.objects.update_or_create(
                granularity=r["granularity"],
                bucket=r["bucket"],
                model=r["model"],
                defaults={
                    "call_count": r["call_count"],
                    "success_count": r["success_count"],
                    "avg_e2e_latency_sec": r["avg_e2e_latency_sec"],
                    "avg_ttft_sec": r["avg_ttft_sec"],
                    "avg_output_tps": r["avg_output_tps"],
                    "total_prompt_tokens": r["total_prompt_tokens"],
                    "total_completion_tokens": r["total_completion_tokens"],
                    "total_tokens": r["total_tokens"],
                    "total_cached_tokens": r["total_cached_tokens"],
                    "total_reasoning_tokens": r["total_reasoning_tokens"],
                    "total_cost": r["total_cost"],
                    "cost_currency": r["cost_currency"],
                },
            )
    logger.info(
        f"aggregate_usage_to_series granularity={granularity} "
        f"range=[{start_date}, {end_date}] upserted={len(rows_to_upsert)}"
    )
    return len(rows_to_upsert)


def get_series_for_charts(
    granularity: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Read pre-aggregated series for chart API (by model curves).

    granularity: API view granularity - day, month, or year (mapped to
    series hour/day/month). Returns list of { bucket, model, ... } for
    performance curves, token and cost (global series only).
    """
    series_gran = VIEW_TO_SERIES_GRANULARITY.get(
        (granularity or "").strip().lower()
    )
    if not series_gran:
        raise ValueError(
            "granularity must be one of: day, month, year"
        )
    start_date = _ensure_aware_datetime(start_date) if start_date else None
    end_date = _ensure_aware_datetime(end_date) if end_date else None
    if not start_date or not end_date:
        return []

    qs = LLMUsageSeries.objects.filter(
        granularity=series_gran,
        bucket__gte=start_date,
        bucket__lte=end_date,
    ).order_by("bucket", "model")

    out = []
    for row in qs:
        cost = row.total_cost
        if cost is not None:
            cost = float(cost)
        if row.bucket is None:
            bucket_str = None
        elif series_gran == SERIES_GRANULARITY_DAY:
            bucket_str = (
                row.bucket.date().isoformat()
                if hasattr(row.bucket, "date")
                else row.bucket.isoformat()
            )
        else:
            bucket_str = row.bucket.isoformat()
        out.append({
            "bucket": bucket_str,
            "model": row.model or "",
            "call_count": row.call_count,
            "success_count": row.success_count,
            "avg_e2e_latency_sec": row.avg_e2e_latency_sec,
            "avg_ttft_sec": row.avg_ttft_sec,
            "avg_output_tps": row.avg_output_tps,
            "total_prompt_tokens": row.total_prompt_tokens,
            "total_completion_tokens": row.total_completion_tokens,
            "total_tokens": row.total_tokens,
            "total_cached_tokens": row.total_cached_tokens,
            "total_reasoning_tokens": row.total_reasoning_tokens,
            "total_cost": cost,
            "cost_currency": row.cost_currency or "USD",
        })
    return out


def _compute_series_from_usage(
    granularity: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Compute (bucket, model) series from LLMUsage without writing to DB.
    Same grouping logic as aggregate_usage_to_series; returns list of dicts
    suitable for chart API (bucket as datetime, cost as Decimal).
    Used as fallback when LLMUsageSeries has no rows for the range.
    """
    if granularity not in (
        SERIES_GRANULARITY_HOUR,
        SERIES_GRANULARITY_DAY,
        SERIES_GRANULARITY_MONTH,
    ):
        return []
    start_date = _ensure_aware_datetime(start_date) if start_date else None
    end_date = _ensure_aware_datetime(end_date) if end_date else None
    if not start_date or not end_date:
        return []

    qs = LLMUsage.objects.filter(
        created_at__gte=start_date,
        created_at__lte=end_date,
    ).only(
        "created_at",
        "started_at",
        "first_chunk_at",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cached_tokens",
        "reasoning_tokens",
        "cost",
        "cost_currency",
        "success",
        "is_streaming",
    )
    groups = defaultdict(
        lambda: {
            "e2e_secs": [],
            "ttft_secs": [],
            "output_tps_list": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
            "cost": Decimal("0"),
            "cost_currency": "USD",
            "call_count": 0,
            "success_count": 0,
        }
    )

    for row in qs.iterator(chunk_size=2000):
        bucket = _truncate_bucket(row.created_at, granularity)
        key = (bucket, row.model or "")
        g = groups[key]
        g["call_count"] += 1
        if row.success:
            g["success_count"] += 1
        g["prompt_tokens"] += row.prompt_tokens or 0
        g["completion_tokens"] += row.completion_tokens or 0
        g["total_tokens"] += row.total_tokens or 0
        g["cached_tokens"] += row.cached_tokens or 0
        g["reasoning_tokens"] += row.reasoning_tokens or 0
        if row.cost is not None:
            g["cost"] += row.cost
        if row.cost_currency:
            g["cost_currency"] = row.cost_currency

        e2e_sec = None
        if row.started_at and row.created_at:
            delta = row.created_at - row.started_at
            e2e_sec = max(0.0, delta.total_seconds())
            g["e2e_secs"].append(e2e_sec)
        ttft_sec = None
        if (
            row.is_streaming
            and row.first_chunk_at is not None
            and row.started_at is not None
        ):
            ttft_delta = row.first_chunk_at - row.started_at
            ttft_sec = max(0.0, ttft_delta.total_seconds())
            g["ttft_secs"].append(ttft_sec)
        if (
            e2e_sec is not None
            and e2e_sec > 0
            and row.completion_tokens is not None
        ):
            g["output_tps_list"].append(
                float(row.completion_tokens) / e2e_sec
            )

    out = []
    for (bucket, model), g in sorted(groups.items()):
        avg_e2e = (
            sum(g["e2e_secs"]) / len(g["e2e_secs"])
            if g["e2e_secs"]
            else None
        )
        avg_ttft = (
            sum(g["ttft_secs"]) / len(g["ttft_secs"])
            if g["ttft_secs"]
            else None
        )
        avg_tps = (
            sum(g["output_tps_list"]) / len(g["output_tps_list"])
            if g["output_tps_list"]
            else None
        )
        cost_val = g["cost"]
        if cost_val == Decimal("0"):
            cost_val = None
        if bucket is None:
            bucket_str = None
        elif granularity == SERIES_GRANULARITY_DAY:
            bucket_str = (
                bucket.date().isoformat()
                if hasattr(bucket, "date")
                else bucket.isoformat()
            )
        else:
            bucket_str = bucket.isoformat()
        out.append({
            "bucket": bucket_str,
            "model": model or "",
            "call_count": g["call_count"],
            "success_count": g["success_count"],
            "avg_e2e_latency_sec": (
                round(avg_e2e, 4) if avg_e2e is not None else None
            ),
            "avg_ttft_sec": (
                round(avg_ttft, 4) if avg_ttft is not None else None
            ),
            "avg_output_tps": (
                round(avg_tps, 2) if avg_tps is not None else None
            ),
            "total_prompt_tokens": g["prompt_tokens"],
            "total_completion_tokens": g["completion_tokens"],
            "total_tokens": g["total_tokens"],
            "total_cached_tokens": g["cached_tokens"],
            "total_reasoning_tokens": g["reasoning_tokens"],
            "total_cost": float(cost_val) if cost_val is not None else None,
            "cost_currency": g["cost_currency"] or "USD",
        })
    return out


def get_series_for_charts_with_fallback(
    granularity: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Return pre-aggregated series for charts. If LLMUsageSeries has no rows
    for the range, compute from LLMUsage on the fly so the by-model charts
    still show.
    """
    result = get_series_for_charts(
        granularity=granularity,
        start_date=start_date,
        end_date=end_date,
    )
    if result:
        return result
    series_gran = VIEW_TO_SERIES_GRANULARITY.get(
        (granularity or "").strip().lower()
    )
    if not series_gran:
        return []
    return _compute_series_from_usage(
        granularity=series_gran,
        start_date=start_date,
        end_date=end_date,
    )
