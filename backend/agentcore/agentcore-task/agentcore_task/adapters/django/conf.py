"""
Global config for agentcore_task (cleanup, etc.). Not user-specific.

NOTE(Ray): This module uses lazy imports of task_config inside four getters
(get_retention_days, get_cleanup_crontab, get_task_timeout_minutes,
get_mark_timeout_crontab) to avoid circular import: conf is imported by
services.__init__, tasks, and apps.ready(); moving task_config to top would
cause "partially initialized module" errors. Exception to "no mid-file
imports".
"""
from django.conf import settings

try:
    from celery.schedules import crontab
except ImportError:
    crontab = None

DEFAULT_RETENTION_DAYS = 180
DEFAULT_CLEANUP_ONLY_COMPLETED = True
DEFAULT_CLEANUP_ENABLED = True
DEFAULT_CLEANUP_BEAT_INTERVAL_HOURS = 24
DEFAULT_CLEANUP_CRONTAB = "0 2 * * *"

DEFAULT_MARK_TIMEOUT_ENABLED = True
DEFAULT_TASK_TIMEOUT_MINUTES = 10
DEFAULT_MARK_TIMEOUT_CRONTAB = "*/30 * * * *"

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = True
DEFAULT_RETRY_BACKOFF_MAX = 600


def get_retention_days():
    """
    Retention days for cleanup: TaskConfig global key first, else settings.
    """
    from agentcore_task.adapters.django.services import task_config

    from_config = task_config.get_retention_days_from_config()
    if from_config is not None:
        return from_config
    return getattr(
        settings, "AGENTCORE_TASK_RETENTION_DAYS", DEFAULT_RETENTION_DAYS
    )


def get_cleanup_only_completed():
    """Return whether cleanup deletes only completed records (default True)."""
    return getattr(
        settings,
        "AGENTCORE_TASK_CLEANUP_ONLY_COMPLETED",
        DEFAULT_CLEANUP_ONLY_COMPLETED,
    )


def get_cleanup_enabled():
    """Return whether cleanup beat task is enabled (default True)."""
    return getattr(
        settings,
        "AGENTCORE_TASK_CLEANUP_ENABLED",
        DEFAULT_CLEANUP_ENABLED,
    )


def get_cleanup_beat_interval_hours():
    """Return cleanup beat interval in hours when crontab not used."""
    return getattr(
        settings,
        "AGENTCORE_TASK_CLEANUP_BEAT_INTERVAL_HOURS",
        DEFAULT_CLEANUP_BEAT_INTERVAL_HOURS,
    )


def get_cleanup_crontab():
    """
    Return 5-field cron expression for cleanup schedule (default daily 2:00).
    TaskConfig global key first, else settings.
    """
    from agentcore_task.adapters.django.services import task_config

    from_config = task_config.get_cleanup_crontab_from_config()
    if from_config is not None:
        return from_config
    return getattr(
        settings,
        "AGENTCORE_TASK_CLEANUP_CRONTAB",
        DEFAULT_CLEANUP_CRONTAB,
    )


def _crontab_from_expression(expr):
    """
    Parse 5-field cron expression (minute hour day_of_month month day_of_week)
    into Celery crontab. On parse error returns None.
    """
    if not crontab or not expr:
        return None
    parts = expr.strip().split()
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


def is_valid_crontab_expression(expr) -> bool:
    """Return True if expr is a valid 5-field cron expression."""
    if not expr or not str(expr).strip():
        return False
    return _crontab_from_expression(str(expr).strip()) is not None


def get_mark_timeout_enabled():
    """Return whether mark-timeout beat task is enabled (default True)."""
    return getattr(
        settings,
        "AGENTCORE_TASK_MARK_TIMEOUT_ENABLED",
        DEFAULT_MARK_TIMEOUT_ENABLED,
    )


def get_task_timeout_minutes():
    """
    Task timeout in minutes: TaskConfig global key first, else settings.
    Used by mark_timed_out_executions to treat STARTED tasks older than
    this as failed.
    """
    from agentcore_task.adapters.django.services import task_config

    from_config = task_config.get_timeout_minutes_from_config()
    if from_config is not None:
        return from_config
    return getattr(
        settings,
        "AGENTCORE_TASK_TIMEOUT_MINUTES",
        DEFAULT_TASK_TIMEOUT_MINUTES,
    )


def get_mark_timeout_crontab():
    """
    Return 5-field cron expression for timeout check (default every 30 min).
    TaskConfig global key first, else settings.
    """
    from agentcore_task.adapters.django.services import task_config

    from_config = task_config.get_mark_timeout_crontab_from_config()
    if from_config is not None:
        return from_config
    return getattr(
        settings,
        "AGENTCORE_TASK_MARK_TIMEOUT_CRONTAB",
        DEFAULT_MARK_TIMEOUT_CRONTAB,
    )


