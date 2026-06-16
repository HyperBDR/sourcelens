from contextlib import contextmanager
from datetime import timedelta
import uuid

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from .datasource_services import dispatch_datasource_sync
from .models import (
    DataSource,
    GlobalSetting,
    LensNode,
    Run,
    RunExecution,
    ScheduledTask,
)


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


def register_datasource_sync_task(
    datasource,
    task_id,
    trigger,
    created_by=None,
):
    """Register a datasource sync execution before Celery starts it."""

    from agentcore_task.adapters.django import TaskTracker

    return TaskTracker.register_task(
        task_id=task_id,
        task_name=_datasource_sync_task_name(datasource),
        module="lens_datasource",
        task_args=[str(datasource.uuid)],
        task_kwargs={"trigger": trigger},
        created_by=created_by,
        metadata=_datasource_task_metadata(datasource, trigger),
    )


def _datasource_sync_task_name(datasource):
    """Return a readable task name for one datasource sync."""

    name = str(getattr(datasource, "name", "") or "").strip()
    if not name:
        return "datasource_sync"
    return f"datasource_sync:{name}"


def _is_global_task_enabled(task_type, default=True):
    """Return whether a global periodic task is enabled."""

    record = ScheduledTask.objects.filter(
        task_type=task_type,
        target_type=None,
        target_id=None,
    ).only("enabled").first()
    if record is None:
        return default
    return bool(record.enabled)


@shared_task(bind=True, name="lens.source_sync", queue="lens")
def source_sync_task(self, datasource_uuid, trigger="scheduled"):
    """Celery entrypoint for synchronizing a datasource on a LensNode."""

    from agentcore_task.adapters.django import TaskTracker
    from agentcore_task.constants import TaskStatus

    task_id = self.request.id or uuid.uuid4().hex
    datasource = DataSource.objects.select_related("lensnode").get(
        uuid=datasource_uuid
    )
    record = _get_or_create_source_sync_record(datasource)
    now = timezone.now()
    record.last_status = ScheduledTask.Status.RUNNING
    record.last_error = ""
    record.last_run_at = now
    record.save(update_fields=["last_status", "last_error", "last_run_at"])
    register_datasource_sync_task(datasource, task_id, trigger)
    TaskTracker.update_task_status(task_id, TaskStatus.STARTED)
    _append_datasource_task_step(
        task_id,
        "prepare",
        "running",
        "Datasource sync task started.",
    )

    try:
        with datasource_lock(datasource.uuid, ttl_s=600):
            _append_datasource_task_step(
                task_id,
                "dispatch",
                "running",
                "Dispatching datasource sync to LensNode.",
            )
            result = dispatch_datasource_sync(
                datasource,
                task_id=task_id,
                trigger=trigger,
            )
            if result.get("status") != "success":
                raise RuntimeError(
                    result.get("error") or "LENS_SOURCE_SYNC_FAILED"
                )
    except SourceSyncBusy as exc:
        record.last_status = ScheduledTask.Status.FAILED
        record.last_error = str(exc)
        record.last_run_at = timezone.now()
        record.save(update_fields=["last_status", "last_error", "last_run_at"])
        TaskTracker.update_task_status(
            task_id,
            TaskStatus.FAILURE,
            error=str(exc),
            metadata=_datasource_step_metadata(
                task_id,
                "lock",
                "failed",
                str(exc),
            ),
        )
        raise
    except Exception as exc:
        datasource.status = DataSource.Status.ERROR
        datasource.last_error = str(exc)
        datasource.save(update_fields=["status", "last_error", "updated_at"])
        record.last_status = ScheduledTask.Status.FAILED
        record.last_error = str(exc)
        record.last_run_at = timezone.now()
        record.save(update_fields=["last_status", "last_error", "last_run_at"])
        TaskTracker.update_task_status(
            task_id,
            TaskStatus.FAILURE,
            error=str(exc),
            metadata=_datasource_step_metadata(
                task_id,
                "failed",
                "failed",
                str(exc),
            ),
        )
        raise

    datasource.status = DataSource.Status.ACTIVE
    datasource.last_error = ""
    datasource.last_synced_at = timezone.now()
    datasource.save(
        update_fields=[
            "status",
            "last_error",
            "last_synced_at",
            "target_path",
            "updated_at",
        ]
    )
    synced = int(result.get("synced") or 0)
    record.last_status = ScheduledTask.Status.SUCCESS
    record.last_error = ""
    record.last_run_at = timezone.now()
    record.last_metrics = {
        "synced": synced,
        "files": result.get("files", 0),
        "target_path": result.get("target_path") or datasource.target_path,
    }
    record.save(
        update_fields=[
            "last_status",
            "last_error",
            "last_run_at",
            "last_metrics",
        ]
    )
    TaskTracker.update_task_status(
        task_id,
        TaskStatus.SUCCESS,
        result=record.last_metrics,
        metadata=_datasource_step_metadata(
            task_id,
            "completed",
            "done",
            "Datasource sync completed.",
            progress_percent=100,
        ),
    )
    return synced


