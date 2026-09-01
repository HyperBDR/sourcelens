"""Model-facing tools backed by trusted built-in Plugin runtimes."""

import base64
import json
import time
from typing import Annotated
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
from langchain.tools import ToolRuntime, tool
from pydantic import Field

from .plugin_runtime import (
    PluginRuntimeError,
    acquire_plugin_lease,
    create_plugin_tool_snapshot,
    fetch_plugin_snapshot,
    retrieve_plugin_material,
)


GITHUB_API_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
GITHUB_READ_MAX_BYTES = 200_000
GITHUB_SEARCH_MAX_BYTES = 1_000_000
GITLAB_READ_MAX_BYTES = 200_000
GITLAB_SEARCH_MAX_BYTES = 1_000_000
JIRA_RESPONSE_MAX_BYTES = 1_000_000


class PluginToolError(RuntimeError):
    """Raised when a frozen Plugin Tool cannot be safely registered."""


def build_plugin_tools(command, config, http_client, emit_event=None):
    """Build allowlisted tools from one Run's frozen Plugin bindings."""

    loaded_plugins = command.get("loaded_plugins") or []
    if not loaded_plugins:
        return []
    if not isinstance(loaded_plugins, list):
        raise PluginToolError("PLUGIN_BINDINGS_INVALID")
    tools = []
    seen_keys = set()
    for plugin in loaded_plugins:
        if not isinstance(plugin, dict):
            raise PluginToolError("PLUGIN_BINDING_INVALID")
        plugin_key = str(plugin.get("plugin_key") or "")
        if plugin_key not in {"github", "gitlab", "jira"} or plugin.get(
            "protocol_version"
        ) != 1:
            raise PluginToolError("PLUGIN_RUNTIME_UNSUPPORTED")
        connection_uuid = str(plugin.get("connection_uuid") or "")
        if not connection_uuid:
            raise PluginToolError("PLUGIN_CONNECTION_REQUIRED")
        for definition in plugin.get("tools") or []:
            tool_key = str(
                definition.get("key")
                if isinstance(definition, dict)
                else ""
            )
            if tool_key in seen_keys:
                raise PluginToolError("PLUGIN_TOOL_NAME_CONFLICT")
            builder = {
                "github": _build_github_tool,
                "gitlab": _build_gitlab_tool,
                "jira": _build_jira_tool,
            }[plugin_key]
            registered = builder(
                command,
                config,
                http_client,
                connection_uuid,
                definition,
                emit_event,
            )
            seen_keys.add(tool_key)
            tools.append(registered)
    return tools


def _build_github_tool(
    command,
    config,
    http_client,
    connection_uuid,
    definition,
    emit_event,
):
    """Return one fixed GitHub implementation for a frozen declaration."""

    if not isinstance(definition, dict):
        raise PluginToolError("PLUGIN_TOOL_INVALID")
    tool_key = str(definition.get("key") or "")
    if (
        definition.get("capability") != "repository.read"
        or definition.get("side_effect") != "none"
    ):
        raise PluginToolError("PLUGIN_TOOL_NOT_READ_ONLY")
    description = str(definition.get("description") or "").strip()
    if not description:
        raise PluginToolError("PLUGIN_TOOL_DESCRIPTION_REQUIRED")

    if tool_key == "github_read_file":

        def invoke(
            repository: Annotated[
                str,
                Field(min_length=3, max_length=201),
            ],
            path: Annotated[
                str,
                Field(min_length=1, max_length=4096),
            ],
            runtime: ToolRuntime,
            ref: Annotated[str, Field(max_length=255)] = "",
        ) -> str:
            return _execute_plugin_tool(
                command,
                config,
                http_client,
                connection_uuid,
                "github",
                tool_key,
                runtime,
                {
                    "repository": repository,
                    "path": path,
                    "ref": ref,
                },
                _github_read_file,
                emit_event,
            )

        return tool(
            tool_key,
            description=description,
        )(invoke)

    if tool_key == "github_search_code":

        def invoke(
            repository: Annotated[
                str,
                Field(min_length=3, max_length=201),
            ],
            query: Annotated[
                str,
                Field(min_length=1, max_length=1024),
            ],
            runtime: ToolRuntime,
            path: Annotated[str, Field(max_length=4096)] = "",
            max_results: Annotated[int, Field(ge=1, le=20)] = 10,
        ) -> str:
            return _execute_plugin_tool(
                command,
                config,
                http_client,
                connection_uuid,
                "github",
                tool_key,
                runtime,
                {
                    "repository": repository,
                    "query": query,
                    "path": path,
                    "max_results": max_results,
                },
                _github_search_code,
                emit_event,
            )

        return tool(
            tool_key,
            description=description,
        )(invoke)

    raise PluginToolError("PLUGIN_TOOL_UNSUPPORTED")


