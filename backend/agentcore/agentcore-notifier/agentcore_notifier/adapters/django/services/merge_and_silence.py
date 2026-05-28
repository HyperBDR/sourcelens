"""
Merge and silence checks for send task.

Design: merge_key MUST include user dimension so alerts from different users
do not mix. Merge/silence windows are applied per
(user, source_app, source_type, source_id).
See docs/MERGE_SILENCE_DESIGN.md for full principles.
"""
from datetime import datetime, timedelta, timezone as utc_tz
from typing import Any, Dict, List, Optional

from django.utils import timezone

from agentcore_notifier.adapters.django.models import NotificationRecord
from agentcore_notifier.constants import Status


def _parse_silence_until(until: Any) -> Optional[datetime]:
    """Parse silence_until to timezone-aware datetime; return None on error."""
    if until is None:
        return None
    try:
        if isinstance(until, str):
            until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
        else:
            until_dt = until
        if until_dt.tzinfo is None:
            until_dt = timezone.make_aware(until_dt, utc_tz.utc)
        return until_dt
    except (ValueError, TypeError, AttributeError):
        return None


def _filter_active_silence_rules(
    rules: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Filter rules to active ones (enabled and silence_until not passed)."""
    if not isinstance(rules, list):
        return []
    now = timezone.now()
    out = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        if not r.get("enabled", True):
            continue
        until = _parse_silence_until(r.get("silence_until"))
        if until is not None and now >= until:
            continue
        out.append(r)
    return out


def _get_silence_rules(provider_type: str) -> List[Dict[str, Any]]:
    """Get silence rules from NotifierConfig (global). Filter by type."""
    # NOTE(Ray): Lazy import to avoid circular import.
    from agentcore_notifier.adapters.django.services import (
        notification_config,
    )

    raw = notification_config.get_config("silence_rules")
    if not isinstance(raw, list):
        return []
    filtered = [
        r for r in raw
        if isinstance(r, dict) and r.get("provider_type") == provider_type
    ]
    return _filter_active_silence_rules(filtered)


def _rule_matches(
    r: Dict[str, Any],
    source_app: str,
    source_type: str,
    source_id: str,
    user_id: Optional[int],
) -> bool:
    if r.get("source_app") and r["source_app"] != source_app:
        return False
    if r.get("source_type") and r["source_type"] != source_type:
        return False
    sid = r.get("source_id")
    if sid is not None and sid != "" and sid != source_id:
        return False
    if r.get("user_id") is not None and r.get("user_id") != user_id:
        return False
    return True


def should_silence_from_rules(
    rules: List[Dict[str, Any]],
    source_app: str,
    source_type: str,
    source_id: str,
    user_id: Optional[int],
) -> bool:
    """
    Return True if (source_app, source_type, source_id, user_id) matches any
    rule. rules: from channel.config["silence_rules"] (already filtered).
    """
    for r in _filter_active_silence_rules(rules or []):
        if _rule_matches(r, source_app, source_type, source_id, user_id):
            return True
    return False


def should_silence(
    provider_type: str,
    source_app: str,
    source_type: str,
    source_id: str,
    user_id: Optional[int],
) -> bool:
    """
    Return True if matches any active silence rule for that provider_type
    (NotifierConfig, legacy).
    """
    rules = _get_silence_rules(provider_type)
    for r in rules:
        if _rule_matches(r, source_app, source_type, source_id, user_id):
            return True
    return False


def merge_key(
    source_app: str,
    source_type: str,
    source_id: str,
    user_id: Optional[int] = None,
) -> str:
    """
    Build merge key for coalesce. Include user dimension so different users'
    alerts are not merged. user_id None treated as "global".
    """
    uid = user_id if user_id is not None else "global"
    return f"{uid}:{source_app}:{source_type}:{source_id}"


def should_skip_due_to_merge(
    provider_type: str,
    source_app: str,
    source_type: str,
    source_id: str,
    window_minutes: int,
    channel_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> bool:
    """
    Return True if there is already a send in the last window_minutes for the
    same merge_key (user + source_app + source_type + source_id) and
    provider_type (and channel_id when provided). User ensures per-user merge.
    """
    if window_minutes <= 0:
        return False
    since = timezone.now() - timedelta(minutes=window_minutes)
    qs = NotificationRecord.objects.filter(
        provider_type=provider_type,
        source_app=source_app,
        source_type=source_type,
        source_id=source_id,
        status__in=(Status.SUCCESS, Status.FAILED),
        created_at__gte=since,
    )
    if user_id is not None:
        qs = qs.filter(user_id=user_id)
    else:
        qs = qs.filter(user__isnull=True)
    if channel_id is not None:
        qs = qs.filter(channel_link_id=channel_id)
    return qs.exists()
