"""
Config API views: global, silence-rules (NotifierConfig scope=global).
Webhook/email config is via NotificationChannel (channels/ API).
"""
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from agentcore_notifier.adapters.django.services import notification_config


class GlobalConfigView(APIView):
    """GET/PUT global config (key=global)."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        value = notification_config.get_config("global")
        return Response({"key": "global", "value": value})

    def put(self, request):
        value = (
            request.data.get("value")
            if "value" in request.data
            else request.data
        )
        notification_config.set_config("global", value)
        return Response({"key": "global", "value": value})


class SilenceRulesView(APIView):
    """GET/PUT silence rules (key=silence_rules, JSON array)."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        value = notification_config.get_config("silence_rules")
        return Response({"key": "silence_rules", "value": value or []})

    def put(self, request):
        value = (
            request.data.get("value")
            if "value" in request.data
            else request.data
        )
        if not isinstance(value, list):
            return Response(
                {"detail": "value must be a list of silence rules"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        notification_config.set_config("silence_rules", value)
        return Response({"key": "silence_rules", "value": value})
