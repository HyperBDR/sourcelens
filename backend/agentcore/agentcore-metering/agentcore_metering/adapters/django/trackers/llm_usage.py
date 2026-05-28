"""
Token counting and usage extraction for LiteLLM responses.

Provides model-agnostic token counts (via LiteLLM token_counter) and
normalized usage dicts from completion/stream chunk objects. Used by
trackers.llm to keep the tracker thin and testable.
"""
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from litellm import completion_cost, token_counter

from agentcore_metering.adapters.django.utils import (
    _read_field,
    _read_nested_int,
    _safe_int,
)
from agentcore_metering.constants import DEFAULT_COST_CURRENCY

logger = logging.getLogger(__name__)


def token_count_text(model: str, text: str) -> int:
    """
    Model-agnostic token count for a string using LiteLLM token_counter.
    Returns 0 on empty text or on error.
    """
    if not (text and text.strip()):
        return 0
    try:
        return int(token_counter(model=model, text=text))
    except Exception as e:
        logger.debug(f"token_counter(model={model!r}, text=...) failed: {e}")
        return 0


def token_count_messages(model: str, messages: list) -> int:
    """
    Model-agnostic token count for messages using LiteLLM token_counter.
    Returns 0 on empty messages or on error.
    """
    if not messages:
        return 0
    try:
        return int(token_counter(model=model, messages=messages))
    except Exception as e:
        logger.debug(
            f"token_counter(model={model!r}, messages=...) failed: {e}"
        )
        return 0


def get_cost_from_response(response: Any) -> Optional[Decimal]:
    """
    Extract cost (USD) from a LiteLLM completion or stream chunk.
    Tries completion_cost() then response._hidden_params.response_cost.
    """
    try:
        cost = completion_cost(completion_response=response)
        if cost is not None:
            return Decimal(str(cost))
    except (TypeError, ValueError) as e:
        logger.debug(f"completion_cost or Decimal failed: {e}")
    except Exception as e:
        logger.debug(f"completion_cost failed: {e}")
    hidden = getattr(response, "_hidden_params", None) or {}
    cost = hidden.get("response_cost")
    if cost is not None:
        try:
            return Decimal(str(cost))
        except (TypeError, ValueError, InvalidOperation):
            model = getattr(response, "model", "unknown")
            logger.warning(
                f"Invalid response_cost in hidden params "
                f"model={model} response_cost={cost}"
            )
            return None
    return None


def usage_dict_from_usage_obj(
    usage_obj: Any, fallback_model: str
) -> Dict[str, Any]:
    """
    Build usage dict (tokens only, no cost) from a LiteLLM usage object.
    Used by both sync response.usage and stream chunk.usage.
    """
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    cached_tokens = 0
    reasoning_tokens = 0
    if usage_obj:
        prompt_tokens = _safe_int(_read_field(usage_obj, "prompt_tokens", 0))
        completion_tokens = _safe_int(
            _read_field(usage_obj, "completion_tokens", 0)
        )
        total_tokens = (
            _safe_int(_read_field(usage_obj, "total_tokens", 0))
            or (prompt_tokens + completion_tokens)
        )
        cached_tokens = _safe_int(_read_field(usage_obj, "cached_tokens", 0))
        reasoning_tokens = _safe_int(
            _read_field(usage_obj, "reasoning_tokens", 0)
        )
        if cached_tokens == 0:
            prompt_details = (
                _read_field(usage_obj, "prompt_tokens_details", None)
                or _read_field(usage_obj, "input_token_details", None)
            )
            cached_tokens = _read_nested_int(
                prompt_details,
                ("cached_tokens", "cache_read_tokens", "cache_read"),
                0,
            )
        if reasoning_tokens == 0:
            completion_details = (
                _read_field(
                    usage_obj,
                    "completion_tokens_details",
                    None,
                )
                or _read_field(usage_obj, "output_token_details", None)
            )
            reasoning_tokens = _read_nested_int(
                completion_details,
                ("reasoning_tokens", "reasoning"),
                0,
            )
    return {
        "model": fallback_model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cost": None,
        "cost_currency": DEFAULT_COST_CURRENCY,
    }


def usage_from_response(response: Any, model: str) -> Dict[str, Any]:
    """
    Build full usage dict from a non-stream completion response.
    Includes cost from get_cost_from_response(response).
    """
    usage_obj = getattr(response, "usage", None)
    usage = usage_dict_from_usage_obj(usage_obj, model)
    cost = get_cost_from_response(response)
    usage["cost"] = float(cost) if cost is not None else None
    return usage


def usage_from_stream_chunk(chunk: Any, fallback_model: str) -> Dict[str, Any]:
    """
    Build full usage dict from a streaming chunk.
    LiteLLM often sends usage in the last chunk; cost from chunk if present.
    """
    usage_obj = getattr(chunk, "usage", None)
    usage = usage_dict_from_usage_obj(usage_obj, fallback_model)
    cost = None
    try:
        cost = get_cost_from_response(chunk)
    except Exception as e:
        logger.debug(f"get_cost_from_response(chunk) failed: {e}")
    usage["cost"] = float(cost) if cost is not None else None
    return usage


def fill_usage_with_token_fallback(
    usage: Dict[str, Any],
    model: str,
    *,
    messages: Optional[List] = None,
    streamed_content: Optional[str] = None,
    content: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fill missing prompt/completion/total with LiteLLM token_counter when
    API did not return usage. Updates total_tokens to keep consistency.

    Call with either (messages + content) for sync, or (messages +
    streamed_content) for stream.
    """
    result = dict(usage)
    prompt = result.get("prompt_tokens") or 0
    completion = result.get("completion_tokens") or 0
    total = result.get("total_tokens") or 0

    if prompt == 0 and messages:
        prompt = token_count_messages(model, messages)
        result["prompt_tokens"] = prompt
        result["total_tokens"] = prompt + completion

    completion_content = (
        streamed_content if streamed_content is not None else content
    )
    if completion_content and (completion == 0 and total == 0):
        completion = max(1, token_count_text(model, completion_content))
        total = prompt + completion
        result["completion_tokens"] = completion
        result["total_tokens"] = total

    return result
