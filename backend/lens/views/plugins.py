"""Administrative views for trusted installed plugins."""

import uuid
from datetime import timedelta

from django.db.models import Count
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from lens.models import Connection, CredentialLease, ExecutionSnapshot
from lens.plugins.registry import (
    PluginNotFoundError,
    discover_plugins,
    latest_plugin,
)
from lens.plugins.tool_snapshots import (
    ACTIVE_RUN_STATUSES,
    ToolSnapshotError,
    create_tool_execution_snapshot,
)
from lens.serializers import ConnectionSerializer
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


class PluginRuntimeNoStoreMixin:
    """Prevent caching of Plugin Runtime responses in every outcome."""

    def finalize_response(self, request, response, *args, **kwargs):
        """Attach the runtime cache policy after DRF handles the request."""

        response = super().finalize_response(
            request,
            response,
            *args,
            **kwargs,
        )
        response["Cache-Control"] = "no-store"
        return response


class PluginRegistryViewSet(BaseAdminViewSet, ViewSet):
    """Expose installed Plugin identities without runtime internals."""

    http_method_names = ["get", "head", "options"]
    lookup_field = "key"

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

    @action(detail=True, methods=["get"], url_path="tools")
    def tools(self, request, key=None):
        """List safe model-facing tools from the latest Plugin version."""

        del request
        try:
            plugin = latest_plugin(key)
        except PluginNotFoundError:
            return Response({"detail": "PLUGIN_NOT_FOUND"}, status=404)
        return Response([
            {
                "key": tool.key,
                "description": tool.description,
                "capability": tool.capability,
                "side_effect": tool.side_effect,
                "input_schema": tool.input_schema,
            }
            for tool in plugin.tools
        ])