def _build_gitlab_tool(
    command,
    config,
    http_client,
    connection_uuid,
    definition,
    emit_event,
):
    """Return one fixed GitLab implementation for a frozen declaration."""

    if not isinstance(definition, dict):
        raise PluginToolError("PLUGIN_TOOL_INVALID")
    tool_key = str(definition.get("key") or "")
    if (
        definition.get("capability") != "repository.read"
        or definition.get("side_effect") != "none"
    ):
        raise PluginToolError("PLUGIN_TOOL_NOT_READ_ONLY")
    description = str(definition.get("description") or "").strip()
    if not description:
        raise PluginToolError("PLUGIN_TOOL_DESCRIPTION_REQUIRED")

    if tool_key == "gitlab_read_file":

        def invoke(
            project: Annotated[str, Field(min_length=3, max_length=255)],
            path: Annotated[str, Field(min_length=1, max_length=4096)],
            runtime: ToolRuntime,
            ref: Annotated[str, Field(max_length=255)] = "",
        ) -> str:
            return _execute_plugin_tool(
                command,
                config,
                http_client,
                connection_uuid,
                "gitlab",
                tool_key,
                runtime,
                {"project": project, "path": path, "ref": ref},
                _gitlab_read_file,
                emit_event,
            )

        return tool(tool_key, description=description)(invoke)

    if tool_key == "gitlab_search_code":

        def invoke(
            project: Annotated[str, Field(min_length=3, max_length=255)],
            query: Annotated[str, Field(min_length=1, max_length=1024)],
            runtime: ToolRuntime,
            path: Annotated[str, Field(max_length=4096)] = "",
            ref: Annotated[str, Field(max_length=255)] = "",
            max_results: Annotated[int, Field(ge=1, le=20)] = 10,
        ) -> str:
            return _execute_plugin_tool(
                command,
                config,
                http_client,
                connection_uuid,
                "gitlab",
                tool_key,
                runtime,
                {
                    "project": project,
                    "query": query,
                    "path": path,
                    "ref": ref,
                    "max_results": max_results,
                },
                _gitlab_search_code,
                emit_event,
            )

        return tool(tool_key, description=description)(invoke)

    raise PluginToolError("PLUGIN_TOOL_UNSUPPORTED")


