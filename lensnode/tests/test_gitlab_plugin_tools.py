import json
from contextlib import contextmanager
from types import SimpleNamespace

import httpx

from lensnode.plugin_tools import build_plugin_tools


def _command(tool_key):
    definitions = {
        "gitlab_read_file": {
            "key": "gitlab_read_file",
            "description": "Read one authorized GitLab project file.",
            "capability": "repository.read",
            "side_effect": "none",
            "input_schema": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "path": {"type": "string"},
                    "ref": {"type": "string"},
                },
                "required": ["project", "path"],
            },
        },
        "gitlab_search_code": {
            "key": "gitlab_search_code",
            "description": "Search one authorized GitLab project.",
            "capability": "repository.read",
            "side_effect": "none",
            "input_schema": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "query": {"type": "string"},
                    "path": {"type": "string"},
                    "ref": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["project", "query"],
            },
        },
    }
    return {
        "run_uuid": "run-1",
        "loaded_plugins": [
            {
                "connection_uuid": "connection-1",
                "plugin_key": "gitlab",
                "plugin_version": "1.0.0",
                "protocol_version": 1,
                "tools": [definitions[tool_key]],
            }
        ],
    }


class GitLabRuntimeClient:
    """Provide control-plane and GitLab responses without real secrets."""

    def post(self, url, **kwargs):
        if url.endswith("/plugin-runtime/tool-snapshots/"):
            payload = kwargs["json"]
            return httpx.Response(
                201,
                json={
                    "snapshot_uuid": f"snapshot-{payload['call_id']}",
                    "run_uuid": payload["run_uuid"],
                    "connection_uuid": payload["connection_uuid"],
                    "tool_key": payload["tool_key"],
                    "invocation_id": payload["call_id"],
                    "plugin_key": "gitlab",
                },
            )
        if url.endswith("/plugin-runtime/leases/"):
            return httpx.Response(
                201,
                json={
                    "lease_uuid": "lease-1",
                    "snapshot_uuid": kwargs["json"]["snapshot_uuid"],
                },
            )
        if url.endswith("/material/"):
            return httpx.Response(
                200,
                json={
                    "plugin_key": "gitlab",
                    "endpoint": "https://gitlab.example",
                    "value": "gitlab-secret",
                },
            )
        raise AssertionError(url)

    def get(self, url, **kwargs):
        if "/plugin-runtime/snapshots/" in url:
            snapshot_uuid = url.rstrip("/").rsplit("/", 1)[-1]
            is_search = "search" in snapshot_uuid
            tool_key = (
                "gitlab_search_code" if is_search else "gitlab_read_file"
            )
            arguments = (
                {
                    "project": "platform/sourcelens",
                    "query": "PluginRuntime",
                    "max_results": 2,
                }
                if is_search
                else {
                    "project": "platform/sourcelens",
                    "path": "README.md",
                    "ref": "main",
                }
            )
            return httpx.Response(
                200,
                json={
                    "snapshot_uuid": snapshot_uuid,
                    "run_uuid": "run-1",
                    "tool_key": tool_key,
                    "invocation_id": snapshot_uuid.removeprefix("snapshot-"),
                    "plugin_key": "gitlab",
                    "resolved_config": {
                        "endpoint": "https://gitlab.example",
                        "arguments": arguments,
                    },
                },
            )
        raise AssertionError(url)

    @contextmanager
    def stream(self, method, url, **kwargs):
        assert method == "GET"
        assert kwargs["headers"]["PRIVATE-TOKEN"] == "gitlab-secret"
        if url.endswith("/raw"):
            yield httpx.Response(200, text="# GitLab project\n")
            return
        if url.endswith("/search"):
            yield httpx.Response(
                200,
                json=[
                    {
                        "filename": "plugin_tools.py",
                        "path": "lensnode/plugin_tools.py",
                        "ref": "main",
                    }
                ],
            )
            return
        raise AssertionError(url)


def _config():
    return SimpleNamespace(
        ai_gateway_url="http://gateway/api/lens/lensnode/ai-gateway/",
        token="node-token",
    )


def test_gitlab_read_file_uses_snapshot_endpoint_and_lease():
    tool = build_plugin_tools(
        _command("gitlab_read_file"),
        _config(),
        GitLabRuntimeClient(),
    )[0]

    result = json.loads(tool.func(
        project="platform/sourcelens",
        path="README.md",
        ref="main",
        runtime=SimpleNamespace(tool_call_id="read-1"),
    ))

    assert result["ok"] is True
    assert result["content"] == "# GitLab project\n"
    assert "gitlab-secret" not in json.dumps(result)


def test_gitlab_search_code_returns_only_bounded_metadata():
    tool = build_plugin_tools(
        _command("gitlab_search_code"),
        _config(),
        GitLabRuntimeClient(),
    )[0]

    result = json.loads(tool.func(
        project="platform/sourcelens",
        query="PluginRuntime",
        path="",
        ref="",
        max_results=2,
        runtime=SimpleNamespace(tool_call_id="search-1"),
    ))

    assert result == {
        "ok": True,
        "project": "platform/sourcelens",
        "query": "PluginRuntime",
        "items": [
            {
                "name": "plugin_tools.py",
                "path": "lensnode/plugin_tools.py",
                "ref": "main",
            }
        ],
    }