def get_mark_timeout_beat_schedule():
    """
    Beat schedule for marking timed-out STARTED tasks as FAILURE.
    Uses AGENTCORE_TASK_MARK_TIMEOUT_CRONTAB (default: every 30 min).
    """
    task_name = (
        "agentcore_task.adapters.django.tasks."
        "mark_timed_out_task_executions"
    )
    schedule = _crontab_from_expression(get_mark_timeout_crontab())
    if schedule is None:
        schedule = 3600.0
    return {
        "agentcore-task-mark-timed-out-executions": {
            "task": task_name,
            "schedule": schedule,
            "options": {},
        }
    }


def get_cleanup_beat_schedule(interval_hours=None):
    """
    Beat schedule for cleanup. Uses AGENTCORE_TASK_CLEANUP_CRONTAB when
    interval_hours is None (e.g. "0 2 * * *" = daily 2:00; "0 2,14 * * *" =
    twice daily). Falls back to interval (seconds) if crontab parse fails.
    """
    task_name = (
        "agentcore_task.adapters.django.tasks.cleanup_old_task_executions"
    )
    if interval_hours is not None:
        schedule = interval_hours * 3600.0
    else:
        schedule = _crontab_from_expression(get_cleanup_crontab())
        if schedule is None:
            schedule = get_cleanup_beat_interval_hours() * 3600.0
    return {
        "agentcore-task-cleanup-old-executions": {
            "task": task_name,
            "schedule": schedule,
            "options": {},
        }
    }


def get_cleanup_beat_schedule_init(interval_hours=None):
    """
    Build cleanup beat schedule from Django settings only (no DB).
    For use in AppConfig.ready() to avoid database-during-init warning.
    """
    task_name = (
        "agentcore_task.adapters.django.tasks.cleanup_old_task_executions"
    )
    if interval_hours is not None:
        schedule = interval_hours * 3600.0
    else:
        crontab_str = getattr(
            settings,
            "AGENTCORE_TASK_CLEANUP_CRONTAB",
            DEFAULT_CLEANUP_CRONTAB,
        )
        schedule = _crontab_from_expression(crontab_str)
        if schedule is None:
            schedule = (
                getattr(
                    settings,
                    "AGENTCORE_TASK_CLEANUP_BEAT_INTERVAL_HOURS",
                    DEFAULT_CLEANUP_BEAT_INTERVAL_HOURS,
                )
                * 3600.0
            )
    return {
        "agentcore-task-cleanup-old-executions": {
            "task": task_name,
            "schedule": schedule,
            "options": {},
        }
    }


def get_mark_timeout_beat_schedule_init():
    """
    Build mark-timeout beat schedule from Django settings only (no DB).
    For use in AppConfig.ready() to avoid database-during-init warning.
    """
    task_name = (
        "agentcore_task.adapters.django.tasks."
        "mark_timed_out_task_executions"
    )
    crontab_str = getattr(
        settings,
        "AGENTCORE_TASK_MARK_TIMEOUT_CRONTAB",
        DEFAULT_MARK_TIMEOUT_CRONTAB,
    )
    schedule = _crontab_from_expression(crontab_str)
    if schedule is None:
        schedule = 3600.0
    return {
        "agentcore-task-mark-timed-out-executions": {
            "task": task_name,
            "schedule": schedule,
            "options": {},
        }
    }


def get_default_max_retries():
    """Return default max retries for Celery task auto-retry."""
    return getattr(
        settings,
        "AGENTCORE_TASK_DEFAULT_MAX_RETRIES",
        DEFAULT_MAX_RETRIES,
    )


def get_retry_backoff():
    """Return whether Celery task retry uses backoff (default True)."""
    return getattr(
        settings, "AGENTCORE_TASK_RETRY_BACKOFF", DEFAULT_RETRY_BACKOFF
    )


def get_retry_backoff_max():
    """Return max backoff seconds for Celery task retry (default 600)."""
    return getattr(
        settings,
        "AGENTCORE_TASK_RETRY_BACKOFF_MAX",
        DEFAULT_RETRY_BACKOFF_MAX,
    )


def get_task_retry_kwargs(max_retries=None):
    """Return kwargs for @shared_task to enable auto-retry on failure."""
    n = max_retries or get_default_max_retries()
    return {
        "bind": True,
        "autoretry_for": (Exception,),
        "retry_backoff": get_retry_backoff(),
        "retry_backoff_max": get_retry_backoff_max(),
        "retry_kwargs": {"max_retries": n},
    }