def _build_jira_tool(
    command,
    config,
    http_client,
    connection_uuid,
    definition,
    emit_event,
):
    """Return one fixed Jira Cloud implementation for a frozen declaration."""

    if not isinstance(definition, dict):
        raise PluginToolError("PLUGIN_TOOL_INVALID")
    tool_key = str(definition.get("key") or "")
    if definition.get("side_effect") != "none":
        raise PluginToolError("PLUGIN_TOOL_NOT_READ_ONLY")
    expected_capability = {
        "jira_get_issue": "issue.read",
        "jira_search_issues": "jira.issue.search",
    }.get(tool_key)
    if not expected_capability or definition.get(
        "capability"
    ) != expected_capability:
        raise PluginToolError("PLUGIN_TOOL_NOT_READ_ONLY")
    description = str(definition.get("description") or "").strip()
    if not description:
        raise PluginToolError("PLUGIN_TOOL_DESCRIPTION_REQUIRED")

    if tool_key == "jira_get_issue":

        def invoke(
            issue_key: Annotated[str, Field(min_length=3, max_length=40)],
            runtime: ToolRuntime,
        ) -> str:
            return _execute_plugin_tool(
                command,
                config,
                http_client,
                connection_uuid,
                "jira",
                tool_key,
                runtime,
                {"issue_key": issue_key},
                _jira_get_issue,
                emit_event,
            )

        return tool(tool_key, description=description)(invoke)

    if tool_key == "jira_search_issues":

        def invoke(
            project: Annotated[str, Field(min_length=2, max_length=20)],
            query: Annotated[str, Field(min_length=1, max_length=500)],
            runtime: ToolRuntime,
            max_results: Annotated[int, Field(ge=1, le=20)] = 10,
        ) -> str:
            return _execute_plugin_tool(
                command,
                config,
                http_client,
                connection_uuid,
                "jira",
                tool_key,
                runtime,
                {
                    "project": project,
                    "query": query,
                    "max_results": max_results,
                },
                _jira_search_issues,
                emit_event,
            )

        return tool(tool_key, description=description)(invoke)

    raise PluginToolError("PLUGIN_TOOL_UNSUPPORTED")


