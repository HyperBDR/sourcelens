import json
from pathlib import Path

import httpx

from lensnode.agent_tools import _build_save_deliverable_tool
from lensnode.config import LensNodeConfig
from lensnode.runtime_resources import RuntimeResources


def _config():
    """Build a minimal config pointing at a fake upload URL."""

    return LensNodeConfig(
        name="test-node",
        token="test-token",
        control_ws_url="ws://backend/ws/",
        ai_gateway_url="http://b/api/lens/lensnode/ai-gateway/",
        deliverable_upload_url="http://b/api/lens/lensnode/deliverables/",
        deliverable_max_bytes=50 * 1024 * 1024,
        workspace_path="/workspace",
        protocol_version="v1",
        agent_version="0.1.0",
        heartbeat_interval_s=15,
        request_timeout_s=30,
        run_idle_timeout_s=180,
        max_concurrent_runs=1,
        summary_trigger_tokens=48000,
        summary_keep_tokens=16000,
    )


def _resources(root):
    """Build RuntimeResources rooted at the given scratch dir."""

    return RuntimeResources(
        root=Path(root),
        skill_paths=[],
        context_skill_contents=[],
        mcp_config_path=Path(root) / "mcp.json",
    )


def _install_transport(monkeypatch, handler):
    """Route agent_tools' httpx.Client through a mock transport."""

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("lensnode.agent_tools.httpx.Client", fake_client)


def test_save_deliverable_uploads_file(monkeypatch, tmp_path):
    (tmp_path / "report.html").write_text("<h1>ok</h1>", encoding="utf-8")
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = request.read()
        return httpx.Response(201, json={"ok": True})

    _install_transport(monkeypatch, handler)
    events = []
    tool = _build_save_deliverable_tool(
        {"run_uuid": "run-123"},
        _resources(tmp_path),
        _config(),
        lambda name, detail: events.append((name, detail)),
    )

    payload = json.loads(tool.invoke({"path": "report.html"}))

    assert payload["ok"] is True
    assert payload["filename"] == "report.html"
    assert captured["url"].endswith("/api/lens/lensnode/deliverables/")
    assert captured["auth"] == "Bearer test-token"
    assert b"run-123" in captured["body"]
    assert b"<h1>ok</h1>" in captured["body"]
    assert ("tool.save_deliverable.done", None) not in events
    assert any(name == "tool.save_deliverable.done" for name, _ in events)


def test_save_deliverable_rejects_escape(monkeypatch, tmp_path):
    def handler(request):
        raise AssertionError("upload must not be attempted")

    _install_transport(monkeypatch, handler)
    tool = _build_save_deliverable_tool(
        {"run_uuid": "run-123"},
        _resources(tmp_path),
        _config(),
        None,
    )

    payload = json.loads(tool.invoke({"path": "../secret.txt"}))

    assert payload["ok"] is False
    assert payload["error"] == "PATH_NOT_ALLOWED"


def test_save_deliverable_rejects_oversized(monkeypatch, tmp_path):
    (tmp_path / "big.html").write_text("x" * 100, encoding="utf-8")

    def handler(request):
        raise AssertionError("upload must not be attempted")

    _install_transport(monkeypatch, handler)
    cfg = _config()
    object.__setattr__(cfg, "deliverable_max_bytes", 10)
    tool = _build_save_deliverable_tool(
        {"run_uuid": "run-123"},
        _resources(tmp_path),
        cfg,
        None,
    )

    payload = json.loads(tool.invoke({"path": "big.html"}))

    assert payload["ok"] is False
    assert payload["error"] == "FILE_TOO_LARGE"


def test_save_deliverable_missing_file(monkeypatch, tmp_path):
    def handler(request):
        raise AssertionError("upload must not be attempted")

    _install_transport(monkeypatch, handler)
    tool = _build_save_deliverable_tool(
        {"run_uuid": "run-123"},
        _resources(tmp_path),
        _config(),
        None,
    )

    payload = json.loads(tool.invoke({"path": "nope.html"}))

    assert payload["ok"] is False
    assert payload["error"] == "FILE_NOT_FOUND"
