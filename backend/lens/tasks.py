from contextlib import contextmanager
from datetime import timedelta
import uuid

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from .models import (
    DataSource,
    GlobalSetting,
    LensNode,
    Run,
    RunExecution,
    ScheduledTask,
)
from .source_sync import sync_datasource


@shared_task(name="lens.execute_answer_run", queue="lens")
def execute_answer_run(run_uuid):
    """Celery entrypoint for executing a Lens run."""

    from .execution import execute_answer_run as execute_answer_run_service

    run = Run.objects.select_related(
        "session",
        "session__assistant",
        "session__assistant__lensnode",
        "input_message",
        "output_message",
        "lensnode",
    ).get(uuid=run_uuid)
    execute_answer_run_service(run)
    return str(run.uuid)


def _get_or_create_source_sync_record(datasource):
    """Return the ScheduledTask mirror for a datasource sync."""

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


def _get_or_create_global_record(task_type):
    """Return the ScheduledTask mirror for a global lens task."""

    record, _ = ScheduledTask.objects.get_or_create(
        task_type=task_type,
        target_type=None,
        target_id=None,
        defaults={
            "name": task_type,
            "enabled": True,
        },
    )
    return record


@shared_task(name="lens.source_sync", queue="lens")
def source_sync_task(datasource_uuid):
    """Celery entrypoint for synchronizing a datasource."""

    datasource = DataSource.objects.get(uuid=datasource_uuid)
    record = _get_or_create_source_sync_record(datasource)
    now = timezone.now()
    record.last_status = ScheduledTask.Status.RUNNING
    record.last_error = ""
    record.last_run_at = now
    record.save(update_fields=["last_status", "last_error", "last_run_at"])

    try:
        with datasource_lock(datasource.uuid, ttl_s=600):
            synced = sync_datasource(datasource)
    except SourceSyncBusy as exc:
        record.last_status = ScheduledTask.Status.FAILED
        record.last_error = str(exc)
        record.last_run_at = timezone.now()
        record.save(update_fields=["last_status", "last_error", "last_run_at"])
        raise
    except Exception as exc:
        datasource.status = DataSource.Status.ERROR
        datasource.save(update_fields=["status", "updated_at"])
        record.last_status = ScheduledTask.Status.FAILED
        record.last_error = str(exc)
        record.last_run_at = timezone.now()
        record.save(update_fields=["last_status", "last_error", "last_run_at"])
        raise

    datasource.status = DataSource.Status.ACTIVE
    datasource.last_synced_at = timezone.now()
    datasource.save(
        update_fields=[
            "status",
            "last_synced_at",
            "target_path",
            "updated_at",
        ]
    )
    record.last_status = ScheduledTask.Status.SUCCESS
    record.last_error = ""
    record.last_run_at = timezone.now()
    record.last_metrics = {"synced": synced}
    record.save(
        update_fields=[
            "last_status",
            "last_error",
            "last_run_at",
            "last_metrics",
        ]
    )
    return synced


class SourceSyncBusy(RuntimeError):
    """Raised when a datasource already has an active sync lock."""


@contextmanager
def datasource_lock(datasource_uuid, ttl_s=600):
    """Acquire an expiring sync lock for one datasource."""

    key = f"lens:datasource-sync:{datasource_uuid}"
    token = uuid.uuid4().hex
    acquired = cache.add(key, token, timeout=ttl_s)
    if not acquired:
        raise SourceSyncBusy("LENS_SOURCE_SYNC_BUSY")
    try:
        yield
    finally:
        if cache.get(key) == token:
            cache.delete(key)


@shared_task(name="lens.lensnode_health", queue="lens")
def lensnode_health_task():
    """Mark stale online LensNodes offline based on heartbeat age."""

    record = _get_or_create_global_record(ScheduledTask.TaskType.LENSNODE_HEALTH)
    record.last_status = ScheduledTask.Status.RUNNING
    record.last_error = ""
    record.last_run_at = timezone.now()
    record.save(update_fields=["last_status", "last_error", "last_run_at"])

    setting = GlobalSetting.objects.filter(
        key="lensnode.health.offline_threshold_s"
    ).first()
    threshold_s = int(setting.value if setting else 60)
    cutoff = timezone.now() - timedelta(seconds=threshold_s)
    updated = LensNode.objects.filter(
        status=LensNode.Status.ONLINE,
        last_heartbeat_at__lt=cutoff,
    ).update(
        status=LensNode.Status.OFFLINE,
        connection_id="",
        updated_at=timezone.now(),
    )

    record.last_status = ScheduledTask.Status.SUCCESS
    record.last_metrics = {
        "offline": updated,
        "threshold_s": threshold_s,
    }
    record.last_run_at = timezone.now()
    record.save(update_fields=["last_status", "last_metrics", "last_run_at"])
    return updated


@shared_task(name="lens.lensnode_cleanup", queue="lens")
def lensnode_cleanup_task():
    """Fail stale non-terminal runs that no LensNode has completed."""

    record = _get_or_create_global_record(ScheduledTask.TaskType.LENSNODE_CLEANUP)
    record.last_status = ScheduledTask.Status.RUNNING
    record.last_error = ""
    record.last_run_at = timezone.now()
    record.save(update_fields=["last_status", "last_error", "last_run_at"])

    setting = GlobalSetting.objects.filter(key="lensnode.defaults.timeout").first()
    timeout_s = int(setting.value if setting else 3600)
    cutoff = timezone.now() - timedelta(seconds=timeout_s)
    stale = Run.objects.filter(
        status__in=[Run.Status.RUNNING, Run.Status.STREAMING],
        started_at__lt=cutoff,
    )
    count = stale.count()
    stale.update(
        status=Run.Status.FAILED,
        error="LENS_RUN_TIMEOUT",
        finished_at=timezone.now(),
        updated_at=timezone.now(),
    )
    RunExecution.objects.filter(
        run__status=Run.Status.FAILED,
        status__in=[
            RunExecution.Status.DISPATCHED,
            RunExecution.Status.RUNNING,
        ],
    ).update(
        status=RunExecution.Status.FAILED,
        finished_at=timezone.now(),
    )

    record.last_status = ScheduledTask.Status.SUCCESS
    record.last_metrics = {
        "failed": count,
        "timeout_s": timeout_s,
    }
    record.last_run_at = timezone.now()
    record.save(update_fields=["last_status", "last_metrics", "last_run_at"])
    return count


@shared_task(name="lens.run_retention", queue="lens")
def run_retention_task():
    """Celery entrypoint for deleting old terminal runs."""

    record = _get_or_create_global_record(ScheduledTask.TaskType.RUN_RETENTION)
    record.last_status = ScheduledTask.Status.RUNNING
    record.last_error = ""
    record.last_run_at = timezone.now()
    record.save(update_fields=["last_status", "last_error", "last_run_at"])

    setting = GlobalSetting.objects.filter(key="retention.run_days").first()
    retention_days = setting.value if setting else 30
    cutoff = timezone.now() - timedelta(days=int(retention_days))

    deleted, _ = Run.objects.filter(
        status__in=[
            Run.Status.DONE,
            Run.Status.FAILED,
            Run.Status.CANCELLED,
        ],
        finished_at__lt=cutoff,
    ).delete()

    record.last_status = ScheduledTask.Status.SUCCESS
    record.last_metrics = {
        "deleted": deleted,
        "retention_days": retention_days,
    }
    record.last_run_at = timezone.now()
    record.save(update_fields=["last_status", "last_metrics", "last_run_at"])
    return deleted