def _execute_plugin_tool(
    command,
    config,
    http_client,
    connection_uuid,
    plugin_key,
    tool_key,
    runtime,
    arguments,
    handler,
    emit_event,
):
    """Authorize, lease, and execute one Tool without exposing secret."""

    call_id = str(getattr(runtime, "tool_call_id", "") or "")
    started = time.monotonic()
    _emit(
        emit_event,
        "tool.plugin.start",
        {
            "plugin": plugin_key,
            "tool": tool_key,
            "invocation_id": call_id,
        },
    )
    material = None
    error = ""
    try:
        if not call_id:
            raise PluginRuntimeError("PLUGIN_TOOL_CALL_ID_REQUIRED")
        snapshot = create_plugin_tool_snapshot(
            http_client,
            config.ai_gateway_url,
            config.token,
            command.get("run_uuid"),
            connection_uuid,
            tool_key,
            call_id,
            arguments,
        )
        snapshot_uuid = snapshot["snapshot_uuid"]
        resolved = fetch_plugin_snapshot(
            http_client,
            config.ai_gateway_url,
            config.token,
            snapshot_uuid,
        )
        normalized_arguments, endpoint, connection_config = _validate_snapshot(
            resolved,
            command.get("run_uuid"),
            plugin_key,
            tool_key,
            call_id,
        )
        lease = acquire_plugin_lease(
            http_client,
            config.ai_gateway_url,
            config.token,
            snapshot_uuid,
        )
        material = retrieve_plugin_material(
            http_client,
            config.ai_gateway_url,
            config.token,
            lease["lease_uuid"],
        )
        if (
            material.get("plugin_key") != plugin_key
            or material.get("endpoint", "").rstrip("/") != endpoint
        ):
            raise PluginRuntimeError("PLUGIN_MATERIAL_MISMATCH")
        result = handler(
            http_client,
            normalized_arguments,
            material["value"],
            endpoint,
            connection_config,
        )
    except PluginRuntimeError as exc:
        error = str(exc)
        result = {"ok": False, "error": error}
    except httpx.HTTPError:
        error = f"{plugin_key.upper()}_REQUEST_FAILED"
        result = {"ok": False, "error": error}
    finally:
        if material is not None:
            material["value"] = ""
        _emit(
            emit_event,
            "tool.plugin.done",
            {
                "plugin": plugin_key,
                "tool": tool_key,
                "invocation_id": call_id,
                "ok": not error,
                "error": error,
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
        )
    return _json(result)


def _validate_snapshot(snapshot, run_uuid, plugin_key, tool_key, call_id):
    """Return normalized arguments from the matching control-plane snapshot."""

    resolved_config = snapshot.get("resolved_config")
    if (
        str(snapshot.get("run_uuid") or "") != str(run_uuid or "")
        or snapshot.get("plugin_key") != plugin_key
        or snapshot.get("tool_key") != tool_key
        or str(snapshot.get("invocation_id") or "") != call_id
        or not isinstance(resolved_config, dict)
        or not isinstance(resolved_config.get("arguments"), dict)
    ):
        raise PluginRuntimeError("PLUGIN_SNAPSHOT_MISMATCH")
    endpoint = _runtime_endpoint(plugin_key, resolved_config.get("endpoint"))
    connection_config = resolved_config.get("connection_config") or {}
    if not isinstance(connection_config, dict):
        raise PluginRuntimeError("PLUGIN_SNAPSHOT_MISMATCH")
    return resolved_config["arguments"], endpoint, connection_config


def _github_read_file(
    client,
    arguments,
    token,
    endpoint="https://github.com",
    connection_config=None,
):
    """Read one text file from the fixed public GitHub REST API host."""

    del endpoint, connection_config
    repository = _required_text(arguments, "repository")
    path = _required_text(arguments, "path")
    ref = str(arguments.get("ref") or "")
    status_code, content, truncated = _github_get(
        client,
        (
            f"{GITHUB_API_URL}/repos/{quote(repository, safe='/')}"
            f"/contents/{quote(path, safe='/')}"
        ),
        token,
        params={"ref": ref} if ref else None,
        accept="application/vnd.github.raw+json",
        max_bytes=GITHUB_READ_MAX_BYTES,
        truncate=True,
    )
    if status_code >= 400:
        raise PluginRuntimeError(_github_error(status_code))
    if b"\x00" in content:
        raise PluginRuntimeError("GITHUB_FILE_NOT_TEXT")
    return {
        "ok": True,
        "repository": repository,
        "path": path,
        "ref": ref,
        "content": content.decode("utf-8", errors="replace"),
        "truncated": truncated,
    }


def _github_search_code(
    client,
    arguments,
    token,
    endpoint="https://github.com",
    connection_config=None,
):
    """Search the default branch and return only bounded result metadata."""

    del endpoint, connection_config
    repository = _required_text(arguments, "repository")
    query = _required_text(arguments, "query")
    path = str(arguments.get("path") or "")
    max_results = arguments.get("max_results", 10)
    qualifiers = [query, f"repo:{repository}"]
    if path:
        qualifiers.append(f"path:{path}")
    status_code, content, truncated = _github_get(
        client,
        f"{GITHUB_API_URL}/search/code",
        token,
        params={
            "q": " ".join(qualifiers),
            "per_page": max_results,
            "page": 1,
        },
        accept="application/vnd.github+json",
        max_bytes=GITHUB_SEARCH_MAX_BYTES,
        truncate=False,
    )
    if status_code >= 400:
        raise PluginRuntimeError(_github_error(status_code))
    if truncated:
        raise PluginRuntimeError("GITHUB_RESPONSE_TOO_LARGE")
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, ValueError) as exc:
        raise PluginRuntimeError("GITHUB_RESPONSE_INVALID") from exc
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise PluginRuntimeError("GITHUB_RESPONSE_INVALID")
    safe_items = []
    for item in items[:max_results]:
        if not isinstance(item, dict):
            continue
        safe_items.append({
            "name": str(item.get("name") or "")[:255],
            "path": str(item.get("path") or "")[:4096],
            "sha": str(item.get("sha") or "")[:128],
        })
    total_count = payload.get("total_count", len(safe_items))
    if isinstance(total_count, bool) or not isinstance(total_count, int):
        total_count = len(safe_items)
    return {
        "ok": True,
        "repository": repository,
        "query": query,
        "path": path,
        "total_count": max(total_count, 0),
        "items": safe_items,
    }


