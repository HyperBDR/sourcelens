"""Base viewsets, renderers, and shared authentication helpers."""

from rest_framework import permissions, viewsets
from rest_framework.renderers import BaseRenderer
from rest_framework_simplejwt.authentication import JWTAuthentication

from lens.lensnode_auth import token_matches
from lens.models import LensNode, Run


class BaseAuthenticatedViewSet(viewsets.ModelViewSet):
    """Base viewset requiring authentication."""

    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "uuid"


class BaseAdminViewSet(BaseAuthenticatedViewSet):
    """Base viewset requiring staff access."""

    permission_classes = [permissions.IsAdminUser]


class EventStreamRenderer(BaseRenderer):
    """Renderer used only for SSE content negotiation."""

    media_type = "text/event-stream"
    format = "event-stream"
    charset = None

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """Return bytes for DRF negotiation fallback paths."""

        del accepted_media_type, renderer_context
        return data or b""


def _authenticate_stream_request(request):
    """Authenticate a native Django SSE request with JWT."""

    if getattr(request, "user", None) is not None:
        if request.user.is_authenticated:
            return request.user

    authenticated = JWTAuthentication().authenticate(request)
    if authenticated is None:
        return None
    user, _ = authenticated
    return user


def _get_user_run(run_uuid, user):
    """Return a run visible to the authenticated user."""

    return (
        Run.objects.filter(uuid=run_uuid, session__user=user)
        .select_related("output_message")
        .first()
    )


class LensNodeAuthMixin:
    """Shared LensNode bearer-token authentication for gateway views."""

    def _authenticate_lensnode(self, request):
        """Authenticate bearer token against approved LensNodes."""

        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        token = header.removeprefix("Bearer ").strip()
        for lensnode in LensNode.objects.filter(
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            token_revoked=False,
        ).exclude(auth_token_hash=""):
            if token_matches(lensnode, token):
                return lensnode
        return None
