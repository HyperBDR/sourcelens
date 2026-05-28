"""LLM usage records listing for admin (read-only, paginated)."""
from typing import Any, Dict, List, Optional

from agentcore_metering.adapters.django.models import LLMUsage
from agentcore_metering.adapters.django.services.usage_aggregation import (
    _parse_date,
    _parse_end_date,
)


def _safe_positive_int(
    value: Any,
    default: int,
    *,
    minimum: int = 1,
) -> int:
    """Return a clamped positive integer parsed from query/input values."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if parsed < minimum:
        return minimum
    return parsed


def get_llm_usage_list(
    page: int = 1,
    page_size: int = 20,
    user_id: Optional[str] = None,
    model_filter: Optional[str] = None,
    success_filter: Optional[str] = None,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Return paginated LLM usage records with filters.
    Applied filters: user_id, model (icontains), success, start_date, end_date.
    """
    page = _safe_positive_int(page, 1, minimum=1)
    page_size = _safe_positive_int(page_size, 20, minimum=1)
    page_size = min(page_size, 100)
    qs = (
        LLMUsage.objects.select_related("user")
        .order_by("-created_at")
    )
    if user_id:
        qs = qs.filter(user_id=user_id)
    if model_filter:
        qs = qs.filter(model__icontains=model_filter)
    if success_filter and success_filter.strip():
        low = success_filter.strip().lower()
        if low == "true":
            qs = qs.filter(success=True)
        elif low == "false":
            qs = qs.filter(success=False)
    if start_date:
        qs = qs.filter(created_at__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__lte=end_date)

    total = qs.count()
    start = (page - 1) * page_size
    usages = qs[start: start + page_size]

    items: List[Dict[str, Any]] = []
    for u in usages:
        created_at = u.created_at.isoformat() if u.created_at else None
        started_at = u.started_at.isoformat() if u.started_at else None
        username = u.user.username if u.user else None
        cost = None
        if u.cost is not None:
            cost = float(u.cost)
        e2e_latency_sec = None
        ttft_sec = None
        if u.started_at and u.created_at:
            delta = u.created_at - u.started_at
            e2e_latency_sec = max(0.0, delta.total_seconds())
        if (
            u.is_streaming
            and u.first_chunk_at is not None
            and u.started_at is not None
        ):
            ttft_delta = u.first_chunk_at - u.started_at
            ttft_sec = max(0.0, ttft_delta.total_seconds())
        # output_tps = completion_tokens / e2e_latency (stream and non-stream)
        output_tps = None
        if (
            e2e_latency_sec is not None
            and e2e_latency_sec > 0
            and u.completion_tokens is not None
        ):
            output_tps = round(float(u.completion_tokens) / e2e_latency_sec, 2)
        item: Dict[str, Any] = {
            "id": str(u.id),
            "user_id": u.user_id,
            "username": username,
            "model": u.model,
            "prompt_tokens": u.prompt_tokens,
            "completion_tokens": u.completion_tokens,
            "total_tokens": u.total_tokens,
            "cost": cost,
            "cost_currency": u.cost_currency or "USD",
            "success": u.success,
            "error": u.error,
            "created_at": created_at,
            "started_at": started_at,
            "e2e_latency_sec": e2e_latency_sec,
            "output_tps": output_tps,
            "metadata": u.metadata,
        }
        if ttft_sec is not None:
            item["ttft_sec"] = ttft_sec
        item["latency_sec"] = e2e_latency_sec
        items.append(item)

    return {
        "results": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_llm_usage_list_from_query(params: Any) -> Dict[str, Any]:
    """
    Build paginated LLM usage list from a query params dict
    (e.g. request.query_params).
    """
    page = _safe_positive_int(params.get("page"), 1, minimum=1)
    page_size = _safe_positive_int(params.get("page_size"), 20, minimum=1)
    page_size = min(page_size, 100)
    user_id = (params.get("user_id") or "").strip() or None
    model_filter = (params.get("model") or "").strip() or None
    success_filter = (params.get("success") or "").strip() or None
    start_date = _parse_date(params.get("start_date"))
    end_date = _parse_end_date(params.get("end_date"))
    return get_llm_usage_list(
        page=page,
        page_size=page_size,
        user_id=user_id,
        model_filter=model_filter,
        success_filter=success_filter,
        start_date=start_date,
        end_date=end_date,
    )
