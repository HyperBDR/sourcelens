# Django adapter: full Django app for task execution tracking.
# Public API: import from here (lazy to avoid AppRegistryNotReady).
# Each symbol is loaded from its defining module (metering-style).

__all__ = [
    "TaskTracker",
    "register_task_execution",
    "get_task_stats",
    "list_task_executions",
    "acquire_task_lock",
    "release_task_lock",
    "is_task_locked",
    "prevent_duplicate_task",
    "TaskStatus",
    "TaskLogCollector",
    "cleanup_old_executions",
    "cleanup_old_task_executions",
    "mark_timed_out_executions",
    "mark_timed_out_task_executions",
    "get_cleanup_beat_schedule",
]

_BASE = "agentcore_task.adapters.django"
_SUBMODULES = (
    "admin",
    "conf",
    "models",
    "serializers",
    "services",
    "tasks",
    "urls",
    "utils",
    "views",
)
_SYMBOLS = (
    ("TaskTracker", f"{_BASE}.services.task_tracker", "TaskTracker"),
    (
        "register_task_execution",
        f"{_BASE}.services.task_tracker",
        "register_task_execution",
    ),
    ("get_task_stats", f"{_BASE}.services.task_stats", "get_task_stats"),
    (
        "list_task_executions",
        f"{_BASE}.services.task_stats",
        "list_task_executions",
    ),
    ("acquire_task_lock", f"{_BASE}.services.task_lock", "acquire_task_lock"),
    ("release_task_lock", f"{_BASE}.services.task_lock", "release_task_lock"),
    ("is_task_locked", f"{_BASE}.services.task_lock", "is_task_locked"),
    (
        "prevent_duplicate_task",
        f"{_BASE}.services.task_lock",
        "prevent_duplicate_task",
    ),
    ("TaskStatus", "agentcore_task.constants", "TaskStatus"),
    (
        "TaskLogCollector",
        f"{_BASE}.services.log_collector",
        "TaskLogCollector",
    ),
    (
        "cleanup_old_executions",
        f"{_BASE}.services.cleanup",
        "cleanup_old_executions",
    ),
    (
        "mark_timed_out_executions",
        f"{_BASE}.services.timeout",
        "mark_timed_out_executions",
    ),
    (
        "cleanup_old_task_executions",
        f"{_BASE}.tasks",
        "cleanup_old_task_executions",
    ),
    (
        "mark_timed_out_task_executions",
        f"{_BASE}.tasks",
        "mark_timed_out_task_executions",
    ),
    (
        "get_cleanup_beat_schedule",
        f"{_BASE}.conf",
        "get_cleanup_beat_schedule",
    ),
)
_LAZY = {name: (mod, attr) for name, mod, attr in _SYMBOLS}


def __getattr__(name):
    from importlib import import_module

    if name in _SUBMODULES:
        return import_module(f".{name}", __name__)
    if name in _LAZY:
        mod_path, attr = _LAZY[name]
        mod = import_module(mod_path)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
