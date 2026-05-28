from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

User = get_user_model()


def _user_payload(user):
    """Build { id, username } for a user (handles custom user models)."""
    if user is None:
        return None
    username = getattr(user, "username", None) or getattr(user, "email", None)
    if username is None:
        username = str(user.pk)
    return {"id": user.pk, "username": username}


class AdminUsersListView(APIView):
    """
    GET: List users (id, username) for admin dropdowns (e.g. per-user LLM).
    If the user table is empty, includes the current request user so at least
    the logged-in admin can be selected for per-user config.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["llm-metering"],
        summary="List users",
        description=(
            "List users (id, username) for admin dropdowns "
            "(e.g. per-user LLM). If empty, includes current request user."
        ),
        responses={
            200: {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "username": {"type": "string"},
                    },
                },
            },
        },
    )
    def get(self, request):
        qs = User.objects.all().order_by("id")
        out = [_user_payload(u) for u in qs]
        if not out and request.user.is_authenticated:
            out = [_user_payload(request.user)]
        return Response(out)
