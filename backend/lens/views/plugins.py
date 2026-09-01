"""Administrative views for trusted installed plugins."""

from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from lens.models import CredentialLease, ExecutionSnapshot
from lens.plugins.registry import discover_plugins
from .base import BaseAdminViewSet, LensNodeAuthMixin


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


class PluginCredentialLeaseView(LensNodeAuthMixin, APIView):
    """Issue a short-lived opaque lease for a node-owned execution snapshot."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        """Create a lease after authenticating the owning LensNode."""

        node = self._authenticate_lensnode(request)
        if node is None:
            return Response({"detail": "LENSNODE_UNAUTHORIZED"}, status=401)
        snapshot_uuid = request.data.get("snapshot_uuid")
        snapshot = (
            ExecutionSnapshot.objects.select_related(
                "datasource",
                "connection",
            )
            .filter(uuid=snapshot_uuid)
            .first()
        )
        if snapshot is None:
            return Response({"detail": "SNAPSHOT_NOT_FOUND"}, status=404)
        if (
            snapshot.datasource_id is None
            or snapshot.datasource.lensnode_id != node.pk
        ):
            return Response({"detail": "SNAPSHOT_NODE_MISMATCH"}, status=403)
        if snapshot.connection.status != snapshot.connection.Status.ACTIVE:
            return Response({"detail": "CONNECTION_DISABLED"}, status=409)
        now = timezone.now()
        lease = CredentialLease.objects.create(
            snapshot=snapshot,
            lensnode=node,
            expires_at=now + timedelta(minutes=5),
        )
        return Response(
            {
                "lease_uuid": str(lease.uuid),
                "snapshot_uuid": str(snapshot.uuid),
                "expires_at": lease.expires_at,
            },
            status=status.HTTP_201_CREATED,
        )


class PluginCredentialMaterialView(LensNodeAuthMixin, APIView):
    """Return lease-bound secret material to the authenticated LensNode."""

    authentication_classes = []
    permission_classes = []

    def post(self, request, lease_uuid):
        """Resolve a non-expired lease without exposing snapshot metadata."""

        node = self._authenticate_lensnode(request)
        if node is None:
            return Response({"detail": "LENSNODE_UNAUTHORIZED"}, status=401)
        lease = (
            CredentialLease.objects.select_related(
                "snapshot__secret_version",
                "snapshot__connection",
            )
            .filter(uuid=lease_uuid, lensnode=node)
            .first()
        )
        if lease is None:
            return Response({"detail": "LEASE_NOT_FOUND"}, status=404)
        now = timezone.now()
        if lease.revoked_at is not None or lease.expires_at <= now:
            return Response({"detail": "LEASE_EXPIRED"}, status=410)
        if (
            lease.snapshot.connection.status
            != lease.snapshot.connection.Status.ACTIVE
        ):
            return Response({"detail": "CONNECTION_DISABLED"}, status=409)
        secret_version = lease.snapshot.secret_version
        value = secret_version.get_value() if secret_version else ""
        if not value:
            return Response({"detail": "SECRET_UNAVAILABLE"}, status=409)
        return Response(
            {
                "lease_uuid": str(lease.uuid),
                "plugin_key": lease.snapshot.plugin_key,
                "endpoint": lease.snapshot.resolved_config.get("endpoint", ""),
                "value": value,
            },
            status=status.HTTP_200_OK,
        )
