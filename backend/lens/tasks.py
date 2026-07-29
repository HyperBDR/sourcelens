from contextlib import contextmanager
from datetime import timedelta
import logging
import uuid

from celery import shared_task
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

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
    if datasource.source_type == DataSource.SourceType.MANAGED_WORKSPACE:
        return 0
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
    metadata = task.metadata or {}
    datasource_uuid = metadata.get("datasource_uuid")
    datasource = DataSource.objects.filter(uuid=datasource_uuid).first()
    record = None
    if datasource is not None:
        record = _get_or_create_source_sync_record(datasource)

    status_value = str(result.get("status") or "failed").lower()
    success = status_value == "success"
    error = result.get("error") or "LENS_SOURCE_SYNC_FAILED"
    changed = result.get("changed")
    if changed is None:
        changed = result.get("synced")
    metrics = {
        "synced": int(result.get("synced") or 0),
        "files": int(result.get("files") or 0),
        "folders": int(result.get("folders") or 0),
        "failed": int(result.get("failed") or 0),
        "scanned": int(result.get("scanned") or 0),
        "changed": int(changed or 0),
        "skipped": int(result.get("skipped") or 0),
        "deleted": int(result.get("deleted") or 0),
        "documents": int(result.get("documents") or 0),
        "by_extension": result.get("by_extension") or {},
        "by_type": result.get("by_type") or {},
        "details": result.get("details") or {},
        "details_truncated": result.get("details_truncated") or {},
        "repository_summaries": result.get("repository_summaries") or [],
        "failed_repositories": result.get("failed_repositories") or [],
        "partial_success": bool(result.get("partial_success")),
        "target_path": result.get("target_path")
        or (datasource.target_path if datasource else ""),
    }
    conversion_summary = result.get("conversion_summary") or {}
    warnings = list(result.get("warnings") or [])
    if result.get("partial_success"):
        warnings.append("DATASOURCE_SYNC_PARTIAL_SUCCESS")
    warnings.extend(conversion_summary.get("warnings") or [])
    if conversion_summary.get("failed"):
        warnings.append("CONVERSION_PARTIAL_FAILED")
    if warnings:
        metrics["warnings"] = list(dict.fromkeys(warnings))
    result_metrics = {
        key: value
        for key, value in metrics.items()
        if key not in {"details", "details_truncated"}
    }
    if task.status in TaskStatus.get_completed_statuses():
        summary_update = {"sync_summary": metrics}
        if conversion_summary:
            summary_update["conversion_summary"] = conversion_summary
        if warnings:
            summary_update["warnings"] = list(dict.fromkeys(warnings))
        if success and not task.result:
            return TaskTracker.update_task_status(
                task_id,
                task.status,
                result=result_metrics,
                metadata=summary_update,
            )
        return TaskTracker.update_task_status(
            task_id,
            task.status,
            metadata=summary_update,
        )

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
        record.last_metrics = result_metrics if success else {}
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
        completion_metadata = _datasource_step_metadata(
            task_id,
            "completed",
            "done",
            "Datasource sync completed.",
            progress_percent=100,
        )
        completion_metadata["sync_summary"] = metrics
        if conversion_summary:
            completion_metadata["conversion_summary"] = conversion_summary
        if warnings:
            completion_metadata["warnings"] = list(dict.fromkeys(warnings))
        return TaskTracker.update_task_status(
            task_id,
            TaskStatus.SUCCESS,
            result=result_metrics,
            metadata=completion_metadata,
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
    if not acquired and _release_orphaned_datasource_lock(datasource_uuid):
        acquired = cache.add(key, token, timeout=ttl_s)
    if not acquired:
        raise SourceSyncBusy("LENS_SOURCE_SYNC_BUSY")
    return token


def _release_orphaned_datasource_lock(datasource_uuid):
    """Release a datasource lock that no running task still owns."""

    from agentcore_task.adapters.django.models import TaskExecution
    from agentcore_task.constants import TaskStatus

    key = f"lens:datasource-sync:{datasource_uuid}"
    lock_token = cache.get(key)
    if not lock_token:
        return True

    running_statuses = [TaskStatus.PENDING, *TaskStatus.get_running_statuses()]
    owner_exists = TaskExecution.objects.filter(
        module="lens_datasource",
        status__in=running_statuses,
        metadata__datasource_uuid=str(datasource_uuid),
        metadata__lock_token=lock_token,
    ).exists()
    if owner_exists:
        return False

    return release_datasource_lock(datasource_uuid, token=lock_token)


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
    sync_policy = datasource.sync_policy or {}
    conversion = sync_policy.get("conversion") or {}
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
        "sync_policy": sync_policy,
        "conversion": conversion,
        "conversion_enabled": _conversion_enabled(conversion),
        "sync_interval_seconds": (
            sync_policy
        ).get("interval_seconds"),
        "steps": [],
        "logs": [],
    }


def _conversion_enabled(conversion):
    """Return whether datasource conversion is enabled."""

    return bool(
        conversion.get("document")
        or conversion.get("image")
        or conversion.get("embedded_image")
    )


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


