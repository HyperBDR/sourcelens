import json
from contextlib import contextmanager
from types import SimpleNamespace

import httpx

from lensnode.plugin_tools import build_plugin_tools


def _command(tool_key):
    definitions = {
        "jira_get_issue": {
            "key": "jira_get_issue",
            "description": "Read one authorized Jira Issue.",
            "capability": "issue.read",
            "side_effect": "none",
            "input_schema": {
                "type": "object",
                "properties": {"issue_key": {"type": "string"}},
                "required": ["issue_key"],
            },
        },
        "jira_search_issues": {
            "key": "jira_search_issues",
            "description": "Search one authorized Jira project.",
            "capability": "jira.issue.search",
            "side_effect": "none",
            "input_schema": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "query": {"type": "string"},
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
                "plugin_key": "jira",
                "plugin_version": "1.0.0",
                "protocol_version": 1,
                "tools": [definitions[tool_key]],
            }
        ],
    }


class JiraRuntimeClient:
    """Provide control-plane and Jira Cloud responses."""

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
                    "plugin_key": "jira",
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
                    "plugin_key": "jira",
                    "endpoint": "https://company.atlassian.net",
                    "value": "jira-api-token",
                },
            )
        raise AssertionError(url)

    def get(self, url, **kwargs):
        if "/plugin-runtime/snapshots/" not in url:
            raise AssertionError(url)
        snapshot_uuid = url.rstrip("/").rsplit("/", 1)[-1]
        is_search = "search" in snapshot_uuid
        tool_key = "jira_search_issues" if is_search else "jira_get_issue"
        arguments = (
            {"project": "SL", "query": "plugin", "max_results": 10}
            if is_search
            else {"issue_key": "SL-488"}
        )
        return httpx.Response(
            200,
            json={
                "snapshot_uuid": snapshot_uuid,
                "run_uuid": "run-1",
                "tool_key": tool_key,
                "invocation_id": snapshot_uuid.removeprefix("snapshot-"),
                "plugin_key": "jira",
                "resolved_config": {
                    "endpoint": "https://company.atlassian.net",
                    "connection_config": {"email": "admin@example.com"},
                    "arguments": arguments,
                },
            },
        )

    @contextmanager
    def stream(self, method, url, **kwargs):
        assert method == "GET"
        authorization = kwargs["headers"]["Authorization"]
        assert authorization.startswith("Basic ")
        assert "jira-api-token" not in authorization
        if "/issue/SL-488" in url:
            yield httpx.Response(
                200,
                json={
                    "key": "SL-488",
                    "fields": {
                        "summary": "Plugin design",
                        "status": {"name": "In Progress"},
                    },
                },
            )
            return
        if url.endswith("/search/jql"):
            assert kwargs["params"]["jql"].startswith('project = "SL"')
            yield httpx.Response(
                200,
                json={
                    "issues": [
                        {
                            "key": "SL-488",
                            "fields": {
                                "summary": "Plugin design",
                                "status": {"name": "In Progress"},
                            },
                        }
                    ]
                },
            )
            return
        raise AssertionError(url)


def _config():
    return SimpleNamespace(
        ai_gateway_url="http://gateway/api/lens/lensnode/ai-gateway/",
        token="node-token",
    )


def test_jira_get_issue_uses_snapshot_connection_config_and_lease():
    tool = build_plugin_tools(
        _command("jira_get_issue"),
        _config(),
        JiraRuntimeClient(),
    )[0]

    result = json.loads(tool.func(
        issue_key="SL-488",
        runtime=SimpleNamespace(tool_call_id="read-1"),
    ))

    assert result["ok"] is True
    assert result["issue"]["key"] == "SL-488"
    assert "jira-api-token" not in json.dumps(result)
    assert tool.metadata["capability_family"] == "plugin"
    assert tool.metadata["plugin_key"] == "jira"
    assert tool.metadata["capability"] == "issue.read"


def test_jira_search_issues_builds_project_bounded_jql():
    tool = build_plugin_tools(
        _command("jira_search_issues"),
        _config(),
        JiraRuntimeClient(),
    )[0]

    result = json.loads(tool.func(
        project="SL",
        query="plugin",
        max_results=10,
        runtime=SimpleNamespace(tool_call_id="search-1"),
    ))

    assert result["ok"] is True
    assert result["items"][0]["key"] == "SL-488"
