from django.db.models.deletion import ProtectedError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from lens.models import EnvironmentVariableSet
from lens.serializers import EnvironmentVariableSetSerializer
from .base import BaseAdminViewSet


class EnvironmentVariableSetViewSet(BaseAdminViewSet):
    """Admin-only CRUD for encrypted Skill environment values."""

    queryset = EnvironmentVariableSet.objects.all()
    serializer_class = EnvironmentVariableSetSerializer

    def destroy(self, request, *args, **kwargs):
        """Reject deleting a set that is still bound to an Assistant."""

        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": "ENVIRONMENT_VARIABLE_SET_IN_USE"},
                status=status.HTTP_409_CONFLICT,
            )

    @action(detail=True, methods=["post"], url_path="reveal")
    def reveal(self, request, uuid=None):
        """Reveal values only during an explicit admin edit action."""

        variable_set = self.get_object()
        return Response(
            {
                "values": [
                    {"key": key, "value": value}
                    for key, value in variable_set.get_values().items()
                ]
            }
        )
