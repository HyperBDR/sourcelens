"""
API view for global metering config: retention, cleanup, aggregation schedules.

Used by frontend to display and update retention_days (default 365),
cleanup_enabled, cleanup_crontab, and aggregation crontabs.
"""
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from agentcore_metering.adapters.django.conf import (
    get_aggregation_crontab,
    get_cleanup_crontab,
    get_cleanup_enabled,
    get_retention_days,
    is_valid_crontab_expression,
)
from agentcore_metering.adapters.django.serializers import (
    MeteringConfigSerializer,
    MeteringConfigUpdateSerializer,
)
from agentcore_metering.adapters.django.services.metering_config import (
    set_global_config,
)

def _effective_config():
    """Return current effective config as dict."""
    return {
        "retention_days": get_retention_days(),
        "cleanup_enabled": get_cleanup_enabled(),
        "cleanup_crontab": get_cleanup_crontab(),
        "aggregation_crontab": get_aggregation_crontab(),
    }


class MeteringConfigAPIView(APIView):
    """
    GET effective config; PATCH to update retention_days, cleanup, crontabs.
    Admin only.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["llm-metering"],
        summary="Get metering config",
        description=(
            "Return effective global metering config (retention_days default "
            "365, cleanup/aggregation schedules) and registered task names."
        ),
        responses={200: MeteringConfigSerializer},
    )
    def get(self, request: Request) -> Response:
        data = _effective_config()
        ser = MeteringConfigSerializer(data)
        return Response(ser.data)

    @extend_schema(
        tags=["llm-metering"],
        summary="Update metering config",
        description=(
            "Update global metering config. After changing crontabs, run "
            "python manage.py register_periodic_tasks to apply to beat."
        ),
        request=MeteringConfigUpdateSerializer,
        responses={200: MeteringConfigSerializer},
    )
    def patch(self, request: Request) -> Response:
        ser = MeteringConfigUpdateSerializer(
            data=request.data, partial=True
        )
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        crontab_fields = [
            "cleanup_crontab",
            "aggregation_crontab",
        ]
        for key in crontab_fields:
            if key in data:
                expr = (data[key] or "").strip()
                if not is_valid_crontab_expression(expr):
                    return Response(
                        {key: "Invalid 5-field cron expression."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                set_global_config(key, expr)
        if "retention_days" in data:
            set_global_config("retention_days", data["retention_days"])
        if "cleanup_enabled" in data:
            set_global_config("cleanup_enabled", data["cleanup_enabled"])
        out = _effective_config()
        return Response(
            MeteringConfigSerializer(out).data,
            status=status.HTTP_200_OK,
        )
