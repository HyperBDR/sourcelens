"""Views for task execution management."""
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from agentcore_task.adapters.django.models import TaskExecution
from agentcore_task.adapters.django.serializers import (
    TaskExecutionListSerializer,
    TaskExecutionSerializer,
    TaskStatsSerializer,
)
from agentcore_task.adapters.django.services import (
    TaskTracker,
    get_task_stats,
    list_task_executions,
)

User = get_user_model()


class TaskExecutionPagination(PageNumberPagination):
    """Plugin-local pagination with configurable page_size."""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema_view(
    list=extend_schema(
        tags=["task-management"],
        summary="List task executions",
        description="List task executions with filtering options.",
    ),
    retrieve=extend_schema(
        tags=["task-management"],
        summary="Retrieve task execution",
        description="Get details for one task execution.",
    ),
)
class TaskExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API for task executions: list, retrieve, stats, sync, my_tasks.
    """

    queryset = TaskExecution.objects.all()
    permission_classes = [IsAuthenticated]
    pagination_class = TaskExecutionPagination

    def get_serializer_class(self):
        if self.action == "list":
            return TaskExecutionListSerializer
        return TaskExecutionSerializer

    def get_queryset(self):
        # Resolve created_by from query params or default to current user
        created_by = self.request.query_params.get("created_by", None)
        my_tasks_only = self.request.query_params.get("my_tasks", None)
        if my_tasks_only is None and created_by is None:
            created_by = self.request.user
        elif my_tasks_only and my_tasks_only.lower() == "false":
            created_by = None
        elif created_by:
            try:
                created_by = User.objects.get(id=created_by)
            except User.DoesNotExist:
                created_by = None
        return list_task_executions(
            module=self.request.query_params.get("module") or None,
            task_name=self.request.query_params.get("task_name") or None,
            status=self.request.query_params.get("status") or None,
            created_by=created_by,
            start_date=self.request.query_params.get("start_date") or None,
            end_date=self.request.query_params.get("end_date") or None,
            search=self.request.query_params.get("search") or None,
            config_platform=(
                self.request.query_params.get("config_platform") or None
            ),
            config_key=self.request.query_params.get("config_key") or None,
        )

    @extend_schema(
        tags=["task-management"],
        summary="Get task status",
        description="Get the status of a specific task by task_id.",
        responses={200: TaskExecutionSerializer},
    )
    @action(detail=False, methods=["get"], url_path="status")
    def status(self, request):
        task_id = request.query_params.get("task_id", None)
        if not task_id:
            return Response(
                {"error": "task_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sync = request.query_params.get("sync", "true").lower() == "true"
        task_execution = TaskTracker.get_task(task_id, sync=sync)
        if not task_execution:
            return Response(
                {"error": "Task not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = TaskExecutionSerializer(task_execution)
        return Response(serializer.data)

    @extend_schema(
        tags=["task-management"],
        summary="Get task by task_id",
        description="Get task execution details by Celery task_id.",
        responses={200: TaskExecutionSerializer},
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="by-task-id/(?P<task_id>[^/.]+)",
    )
    def by_task_id(self, request, task_id=None):
        sync = request.query_params.get("sync", "true").lower() == "true"
        task_execution = TaskTracker.get_task(task_id, sync=sync)
        if not task_execution:
            return Response(
                {"error": "Task not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = TaskExecutionSerializer(task_execution)
        return Response(serializer.data)

    @extend_schema(
        tags=["task-management"],
        summary="Sync task status",
        description="Manually sync task status from Celery result backend.",
        responses={200: TaskExecutionSerializer},
    )
    @action(detail=True, methods=["post"], url_path="sync")
    def sync(self, request, pk=None):
        task_execution = self.get_object()
        synced_task = TaskTracker.sync_task_from_celery(task_execution.task_id)
        if not synced_task:
            return Response(
                {"error": "Failed to sync task"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        serializer = TaskExecutionSerializer(synced_task)
        return Response(serializer.data)

    @extend_schema(
        tags=["task-management"],
        summary="Get task statistics",
        description="Get statistical information about task executions.",
        responses={200: TaskStatsSerializer},
    )
    @action(detail=False, methods=["get"])
    def stats(self, request):
        created_by = request.query_params.get("created_by", None)
        my_tasks_only = request.query_params.get("my_tasks", None)
        if my_tasks_only is None and created_by is None:
            user_filter = request.user
        elif created_by:
            try:
                user_filter = User.objects.get(id=created_by)
            except User.DoesNotExist:
                user_filter = None
        else:
            user_filter = None
        stats = get_task_stats(
            module=request.query_params.get("module") or None,
            task_name=request.query_params.get("task_name") or None,
            created_by=user_filter,
            start_date=request.query_params.get("start_date") or None,
            end_date=request.query_params.get("end_date") or None,
            granularity=request.query_params.get("granularity") or None,
        )
        serializer = TaskStatsSerializer(stats)
        return Response(serializer.data)

    @extend_schema(
        tags=["task-management"],
        summary="Get my tasks",
        description="Get current user's task executions.",
        responses={200: TaskExecutionListSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="my-tasks")
    def my_tasks(self, request):
        queryset = list_task_executions(
            module=request.query_params.get("module") or None,
            task_name=request.query_params.get("task_name") or None,
            status=request.query_params.get("status") or None,
            created_by=request.user,
            start_date=request.query_params.get("start_date") or None,
            end_date=request.query_params.get("end_date") or None,
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = TaskExecutionListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = TaskExecutionListSerializer(queryset, many=True)
        return Response(serializer.data)