def _gitlab_read_file(
    client,
    arguments,
    token,
    endpoint,
    connection_config=None,
):
    """Read one text file from a validated GitLab REST API host."""

    del connection_config
    project = _required_text(arguments, "project")
    path = _required_text(arguments, "path")
    ref = str(arguments.get("ref") or "main")
    status_code, content, truncated = _gitlab_get(
        client,
        (
            f"{endpoint}/api/v4/projects/{quote(project, safe='')}"
            f"/repository/files/{quote(path, safe='')}/raw"
        ),
        token,
        params={"ref": ref},
        max_bytes=GITLAB_READ_MAX_BYTES,
        truncate=True,
    )
    if status_code >= 400:
        raise PluginRuntimeError(_gitlab_error(status_code))
    if b"\x00" in content:
        raise PluginRuntimeError("GITLAB_FILE_NOT_TEXT")
    return {
        "ok": True,
        "project": project,
        "path": path,
        "ref": ref,
        "content": content.decode("utf-8", errors="replace"),
        "truncated": truncated,
    }


def _gitlab_search_code(
    client,
    arguments,
    token,
    endpoint,
    connection_config=None,
):
    """Search one GitLab project and return bounded result metadata."""

    del connection_config
    project = _required_text(arguments, "project")
    query = _required_text(arguments, "query")
    path = str(arguments.get("path") or "")
    ref = str(arguments.get("ref") or "")
    max_results = arguments.get("max_results", 10)
    status_code, content, truncated = _gitlab_get(
        client,
        f"{endpoint}/api/v4/projects/{quote(project, safe='')}/search",
        token,
        params={
            "scope": "blobs",
            "search": query,
            "per_page": max_results,
            "page": 1,
        },
        max_bytes=GITLAB_SEARCH_MAX_BYTES,
        truncate=False,
    )
    if status_code >= 400:
        raise PluginRuntimeError(_gitlab_error(status_code))
    if truncated:
        raise PluginRuntimeError("GITLAB_RESPONSE_TOO_LARGE")
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, ValueError) as exc:
        raise PluginRuntimeError("GITLAB_RESPONSE_INVALID") from exc
    if not isinstance(payload, list):
        raise PluginRuntimeError("GITLAB_RESPONSE_INVALID")
    items = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        item_path = str(item.get("path") or "")[:4096]
        if path and not item_path.startswith(f"{path.rstrip('/')}/"):
            continue
        item_ref = str(item.get("ref") or "")[:255]
        if ref and item_ref != ref:
            continue
        items.append(
            {
                "name": str(item.get("filename") or "")[:255],
                "path": item_path,
                "ref": item_ref,
            }
        )
        if len(items) >= max_results:
            break
    return {
        "ok": True,
        "project": project,
        "query": query,
        "items": items,
    }


def _jira_get_issue(client, arguments, token, endpoint, connection_config):
    """Read one Jira Issue and return bounded non-sensitive fields."""

    issue_key = _required_text(arguments, "issue_key")
    payload = _jira_json_request(
        client,
        f"{endpoint}/rest/api/3/issue/{quote(issue_key, safe='')}",
        token,
        connection_config,
        params={
            "fields": "summary,status,assignee,priority,updated,description"
        },
    )
    return {"ok": True, "issue": _jira_issue(payload)}


def _jira_search_issues(client, arguments, token, endpoint, connection_config):
    """Search text only inside one approved Jira project."""

    project = _required_text(arguments, "project")
    query = _required_text(arguments, "query")
    max_results = arguments.get("max_results", 10)
    escaped = query.replace("\\", "\\\\").replace('"', '\\"')
    payload = _jira_json_request(
        client,
        f"{endpoint}/rest/api/3/search/jql",
        token,
        connection_config,
        params={
            "jql": f'project = "{project}" AND text ~ "{escaped}"',
            "maxResults": max_results,
            "fields": "summary,status,assignee,priority,updated",
        },
    )
    raw_issues = payload.get("issues") if isinstance(payload, dict) else None
    if not isinstance(raw_issues, list):
        raise PluginRuntimeError("JIRA_RESPONSE_INVALID")
    return {
        "ok": True,
        "project": project,
        "query": query,
        "items": [
            _jira_issue(item) for item in raw_issues[:max_results]
        ],
    }


