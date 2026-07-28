"""Assistant CRUD and public assistant metadata views."""

from django.db import transaction
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasRequiredFeature

from lens.models import Assistant, user_sees_all_assistants
from lens.serializers import AssistantSerializer
from .base import BaseAuthenticatedViewSet


class AssistantViewSet(BaseAuthenticatedViewSet):
    """Manage assistants and their lifecycle.

    Anyone authenticated may list/retrieve the assistants visible to them;
    creating, editing, archiving, and restoring assistants (including
    visibility and access grants) requires the admin console feature.
    """

    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    required_feature = "admin_console"
    queryset = Assistant.objects.select_related("lensnode").prefetch_related(
        "skill_bindings",
        "mcp_bindings",
        "access_grants__group",
        "access_grants__user",
    )
    serializer_class = AssistantSerializer

    def get_permissions(self):
        """Require the admin console feature for write actions."""

        if self.action in (
            "create",
            "update",
            "partial_update",
            "archive",
            "restore",
        ):
            return [permissions.IsAuthenticated(), HasRequiredFeature()]
        return super().get_permissions()

    def get_queryset(self):
        """Scope assistants to those the caller may see."""

        queryset = super().get_queryset().visible_to(self.request.user)
        if self.action == "restore":
            return queryset.filter(status=Assistant.Status.ARCHIVED)
        if self.action == "archive":
            return queryset.filter(status=Assistant.Status.ACTIVE)

        archived = self.request.query_params.get("archived", "").lower()
        if archived == "true":
            if not user_sees_all_assistants(self.request.user):
                return queryset.none()
            return queryset.filter(status=Assistant.Status.ARCHIVED)
        return queryset.filter(status=Assistant.Status.ACTIVE)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def archive(self, request, *args, **kwargs):
        """Archive an active assistant without deleting its data."""

        assistant = self.get_object()
        assistant = Assistant.objects.select_for_update().get(pk=assistant.pk)
        assistant.status = Assistant.Status.ARCHIVED
        assistant.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(assistant).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def restore(self, request, *args, **kwargs):
        """Restore an archived assistant to active use."""

        assistant = self.get_object()
        assistant = Assistant.objects.select_for_update().get(pk=assistant.pk)
        assistant.status = Assistant.Status.ACTIVE
        assistant.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(assistant).data)


class PublicAssistantView(APIView):
    """Public read-only assistant metadata for the shared chat page."""

    authentication_classes = []
    permission_classes = []

    def get(self, request, slug):
        """Return minimal metadata for an active assistant by slug."""

        assistant = Assistant.objects.filter(
            slug=slug,
            status=Assistant.Status.ACTIVE,
            visibility=Assistant.Visibility.PUBLIC,
        ).first()
        if assistant is None:
            return Response(
                {"detail": "Assistant not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {
                "name": assistant.name,
                "description": assistant.description,
                "slug": assistant.slug,
                "status": assistant.status,
            }
        )
