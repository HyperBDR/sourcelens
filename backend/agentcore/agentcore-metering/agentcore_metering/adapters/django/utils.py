"""
Shared helpers for reading usage/response fields from LiteLLM-style objects.

Used by runtime_config and trackers.llm to normalize dict vs object access
and safe int conversion for token counts and nested details.
"""
from typing import Any, Tuple


def _safe_int(value: Any, default: int = 0) -> int:
    """
    Coerce value to int; return default on None or invalid value.
    """
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _read_field(obj: Any, key: str, default: Any = None) -> Any:
    """
    Read key from obj whether it is a dict or an object with attributes.
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _read_nested_int(
    obj: Any, keys: Tuple[str, ...], default: int = 0
) -> int:
    """
    Try each key in order; return first non-None value coerced to int.
    """
    for key in keys:
        value = _read_field(obj, key, None)
        if value is None:
            continue
        return _safe_int(value, default)
    return default
