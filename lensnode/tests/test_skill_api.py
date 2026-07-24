import json
from pathlib import Path

import httpx

from lensnode.agent_tools import _build_skill_api_tool
from lensnode.runtime_resources import RuntimeResources


def _resources(root):
    """Build runtime resources with one manual Skill environment."""

    skill_dir = Path(root) / "skills" / "devmind-connector"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# DevMind", encoding="utf-8")
    return RuntimeResources(
        root=Path(root),
        skill_paths=[str(skill_dir)],
        context_skill_contents=[],
        skill_environments={
            "devmind-connector": {
                "DEVMIND_BASE_URL": "http://devmind.example",
                "DEVMIND_USERNAME": "admin@example.com",
                "DEVMIND_PASSWORD": "super-secret",
            }
        },
        mcp_config_path=Path(root) / "mcp.json",
    )


def _install_transport(monkeypatch, handler):
    """Route Skill API requests through a mock transport."""

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("lensnode.agent_tools.httpx.Client", fake_client)


def test_manual_skill_api_uses_env_and_keeps_captured_token_private(
    monkeypatch,
    tmp_path,
):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/v1/auth/login":
            assert json.loads(request.content) == {
                "username": "admin@example.com",
                "password": "super-secret",
            }
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "access": "private-access-token",
                        "username": "admin@example.com",
                    },
                },
            )
        assert request.headers["authorization"] == (
            "Bearer private-access-token"
        )
        return httpx.Response(200, json={"items": [{"quote_no": "Q-1"}]})

    _install_transport(monkeypatch, handler)
    tool = _build_skill_api_tool(_resources(tmp_path))

    login = json.loads(
        tool.invoke(
            {
                "skill": "devmind-connector",
                "base_url_env": "DEVMIND_BASE_URL",
                "method": "POST",
                "path": "/api/v1/auth/login",
                "json_body": {
                    "username": "{{DEVMIND_USERNAME}}",
                    "password": "{{DEVMIND_PASSWORD}}",
                },
                "capture": {"access_token": "data.access"},
            }
        )
    )

    assert login["ok"] is True
    assert login["captured"] == ["access_token"]
    assert login["response"]["data"]["access"] == "***"
    assert login["response"]["data"]["username"] == "***"
    assert "private-access-token" not in json.dumps(login)
    assert "super-secret" not in json.dumps(login)

    quotations = json.loads(
        tool.invoke(
            {
                "skill": "devmind-connector",
                "base_url_env": "DEVMIND_BASE_URL",
                "path": "/api/v1/quotation/quotations",
                "headers": {
                    "Authorization": "Bearer {{session.access_token}}"
                },
            }
        )
    )

    assert quotations == {
        "ok": True,
        "status_code": 200,
        "response": {"items": [{"quote_no": "Q-1"}]},
    }
    assert len(requests) == 2


def test_manual_skill_api_rejects_unbound_env(monkeypatch, tmp_path):
    def handler(request):
        raise AssertionError(f"Unexpected request to {request.url}")

    _install_transport(monkeypatch, handler)
    tool = _build_skill_api_tool(_resources(tmp_path))

    payload = json.loads(
        tool.invoke(
            {
                "skill": "devmind-connector",
                "base_url_env": "MISSING_BASE_URL",
            }
        )
    )

    assert payload == {"ok": False, "error": "ENVIRONMENT_NOT_BOUND"}


def test_manual_skill_api_rejects_absolute_request_path(
    monkeypatch,
    tmp_path,
):
    def handler(request):
        raise AssertionError(f"Unexpected request to {request.url}")

    _install_transport(monkeypatch, handler)
    tool = _build_skill_api_tool(_resources(tmp_path))

    payload = json.loads(
        tool.invoke(
            {
                "skill": "devmind-connector",
                "base_url_env": "DEVMIND_BASE_URL",
                "path": "https://unexpected.example/secrets",
            }
        )
    )

    assert payload == {"ok": False, "error": "PATH_MUST_BE_RELATIVE"}
