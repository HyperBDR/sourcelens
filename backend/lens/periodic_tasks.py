from core.periodic_registry import TASK_REGISTRY

from .models import DataSource, ScheduledTask


def _ensure_global_scheduled_task(task_type):
    """Create the UI mirror row for a global periodic task."""

    ScheduledTask.objects.get_or_create(
        task_type=task_type,
        target_type=None,
        target_id=None,
        defaults={"name": task_type, "enabled": True},
    )


def _ensure_source_scheduled_task(datasource):
    """Create the UI mirror row for a datasource periodic task."""

    record, _ = ScheduledTask.objects.get_or_create(
        task_type=ScheduledTask.TaskType.SOURCE_SYNC,
        target_type="datasource",
        target_id=datasource.uuid,
        defaults={
            "name": f"source_sync:{datasource.uuid}",
            "enabled": True,
        },
    )
    return record


def ensure_datasource_periodic_task(datasource):
    """Create missing Celery Beat and UI rows for a datasource sync."""

    if datasource.status == DataSource.Status.DISABLED:
        _disable_datasource_periodic_task(datasource)
        return None

    from django_celery_beat.models import (
        IntervalSchedule,
        PeriodicTask,
        PeriodicTasks,
    )

    interval = datasource.sync_policy.get("interval_seconds", 3600)
    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=max(int(interval), 1),
        period=IntervalSchedule.SECONDS,
    )
    name = f"lens-source-sync-{datasource.uuid}"
    task, created = PeriodicTask.objects.get_or_create(
        name=name,
        defaults={
            "task": "lens.source_sync",
            "interval": schedule,
            "args": f'["{datasource.uuid}"]',
            "queue": "lens",
            "enabled": True,
        },
    )
    if created:
        PeriodicTasks.update_changed()

    record = _ensure_source_scheduled_task(datasource)
    if record.periodic_task_ref != task.id:
        record.periodic_task_ref = task.id
    if not record.enabled:
        record.enabled = True
    record.save(update_fields=["periodic_task_ref", "enabled"])
    return record


def _disable_datasource_periodic_task(datasource):
    from django_celery_beat.models import PeriodicTask, PeriodicTasks

    name = f"lens-source-sync-{datasource.uuid}"
    task = PeriodicTask.objects.filter(name=name).first()
    if task is not None and task.enabled:
        task.enabled = False
        task.save(update_fields=["enabled"])
        PeriodicTasks.update_changed()

    ScheduledTask.objects.filter(
        task_type=ScheduledTask.TaskType.SOURCE_SYNC,
        target_type="datasource",
        target_id=datasource.uuid,
    ).update(enabled=False)


def register_periodic_tasks():
    """Register Lens periodic tasks in the project registry."""

    global_tasks = [
        (
            ScheduledTask.TaskType.LENSNODE_CLEANUP,
            "lens-lensnode-cleanup",
            "lens.lensnode_cleanup",
            3600,
        ),
        (
            ScheduledTask.TaskType.LENSNODE_HEALTH,
            "lens-lensnode-health",
            "lens.lensnode_health",
            60,
        ),
        (
            ScheduledTask.TaskType.RUN_RETENTION,
            "lens-run-retention",
            "lens.run_retention",
            86400,
        ),
    ]
    for task_type, name, task, schedule in global_tasks:
        _ensure_global_scheduled_task(task_type)
        TASK_REGISTRY.add(
            name=name,
            task=task,
            schedule=schedule,
            queue="lens",
            enabled=True,
        )

    datasources = DataSource.objects.filter(
        status__in=[DataSource.Status.ACTIVE, DataSource.Status.ERROR]
    )
    for datasource in datasources:
        interval = datasource.sync_policy.get("interval_seconds", 3600)
        _ensure_source_scheduled_task(datasource)
        TASK_REGISTRY.add(
            name=f"lens-source-sync-{datasource.uuid}",
            task="lens.source_sync",
            schedule=interval,
            args=(str(datasource.uuid),),
            queue="lens",
            enabled=True,
        )


def sync_registered_periodic_tasks():
    """Backfill django-celery-beat PeriodicTask IDs into ScheduledTask."""

    from django_celery_beat.models import PeriodicTask

    mappings = [
        (
            ScheduledTask.TaskType.LENSNODE_CLEANUP,
            None,
            None,
            "lens-lensnode-cleanup",
        ),
        (
            ScheduledTask.TaskType.LENSNODE_HEALTH,
            None,
            None,
            "lens-lensnode-health",
        ),
        (
            ScheduledTask.TaskType.RUN_RETENTION,
            None,
            None,
            "lens-run-retention",
        ),
    ]
    for datasource in DataSource.objects.all():
        mappings.append(
            (
                ScheduledTask.TaskType.SOURCE_SYNC,
                "datasource",
                datasource.uuid,
                f"lens-source-sync-{datasource.uuid}",
            )
        )

    for task_type, target_type, target_id, name in mappings:
        periodic_task = PeriodicTask.objects.filter(name=name).first()
        if periodic_task is None:
            continue
        ScheduledTask.objects.filter(
            task_type=task_type,
            target_type=target_type,
            target_id=target_id,
        ).update(periodic_task_ref=periodic_task.id)