def _github_get(
    client,
    url,
    token,
    *,
    params,
    accept,
    max_bytes,
    truncate,
):
    """Read one GitHub response with redirects disabled and bounded bytes."""

    with client.stream(
        "GET",
        url,
        params=params,
        headers={
            "Accept": accept,
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "SourceLens-LensNode",
        },
        follow_redirects=False,
    ) as response:
        if response.is_redirect:
            raise PluginRuntimeError("GITHUB_REDIRECT_REJECTED")
        if response.status_code >= 400:
            return response.status_code, b"", False
        chunks = []
        captured = 0
        oversized = False
        for chunk in response.iter_bytes():
            remaining = max_bytes - captured
            if len(chunk) > remaining:
                if remaining > 0:
                    chunks.append(chunk[:remaining])
                oversized = True
                break
            chunks.append(chunk)
            captured += len(chunk)
        if oversized and not truncate:
            return response.status_code, b"", True
        return response.status_code, b"".join(chunks), oversized


def _gitlab_get(
    client,
    url,
    token,
    *,
    params,
    max_bytes,
    truncate,
):
    """Read one GitLab response with redirects disabled and bounded bytes."""

    with client.stream(
        "GET",
        url,
        params=params,
        headers={
            "Accept": "application/json",
            "PRIVATE-TOKEN": token,
            "User-Agent": "SourceLens-LensNode",
        },
        follow_redirects=False,
    ) as response:
        if response.is_redirect:
            raise PluginRuntimeError("GITLAB_REDIRECT_REJECTED")
        if response.status_code >= 400:
            return response.status_code, b"", False
        chunks = []
        captured = 0
        oversized = False
        for chunk in response.iter_bytes():
            remaining = max_bytes - captured
            if len(chunk) > remaining:
                if remaining > 0:
                    chunks.append(chunk[:remaining])
                oversized = True
                break
            chunks.append(chunk)
            captured += len(chunk)
        if oversized and not truncate:
            return response.status_code, b"", True
        return response.status_code, b"".join(chunks), oversized


def _jira_json_request(
    client,
    url,
    token,
    connection_config,
    *,
    params,
):
    """Read one bounded Jira Cloud JSON response."""

    with client.stream(
        "GET",
        url,
        params=params,
        headers=_jira_headers(token, connection_config),
        follow_redirects=False,
    ) as response:
        if response.is_redirect:
            raise PluginRuntimeError("JIRA_REDIRECT_REJECTED")
        if response.status_code >= 400:
            raise PluginRuntimeError(_jira_error(response.status_code))
        body = bytearray()
        for chunk in response.iter_bytes():
            if len(body) + len(chunk) > JIRA_RESPONSE_MAX_BYTES:
                raise PluginRuntimeError("JIRA_RESPONSE_TOO_LARGE")
            body.extend(chunk)
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, ValueError) as exc:
        raise PluginRuntimeError("JIRA_RESPONSE_INVALID") from exc
    if not isinstance(payload, dict):
        raise PluginRuntimeError("JIRA_RESPONSE_INVALID")
    return payload


def _jira_headers(token, connection_config):
    """Build Jira Cloud Basic authentication from frozen connection data."""

    email = connection_config.get("email")
    if not isinstance(email, str) or not email or not token:
        raise PluginRuntimeError("PLUGIN_SNAPSHOT_MISMATCH")
    credential = base64.b64encode(
        f"{email}:{token}".encode("utf-8")
    ).decode("ascii")
    return {
        "Accept": "application/json",
        "Authorization": f"Basic {credential}",
        "User-Agent": "SourceLens-LensNode",
    }


