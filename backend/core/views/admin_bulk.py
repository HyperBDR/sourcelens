"""Admin batch endpoints for resources exposed by agentcore apps."""

from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.services.admin_bulk import (
    AdminBulkMutationError,
    delete_notification_channels,
    mutate_llm_configs,
)


class NotificationChannelBulkDeleteView(APIView):
    """POST an atomic deletion for a bounded channel selection."""

    permission_classes = [IsAdminUser]

    def post(self, request):
        try:
            count = delete_notification_channels(
                request.data.get("channel_ids")
            )
        except AdminBulkMutationError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"count": count}, status=status.HTTP_200_OK)


class LLMConfigBulkView(APIView):
    """POST an atomic mutation for a bounded LLM config selection."""

    permission_classes = [IsAdminUser]

    def post(self, request):
        try:
            count = mutate_llm_configs(
                request.data.get("config_ids"),
                request.data.get("action"),
            )
        except AdminBulkMutationError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"count": count}, status=status.HTTP_200_OK)
