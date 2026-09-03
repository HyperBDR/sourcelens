"""GitLab LensNode runtime entrypoint."""

import json
from typing import Annotated
from urllib.parse import quote, urlsplit, urlunsplit

from langchain.tools import ToolRuntime, tool
from pydantic import Field

from lensnode.plugin_runtime import PluginRuntimeError

PLUGIN_API_VERSION = 1
PLUGIN_KEY = "gitlab"
PLUGIN_VERSION = "1.0.0"
READ_MAX_BYTES = 200_000
SEARCH_MAX_BYTES = 1_000_000


def http_origins(endpoint):
    """Return the validated GitLab API origin for connection pooling."""

    return (_endpoint(endpoint),)


def build_tool(definition, executor):
    """Create a fixed GitLab read-only tool."""

    if (not isinstance(definition, dict)
            or definition.get("capability") != "repository.read"
            or definition.get("side_effect") != "none"):
        raise PluginRuntimeError("PLUGIN_TOOL_NOT_READ_ONLY")
    key = str(definition.get("key") or "")
    description = str(definition.get("description") or "").strip()
    if not description:
        raise PluginRuntimeError("PLUGIN_TOOL_DESCRIPTION_REQUIRED")
    if key == "gitlab_read_file":
        def invoke(project: Annotated[str, Field(min_length=3, max_length=255)],
                   path: Annotated[str, Field(min_length=1, max_length=4096)],
                   runtime: ToolRuntime,
                   ref: Annotated[str, Field(max_length=255)] = "") -> str:
            return executor(key, {"project": project, "path": path, "ref": ref}, runtime)
        return tool(key, description=description)(invoke)
    if key == "gitlab_search_code":
        def invoke(project: Annotated[str, Field(min_length=3, max_length=255)],
                   query: Annotated[str, Field(min_length=1, max_length=1024)],
                   runtime: ToolRuntime,
                   path: Annotated[str, Field(max_length=4096)] = "",
                   ref: Annotated[str, Field(max_length=255)] = "",
                   max_results: Annotated[int, Field(ge=1, le=20)] = 10) -> str:
            return executor(key, {"project": project, "query": query, "path": path,
                                  "ref": ref, "max_results": max_results}, runtime)
        return tool(key, description=description)(invoke)
    raise PluginRuntimeError("PLUGIN_TOOL_UNSUPPORTED")


def execute_tool(key, client, arguments, secret, endpoint, config):
    """Execute one bounded GitLab REST call."""

    del config
    endpoint = _endpoint(endpoint)
    project = _text(arguments, "project")
    if key == "gitlab_read_file":
        path, ref = _text(arguments, "path"), str(arguments.get("ref") or "main")
        status, body, truncated = _get(client, f"{endpoint}/api/v4/projects/{quote(project, safe='')}/repository/files/{quote(path, safe='')}/raw", secret, {"ref": ref}, READ_MAX_BYTES, True)
        _status(status)
        if b"\x00" in body: raise PluginRuntimeError("GITLAB_FILE_NOT_TEXT")
        return {"ok": True, "project": project, "path": path, "ref": ref,
                "content": body.decode("utf-8", "replace"), "truncated": truncated}
    if key == "gitlab_search_code":
        query, path, ref = _text(arguments, "query"), str(arguments.get("path") or ""), str(arguments.get("ref") or "")
        max_results = arguments.get("max_results", 10)
        status, body, truncated = _get(client, f"{endpoint}/api/v4/projects/{quote(project, safe='')}/search", secret, {"scope": "blobs", "search": query, "per_page": max_results, "page": 1}, SEARCH_MAX_BYTES, False)
        _status(status)
        if truncated: raise PluginRuntimeError("GITLAB_RESPONSE_TOO_LARGE")
        try: payload = json.loads(body)
        except (UnicodeDecodeError, ValueError) as exc: raise PluginRuntimeError("GITLAB_RESPONSE_INVALID") from exc
        if not isinstance(payload, list): raise PluginRuntimeError("GITLAB_RESPONSE_INVALID")
        items = []
        for item in payload:
            if not isinstance(item, dict): continue
            item_path, item_ref = str(item.get("path") or "")[:4096], str(item.get("ref") or "")[:255]
            if (path and not item_path.startswith(f"{path.rstrip('/')}/")) or (ref and item_ref != ref): continue
            items.append({"name": str(item.get("filename") or "")[:255], "path": item_path, "ref": item_ref})
            if len(items) >= max_results: break
        return {"ok": True, "project": project, "query": query, "items": items}
    raise PluginRuntimeError("PLUGIN_TOOL_UNSUPPORTED")


def build_datasource_command(snapshot, material, trigger):
    """Build one Git datasource command from frozen GitLab state."""

    resolved = snapshot.get("resolved_config")
    if not isinstance(resolved, dict): raise PluginRuntimeError("PLUGIN_CONFIG_INVALID")
    endpoint = _endpoint(resolved.get("endpoint"))
    if not isinstance(material, dict) or material.get("plugin_key") != PLUGIN_KEY or str(material.get("endpoint") or "").rstrip("/") != endpoint or not material.get("value"):
        raise PluginRuntimeError("PLUGIN_MATERIAL_MISMATCH")
    datasource = resolved.get("datasource_config") or {}
    project = datasource.get("project") if isinstance(datasource, dict) else ""
    if not isinstance(project, str) or not project: raise PluginRuntimeError("PLUGIN_CONFIG_INVALID")
    return {"source_type": "git", "datasource_uuid": snapshot.get("datasource_uuid"), "target_path": resolved.get("target_path"), "sync_policy": resolved.get("sync_policy") or {}, "trigger": trigger, "config": {"repo_url": f"{endpoint}/{project}.git", "branch": datasource.get("branch") or "main", "directory": datasource.get("directory") or "", "auth_scheme": "token", "access_token": material["value"]}}


def _endpoint(value):
    parsed = urlsplit(str(value or "").strip())
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.path not in {"", "/"} or parsed.query or parsed.fragment): raise PluginRuntimeError("PLUGIN_SNAPSHOT_MISMATCH")
    return urlunsplit(("https", parsed.netloc, "", "", ""))


def _text(arguments, name):
    value = arguments.get(name)
    if not isinstance(value, str) or not value: raise PluginRuntimeError("PLUGIN_ARGUMENTS_INVALID")
    return value


def _get(client, url, token, params, max_bytes, truncate):
    with client.stream("GET", url, params=params, follow_redirects=False, headers={"Accept": "application/json", "PRIVATE-TOKEN": token, "User-Agent": "SourceLens-LensNode"}) as response:
        if response.is_redirect: raise PluginRuntimeError("GITLAB_REDIRECT_REJECTED")
        if response.status_code >= 400: return response.status_code, b"", False
        body = b"".join(response.iter_bytes())
    return response.status_code, body[:max_bytes], len(body) > max_bytes


def _status(status):
    if status < 400: return
    raise PluginRuntimeError({404: "GITLAB_NOT_FOUND", 401: "GITLAB_ACCESS_DENIED", 403: "GITLAB_ACCESS_DENIED", 429: "GITLAB_RATE_LIMITED"}.get(status, "GITLAB_REQUEST_FAILED"))
