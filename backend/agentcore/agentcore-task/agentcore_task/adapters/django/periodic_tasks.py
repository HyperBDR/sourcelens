"""
Register this app's periodic tasks with the scheduler registry.

Called by the main project's register_periodic_tasks management command.
"""
from core.periodic_registry import TASK_REGISTRY

from agentcore_task.adapters.django.conf import (
    get_cleanup_beat_schedule_init,
    get_cleanup_enabled,
    get_mark_timeout_beat_schedule_init,
    get_mark_timeout_enabled,
)


def register_periodic_tasks():
    if get_cleanup_enabled():
        for name, entry in get_cleanup_beat_schedule_init().items():
            _add_entry(name, entry)
    if get_mark_timeout_enabled():
        for name, entry in get_mark_timeout_beat_schedule_init().items():
            _add_entry(name, entry)


def _add_entry(name, entry):
    task_name = entry.get("task")
    schedule = entry.get("schedule")
    if not task_name or schedule is None:
        return
    options = entry.get("options") or {}
    queue = options.get("queue") if isinstance(options, dict) else None
    TASK_REGISTRY.add(
        name=name,
        task=task_name,
        schedule=schedule,
        args=entry.get("args", ()),
        kwargs=entry.get("kwargs"),
        queue=queue,
        enabled=True,
    )
