from types import SimpleNamespace

import httpx

from lensnode.main import LensNodeClient
from lensnode.plugin_runtime import acquire_plugin_lease, lease_url


def test_lease_url_replaces_ai_gateway_path():
    assert lease_url(
        "http://gateway/api/lens/lensnode/ai-gateway/"
    ) == "http://gateway/api/lens/plugin-runtime/leases"


def test_acquire_plugin_lease_returns_opaque_metadata():
    request = httpx.Request(
        "POST",
        "http://gateway/api/lens/plugin-runtime/leases",
    )
    response = httpx.Response(
        200,
        json={
            "lease_uuid": "lease-1",
            "snapshot_uuid": "snapshot-1",
            "expires_at": "2099-01-01T00:00:00Z",
        },
        request=request,
    )

    class Client:
        def post(self, url, **kwargs):
            assert url.endswith("/plugin-runtime/leases")
            assert kwargs["json"] == {"snapshot_uuid": "snapshot-1"}
            assert "secret" not in kwargs
            return response

    result = acquire_plugin_lease(
        Client(),
        "http://gateway/api/lens/lensnode/ai-gateway/",
        "node-token",
        "snapshot-1",
    )
    assert result["lease_uuid"] == "lease-1"
    assert "access_token" not in result


def test_plugin_sync_does_not_fallback_to_legacy_credentials(monkeypatch):
    client = LensNodeClient.__new__(LensNodeClient)
    client.config = SimpleNamespace(
        ai_gateway_url="http://gateway/api/lens/lensnode/ai-gateway/",
        token="node-token",
    )
    client.gateway_http_client = object()
    monkeypatch.setattr(
        "lensnode.main.acquire_plugin_lease",
        lambda *args: {"lease_uuid": "lease-1"},
    )
    monkeypatch.setattr(
        "lensnode.main.retrieve_plugin_material",
        lambda *args: {"value": "secret"},
    )

    result = client._execute_plugin_datasource_sync(
        {"snapshot_uuid": "snapshot-1", "access_token": "must-not-use"}
    )
    assert result == {
        "status": "failed",
        "error": "PLUGIN_PROVIDER_RUNTIME_UNAVAILABLE",
    }
