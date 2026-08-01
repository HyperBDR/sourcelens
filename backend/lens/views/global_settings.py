"""Global setting CRUD and system-health scheduling views."""

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from lens.models import GlobalSetting, ScheduledTask
from lens.periodic_tasks import (
    GLOBAL_PERIODIC_TASKS,
    sync_global_periodic_task,
)
from lens.serializers import GlobalSettingSerializer
from .base import BaseAdminViewSet


class GlobalSettingViewSet(BaseAdminViewSet):
    """CRUD for global settings."""

    queryset = GlobalSetting.objects.all()
    pagination_class = None
    serializer_class = GlobalSettingSerializer
    lookup_field = "key"
    lookup_value_regex = "[^/]+"

    def perform_create(self, serializer):
        """Create a global setting and sync derived runtime config."""

        setting = serializer.save()
        self._sync_runtime_schedule(setting)

    def perform_update(self, serializer):
        """Update a global setting and sync derived runtime config."""

        setting = serializer.save()
        self._sync_runtime_schedule(setting)

    def partial_update(self, request, *args, **kwargs):
        """Update or create a setting addressed by key."""

        key = kwargs.get(self.lookup_field)
        instance = self.queryset.filter(key=key).first()
        data = request.data.copy()
        data["key"] = key
        serializer = self.get_serializer(
            instance,
            data=data,
            partial=instance is not None,
        )
        serializer.is_valid(raise_exception=True)
        setting = serializer.save()
        self._sync_runtime_schedule(setting)
        return Response(self.get_serializer(setting).data)

    def _sync_runtime_schedule(self, setting):
        """Propagate interval settings to celery beat rows."""

        if setting.key not in {
            meta["setting_key"] for meta in GLOBAL_PERIODIC_TASKS.values()
        }:
            return

        for task_type, meta in GLOBAL_PERIODIC_TASKS.items():
            if meta["setting_key"] == setting.key:
                sync_global_periodic_task(task_type)
                break

    @action(detail=False, methods=["get", "patch"], url_path="system-health")
    def system_health(self, request):
        """Expose and update the enabled state for global scheduled tasks."""

        if request.method == "GET":
            tasks = ScheduledTask.objects.filter(
                task_type__in=[
                    ScheduledTask.TaskType.LENSNODE_CLEANUP,
                    ScheduledTask.TaskType.LENSNODE_HEALTH,
                    ScheduledTask.TaskType.RUN_RETENTION,
                ]
            ).order_by("task_type")
            data = [
                {
                    "name": task.name,
                    "task_type": task.task_type,
                    "enabled": task.enabled,
                    "last_status": task.last_status,
                    "last_run_at": task.last_run_at,
                    "last_error": task.last_error,
                    "last_metrics": task.last_metrics,
                }
                for task in tasks
            ]
            return Response(data)

        task_type = request.data.get("task_type")
        enabled = request.data.get("enabled")

        valid_task_types = {
            ScheduledTask.TaskType.LENSNODE_CLEANUP,
            ScheduledTask.TaskType.LENSNODE_HEALTH,
            ScheduledTask.TaskType.RUN_RETENTION,
        }
        if task_type not in valid_task_types:
            return Response(
                {"detail": "Invalid task_type."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(enabled, bool):
            return Response(
                {"detail": "enabled must be a boolean."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        task_name_map = {
            ScheduledTask.TaskType.LENSNODE_CLEANUP: "lens-lensnode-cleanup",
            ScheduledTask.TaskType.LENSNODE_HEALTH: "lens-lensnode-health",
            ScheduledTask.TaskType.RUN_RETENTION: "lens-run-retention",
        }
        task, _ = ScheduledTask.objects.get_or_create(
            task_type=task_type,
            target_type=None,
            target_id=None,
            defaults={
                "name": task_name_map[task_type],
                "enabled": enabled,
            },
        )
        if task.enabled != enabled:
            task.enabled = enabled
            task.save(update_fields=["enabled", "updated_at"])

        from django_celery_beat.models import PeriodicTask

        periodic_task_name = task_name_map[task_type]
        periodic_task = PeriodicTask.objects.filter(
            name=periodic_task_name
        ).first()
        if periodic_task is not None and periodic_task.enabled != enabled:
            periodic_task.enabled = enabled
            periodic_task.save(update_fields=["enabled"])
            from django_celery_beat.models import PeriodicTasks

            PeriodicTasks.update_changed()

        return Response(
            {
                "name": task.name,
                "task_type": task.task_type,
                "enabled": task.enabled,
                "last_status": task.last_status,
                "last_run_at": task.last_run_at,
                "last_error": task.last_error,
                "last_metrics": task.last_metrics,
            }
        )
