"""Jira Cloud LensNode runtime entrypoint."""

import base64
import json
from typing import Annotated
from urllib.parse import quote, urlsplit, urlunsplit

from langchain.tools import ToolRuntime, tool
from pydantic import Field

from lensnode.plugin_runtime import PluginRuntimeError

PLUGIN_API_VERSION = 1
PLUGIN_KEY = "jira"
PLUGIN_VERSION = "1.0.0"
RESPONSE_MAX_BYTES = 1_000_000


def http_origins(endpoint):
    """Return the validated Jira Cloud origin for connection pooling."""

    return (_endpoint(endpoint),)


def build_tool(definition, executor):
    """Create a fixed Jira Cloud read-only tool."""

    if not isinstance(definition, dict) or definition.get("side_effect") != "none":
        raise PluginRuntimeError("PLUGIN_TOOL_NOT_READ_ONLY")
    key, description = str(definition.get("key") or ""), str(definition.get("description") or "").strip()
    expected = {"jira_get_issue": "issue.read", "jira_search_issues": "jira.issue.search"}.get(key)
    if not expected or definition.get("capability") != expected: raise PluginRuntimeError("PLUGIN_TOOL_NOT_READ_ONLY")
    if not description: raise PluginRuntimeError("PLUGIN_TOOL_DESCRIPTION_REQUIRED")
    if key == "jira_get_issue":
        def invoke(issue_key: Annotated[str, Field(min_length=3, max_length=40)], runtime: ToolRuntime) -> str:
            return executor(key, {"issue_key": issue_key}, runtime)
        return tool(key, description=description)(invoke)
    def invoke(project: Annotated[str, Field(min_length=2, max_length=20)], query: Annotated[str, Field(min_length=1, max_length=500)], runtime: ToolRuntime, max_results: Annotated[int, Field(ge=1, le=20)] = 10) -> str:
        return executor(key, {"project": project, "query": query, "max_results": max_results}, runtime)
    return tool(key, description=description)(invoke)


def execute_tool(key, client, arguments, secret, endpoint, config):
    """Execute one bounded Jira Cloud REST call."""

    endpoint, headers = _endpoint(endpoint), _headers(secret, config)
    if key == "jira_get_issue":
        payload = _request(client, f"{endpoint}/rest/api/3/issue/{quote(_text(arguments, 'issue_key'), safe='')}", headers, {"fields": "summary,status,assignee,priority,updated,description"})
        return {"ok": True, "issue": _issue(payload)}
    if key == "jira_search_issues":
        project, query = _text(arguments, "project"), _text(arguments, "query")
        max_results = arguments.get("max_results", 10)
        escaped = query.replace("\\", "\\\\").replace('"', '\\"')
        payload = _request(client, f"{endpoint}/rest/api/3/search/jql", headers, {"jql": f'project = "{project}" AND text ~ "{escaped}"', "maxResults": max_results, "fields": "summary,status,assignee,priority,updated"})
        issues = payload.get("issues") if isinstance(payload, dict) else None
        if not isinstance(issues, list): raise PluginRuntimeError("JIRA_RESPONSE_INVALID")
        return {"ok": True, "project": project, "query": query, "items": [_issue(item) for item in issues[:max_results]]}
    raise PluginRuntimeError("PLUGIN_TOOL_UNSUPPORTED")


