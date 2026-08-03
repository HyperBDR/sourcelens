"""Datasource CRUD, search, and synchronization views."""

import json
import uuid as uuid_mod

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from lens.datasource_archives import (
    delete_datasource_archive,
    store_datasource_archive,
)
from lens.datasource_services import (
    DataSourceDispatchError,
    DataSourcePathError,
    check_datasource_path,
)
from lens.models import DataSource, ScheduledTask
from lens.periodic_tasks import ensure_datasource_periodic_task
from lens.serializers import (
    DataSourceArchiveUploadSerializer,
    DataSourceConversionRequestSerializer,
    DataSourceSerializer,
)
from lens.services import (
    cancel_datasource_conversion_on_lensnode,
    cancel_datasource_sync_on_lensnode,
)
from lens.tasks import (
    datasource_conversion_task,
    register_datasource_conversion_task,
    register_datasource_sync_task,
    release_datasource_lock,
    source_sync_task,
)
from .base import BaseAdminViewSet


def _active_archive_upload_exists(datasource):
    """Return whether a file datasource already has an active upload."""

    from agentcore_task.adapters.django.models import TaskExecution
    from agentcore_task.constants import TaskStatus

    return TaskExecution.objects.filter(
        module="lens_datasource",
        metadata__datasource_uuid=str(datasource.uuid),
        metadata__trigger__in=["initial_upload", "reupload"],
        status__in=[
            TaskStatus.PENDING,
            *TaskStatus.get_running_statuses(),
        ],
    ).exists()


