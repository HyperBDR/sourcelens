"""
Admin API views for LLM usage list and token statistics.

Read-only; requires IsAdminUser. Used by management UI for usage log and
cost/summary stats.
"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from agentcore_metering.adapters.django.serializers import (
    ErrorDetailSerializer,
    LLMUsageListResponseSerializer,
    TokenStatsResponseSerializer,
)
from agentcore_metering.adapters.django.services.usage_list import (
    get_llm_usage_list_from_query,
)
from agentcore_metering.adapters.django.services.usage_aggregation import (
    get_token_stats_from_query,
)


class AdminTokenStatsView(APIView):
    """
    GET: LLM token consumption statistics (summary, by_model, time series).
    Query params: start_date, end_date, user_id, granularity (day|month|year).
    Admin only.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["llm-metering"],
        summary="Token statistics",
        description=(
            "LLM token consumption statistics (summary, by_model, optional "
            "time series). Set granularity to get series: day=hourly, "
            "month=daily, year=monthly."
        ),
        parameters=[
            OpenApiParameter(
                "start_date",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                description="Start date (ISO 8601 or YYYY-MM-DD)",
            ),
            OpenApiParameter(
                "end_date",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                description=(
                    "End date (ISO or YYYY-MM-DD); date-only=end of day."
                ),
            ),
            OpenApiParameter(
                "user_id",
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                description="Filter by user id",
            ),
            OpenApiParameter(
                "granularity",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                description="Time bucket: day/month/year. Omit for summary.",
                enum=["day", "month", "year"],
            ),
            OpenApiParameter(
                "use_series",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                description=(
                    "If 1/true/yes and granularity+date range set, include "
                    "series_by_model from pre-aggregated table."
                ),
            ),
        ],
        responses={
            200: TokenStatsResponseSerializer,
            400: ErrorDetailSerializer,
        },
    )
    def get(self, request):
        try:
            data = get_token_stats_from_query(request.query_params)
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(data)


class AdminLLMUsageListView(APIView):
    """
    GET: Paginated list of LLM usage records with filters.
    Query params: page, page_size, user_id, model, success, start_date,
    end_date. Read-only. Admin only.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["llm-metering"],
        summary="List LLM usage",
        description=(
            "Paginated list of LLM usage records. Filter by user, model, "
            "success, or date range."
        ),
        parameters=[
            OpenApiParameter(
                "page",
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                description="Page number (1-based)",
                default=1,
            ),
            OpenApiParameter(
                "page_size",
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                description="Page size (1–100)",
                default=20,
            ),
            OpenApiParameter(
                "user_id",
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                description="Filter by user id",
            ),
            OpenApiParameter(
                "model",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                description=(
                    "Filter by model name (substring, case-insensitive)"
                ),
            ),
            OpenApiParameter(
                "success",
                OpenApiTypes.BOOL,
                OpenApiParameter.QUERY,
                description="Filter by success (true/false)",
            ),
            OpenApiParameter(
                "start_date",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                description="Start date (ISO or YYYY-MM-DD)",
            ),
            OpenApiParameter(
                "end_date",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                description="End date (ISO or YYYY-MM-DD)",
            ),
        ],
        responses={200: LLMUsageListResponseSerializer},
    )
    def get(self, request):
        data = get_llm_usage_list_from_query(request.query_params)
        return Response(data)
