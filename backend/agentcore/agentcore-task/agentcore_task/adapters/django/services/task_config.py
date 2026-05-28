"""
Read and write task config from TaskConfig model (global scope only for now).
Used by conf.get_retention_days() / get_task_timeout_minutes() with fallback
to settings.
"""
import logging
from typing import Any, Optional

from django.db.utils import OperationalError, ProgrammingError

from agentcore_task.adapters.django.models import TaskConfig

logger = logging.getLogger(__name__)


def set_global_task_config(key: str, value: Any) -> None:
    """
    Set global config key in TaskConfig. Creates or updates the row.
    No-op if table does not exist (e.g. migrations not run).
    """
    try:
        TaskConfig.objects.update_or_create(
            scope=TaskConfig.SCOPE_GLOBAL,
            user=None,
            key=key,
            defaults={"value": value},
        )
    except (OperationalError, ProgrammingError) as e:
        logger.warning(
            f"set_global_task_config({key}) skipped: {e}",
        )


def get_global_task_config(key: str) -> Optional[Any]:
    """
    Return value for global config key from TaskConfig, or None if not set.
    On DB/table errors (e.g. table missing), returns None so conf falls
    back to settings.
    """
    try:
        row = TaskConfig.objects.filter(
            scope=TaskConfig.SCOPE_GLOBAL,
            user__isnull=True,
            key=key,
        ).first()
        if row is not None and row.value is not None:
            return row.value
    except (OperationalError, ProgrammingError) as e:
        logger.warning(
            f"get_global_task_config({key}) failed (using defaults): {e}",
        )
    except Exception as e:
        logger.debug(f"get_global_task_config({key}) failed: {e}")
    return None


def get_retention_days_from_config() -> Optional[int]:
    """
    Return global retention_days from TaskConfig if set and valid.
    Value may be int or dict with 'retention_days' key.
    """
    raw = get_global_task_config("retention_days")
    if raw is None:
        return None
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, dict):
        v = raw.get("retention_days")
        if isinstance(v, int) and v > 0:
            return v
    return None


def get_timeout_minutes_from_config() -> Optional[int]:
    """
    Return global task timeout (minutes) from TaskConfig if set and valid.
    Value may be int or dict with 'timeout_minutes' key.
    """
    raw = get_global_task_config("timeout_minutes")
    if raw is None:
        return None
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, dict):
        v = raw.get("timeout_minutes")
        if isinstance(v, int) and v > 0:
            return v
    return None


def _str_from_config(key: str) -> Optional[str]:
    """Return non-empty string from TaskConfig for key, or None."""
    raw = get_global_task_config(key)
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, dict):
        v = raw.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def get_cleanup_crontab_from_config() -> Optional[str]:
    """Return global cleanup_crontab (5-field cron) from TaskConfig if set."""
    return _str_from_config("cleanup_crontab")


def get_mark_timeout_crontab_from_config() -> Optional[str]:
    """Return global mark_timeout_crontab (5-field cron) from TaskConfig."""
    return _str_from_config("mark_timeout_crontab")
