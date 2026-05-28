"""
Global config for agentcore_metering: retention, cleanup, aggregation.

Reads from MeteringConfig (DB) first, then Django settings. Used by periodic
tasks and config API for frontend management.
"""
from django.conf import settings

try:
    from celery.schedules import crontab
except ImportError:
    crontab = None

DEFAULT_RETENTION_DAYS = 365
DEFAULT_CLEANUP_ENABLED = True
DEFAULT_CLEANUP_CRONTAB = "0 2 * * *"
DEFAULT_AGGREGATION_CRONTAB = "5 * * * *"

# Timezone for "yesterday" / "last month" when computing aggregation range.
# Celery may run at 02:00 Shanghai; we aggregate Shanghai's yesterday.
DEFAULT_AGGREGATION_TIMEZONE = "Asia/Shanghai"


def _get_global_config(key: str):
    # NOTE(Ray): Lazy import to avoid circular import (conf used by
    # services.__init__, tasks, apps.ready(); metering_config may import conf).
    from agentcore_metering.adapters.django.services import metering_config

    return metering_config.get_global_config(key)


def get_retention_days() -> int:
    """
    Retention days for cleanup: MeteringConfig first, else settings.
    Default 365 days.
    """
    val = _get_global_config("retention_days")
    if isinstance(val, int) and val > 0:
        return val
    return getattr(
        settings,
        "AGENTCORE_METERING_RETENTION_DAYS",
        DEFAULT_RETENTION_DAYS,
    )


def get_cleanup_enabled() -> bool:
    """Whether cleanup beat task is enabled (default True)."""
    val = _get_global_config("cleanup_enabled")
    if val is not None:
        return bool(val)
    return getattr(
        settings,
        "AGENTCORE_METERING_CLEANUP_ENABLED",
        DEFAULT_CLEANUP_ENABLED,
    )


def get_cleanup_crontab() -> str:
    """Five-field cron expression for cleanup (default daily 2:00)."""
    val = _get_global_config("cleanup_crontab")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return getattr(
        settings,
        "AGENTCORE_METERING_CLEANUP_CRONTAB",
        DEFAULT_CLEANUP_CRONTAB,
    )


def get_aggregation_crontab() -> str:
    """
    Cron for aggregation task (hour/day/month in one run).
    Default: minute 5 past each hour (5 * * * *).
    """
    val = _get_global_config("aggregation_crontab")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return getattr(
        settings,
        "AGENTCORE_METERING_AGGREGATION_CRONTAB",
        DEFAULT_AGGREGATION_CRONTAB,
    )


def get_aggregation_timezone() -> str:
    """
    Timezone for computing aggregation date range (yesterday, last month).
    Ensures "yesterday" is the calendar day in this timezone; range is then
    converted to UTC for DB query. Default Asia/Shanghai.
    """
    return getattr(
        settings,
        "AGENTCORE_METERING_AGGREGATION_TIMEZONE",
        DEFAULT_AGGREGATION_TIMEZONE,
    )


def _crontab_from_expression(expr: str):
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


def is_valid_crontab_expression(expr: str) -> bool:
    """Return True if expr is a valid 5-field cron expression."""
    if not expr or not str(expr).strip():
        return False
    return _crontab_from_expression(str(expr).strip()) is not None


def get_cleanup_beat_schedule_init():
    """
    Build cleanup beat schedule from Django settings only (no DB in init).
    For use in periodic_tasks.register_periodic_tasks.
    """
    task_name = (
        "agentcore_metering.adapters.django.tasks.cleanup."
        "cleanup_old_llm_usage_task"
    )
    crontab_str = getattr(
        settings,
        "AGENTCORE_METERING_CLEANUP_CRONTAB",
        DEFAULT_CLEANUP_CRONTAB,
    )
    schedule = _crontab_from_expression(crontab_str)
    if schedule is None:
        schedule = 24 * 3600.0
    return {
        "agentcore-metering-cleanup-old-usage": {
            "task": task_name,
            "schedule": schedule,
            "options": {},
        }
    }


def get_aggregation_beat_schedule_init():
    """
    Build single aggregation beat schedule from settings only.
    One task runs hour + day + month aggregation each time.
    """
    task_name = (
        "agentcore_metering.adapters.django.tasks.aggregate."
        "aggregate_llm_usage_series_task"
    )
    crontab_str = getattr(
        settings,
        "AGENTCORE_METERING_AGGREGATION_CRONTAB",
        DEFAULT_AGGREGATION_CRONTAB,
    )
    schedule = _crontab_from_expression(crontab_str)
    if schedule is None:
        schedule = 3600.0
    return {
        "agentcore-metering-aggregate": {
            "task": task_name,
            "schedule": schedule,
            "options": {},
        }
    }
