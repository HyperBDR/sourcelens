"""
Register this app's periodic tasks with the scheduler registry.

Called by the main project's register_periodic_tasks management command.
Registers: cleanup old LLM usage, aggregate usage series (hour/day/month).
"""
from django.conf import settings

from core.periodic_registry import TASK_REGISTRY

from agentcore_metering.adapters.django.conf import (
    DEFAULT_CLEANUP_ENABLED,
    get_aggregation_beat_schedule_init,
    get_cleanup_beat_schedule_init,
)


def register_periodic_tasks():
    enabled = getattr(
        settings,
        "AGENTCORE_METERING_CLEANUP_ENABLED",
        DEFAULT_CLEANUP_ENABLED,
    )
    if enabled:
        for name, entry in get_cleanup_beat_schedule_init().items():
            _add_entry(name, entry)
    for name, entry in get_aggregation_beat_schedule_init().items():
        _add_entry(name, entry)


def _add_entry(name, entry):
    task_name = entry.get("task")
    schedule = entry.get("schedule")
    if not task_name or schedule is None:
        return
    options = entry.get("options") or {}
    queue = options.get("queue") if isinstance(options, dict) else None
    kwargs = entry.get("kwargs") or {}
    TASK_REGISTRY.add(
        name=name,
        task=task_name,
        schedule=schedule,
        args=entry.get("args", ()),
        kwargs=kwargs,
        queue=queue,
        enabled=True,
    )
