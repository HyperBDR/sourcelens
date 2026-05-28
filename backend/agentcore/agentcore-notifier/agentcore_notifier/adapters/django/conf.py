"""
Global config for agentcore_notifier (cleanup, merge). Not user-specific.
Uses lazy imports of notification_config to avoid circular import.
"""
try:
    from celery.schedules import crontab
except ImportError:
    crontab = None

from django.conf import settings

DEFAULT_RETENTION_DAYS = 180
DEFAULT_CLEANUP_ONLY_COMPLETED = True
DEFAULT_CLEANUP_ENABLED = True
DEFAULT_CLEANUP_CRONTAB = "0 2 * * *"


def _get_global_config():
    # NOTE(Ray): Lazy import to avoid circular import.
    from agentcore_notifier.adapters.django.services import notification_config

    raw = notification_config.get_config("global")
    return raw if isinstance(raw, dict) else {}


def get_retention_days():
    """
    Retention days for cleanup: NotifierConfig key=global first, else settings.
    """
    g = _get_global_config()
    v = g.get("retention_days")
    if isinstance(v, int) and v > 0:
        return v
    return getattr(
        settings,
        "AGENTCORE_NOTIFIER_RETENTION_DAYS",
        DEFAULT_RETENTION_DAYS,
    )


def get_cleanup_only_completed():
    """Return whether cleanup deletes only completed records (default True)."""
    return getattr(
        settings,
        "AGENTCORE_NOTIFIER_CLEANUP_ONLY_COMPLETED",
        DEFAULT_CLEANUP_ONLY_COMPLETED,
    )


def get_cleanup_enabled():
    """Return whether cleanup beat task is enabled (default True)."""
    g = _get_global_config()
    if "cleanup_enabled" in g:
        return bool(g["cleanup_enabled"])
    return getattr(
        settings, "AGENTCORE_NOTIFIER_CLEANUP_ENABLED", DEFAULT_CLEANUP_ENABLED
    )


def get_cleanup_crontab():
    """Return 5-field cron expression for cleanup (default daily 2:00)."""
    g = _get_global_config()
    v = g.get("cleanup_crontab")
    if isinstance(v, str) and v.strip():
        return v.strip()
    return getattr(
        settings, "AGENTCORE_NOTIFIER_CLEANUP_CRONTAB", DEFAULT_CLEANUP_CRONTAB
    )


def _crontab_from_expression(expr):
    """Parse 5-field cron into Celery crontab. On parse error returns None."""
    if not crontab or not expr:
        return None
    parts = str(expr).strip().split()
    if len(parts) != 5:
        return None
    try:
        return crontab(
            minute=parts[0],
            hour=parts[1],
            day_of_month=parts[2],
            month_of_year=parts[3],
            day_of_week=parts[4],
        )
    except (TypeError, ValueError):
        return None


def get_cleanup_beat_schedule(interval_hours=None):
    """Beat schedule for cleanup. Uses get_cleanup_crontab() or interval."""
    task_name = (
        "agentcore_notifier.adapters.django.tasks.cleanup."
        "cleanup_old_notification_records_task"
    )
    if interval_hours is not None:
        schedule = interval_hours * 3600.0
    else:
        schedule = _crontab_from_expression(get_cleanup_crontab())
        if schedule is None:
            schedule = 24 * 3600.0
    return {
        "agentcore-notifier-cleanup-old-records": {
            "task": task_name,
            "schedule": schedule,
            "options": {},
        }
    }


def get_cleanup_beat_schedule_init(interval_hours=None):
    """
    Build cleanup beat schedule from Django settings only (no DB).
    For use in AppConfig.ready() to avoid database-during-init warning.
    Runtime DB config is still applied when the cleanup task runs.
    """
    task_name = (
        "agentcore_notifier.adapters.django.tasks.cleanup."
        "cleanup_old_notification_records_task"
    )
    if interval_hours is not None:
        schedule = interval_hours * 3600.0
    else:
        crontab_str = getattr(
            settings,
            "AGENTCORE_NOTIFIER_CLEANUP_CRONTAB",
            DEFAULT_CLEANUP_CRONTAB,
        )
        schedule = _crontab_from_expression(crontab_str)
        if schedule is None:
            schedule = 24 * 3600.0
    return {
        "agentcore-notifier-cleanup-old-records": {
            "task": task_name,
            "schedule": schedule,
            "options": {},
        }
    }


def get_merge_enabled(provider_type: str) -> bool:
    """Return whether merge is enabled for this provider (default False)."""
    # NOTE(Ray): Lazy import to avoid circular import.
    from agentcore_notifier.adapters.django.services import notification_config

    key = f"channel_{provider_type}"
    raw = notification_config.get_config(key)
    if isinstance(raw, dict) and "merge_enabled" in raw:
        return bool(raw["merge_enabled"])
    return False


def get_merge_window_minutes(provider_type: str):
    """Return merge window in minutes for this provider, or None (disabled)."""
    # NOTE(Ray): Lazy import to avoid circular import.
    from agentcore_notifier.adapters.django.services import notification_config

    key = f"channel_{provider_type}"
    raw = notification_config.get_config(key)
    if isinstance(raw, dict):
        v = raw.get("merge_window_minutes")
        if isinstance(v, int) and v > 0:
            return v
    return None