def _datasource_task_metadata(datasource, trigger):
    """Return unified task metadata for datasource synchronization."""

    lensnode = datasource.lensnode
    config = datasource.config or {}
    return {
        "type": "datasource",
        "trigger": trigger,
        "datasource_uuid": str(datasource.uuid),
        "datasource_name": datasource.name,
        "source_type": datasource.source_type,
        "repo_url": config.get("repo_url", ""),
        "branch": config.get("branch", ""),
        "auth_scheme": config.get("auth_scheme", ""),
        "document_url": config.get("document_url", ""),
        "app_token": config.get("app_token", ""),
        "doc_ids": config.get("doc_ids", []),
        "sync_mode": config.get("sync_mode", ""),
        "folder_url": config.get("folder_url", ""),
        "folder_token": config.get("folder_token", ""),
        "recursive": config.get("recursive", True),
        "max_depth": config.get("max_depth", ""),
        "credential_configured": bool(datasource.credential_id),
        "lensnode_uuid": str(lensnode.uuid) if lensnode else "",
        "lensnode_name": lensnode.name if lensnode else "",
        "target_path": datasource.target_path,
        "sync_interval_seconds": (
            datasource.sync_policy or {}
        ).get("interval_seconds"),
        "steps": [],
        "logs": [],
    }


def _append_datasource_task_step(task_id, name, status, message):
    """Append one datasource task step to TaskExecution metadata."""

    from agentcore_task.adapters.django import TaskTracker
    from agentcore_task.constants import TaskStatus

    TaskTracker.update_task_status(
        task_id,
        TaskStatus.STARTED,
        metadata=_datasource_step_metadata(task_id, name, status, message),
    )


def _datasource_step_metadata(
    task_id,
    name,
    status,
    message,
    progress_percent=None,
):
    """Return metadata with an appended datasource task step."""

    from agentcore_task.adapters.django.models import TaskExecution

    task = TaskExecution.objects.filter(task_id=task_id).first()
    metadata = dict(task.metadata or {}) if task else {}
    steps = list(metadata.get("steps") or [])
    steps.append(
        {
            "name": name,
            "status": status,
            "message": message,
            "timestamp": timezone.now().isoformat(),
        }
    )
    result = {
        "steps": steps,
        "progress_step": name,
        "progress_message": message,
    }
    if progress_percent is not None:
        result["progress_percent"] = progress_percent
    return result


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

    if not _is_global_task_enabled(ScheduledTask.TaskType.LENSNODE_HEALTH):
        return 0

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

    if not _is_global_task_enabled(ScheduledTask.TaskType.LENSNODE_CLEANUP):
        return 0

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

    if not _is_global_task_enabled(ScheduledTask.TaskType.RUN_RETENTION):
        return 0

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
