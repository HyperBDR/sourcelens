from contextlib import contextmanager
from datetime import timedelta
import logging
import uuid

from celery import shared_task
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from .datasource_services import (
    dispatch_datasource_sync_async,
    get_datasource_sync_timeout_s,
)
from .models import (
    DataSource,
    GlobalSetting,
    LensNode,
    Run,
    RunExecution,
    ScheduledTask,
)

logger = logging.getLogger(__name__)


@shared_task(name="lens.execute_answer_run", queue="lens")
def execute_answer_run(run_uuid):
    """Celery entrypoint for executing a Lens run."""

    logger.info("task execute_answer_run received: run_uuid=%s", run_uuid)
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
    metadata=None,
):
    """Register a datasource sync execution before Celery starts it."""

    from agentcore_task.adapters.django import TaskTracker

    task_metadata = _datasource_task_metadata(datasource, trigger)
    task_metadata.update(metadata or {})
    return TaskTracker.register_task(
        task_id=task_id,
        task_name=_datasource_sync_task_name(datasource),
        module="lens_datasource",
        task_args=[str(datasource.uuid)],
        task_kwargs={"trigger": trigger},
        created_by=created_by,
        metadata=task_metadata,
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
def source_sync_task(self, datasource_uuid, trigger="scheduled", task_id=None):
    """Celery entrypoint for dispatching datasource sync to a LensNode."""

    from agentcore_task.adapters.django import TaskTracker
    from agentcore_task.constants import TaskStatus

    # Track this run under a standalone id, not the Celery task id. The
    # Celery task returns SUCCESS right after dispatching to the LensNode,
    # so a tracked id equal to the Celery id would let the periodic sync
    # mark the run complete prematurely. With a standalone id Celery reports
    # PENDING (unknown id) and the LensNode completion callback owns the
    # final status.
    task_id = task_id or uuid.uuid4().hex
    datasource = DataSource.objects.select_related("lensnode").get(
        uuid=datasource_uuid
    )
    record = _get_or_create_source_sync_record(datasource)
    if datasource.status == DataSource.Status.DISABLED:
        if record.enabled:
            record.enabled = False
            record.save(update_fields=["enabled"])
        return 0

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
        acquire_datasource_lock(
            datasource.uuid,
            token=task_id,
            ttl_s=get_datasource_sync_timeout_s(),
        )
        _append_datasource_task_step(
            task_id,
            "dispatch",
            "running",
            "Dispatching datasource sync to LensNode.",
        )
        request_id = dispatch_datasource_sync_async(
            datasource,
            task_id=task_id,
            trigger=trigger,
        )
        TaskTracker.update_task_status(
            task_id,
            TaskStatus.STARTED,
            metadata={
                "completion_source": "lensnode_callback",
                "datasource_sync_request_id": request_id,
                "lock_token": task_id,
            },
        )
    except SourceSyncBusy as exc:
        record.last_error = str(exc)
        record.last_run_at = timezone.now()
        record.save(update_fields=["last_error", "last_run_at"])
        TaskTracker.update_task_status(
            task_id,
            TaskStatus.REVOKED,
            error=str(exc),
            metadata=_datasource_step_metadata(
                task_id,
                "lock",
                "skipped",
                str(exc),
            ),
        )
        return 0
    except Exception as exc:
        release_datasource_lock(datasource.uuid, token=task_id)
        datasource.last_error = str(exc)
        datasource.save(update_fields=["last_error", "updated_at"])
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

    return 0


def complete_datasource_sync_task(task_id, result):
    """Complete a datasource sync after LensNode reports final status."""

    from agentcore_task.adapters.django import TaskTracker
    from agentcore_task.adapters.django.models import TaskExecution
    from agentcore_task.constants import TaskStatus

    task = TaskExecution.objects.filter(task_id=task_id).first()
    if task is None:
        return None
    if task.status in TaskStatus.get_completed_statuses():
        return task

    metadata = task.metadata or {}
    datasource_uuid = metadata.get("datasource_uuid")
    datasource = DataSource.objects.filter(uuid=datasource_uuid).first()
    record = None
    if datasource is not None:
        record = _get_or_create_source_sync_record(datasource)

    status_value = str(result.get("status") or "failed").lower()
    success = status_value == "success"
    error = result.get("error") or "LENS_SOURCE_SYNC_FAILED"
    metrics = {
        "synced": int(result.get("synced") or 0),
        "files": int(result.get("files") or 0),
        "folders": int(result.get("folders") or 0),
        "failed": int(result.get("failed") or 0),
        "target_path": result.get("target_path")
        or (datasource.target_path if datasource else ""),
    }

    if datasource is not None:
        if success:
            datasource.last_error = ""
            datasource.last_synced_at = timezone.now()
            if metrics["target_path"]:
                datasource.target_path = metrics["target_path"]
            datasource.save(
                update_fields=[
                    "last_error",
                    "last_synced_at",
                    "target_path",
                    "updated_at",
                ]
            )
        else:
            datasource.last_error = error
            datasource.save(update_fields=["last_error", "updated_at"])

    if record is not None:
        record.last_status = (
            ScheduledTask.Status.SUCCESS
            if success
            else ScheduledTask.Status.FAILED
        )
        record.last_error = "" if success else error
        record.last_run_at = timezone.now()
        record.last_metrics = metrics if success else {}
        record.save(
            update_fields=[
                "last_status",
                "last_error",
                "last_run_at",
                "last_metrics",
            ]
        )

    lock_token = metadata.get("lock_token")
    if datasource_uuid and lock_token:
        release_datasource_lock(
            datasource_uuid,
            token=lock_token,
        )

    if success:
        return TaskTracker.update_task_status(
            task_id,
            TaskStatus.SUCCESS,
            result=metrics,
            metadata=_datasource_step_metadata(
                task_id,
                "completed",
                "done",
                "Datasource sync completed.",
                progress_percent=100,
            ),
        )

    return TaskTracker.update_task_status(
        task_id,
        TaskStatus.FAILURE,
        error=error,
        metadata=_datasource_step_metadata(
            task_id,
            "failed",
            "failed",
            error,
        ),
    )


def resolve_datasource_sync_task_id(request_id, content):
    """Resolve a datasource sync task id from callback content."""

    task_id = content.get("task_id") or ""
    if task_id:
        return task_id

    cached_task_id = cache.get(f"lens:datasource_sync_request:{request_id}")
    if cached_task_id:
        return cached_task_id

    from agentcore_task.adapters.django.models import TaskExecution

    task = TaskExecution.objects.filter(
        module="lens_datasource",
        metadata__datasource_sync_request_id=request_id,
    ).first()
    return task.task_id if task else ""


def acquire_datasource_lock(datasource_uuid, token, ttl_s=600):
    """Acquire an expiring sync lock for one datasource."""

    key = f"lens:datasource-sync:{datasource_uuid}"
    acquired = cache.add(key, token, timeout=ttl_s)
    if not acquired:
        raise SourceSyncBusy("LENS_SOURCE_SYNC_BUSY")
    return token


def release_datasource_lock(datasource_uuid, token=None):
    """Release a datasource sync lock when ownership is known."""

    key = f"lens:datasource-sync:{datasource_uuid}"
    if token is None or cache.get(key) == token:
        cache.delete(key)
        return True
    return False


def cleanup_stale_datasource_sync_tasks(startup=False):
    """Cancel timed-out datasource syncs and release orphaned sync locks.

    Datasource sync work is completed by LensNode callback after this Celery
    task has dispatched it. A worker restart does not mean the external sync
    was interrupted, so startup cleanup still honors the configured timeout.
    """

    from agentcore_task.adapters.django.models import TaskExecution
    from agentcore_task.constants import TaskStatus

    from .services import cancel_datasource_sync_on_lensnode

    now = timezone.now()
    timeout_s = get_datasource_sync_timeout_s()
    cutoff = now - timedelta(seconds=timeout_s)
    running_statuses = [TaskStatus.PENDING, *TaskStatus.get_running_statuses()]

    stale = TaskExecution.objects.filter(
        module="lens_datasource",
        status__in=running_statuses,
        metadata__datasource_uuid__isnull=False,
    ).filter(
        Q(started_at__lt=cutoff)
        | Q(started_at__isnull=True, created_at__lt=cutoff)
    )

    failed_count = 0
    for task in stale:
        metadata = dict(task.metadata or {})
        datasource_uuid = metadata.get("datasource_uuid")
        datasource = DataSource.objects.filter(uuid=datasource_uuid).first()
        if datasource is not None:
            cancel_datasource_sync_on_lensnode(
                datasource.lensnode,
                task.task_id,
            )
            record = _get_or_create_source_sync_record(datasource)
            record.last_status = ScheduledTask.Status.FAILED
            record.last_error = "LENS_SOURCE_SYNC_TIMEOUT"
            record.last_run_at = now
            record.save(
                update_fields=["last_status", "last_error", "last_run_at"]
            )

        release_datasource_lock(
            datasource_uuid,
            token=metadata.get("lock_token") or task.task_id,
        )
        metadata["timeout_cancelled_at"] = now.isoformat()
        task.status = TaskStatus.FAILURE
        task.finished_at = now
        task.error = "LENS_SOURCE_SYNC_TIMEOUT"
        task.metadata = metadata
        task.save(
            update_fields=["status", "finished_at", "error", "metadata"]
        )
        failed_count += 1

    completed = TaskExecution.objects.filter(
        module="lens_datasource",
        status__in=TaskStatus.get_completed_statuses(),
        metadata__datasource_uuid__isnull=False,
        metadata__lock_token__isnull=False,
        finished_at__gte=cutoff,
    )
    released_count = 0
    for task in completed:
        metadata = task.metadata or {}
        datasource_uuid = metadata.get("datasource_uuid")
        released = release_datasource_lock(
            datasource_uuid,
            token=metadata.get("lock_token"),
        )
        if released:
            released_count += 1
        if released and task.status in [
            TaskStatus.FAILURE,
            TaskStatus.REVOKED,
        ]:
            datasource = DataSource.objects.filter(
                uuid=datasource_uuid
            ).first()
            if datasource is not None:
                cancel_datasource_sync_on_lensnode(
                    datasource.lensnode,
                    task.task_id,
                )

    return {
        "failed": failed_count,
        "locks_released": released_count,
        "timeout_s": timeout_s,
        "startup": startup,
    }


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

    token = uuid.uuid4().hex
    acquire_datasource_lock(datasource_uuid, token=token, ttl_s=ttl_s)
    try:
        yield
    finally:
        release_datasource_lock(datasource_uuid, token=token)


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
    datasource_sync_metrics = cleanup_stale_datasource_sync_tasks()

    record.last_status = ScheduledTask.Status.SUCCESS
    record.last_metrics = {
        "failed": count,
        "timeout_s": timeout_s,
        "datasource_sync": datasource_sync_metrics,
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
