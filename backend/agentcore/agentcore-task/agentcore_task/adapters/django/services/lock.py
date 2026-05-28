"""
Task lock: prevent duplicate task execution.
Public API: import from agentcore_task.adapters.django.
"""
import hashlib
import logging
from typing import Optional

from django.core.cache import cache

logger = logging.getLogger(__name__)

DEFAULT_TASK_TIMEOUT = 3600
LOCK_KEY_PREFIX = "agentcore_task_task_lock"


def acquire_task_lock(lock_name: str, timeout: int = DEFAULT_TASK_TIMEOUT):
    """
    Acquire a task lock by name. Returns True if acquired, False if already
    held or on error.
    """
    lock_key = f"{LOCK_KEY_PREFIX}:{lock_name}"
    try:
        acquired = cache.add(lock_key, "locked", timeout=timeout)
        if acquired:
            logger.info(f"Acquired task lock lock_name={lock_name}")
        else:
            logger.warning(f"Task lock already exists lock_name={lock_name}")
        return acquired
    except Exception as exc:
        logger.error(
            f"Failed to acquire task lock lock_name={lock_name}: {exc}"
        )
        return False


def release_task_lock(lock_name: str):
    """Release a task lock by name. Returns True on success, False on error."""
    lock_key = f"{LOCK_KEY_PREFIX}:{lock_name}"
    try:
        cache.delete(lock_key)
        logger.info(f"Released task lock lock_name={lock_name}")
        return True
    except Exception as exc:
        logger.error(
            f"Failed to release task lock lock_name={lock_name}: {exc}"
        )
        return False


def is_task_locked(lock_name: str):
    """Return True if the given task lock is currently held, else False."""
    lock_key = f"{LOCK_KEY_PREFIX}:{lock_name}"
    try:
        return cache.get(lock_key) is not None
    except Exception as exc:
        logger.error(
            f"Failed to check task lock lock_name={lock_name}: {exc}"
        )
        return False


def _extract_lock_param_value(args, kwargs, lock_param):
    param_value = kwargs.get(lock_param)
    if not param_value and args:
        if hasattr(args[0], "request"):
            param_value = args[1] if len(args) > 1 else None
        else:
            param_value = args[0]
    return param_value


def _build_task_lock_name(lock_name, lock_param, param_value):
    if not param_value:
        return lock_name
    param_str = str(param_value)
    if len(param_str) > 200:
        h = hashlib.md5(param_str.encode("utf-8")).hexdigest()[:16]
        return f"{lock_name}_{h}"
    return f"{lock_name}_{param_value}"


def prevent_duplicate_task(
    lock_name: str,
    timeout: int = DEFAULT_TASK_TIMEOUT,
    lock_param: Optional[str] = None,
):
    """
    Decorator to prevent duplicate task execution: acquires lock before run,
    releases after. Returns skip payload if lock exists or acquisition fails.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            task_lock_name = lock_name
            if lock_param:
                pv = _extract_lock_param_value(args, kwargs, lock_param)
                if pv is not None:
                    task_lock_name = _build_task_lock_name(
                        lock_name, lock_param, pv
                    )
                else:
                    logger.warning(
                        f"Could not extract lock_param={lock_param}, "
                        f"using lock_name={lock_name}"
                    )
            if is_task_locked(task_lock_name):
                return {
                    "success": False,
                    "status": "skipped",
                    "reason": "task_already_running",
                    "error": f"Task {task_lock_name} is already running",
                }
            if not acquire_task_lock(task_lock_name, timeout):
                return {
                    "success": False,
                    "status": "skipped",
                    "reason": "lock_acquisition_failed",
                    "error": f"Failed to acquire lock for {task_lock_name}",
                }
            try:
                return func(*args, **kwargs)
            finally:
                release_task_lock(task_lock_name)
        wrapper.__name__ = func.__name__
        wrapper.__module__ = func.__module__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator
