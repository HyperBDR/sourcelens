"""
Registry for periodic tasks. Apps register entries via
register_periodic_tasks(); apply_registry() writes them to
django_celery_beat. Existing rows are left untouched.

No Django signals; intended to be called from a CLI so the flow is portable
(e.g. future FastAPI migration).
"""
import json
import logging

logger = logging.getLogger(__name__)


def _is_crontab_schedule(schedule):
    return hasattr(schedule, "_orig_minute")


def _get_or_create_crontab(schedule):
    from django_celery_beat.models import CrontabSchedule
    from django.conf import settings

    try:
        obj, created = CrontabSchedule.from_schedule(schedule)
        if created:
            obj.save()
    except (AttributeError, TypeError):
        tz = getattr(schedule, "tz", None) or getattr(
            settings, "CELERY_TIMEZONE", None
        )
        spec = {
            "minute": getattr(schedule, "_orig_minute", "*"),
            "hour": getattr(schedule, "_orig_hour", "*"),
            "day_of_week": getattr(schedule, "_orig_day_of_week", "*"),
            "day_of_month": getattr(schedule, "_orig_day_of_month", "*"),
            "month_of_year": getattr(schedule, "_orig_month_of_year", "*"),
        }
        if tz:
            spec["timezone"] = tz
        obj, _ = CrontabSchedule.objects.get_or_create(**spec)
    return obj


def _get_or_create_interval_seconds(seconds):
    from django_celery_beat.models import IntervalSchedule

    every = max(int(seconds), 1)
    obj, _ = IntervalSchedule.objects.get_or_create(
        every=every,
        period=IntervalSchedule.SECONDS,
    )
    return obj


class TaskRegistry:
    """
    In-memory registry of periodic task definitions.

    Apps add entries via add(); apply() writes them to django_celery_beat.
    New tasks are created with full defaults. Existing tasks are left
    untouched so database-side customisations are preserved.
    """

    def __init__(self):
        self._entries = {}

    def clear(self):
        self._entries.clear()

    def __len__(self):
        return len(self._entries)

    def add(
        self,
        name,
        task,
        schedule,
        args=(),
        kwargs=None,
        queue=None,
        enabled=True,
    ):
        """
        Register a periodic task.

        name: unique identifier (e.g. "agentcore-task-mark-timed-out")
        task: Celery task name (e.g. agentcore_task.adapters.django.tasks...)
        schedule: celery.schedules.crontab, or number (seconds), or schedule
        args, kwargs: passed to the task
        queue: optional queue name
        enabled: whether the PeriodicTask is enabled
        """
        self._entries[name] = {
            "task": task,
            "schedule": schedule,
            "args": tuple(args) if args else (),
            "kwargs": dict(kwargs) if kwargs else {},
            "queue": queue,
            "enabled": enabled,
        }

    def _apply_one(self, name, entry):
        from django_celery_beat.models import PeriodicTask, PeriodicTasks

        task_name = entry["task"]
        schedule = entry["schedule"]
        args = entry["args"]
        kwargs = entry["kwargs"]
        queue = entry["queue"]
        enabled = entry["enabled"]

        if _is_crontab_schedule(schedule):
            crontab_schedule = _get_or_create_crontab(schedule)
            interval_schedule = None
        elif isinstance(schedule, (int, float)):
            interval_schedule = _get_or_create_interval_seconds(schedule)
            crontab_schedule = None
        else:
            run_every = getattr(schedule, "run_every", None)
            if run_every is not None:
                secs = run_every.total_seconds()
                interval_schedule = _get_or_create_interval_seconds(secs)
                crontab_schedule = None
            else:
                crontab_schedule = _get_or_create_crontab(schedule)
                interval_schedule = None

        create_defaults = {
            "task": task_name,
            "args": json.dumps(list(args)),
            "kwargs": json.dumps(kwargs),
            "queue": queue,
            "enabled": enabled,
        }
        if crontab_schedule is not None:
            create_defaults["crontab"] = crontab_schedule
            create_defaults["interval"] = None
        else:
            create_defaults["interval"] = interval_schedule
            create_defaults["crontab"] = None

        obj, created = PeriodicTask.objects.get_or_create(
            name=name, defaults=create_defaults
        )
        if not created:
            logger.debug(
                "Periodic task already exists, skipping update: %s",
                name,
            )
            return False

        PeriodicTasks.update_changed()
        return True

    def apply(self):
        """
        Write all registered entries to django_celery_beat.

        Existing rows are skipped so database-side edits are preserved.
        """
        for name, entry in self._entries.items():
            try:
                created = self._apply_one(name, entry)
                if created:
                    logger.debug(f"Registered periodic task: {name}")
                else:
                    logger.debug(f"Skipped existing periodic task: {name}")
            except Exception as e:
                logger.exception(
                    f"Failed to register periodic task {name}: {e}"
                )


TASK_REGISTRY = TaskRegistry()


def apply_registry():
    """Apply the global TASK_REGISTRY to django_celery_beat."""
    TASK_REGISTRY.apply()