def build_datasource_command(snapshot, material, trigger):
    """Build one Jira datasource command from frozen Jira state."""

    resolved = snapshot.get("resolved_config")
    if not isinstance(resolved, dict): raise PluginRuntimeError("PLUGIN_CONFIG_INVALID")
    endpoint = _endpoint(resolved.get("endpoint"))
    if not isinstance(material, dict) or material.get("plugin_key") != PLUGIN_KEY or str(material.get("endpoint") or "").rstrip("/") != endpoint or not material.get("value"): raise PluginRuntimeError("PLUGIN_MATERIAL_MISMATCH")
    datasource, config = resolved.get("datasource_config") or {}, resolved.get("connection_config") or {}
    project = datasource.get("project") if isinstance(datasource, dict) else ""
    if not isinstance(project, str) or not project or not isinstance(config, dict): raise PluginRuntimeError("PLUGIN_CONFIG_INVALID")
    return {"source_type": "jira", "datasource_uuid": snapshot.get("datasource_uuid"), "target_path": resolved.get("target_path"), "sync_policy": resolved.get("sync_policy") or {}, "trigger": trigger, "config": {"endpoint": endpoint, "email": config.get("email"), "access_token": material["value"], "project": project, "max_issues": datasource.get("max_issues") or 100}}


def _endpoint(value):
    parsed = urlsplit(str(value or "").strip()); hostname = (parsed.hostname or "").lower()
    if (parsed.scheme != "https" or not hostname.endswith(".atlassian.net") or hostname == "atlassian.net" or parsed.username is not None or parsed.password is not None or parsed.port not in {None, 443} or parsed.path not in {"", "/"} or parsed.query or parsed.fragment): raise PluginRuntimeError("PLUGIN_SNAPSHOT_MISMATCH")
    return urlunsplit(("https", parsed.netloc, "", "", ""))


def _headers(token, config):
    email = config.get("email") if isinstance(config, dict) else ""
    if not isinstance(email, str) or not email or not token: raise PluginRuntimeError("PLUGIN_SNAPSHOT_MISMATCH")
    auth = base64.b64encode(f"{email}:{token}".encode()).decode("ascii")
    return {"Accept": "application/json", "Authorization": f"Basic {auth}", "User-Agent": "SourceLens-LensNode"}


def _text(arguments, name):
    value = arguments.get(name)
    if not isinstance(value, str) or not value: raise PluginRuntimeError("PLUGIN_ARGUMENTS_INVALID")
    return value


def _request(client, url, headers, params):
    with client.stream("GET", url, params=params, headers=headers, follow_redirects=False) as response:
        if response.is_redirect: raise PluginRuntimeError("JIRA_REDIRECT_REJECTED")
        if response.status_code >= 400: raise PluginRuntimeError({404: "JIRA_NOT_FOUND", 401: "JIRA_ACCESS_DENIED", 403: "JIRA_ACCESS_DENIED", 429: "JIRA_RATE_LIMITED"}.get(response.status_code, "JIRA_REQUEST_FAILED"))
        body = b"".join(response.iter_bytes())
    if len(body) > RESPONSE_MAX_BYTES: raise PluginRuntimeError("JIRA_RESPONSE_TOO_LARGE")
    try: payload = json.loads(body)
    except (UnicodeDecodeError, ValueError) as exc: raise PluginRuntimeError("JIRA_RESPONSE_INVALID") from exc
    if not isinstance(payload, dict): raise PluginRuntimeError("JIRA_RESPONSE_INVALID")
    return payload


def _issue(value):
    if not isinstance(value, dict) or not isinstance(value.get("fields"), dict) or not isinstance(value.get("key"), str): raise PluginRuntimeError("JIRA_RESPONSE_INVALID")
    fields = value["fields"]
    def nested(name):
        item = fields.get(name); return str(item.get("name") or item.get("displayName") or "")[:160] if isinstance(item, dict) else ""
    return {"key": value["key"][:40], "summary": str(fields.get("summary") or "")[:1000], "status": nested("status"), "assignee": nested("assignee"), "priority": nested("priority"), "updated": str(fields.get("updated") or "")[:64], "description": _description(fields.get("description"))}


def _description(value):
    output = []
    def visit(item):
        if len("".join(output)) >= 20000: return
        if isinstance(item, dict):
            if isinstance(item.get("text"), str): output.append(item["text"])
            for child in item.get("content") or []: visit(child)
        elif isinstance(item, list):
            for child in item: visit(child)
    visit(value); return "\n".join(output)[:20000]
