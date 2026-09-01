"""Administrative views for trusted installed plugins."""

from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from lens.models import Connection, CredentialLease, ExecutionSnapshot
from lens.serializers import ConnectionSerializer
from lens.plugins.registry import discover_plugins
from .base import BaseAdminViewSet, LensNodeAuthMixin


SENSITIVE_KEYS = frozenset({
    "access_token",
    "api_key",
    "authorization",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
})


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


class ConnectionViewSet(BaseAdminViewSet):
    """Admin CRUD for reusable Plugin connections."""

    queryset = Connection.objects.all().select_related("secret_version")
    serializer_class = ConnectionSerializer

    def get_queryset(self):
        """Filter connections by Plugin or lifecycle status."""

        queryset = super().get_queryset()
        plugin_key = self.request.query_params.get("plugin_key")
        status_value = self.request.query_params.get("status")
        if plugin_key:
            queryset = queryset.filter(plugin_key=plugin_key)
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset

    def destroy(self, request, *args, **kwargs):
        """Reject deletion while a connection is referenced."""

        connection = self.get_object()
        if (
            connection.datasources.exists()
            or connection.execution_snapshots.exists()
        ):
            return Response(
                {"detail": "CONNECTION_IN_USE"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


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
                "secret_version",
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
        if (
            snapshot.secret_version is not None
            and snapshot.secret_version.status != "active"
        ):
            return Response({"detail": "SECRET_VERSION_DISABLED"}, status=409)
        now = timezone.now()
        lease = CredentialLease.objects.create(
            snapshot=snapshot,
            lensnode=node,
            expires_at=now + timedelta(minutes=5),
        )
        response = Response(
            {
                "lease_uuid": str(lease.uuid),
                "snapshot_uuid": str(snapshot.uuid),
                "expires_at": lease.expires_at,
            },
            status=status.HTTP_201_CREATED,
        )
        response["Cache-Control"] = "no-store"
        return response


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
        if (
            secret_version is not None
            and secret_version.status != "active"
        ):
            return Response({"detail": "SECRET_VERSION_DISABLED"}, status=409)
        if (
            secret_version is not None
            and secret_version.material.status != "active"
        ):
            return Response({"detail": "SECRET_MATERIAL_DISABLED"}, status=409)
        value = secret_version.get_value() if secret_version else ""
        if not value:
            return Response({"detail": "SECRET_UNAVAILABLE"}, status=409)
        response = Response(
            {
                "lease_uuid": str(lease.uuid),
                "plugin_key": lease.snapshot.plugin_key,
                "endpoint": lease.snapshot.resolved_config.get("endpoint", ""),
                "value": value,
            },
            status=status.HTTP_200_OK,
        )
        response["Cache-Control"] = "no-store"
        return response


class PluginExecutionSnapshotView(LensNodeAuthMixin, APIView):
    """Return non-sensitive execution data to the owning LensNode."""

    authentication_classes = []
    permission_classes = []

    def get(self, request, snapshot_uuid):
        """Resolve one snapshot for a node without returning its secret."""

        node = self._authenticate_lensnode(request)
        if node is None:
            return Response({"detail": "LENSNODE_UNAUTHORIZED"}, status=401)
        snapshot = (
            ExecutionSnapshot.objects.select_related("datasource")
            .filter(
                uuid=snapshot_uuid,
                datasource__lensnode=node,
            )
            .first()
        )
        if snapshot is None:
            return Response({"detail": "SNAPSHOT_NOT_FOUND"}, status=404)
        response = Response(
            {
                "snapshot_uuid": str(snapshot.uuid),
                "datasource_uuid": str(snapshot.datasource.uuid),
                "plugin_key": snapshot.plugin_key,
                "plugin_version": snapshot.plugin_version,
                "protocol_version": snapshot.protocol_version,
                "resolved_config": _safe_snapshot_config(
                    snapshot.resolved_config
                ),
            },
            status=status.HTTP_200_OK,
        )
        response["Cache-Control"] = "no-store"
        return response


def _safe_snapshot_config(value):
    """Remove credential-shaped keys before returning snapshot data."""

    if isinstance(value, dict):
        return {
            key: _safe_snapshot_config(nested)
            for key, nested in value.items()
            if str(key).lower() not in SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [_safe_snapshot_config(item) for item in value]
    return value
