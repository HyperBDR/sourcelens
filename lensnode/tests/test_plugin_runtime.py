from types import SimpleNamespace

import httpx

from lensnode.main import LensNodeClient
from lensnode.plugin_runtime import (
    acquire_plugin_lease,
    fetch_plugin_snapshot,
    lease_url,
)


def test_lease_url_replaces_ai_gateway_path():
    assert lease_url(
        "http://gateway/api/lens/lensnode/ai-gateway/"
    ) == "http://gateway/api/lens/plugin-runtime/leases/"


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
            assert url.endswith("/plugin-runtime/leases/")
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


def test_retrieve_plugin_material_uses_snapshot_lease_path():
    class Client:
        def post(self, url, **kwargs):
            assert url.endswith("/plugin-runtime/leases/lease-1/material/")
            assert "json" not in kwargs
            return httpx.Response(200, json={"value": "secret"})

    from lensnode.plugin_runtime import retrieve_plugin_material

    result = retrieve_plugin_material(
        Client(),
        "http://gateway/api/lens/lensnode/ai-gateway/",
        "node-token",
        "lease-1",
    )
    assert result["value"] == "secret"


def test_fetch_plugin_snapshot_returns_non_sensitive_config():
    class Client:
        def get(self, url, **kwargs):
            assert url.endswith("/plugin-runtime/snapshots/snapshot-1/")
            assert kwargs["headers"]["Authorization"] == "Bearer node-token"
            return httpx.Response(
                200,
                json={
                    "snapshot_uuid": "snapshot-1",
                    "resolved_config": {"target_path": "/workspace/repo"},
                },
            )

    result = fetch_plugin_snapshot(
        Client(),
        "http://gateway/api/lens/lensnode/ai-gateway/",
        "node-token",
        "snapshot-1",
    )
    assert result["resolved_config"]["target_path"] == "/workspace/repo"


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
        "lensnode.main.fetch_plugin_snapshot",
        lambda *args: {
            "plugin_key": "github",
            "datasource_uuid": "datasource-1",
            "resolved_config": {
                "endpoint": "https://github.com",
                "target_path": "/workspace/repo",
                "datasource_config": {"repository": "owner/repo"},
            },
        },
    )
    monkeypatch.setattr(
        "lensnode.main.retrieve_plugin_material",
        lambda *args: {"plugin_key": "github", "value": "secret"},
    )
    seen = {}

    def fake_sync(command, workspace, emit):
        seen["token"] = command["config"].get("access_token")
        return {"status": "success"}

    monkeypatch.setattr("lensnode.main.sync_datasource", fake_sync)

    result = client._execute_plugin_datasource_sync(
        {"snapshot_uuid": "snapshot-1", "access_token": "must-not-use"}
    )
    assert result["status"] == "success"
    assert seen["token"] == "secret"


def test_plugin_sync_rejects_material_for_another_plugin(monkeypatch):
    client = LensNodeClient.__new__(LensNodeClient)
    client.config = SimpleNamespace(
        ai_gateway_url="http://gateway/api/lens/lensnode/ai-gateway/",
        token="node-token",
    )
    client.gateway_http_client = object()
    monkeypatch.setattr(
        "lensnode.main.fetch_plugin_snapshot",
        lambda *args: {
            "plugin_key": "github",
            "resolved_config": {"datasource_config": {}},
        },
    )
    monkeypatch.setattr(
        "lensnode.main.acquire_plugin_lease",
        lambda *args: {"lease_uuid": "lease-1"},
    )
    material = {"plugin_key": "gitlab", "value": "secret"}
    monkeypatch.setattr(
        "lensnode.main.retrieve_plugin_material",
        lambda *args: material,
    )

    result = client._execute_plugin_datasource_sync(
        {"snapshot_uuid": "snapshot-1"}
    )

    assert result["error"] == "PLUGIN_MATERIAL_MISMATCH"
    assert material["value"] == ""
