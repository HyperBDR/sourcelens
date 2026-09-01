"""Administrative views for trusted installed plugins."""

from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from lens.plugins.registry import discover_plugins
from .base import BaseAdminViewSet


class PluginRegistryViewSet(BaseAdminViewSet, ViewSet):
    """Expose installed Plugin identities without runtime internals."""

    http_method_names = ["get", "head", "options"]

    def list(self, request):
        """List installed Plugin versions visible to administrators."""

        del request
        return Response([
            {
                "key": plugin.key,
                "version": plugin.version,
                "protocol_version": plugin.protocol_version,
            }
            for plugin in discover_plugins()
        ])
