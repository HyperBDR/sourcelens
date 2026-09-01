"""Control-plane helpers for trusted plugin execution."""

from urllib.parse import urlsplit, urlunsplit

import httpx


class PluginRuntimeError(RuntimeError):
    """Raised when a plugin runtime lease cannot be acquired."""


def lease_url(ai_gateway_url):
    """Build the plugin lease endpoint from the configured API URL."""

    parsed = urlsplit(str(ai_gateway_url or ""))
    path = parsed.path.rstrip("/")
    marker = "/api/lens/lensnode/ai-gateway"
    if marker in path:
        path = path.split(marker, 1)[0] + "/api/lens/plugin-runtime/leases"
    else:
        path = "/api/lens/plugin-runtime/leases"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def acquire_plugin_lease(client, ai_gateway_url, token, snapshot_uuid):
    """Acquire an opaque, snapshot-bound lease without returning secrets."""

    if not snapshot_uuid:
        raise PluginRuntimeError("PLUGIN_SNAPSHOT_REQUIRED")
    response = client.post(
        lease_url(ai_gateway_url),
        json={"snapshot_uuid": str(snapshot_uuid)},
        headers={"Authorization": f"Bearer {token}"},
    )
    if response.is_error:
        raise PluginRuntimeError("PLUGIN_LEASE_REQUEST_FAILED")
    payload = response.json()
    lease_uuid = payload.get("lease_uuid")
    if not lease_uuid:
        raise PluginRuntimeError("PLUGIN_LEASE_INVALID_RESPONSE")
    return {
        "lease_uuid": str(lease_uuid),
        "snapshot_uuid": str(payload.get("snapshot_uuid") or snapshot_uuid),
        "expires_at": payload.get("expires_at"),
    }


def retrieve_plugin_material(client, ai_gateway_url, token, lease_uuid):
    """Resolve lease-bound material in memory for the trusted plugin."""

    if not lease_uuid:
        raise PluginRuntimeError("PLUGIN_LEASE_REQUIRED")
    response = client.post(
        f"{lease_url(ai_gateway_url)}/{lease_uuid}/material/",
        headers={"Authorization": f"Bearer {token}"},
    )
    if response.is_error:
        raise PluginRuntimeError("PLUGIN_MATERIAL_REQUEST_FAILED")
    payload = response.json()
    value = payload.get("value")
    if not isinstance(value, str) or not value:
        raise PluginRuntimeError("PLUGIN_MATERIAL_INVALID_RESPONSE")
    return {
        "plugin_key": str(payload.get("plugin_key") or ""),
        "endpoint": str(payload.get("endpoint") or ""),
        "value": value,
    }