class ConnectionViewSet(BaseAdminViewSet):
    """Admin CRUD for reusable Plugin connections."""

    queryset = (
        Connection.objects.all()
        .select_related("secret_version")
        .annotate(
            assistant_usage_count=Count(
                "assistant_bindings",
                distinct=True,
            ),
            datasource_usage_count=Count(
                "datasources",
                distinct=True,
            ),
        )
    )
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
            or connection.assistant_bindings.exists()
            or connection.execution_snapshots.exists()
        ):
            return Response(
                {"detail": "CONNECTION_IN_USE"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": "CONNECTION_IN_USE"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class PluginToolExecutionSnapshotView(
    PluginRuntimeNoStoreMixin,
    LensNodeAuthMixin,
    APIView,
):
    """Create one authorized execution snapshot for a Plugin Tool call."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        """Authorize a Run-bound Tool call for the requesting LensNode."""

        node = self._authenticate_lensnode(request)
        if node is None:
            return Response({"detail": "LENSNODE_UNAUTHORIZED"}, status=401)
        if not isinstance(request.data, dict):
            return Response({"detail": "TOOL_REQUEST_INVALID"}, status=400)
        run_uuid = _parse_uuid(request.data.get("run_uuid"))
        connection_uuid = _parse_uuid(request.data.get("connection_uuid"))
        if run_uuid is None or connection_uuid is None:
            return Response({"detail": "TOOL_REQUEST_INVALID"}, status=400)
        try:
            snapshot, created = create_tool_execution_snapshot(
                run_uuid=run_uuid,
                lensnode=node,
                connection_uuid=connection_uuid,
                tool_key=request.data.get("tool_key"),
                call_id=request.data.get("call_id"),
                arguments=request.data.get("arguments"),
            )
        except ToolSnapshotError as exc:
            return Response(
                {"detail": exc.code},
                status=exc.status_code,
            )
        response = Response(
            {
                "snapshot_uuid": str(snapshot.uuid),
                "run_uuid": str(snapshot.run.uuid),
                "connection_uuid": str(snapshot.connection.uuid),
                "tool_key": snapshot.tool_key,
                "invocation_id": snapshot.invocation_id,
                "plugin_key": snapshot.plugin_key,
                "plugin_version": snapshot.plugin_version,
                "protocol_version": snapshot.protocol_version,
            },
            status=(
                status.HTTP_201_CREATED
                if created
                else status.HTTP_200_OK
            ),
        )
        return response


class PluginCredentialLeaseView(
    PluginRuntimeNoStoreMixin,
    LensNodeAuthMixin,
    APIView,
):
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
                "run",
                "connection",
                "secret_version__material",
            )
            .filter(uuid=snapshot_uuid)
            .first()
        )
        if snapshot is None:
            return Response({"detail": "SNAPSHOT_NOT_FOUND"}, status=404)
        if _snapshot_node_id(snapshot) != node.pk:
            return Response({"detail": "SNAPSHOT_NODE_MISMATCH"}, status=403)
        if not _tool_snapshot_run_is_active(snapshot):
            return Response({"detail": "RUN_NOT_ACTIVE"}, status=409)
        if snapshot.connection.status != snapshot.connection.Status.ACTIVE:
            return Response({"detail": "CONNECTION_DISABLED"}, status=409)
        if (
            snapshot.secret_version is not None
            and snapshot.secret_version.status != "active"
        ):
            return Response({"detail": "SECRET_VERSION_DISABLED"}, status=409)
        if (
            snapshot.kind == ExecutionSnapshot.Kind.TOOL_INVOKE
            and snapshot.secret_version is not None
            and snapshot.secret_version.material.status != "active"
        ):
            return Response({"detail": "SECRET_MATERIAL_DISABLED"}, status=409)
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
        return response


class PluginCredentialMaterialView(
    PluginRuntimeNoStoreMixin,
    LensNodeAuthMixin,
    APIView,
):
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
                "snapshot__run",
            )
            .filter(uuid=lease_uuid, lensnode=node)
            .first()
        )
        if lease is None:
            return Response({"detail": "LEASE_NOT_FOUND"}, status=404)
        now = timezone.now()
        if lease.revoked_at is not None or lease.expires_at <= now:
            return Response({"detail": "LEASE_EXPIRED"}, status=410)
        if not _tool_snapshot_run_is_active(lease.snapshot):
            return Response({"detail": "RUN_NOT_ACTIVE"}, status=409)
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
        return response


class PluginExecutionSnapshotView(
    PluginRuntimeNoStoreMixin,
    LensNodeAuthMixin,
    APIView,
):
    """Return non-sensitive execution data to the owning LensNode."""

    authentication_classes = []
    permission_classes = []

    def get(self, request, snapshot_uuid):
        """Resolve one snapshot for a node without returning its secret."""

        node = self._authenticate_lensnode(request)
        if node is None:
            return Response({"detail": "LENSNODE_UNAUTHORIZED"}, status=401)
        snapshot = (
            ExecutionSnapshot.objects.select_related("datasource", "run")
            .filter(uuid=snapshot_uuid)
            .first()
        )
        if snapshot is None or _snapshot_node_id(snapshot) != node.pk:
            return Response({"detail": "SNAPSHOT_NOT_FOUND"}, status=404)
        payload = {
            "snapshot_uuid": str(snapshot.uuid),
            "plugin_key": snapshot.plugin_key,
            "plugin_version": snapshot.plugin_version,
            "protocol_version": snapshot.protocol_version,
            "resolved_config": _safe_snapshot_config(
                snapshot.resolved_config
            ),
        }
        if snapshot.kind == ExecutionSnapshot.Kind.DATASOURCE_SYNC:
            payload["datasource_uuid"] = str(snapshot.datasource.uuid)
        elif snapshot.kind == ExecutionSnapshot.Kind.TOOL_INVOKE:
            payload.update({
                "run_uuid": str(snapshot.run.uuid),
                "tool_key": snapshot.tool_key,
                "invocation_id": snapshot.invocation_id,
            })
        else:
            return Response({"detail": "SNAPSHOT_NOT_FOUND"}, status=404)
        response = Response(
            payload,
            status=status.HTTP_200_OK,
        )
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


def _parse_uuid(value):
    """Return a UUID or None for malformed external identifiers."""

    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _snapshot_node_id(snapshot):
    """Return the LensNode owner for a valid typed execution snapshot."""

    if (
        snapshot.kind == ExecutionSnapshot.Kind.DATASOURCE_SYNC
        and snapshot.datasource_id is not None
    ):
        return snapshot.datasource.lensnode_id
    if (
        snapshot.kind == ExecutionSnapshot.Kind.TOOL_INVOKE
        and snapshot.run_id is not None
    ):
        return snapshot.run.lensnode_id
    return None


def _tool_snapshot_run_is_active(snapshot):
    """Return whether a snapshot is executable under its Run lifecycle."""

    if snapshot.kind != ExecutionSnapshot.Kind.TOOL_INVOKE:
        return True
    return (
        snapshot.run_id is not None
        and snapshot.run.status in ACTIVE_RUN_STATUSES
    )
