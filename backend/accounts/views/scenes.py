"""
Scene-related views.
"""

import logging

from django.utils.translation import gettext_lazy as _

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiParameter

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..serializers import SceneSerializer

logger = logging.getLogger(__name__)


class GetAvailableScenesView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["auth"],
        summary=_("Get available scenes"),
        parameters=[
            OpenApiParameter(
                name="language",
                type=OpenApiTypes.STRING,
                location=OpenApiParameter.QUERY,
                description=_("Language code (e.g., 'zh-CN', 'en-US')"),
                required=False,
            )
        ],
        responses={200: SceneSerializer(many=True)},
    )
    def get(self, request):
        try:
            scenes = [
                {
                    "key": "default",
                    "name": "Default",
                    "description": "Default usage scene",
                }
            ]

            serializer = SceneSerializer(scenes, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(
                f"Failed to get available scenes: {e}",
                exc_info=True,
            )
            return Response(
                {
                    "success": False,
                    "error": _("Failed to retrieve available scenes"),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