class DataSourceViewSet(BaseAdminViewSet):
    """CRUD for datasources."""

    queryset = DataSource.objects.all()
    serializer_class = DataSourceSerializer

    def get_queryset(self):
        """Return datasources filtered by optional search query."""

        queryset = super().get_queryset().select_related(
            "lensnode",
            "credential",
        )
        filters = self._datasource_search_filters(
            self.request.query_params.get("filters")
        )
        for item in filters:
            queryset = queryset.filter(
                self._datasource_search_query(
                    item.get("value", ""),
                    item.get("key", ""),
                )
            )
        if filters:
            return queryset
        search = str(self.request.query_params.get("search") or "").strip()
        if not search:
            return queryset
        search_key = str(
            self.request.query_params.get("search_key") or ""
        ).strip()
        return queryset.filter(
            self._datasource_search_query(search, search_key)
        )

    @staticmethod
    def _datasource_search_filters(value):
        """Parse datasource search filters from query params."""

        if not value:
            return []
        try:
            raw_filters = json.loads(value)
        except (TypeError, ValueError):
            return []
        if not isinstance(raw_filters, list):
            return []
        filters = []
        for item in raw_filters:
            if not isinstance(item, dict):
                continue
            keyword = str(item.get("value") or "").strip()
            if not keyword:
                continue
            filters.append(
                {
                    "key": str(item.get("key") or "").strip(),
                    "value": keyword,
                }
            )
        return filters

    @staticmethod
    def _datasource_search_query(search, search_key):
        """Build a whitelisted datasource search query."""

        sync_status_datasource_ids = ScheduledTask.objects.filter(
            task_type=ScheduledTask.TaskType.SOURCE_SYNC,
            target_type="datasource",
            last_status__icontains=search,
        ).values("target_id")
        queries = {
            "name": Q(name__icontains=search),
            "source_type": Q(source_type__icontains=search),
            "repository": (
                Q(config__repo_url__icontains=search)
                | Q(config__document_url__icontains=search)
                | Q(config__folder_url__icontains=search)
                | Q(config__app_token__icontains=search)
            ),
            "lensnode": Q(lensnode__name__icontains=search),
            "target_path": Q(target_path__icontains=search),
            "status": (
                Q(status__icontains=search)
                | Q(last_error__icontains=search)
                | Q(uuid__in=sync_status_datasource_ids)
            ),
            "sync_policy": (
                Q(sync_policy__mode__icontains=search)
                | Q(sync_policy__cron__icontains=search)
                | Q(sync_policy__timezone__icontains=search)
            ),
        }
        if search_key in queries:
            return queries[search_key]
        query = Q()
        for item in queries.values():
            query |= item
        return query

    def create(self, request, *args, **kwargs):
        """Create datasource and return the initial sync task id."""

        self._initial_sync_task_id = ""
        response = super().create(request, *args, **kwargs)
        task_id = getattr(self, "_initial_sync_task_id", "")
        if task_id and isinstance(response.data, dict):
            response.data["initial_sync_task_id"] = task_id
        return response

    def perform_create(self, serializer):
        """Create datasource, register schedule, and enqueue initial sync."""

        datasource = serializer.save()
        ensure_datasource_periodic_task(datasource)
        if datasource.source_type == DataSource.SourceType.MANAGED_WORKSPACE:
            return
        if datasource.status == DataSource.Status.DISABLED:
            return
        task_id = uuid_mod.uuid4().hex
        self._initial_sync_task_id = task_id
        user = self.request.user
        transaction.on_commit(
            lambda: self._enqueue_datasource_sync(
                datasource,
                task_id,
                "initial",
                user,
            )
        )

    def perform_update(self, serializer):
        """Update datasource and register its sync schedule."""

        datasource = serializer.save()
        ensure_datasource_periodic_task(datasource)

    @action(
        detail=False,
        methods=["post"],
        url_path="upload",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload(self, request):
        """Create a file datasource from one uploaded archive."""

        upload_serializer = DataSourceArchiveUploadSerializer(
            data=request.data,
        )
        upload_serializer.is_valid(raise_exception=True)
        datasource_serializer = DataSourceSerializer(
            data=upload_serializer.validated_data["metadata"],
            context={"request": request, "archive_upload": True},
        )
        datasource_serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            datasource = datasource_serializer.save()
            task_id = self._enqueue_archive_upload(
                datasource,
                upload_serializer.validated_data,
                "initial_upload",
                request.user,
            )
        payload = DataSourceSerializer(datasource).data
        payload["initial_sync_task_id"] = task_id
        return Response(payload, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["post"],
        url_path="reupload",
        parser_classes=[MultiPartParser, FormParser],
    )
    def reupload(self, request, uuid=None):
        """Replace a file datasource using one newly uploaded archive."""

        datasource_ref = self.get_object()
        if datasource_ref.source_type != DataSource.SourceType.FILE:
            return Response(
                {"detail": "DATASOURCE_ARCHIVE_UPLOAD_NOT_SUPPORTED"},
                status=status.HTTP_409_CONFLICT,
            )
        if datasource_ref.status == DataSource.Status.DISABLED:
            return Response(
                {"detail": "DATASOURCE_DISABLED"},
                status=status.HTTP_409_CONFLICT,
            )
        upload_serializer = DataSourceArchiveUploadSerializer(
            data=request.data
        )
        upload_serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            datasource = (
                DataSource.objects.select_for_update()
                .select_related("lensnode", "credential")
                .get(pk=datasource_ref.pk)
            )
            if _active_archive_upload_exists(datasource):
                return Response(
                    {"detail": "DATASOURCE_ARCHIVE_UPLOAD_ACTIVE"},
                    status=status.HTTP_409_CONFLICT,
                )
            metadata = upload_serializer.validated_data["metadata"]
            metadata.setdefault("name", datasource.name)
            metadata.setdefault(
                "lensnode_uuid",
                str(datasource.lensnode.uuid),
            )
            metadata.setdefault("target_path", datasource.target_path)
            metadata.setdefault("config", {})
            metadata.setdefault("sync_policy", datasource.sync_policy)
            metadata.setdefault("status", datasource.status)
            datasource_serializer = DataSourceSerializer(
                datasource,
                data=metadata,
                partial=True,
                context={"request": request, "archive_upload": True},
            )
            datasource_serializer.is_valid(raise_exception=True)
            datasource = datasource_serializer.save()
            task_id = self._enqueue_archive_upload(
                datasource,
                upload_serializer.validated_data,
                "reupload",
                request.user,
            )
        payload = DataSourceSerializer(datasource).data
        payload["task_id"] = task_id
        return Response(payload, status=status.HTTP_202_ACCEPTED)

    def _enqueue_archive_upload(
        self,
        datasource,
        upload_data,
        trigger,
        user,
    ):
        """Persist an archive and enqueue its one-time datasource task."""

        task_id = uuid_mod.uuid4().hex
        stored_archive = store_datasource_archive(
            upload_data["file"],
            upload_data["archive"],
            task_id,
        )
        try:
            self._enqueue_datasource_sync(
                datasource,
                task_id,
                trigger,
                user,
                metadata={"archive": stored_archive},
            )
        except Exception:
            delete_datasource_archive(stored_archive)
            raise
        return task_id

    @staticmethod
    def _enqueue_datasource_sync(
        datasource,
        task_id,
        trigger,
        user=None,
        metadata=None,
    ):
        """Register and enqueue one datasource sync task."""

        if datasource.source_type == DataSource.SourceType.MANAGED_WORKSPACE:
            raise ValueError("DATASOURCE_SYNC_NOT_SUPPORTED")
        if datasource.status == DataSource.Status.DISABLED:
            raise ValueError("DATASOURCE_DISABLED")
        celery_task_id = uuid_mod.uuid4().hex
        task_execution = register_datasource_sync_task(
            datasource,
            task_id,
            trigger,
            created_by=user,
            metadata=metadata,
        )
        metadata = dict(task_execution.metadata or {})
        metadata["celery_task_id"] = celery_task_id
        task_execution.metadata = metadata
        task_execution.save(update_fields=["metadata"])
        source_sync_task.apply_async(
            args=[str(datasource.uuid), trigger, task_id],
            task_id=celery_task_id,
        )
        return task_execution

    @action(detail=True, methods=["post"])
    def sync(self, request, uuid=None):
        """Enqueue datasource synchronization on its LensNode."""

        datasource = self.get_object()
        if datasource.source_type in {
            DataSource.SourceType.FILE,
            DataSource.SourceType.MANAGED_WORKSPACE,
        }:
            return Response(
                {"detail": "DATASOURCE_SYNC_NOT_SUPPORTED"},
                status=status.HTTP_409_CONFLICT,
            )
        if datasource.status == DataSource.Status.DISABLED:
            return Response(
                {"detail": "DATASOURCE_DISABLED"},
                status=status.HTTP_409_CONFLICT,
            )
        task_id = uuid_mod.uuid4().hex
        task_execution = self._enqueue_datasource_sync(
            datasource,
            task_id,
            "manual",
            request.user,
        )
        return Response(
            {
                "uuid": str(datasource.uuid),
                "task_id": task_id,
                "task_execution_id": task_execution.id,
                "status": datasource.status,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"])
    def convert(self, request, uuid=None):
        """Enqueue explicit conversion for a managed workspace."""

        datasource = self.get_object()
        if datasource.source_type != DataSource.SourceType.MANAGED_WORKSPACE:
            return Response(
                {"detail": "DATASOURCE_CONVERSION_NOT_SUPPORTED"},
                status=status.HTTP_409_CONFLICT,
            )
        if datasource.status == DataSource.Status.DISABLED:
            return Response(
                {"detail": "DATASOURCE_DISABLED"},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = DataSourceConversionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversion = serializer.validated_data["conversion"]
        force = serializer.validated_data["force"]
        task_id = uuid_mod.uuid4().hex
        celery_task_id = uuid_mod.uuid4().hex
        task_execution = register_datasource_conversion_task(
            datasource,
            task_id,
            conversion,
            force=force,
            created_by=request.user,
            metadata={"celery_task_id": celery_task_id},
        )
        datasource.last_conversion_status = "PENDING"
        datasource.save(update_fields=["last_conversion_status", "updated_at"])
        datasource_conversion_task.apply_async(
            args=[
                str(datasource.uuid),
                conversion,
                force,
                task_id,
            ],
            task_id=celery_task_id,
        )
        return Response(
            {
                "uuid": str(datasource.uuid),
                "task_id": task_id,
                "task_execution_id": task_execution.id,
                "status": task_execution.status,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"], url_path="set-enabled")
    def set_enabled(self, request, uuid=None):
        """Enable or disable a datasource and sync its schedule."""

        enabled = request.data.get("enabled")
        if not isinstance(enabled, bool):
            return Response(
                {"detail": "enabled must be a boolean."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        datasource = self.get_object()
        next_status = (
            DataSource.Status.ACTIVE
            if enabled
            else DataSource.Status.DISABLED
        )
        if datasource.status != next_status:
            datasource.status = next_status
            datasource.save(update_fields=["status", "updated_at"])
        ensure_datasource_periodic_task(datasource)
        return Response(DataSourceSerializer(datasource).data)

    @action(detail=True, methods=["post"], url_path="refresh-availability")
    def refresh_availability(self, request, uuid=None):
        """Refresh a managed workspace path without modifying its contents."""

        datasource = self.get_object()
        if datasource.source_type != DataSource.SourceType.MANAGED_WORKSPACE:
            return Response(
                {"detail": "DATASOURCE_AVAILABILITY_NOT_SUPPORTED"},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            result = check_datasource_path(
                datasource.lensnode,
                datasource.target_path,
                datasource.source_type,
            )
        except (DataSourcePathError, DataSourceDispatchError) as exc:
            datasource.availability_status = (
                DataSource.AvailabilityStatus.ERROR
            )
            datasource.availability_message = str(exc)
        else:
            is_available = bool(
                result.get("exists") and result.get("is_directory")
            )
            datasource.availability_status = (
                DataSource.AvailabilityStatus.AVAILABLE
                if is_available
                else DataSource.AvailabilityStatus.UNAVAILABLE
            )
            datasource.availability_message = str(
                result.get("message") or ""
            )
        datasource.availability_checked_at = timezone.now()
        datasource.save(
            update_fields=[
                "availability_status",
                "availability_checked_at",
                "availability_message",
                "updated_at",
            ]
        )
        return Response(DataSourceSerializer(datasource).data)

    @action(detail=True, methods=["get"], url_path="sync-tasks")
    def sync_tasks(self, request, uuid=None):
        """List sync task executions for this datasource (paginated)."""

        from agentcore_task.adapters.django.models import TaskExecution
        from agentcore_task.adapters.django.serializers import (
            TaskExecutionListSerializer,
        )

        datasource = self.get_object()
        queryset = TaskExecution.objects.filter(
            module="lens_datasource",
            metadata__datasource_uuid=str(datasource.uuid),
        ).order_by("-created_at")
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = TaskExecutionListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = TaskExecutionListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="conversion-tasks")
    def conversion_tasks(self, request, uuid=None):
        """List managed workspace conversion tasks (paginated)."""

        from agentcore_task.adapters.django.models import TaskExecution
        from agentcore_task.adapters.django.serializers import (
            TaskExecutionListSerializer,
        )

        datasource = self.get_object()
        queryset = TaskExecution.objects.filter(
            module="lens_datasource_conversion",
            metadata__datasource_uuid=str(datasource.uuid),
        ).order_by("-created_at")
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = TaskExecutionListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = TaskExecutionListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="cancel-sync")
    def cancel_sync(self, request, uuid=None):
        """Cancel the latest running synchronization for this datasource."""

        from agentcore_task.adapters.django.models import TaskExecution
        from agentcore_task.constants import TaskStatus
        from core.celery import app

        datasource = self.get_object()
        task = (
            TaskExecution.objects.filter(
                module="lens_datasource",
                metadata__datasource_uuid=str(datasource.uuid),
                status__in=[
                    TaskStatus.PENDING,
                    *TaskStatus.get_running_statuses(),
                ],
            )
            .order_by("-created_at")
            .first()
        )
        if task is None:
            return Response(
                {"detail": "No running datasource sync task."},
                status=status.HTTP_404_NOT_FOUND,
            )

        metadata = dict(task.metadata or {})
        celery_task_id = metadata.get("celery_task_id") or task.task_id
        app.control.revoke(celery_task_id, terminate=True, signal="SIGTERM")
        cancel_datasource_sync_on_lensnode(datasource.lensnode, task.task_id)
        delete_datasource_archive(metadata.get("archive") or {})

        lock_token = metadata.get("lock_token") or task.task_id
        release_datasource_lock(datasource.uuid, token=lock_token)
        metadata["manual_revoked_at"] = timezone.now().isoformat()
        metadata["manual_revoked_by"] = request.user.pk
        task.status = TaskStatus.REVOKED
        task.finished_at = timezone.now()
        task.error = "Task manually revoked by operator."
        task.metadata = metadata
        task.save(
            update_fields=[
                "status",
                "finished_at",
                "error",
                "metadata",
            ]
        )
        return Response(
            {
                "uuid": str(datasource.uuid),
                "task_id": task.task_id,
                "task_execution_id": task.id,
                "status": task.status,
            }
        )

    @action(detail=True, methods=["post"], url_path="cancel-conversion")
    def cancel_conversion(self, request, uuid=None):
        """Cancel the latest active managed workspace conversion."""

        from agentcore_task.adapters.django.models import TaskExecution
        from agentcore_task.constants import TaskStatus
        from core.celery import app

        datasource = self.get_object()
        task = (
            TaskExecution.objects.filter(
                module="lens_datasource_conversion",
                metadata__datasource_uuid=str(datasource.uuid),
                status__in=[
                    TaskStatus.PENDING,
                    *TaskStatus.get_running_statuses(),
                ],
            )
            .order_by("-created_at")
            .first()
        )
        if task is None:
            return Response(
                {"detail": "No running datasource conversion task."},
                status=status.HTTP_404_NOT_FOUND,
            )
        metadata = dict(task.metadata or {})
        celery_task_id = metadata.get("celery_task_id") or task.task_id
        app.control.revoke(celery_task_id, terminate=False)
        cancel_datasource_conversion_on_lensnode(
            datasource.lensnode,
            task.task_id,
        )
        release_datasource_lock(
            datasource.uuid,
            token=metadata.get("lock_token") or task.task_id,
        )
        now = timezone.now()
        metadata["manual_revoked_at"] = now.isoformat()
        metadata["manual_revoked_by"] = request.user.pk
        task.status = TaskStatus.REVOKED
        task.finished_at = now
        task.error = "DATASOURCE_CONVERSION_CANCELLED"
        task.metadata = metadata
        task.save(
            update_fields=[
                "status",
                "finished_at",
                "error",
                "metadata",
            ]
        )
        datasource.last_conversion_status = TaskStatus.REVOKED
        datasource.last_conversion_at = now
        datasource.save(
            update_fields=[
                "last_conversion_status",
                "last_conversion_at",
                "updated_at",
            ]
        )
        return Response(
            {
                "uuid": str(datasource.uuid),
                "task_id": task.task_id,
                "task_execution_id": task.id,
                "status": task.status,
            }
        )