@shared_task(
    name="lens.check_lensnode_disconnect_grace_period",
    queue="lens",
    ignore_result=True,
)
def check_lensnode_disconnect_grace_period(lensnode_uuid, disconnected_at_iso):
    """Fail a node's runs only if it stays disconnected past the grace window.

    Scheduled once (with a countdown) by LensNodeConsumer.disconnect(). A brief
    WebSocket drop (e.g. a blue/green API recycle) must not fail runs the node
    is still executing, so failure is deferred here. disconnected_at_iso pins
    this to the disconnect episode that scheduled it: if the node reconnected
    (and maybe dropped again) since, disconnected_at has moved on and this
    stale check no-ops, leaving the newer disconnect's own check to handle it.

    Separate from the periodic idle reaper (lensnode_cleanup_task): that
    backstops genuinely stuck runs on live nodes, this handles a confirmed-gone
    node — different purposes, not merged.
    """

    scheduled_at = parse_datetime(disconnected_at_iso)

    def is_same_episode():
        # Tolerant compare: a DB that truncates sub-second precision (or any
        # round-trip skew) must not make the episode pin spuriously mismatch.
        # Real disconnects are always seconds apart (reconnect backoff), so a
        # 1s window identifies the episode unambiguously.
        if node.disconnected_at is None or scheduled_at is None:
            return False
        return abs((node.disconnected_at - scheduled_at).total_seconds()) <= 1

    try:
        node = LensNode.objects.get(uuid=lensnode_uuid)
    except LensNode.DoesNotExist:
        return

    if node.status == LensNode.Status.ONLINE:
        logger.info(
            "LensNode %s reconnected within the grace period; nothing to do",
            lensnode_uuid,
        )
        return

    if not is_same_episode():
        logger.info(
            "LensNode %s disconnected again since this check was scheduled; "
            "deferring to that episode's own check",
            lensnode_uuid,
        )
        return

    # Re-read right before acting to narrow (not eliminate) the race where the
    # node reconnects between the check above and failing its runs.
    node.refresh_from_db()
    if node.status == LensNode.Status.ONLINE or not is_same_episode():
        return

    from .services import fail_active_runs_for_lensnode

    logger.warning(
        "LensNode %s still disconnected after the grace period; failing its "
        "RUNNING/STREAMING runs",
        lensnode_uuid,
    )
    fail_active_runs_for_lensnode(lensnode_uuid)


@shared_task(
    name="lens.confirm_reconcile_orphan",
    queue="lens",
    ignore_result=True,
)
def confirm_reconcile_orphan(run_uuid):
    """Fail a run only if it's still non-terminal after the confirm window.

    Scheduled (with a countdown) by
    lens.services.schedule_reconcile_orphan_confirmation when a reconnecting
    node's hello doesn't report the run as active. LensNode redelivers
    run_done at-least-once through a durable outbox, so a run that finished
    during the drop reaches a terminal state through the normal completion
    path before this fires. The filtered update is atomic and inherently
    idempotent — no episode-pinning needed (unlike
    check_lensnode_disconnect_grace_period, which guards a shared,
    overwritable LensNode.disconnected_at field): this only ever acts on the
    one run_uuid it was scheduled for, and a run that already left
    RUNNING/STREAMING simply won't match the filter.
    """

    now = timezone.now()
    updated = Run.objects.filter(
        uuid=run_uuid,
        status__in=[Run.Status.RUNNING, Run.Status.STREAMING],
    ).update(
        status=Run.Status.FAILED,
        error="LENSNODE_RECONNECT_ORPHANED",
        finished_at=now,
        updated_at=now,
    )
    if updated:
        logger.warning(
            "Run %s still non-terminal after the reconcile confirm grace "
            "window; marking it failed (LENSNODE_RECONNECT_ORPHANED)",
            run_uuid,
        )


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

    # Reap runs that went silent (idle), not ones that are simply long but
    # still streaming: a live run refreshes last_activity_at continuously,
    # so a long answer survives as long as it keeps producing output. The
    # absolute timeout is a deliberately generous runaway ceiling that
    # still bounds a run which never stops emitting; raise it if you expect
    # single answers to legitimately exceed it.
    idle_setting = GlobalSetting.objects.filter(
        key="lensnode.defaults.idle_timeout"
    ).first()
    idle_timeout_s = int(idle_setting.value if idle_setting else 300)
    setting = GlobalSetting.objects.filter(key="lensnode.defaults.timeout").first()
    timeout_s = int(setting.value if setting else 14400)
    now = timezone.now()
    idle_cutoff = now - timedelta(seconds=idle_timeout_s)
    abs_cutoff = now - timedelta(seconds=timeout_s)
    stale = Run.objects.filter(
        status__in=[Run.Status.RUNNING, Run.Status.STREAMING],
    ).filter(
        Q(last_activity_at__lt=idle_cutoff)
        | Q(last_activity_at__isnull=True, started_at__lt=idle_cutoff)
        | Q(started_at__lt=abs_cutoff)
    )
    count = stale.count()
    stale.update(
        status=Run.Status.FAILED,
        error="LENS_RUN_TIMEOUT",
        finished_at=now,
        updated_at=now,
    )
    RunExecution.objects.filter(
        run__status=Run.Status.FAILED,
        status__in=[
            RunExecution.Status.QUEUED,
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
        "idle_timeout_s": idle_timeout_s,
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
