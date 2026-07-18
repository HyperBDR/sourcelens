"""Assistant CRUD and public assistant metadata views."""

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasRequiredFeature

from lens.models import Assistant
from lens.serializers import AssistantSerializer
from .base import BaseAuthenticatedViewSet


class AssistantViewSet(BaseAuthenticatedViewSet):
    """CRUD for assistants.

    Anyone authenticated may list/retrieve the assistants visible to them;
    creating, editing, and deleting assistants (including visibility and
    access grants) requires the admin console feature.
    """

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

        if self.action in ("create", "update", "partial_update", "destroy"):
            return [permissions.IsAuthenticated(), HasRequiredFeature()]
        return super().get_permissions()

    def get_queryset(self):
        """Scope assistants to those the caller may see."""

        return super().get_queryset().visible_to(self.request.user)

    def destroy(self, request, *args, **kwargs):
        """Soft-retire assistant instead of hard delete."""

        assistant = self.get_object()
        assistant.status = Assistant.Status.DISABLED
        assistant.save(update_fields=["status", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


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
