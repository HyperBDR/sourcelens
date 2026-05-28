"""API view for global task config (timeout_minutes, retention_days)."""
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from agentcore_task.adapters.django.conf import (
    get_cleanup_crontab,
    get_mark_timeout_crontab,
    get_retention_days,
    get_task_timeout_minutes,
    is_valid_crontab_expression,
)
from agentcore_task.adapters.django.serializers import (
    TaskConfigSerializer,
    TaskConfigUpdateSerializer,
)
from agentcore_task.adapters.django.services import task_config


def _effective_config():
    """Return current effective config as dict."""
    return {
        "timeout_minutes": get_task_timeout_minutes(),
        "retention_days": get_retention_days(),
        "cleanup_crontab": get_cleanup_crontab(),
        "mark_timeout_crontab": get_mark_timeout_crontab(),
    }


class TaskConfigAPIView(APIView):
    """
    GET effective config; PATCH to update timeout_minutes / retention_days.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["task-management"],
        summary="Get task config",
        description=(
            "Return effective global config (timeout_minutes, retention_days)."
        ),
        responses={200: TaskConfigSerializer},
    )
    def get(self, request: Request) -> Response:
        data = _effective_config()
        ser = TaskConfigSerializer(data)
        return Response(ser.data)

    @extend_schema(
        tags=["task-management"],
        summary="Update task config",
        description=(
            "Update global task config "
            "(timeout_minutes and/or retention_days)."
        ),
        request=TaskConfigUpdateSerializer,
        responses={200: TaskConfigSerializer},
    )
    def patch(self, request: Request) -> Response:
        ser = TaskConfigUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if "timeout_minutes" in data:
            task_config.set_global_task_config(
                "timeout_minutes", data["timeout_minutes"]
            )
        if "retention_days" in data:
            task_config.set_global_task_config(
                "retention_days", data["retention_days"]
            )
        if "cleanup_crontab" in data:
            expr = data["cleanup_crontab"].strip()
            if not is_valid_crontab_expression(expr):
                return Response(
                    {"cleanup_crontab": "Invalid 5-field cron expression."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            task_config.set_global_task_config("cleanup_crontab", expr)
        if "mark_timeout_crontab" in data:
            expr = data["mark_timeout_crontab"].strip()
            if not is_valid_crontab_expression(expr):
                return Response(
                    {"mark_timeout_crontab": "Invalid cron expression."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            task_config.set_global_task_config("mark_timeout_crontab", expr)
        out = _effective_config()
        return Response(
            TaskConfigSerializer(out).data, status=status.HTTP_200_OK
        )