def _jira_issue(payload):
    """Return bounded Jira Issue fields safe for the model context."""

    if not isinstance(payload, dict):
        raise PluginRuntimeError("JIRA_RESPONSE_INVALID")
    key = payload.get("key")
    fields = payload.get("fields")
    if not isinstance(key, str) or not isinstance(fields, dict):
        raise PluginRuntimeError("JIRA_RESPONSE_INVALID")
    status = fields.get("status")
    assignee = fields.get("assignee")
    priority = fields.get("priority")
    return {
        "key": key[:40],
        "summary": str(fields.get("summary") or "")[:1000],
        "status": (
            str(status.get("name") or "")[:160]
            if isinstance(status, dict)
            else ""
        ),
        "assignee": (
            str(assignee.get("displayName") or "")[:160]
            if isinstance(assignee, dict)
            else ""
        ),
        "priority": (
            str(priority.get("name") or "")[:160]
            if isinstance(priority, dict)
            else ""
        ),
        "updated": str(fields.get("updated") or "")[:64],
        "description": _jira_description(fields.get("description")),
    }


def _jira_description(value):
    """Flatten bounded text nodes from Atlassian document format."""

    text = []

    def visit(node):
        if sum(len(item) for item in text) >= 20_000:
            return
        if isinstance(node, dict):
            value = node.get("text")
            if isinstance(value, str):
                text.append(value)
            for child in node.get("content") or []:
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return "\n".join(text)[:20_000]


def _github_error(status_code):
    """Map provider status codes without returning third-party bodies."""

    if status_code == 404:
        return "GITHUB_NOT_FOUND"
    if status_code in {401, 403}:
        return "GITHUB_ACCESS_DENIED"
    if status_code == 429:
        return "GITHUB_RATE_LIMITED"
    return "GITHUB_REQUEST_FAILED"


def _gitlab_error(status_code):
    """Map provider status codes without returning third-party bodies."""

    if status_code == 404:
        return "GITLAB_NOT_FOUND"
    if status_code in {401, 403}:
        return "GITLAB_ACCESS_DENIED"
    if status_code == 429:
        return "GITLAB_RATE_LIMITED"
    return "GITLAB_REQUEST_FAILED"


def _jira_error(status_code):
    """Map Jira statuses without returning third-party bodies."""

    if status_code == 404:
        return "JIRA_NOT_FOUND"
    if status_code in {401, 403}:
        return "JIRA_ACCESS_DENIED"
    if status_code == 429:
        return "JIRA_RATE_LIMITED"
    return "JIRA_REQUEST_FAILED"


def _runtime_endpoint(plugin_key, value):
    """Validate a frozen Provider endpoint before material exchange."""

    parsed = urlsplit(str(value or "").strip())
    if plugin_key == "github":
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise PluginRuntimeError("PLUGIN_SNAPSHOT_MISMATCH")
        return "https://github.com"
    if plugin_key == "gitlab":
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise PluginRuntimeError("PLUGIN_SNAPSHOT_MISMATCH")
        return urlunsplit(("https", parsed.netloc, "", "", ""))
    if plugin_key == "jira":
        hostname = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or not hostname.endswith(".atlassian.net")
            or hostname == "atlassian.net"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise PluginRuntimeError("PLUGIN_SNAPSHOT_MISMATCH")
        return urlunsplit(("https", parsed.netloc, "", "", ""))
    raise PluginRuntimeError("PLUGIN_RUNTIME_UNSUPPORTED")


def _required_text(arguments, key):
    """Return one non-empty normalized snapshot argument."""

    value = arguments.get(key)
    if not isinstance(value, str) or not value:
        raise PluginRuntimeError("PLUGIN_SNAPSHOT_MISMATCH")
    return value


def _emit(emit_event, name, detail):
    """Emit bounded operational metadata without Plugin request bodies."""

    if emit_event is not None:
        emit_event(name, detail)


def _json(value):
    """Serialize a model-facing Tool result deterministically."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True)
