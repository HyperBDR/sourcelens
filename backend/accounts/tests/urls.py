"""URLs for accounts tests."""
from django.urls import path

from dj_rest_auth.views import PasswordChangeView
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.views.management import (
    ManagementGroupListView,
    ManagementUserListView,
)
from accounts.views.password import (
    ConfirmPasswordResetView,
    SendPasswordResetEmailView,
)


class AuthenticatedProbeView(APIView):
    """Return the authenticated user's ID for JWT regression tests."""

    def get(self, request):
        """Return a minimal authenticated response."""
        return Response({"user_id": request.user.pk})


urlpatterns = [
    path(
        "api/v1/auth/password/reset",
        SendPasswordResetEmailView.as_view(),
    ),
    path(
        "api/v1/auth/password/reset/confirm",
        ConfirmPasswordResetView.as_view(),
    ),
    path(
        "api/v1/auth/password/change",
        PasswordChangeView.as_view(),
    ),
    path("api/v1/auth/probe", AuthenticatedProbeView.as_view()),
    path(
        "api/v1/management/users/",
        ManagementUserListView.as_view(),
    ),
    path(
        "api/v1/management/groups/",
        ManagementGroupListView.as_view(),
    ),
]
