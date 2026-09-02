"""GitHub LensNode runtime entrypoint."""

import json
from typing import Annotated
from urllib.parse import quote, urlsplit

from langchain.tools import ToolRuntime, tool
from pydantic import Field

from lensnode.plugin_runtime import PluginRuntimeError


PLUGIN_API_VERSION = 1
PLUGIN_KEY = "github"
PLUGIN_VERSION = "1.0.0"
API_URL = "https://api.github.com"
API_VERSION = "2022-11-28"
READ_MAX_BYTES = 200_000
SEARCH_MAX_BYTES = 1_000_000


def build_tool(definition, executor):
    """Create a fixed GitHub read-only tool from its manifest declaration."""

    _validate_definition(definition)
    key = definition["key"]
    description = definition["description"].strip()
    if key == "github_read_file":

        def invoke(
            repository: Annotated[str, Field(min_length=3, max_length=201)],
            path: Annotated[str, Field(min_length=1, max_length=4096)],
            runtime: ToolRuntime,
            ref: Annotated[str, Field(max_length=255)] = "",
        ) -> str:
            return executor(key, {"repository": repository, "path": path,
                                  "ref": ref}, runtime)

        return tool(key, description=description)(invoke)
    if key == "github_search_code":

        def invoke(
            repository: Annotated[str, Field(min_length=3, max_length=201)],
            query: Annotated[str, Field(min_length=1, max_length=1024)],
            runtime: ToolRuntime,
            path: Annotated[str, Field(max_length=4096)] = "",
            max_results: Annotated[int, Field(ge=1, le=20)] = 10,
        ) -> str:
            return executor(key, {"repository": repository, "query": query,
                                  "path": path, "max_results": max_results},
                            runtime)

        return tool(key, description=description)(invoke)
    raise PluginRuntimeError("PLUGIN_TOOL_UNSUPPORTED")


def execute_tool(key, client, arguments, secret, endpoint, config):
    """Execute one bounded GitHub REST request."""

    del config
    _endpoint(endpoint)
    if key == "github_read_file":
        repository = _text(arguments, "repository")
        path = _text(arguments, "path")
        ref = str(arguments.get("ref") or "")
        status, body, truncated = _get(
            client,
            f"{API_URL}/repos/{quote(repository, safe='/')}/contents/"
            f"{quote(path, safe='/')}",
            secret,
            {"ref": ref} if ref else None,
            "application/vnd.github.raw+json",
            READ_MAX_BYTES,
            True,
        )
        _status(status)
        if b"\x00" in body:
            raise PluginRuntimeError("GITHUB_FILE_NOT_TEXT")
        return {"ok": True, "repository": repository, "path": path,
                "ref": ref, "content": body.decode("utf-8", "replace"),
                "truncated": truncated}
    if key == "github_search_code":
        repository = _text(arguments, "repository")
        query = _text(arguments, "query")
        if any(item in query.lower() for item in ("repo:", "org:", "user:")):
            raise PluginRuntimeError("GITHUB_SEARCH_SCOPE_INVALID")
        path = str(arguments.get("path") or "")
        max_results = arguments.get("max_results", 10)
        if isinstance(max_results, bool) or not isinstance(max_results, int):
            raise PluginRuntimeError("PLUGIN_ARGUMENTS_INVALID")
        qualifiers = [query, f"repo:{repository}"]
        if path:
            qualifiers.append(f"path:{path}")
        status, body, truncated = _get(
            client, f"{API_URL}/search/code", secret,
            {"q": " ".join(qualifiers), "per_page": max_results, "page": 1},
            "application/vnd.github+json", SEARCH_MAX_BYTES, False,
        )
        _status(status)
        if truncated:
            raise PluginRuntimeError("GITHUB_RESPONSE_TOO_LARGE")
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, ValueError) as exc:
            raise PluginRuntimeError("GITHUB_RESPONSE_INVALID") from exc
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise PluginRuntimeError("GITHUB_RESPONSE_INVALID")
        return {"ok": True, "repository": repository, "query": query,
                "path": path, "total_count": max(payload.get("total_count", 0), 0),
                "items": [{"name": str(item.get("name") or "")[:255],
                           "path": str(item.get("path") or "")[:4096],
                           "sha": str(item.get("sha") or "")[:128]}
                          for item in items[:max_results] if isinstance(item, dict)]}
    raise PluginRuntimeError("PLUGIN_TOOL_UNSUPPORTED")


def build_datasource_command(snapshot, material, trigger):
    """Build one Git datasource command from frozen GitHub state."""

    resolved = _resolved(snapshot)
    endpoint = _endpoint(resolved.get("endpoint"))
    _material(material, endpoint)
    datasource = resolved.get("datasource_config") or {}
    repository = datasource.get("repository") if isinstance(datasource, dict) else ""
    if not isinstance(repository, str) or not repository:
        raise PluginRuntimeError("PLUGIN_CONFIG_INVALID")
    return {"source_type": "git", "datasource_uuid": snapshot.get("datasource_uuid"),
            "target_path": resolved.get("target_path"),
            "sync_policy": resolved.get("sync_policy") or {}, "trigger": trigger,
            "config": {"repo_url": f"{endpoint}/{repository}.git",
                       "branch": datasource.get("branch") or "main",
                       "directory": datasource.get("directory") or "",
                       "auth_scheme": "token", "access_token": material["value"]}}


def _validate_definition(value):
    if (not isinstance(value, dict) or value.get("capability") != "repository.read"
            or value.get("side_effect") != "none"
            or not isinstance(value.get("description"), str)
            or not value["description"].strip()):
        raise PluginRuntimeError("PLUGIN_TOOL_NOT_READ_ONLY")


def _endpoint(value):
    parsed = urlsplit(str(value or "").strip())
    if (parsed.scheme != "https" or parsed.hostname != "github.com"
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise PluginRuntimeError("PLUGIN_SNAPSHOT_MISMATCH")
    return "https://github.com"


def _resolved(snapshot):
    resolved = snapshot.get("resolved_config")
    if not isinstance(resolved, dict):
        raise PluginRuntimeError("PLUGIN_CONFIG_INVALID")
    return resolved


def _material(material, endpoint):
    if (not isinstance(material, dict) or material.get("plugin_key") != PLUGIN_KEY
            or str(material.get("endpoint") or "").rstrip("/") != endpoint
            or not material.get("value")):
        raise PluginRuntimeError("PLUGIN_MATERIAL_MISMATCH")


def _text(arguments, name):
    value = arguments.get(name)
    if not isinstance(value, str) or not value:
        raise PluginRuntimeError("PLUGIN_ARGUMENTS_INVALID")
    return value


def _get(client, url, token, params, accept, max_bytes, truncate):
    with client.stream("GET", url, params=params, follow_redirects=False,
                       headers={"Accept": accept, "Authorization": f"Bearer {token}",
                                "X-GitHub-Api-Version": API_VERSION,
                                "User-Agent": "SourceLens-LensNode"}) as response:
        if response.is_redirect:
            raise PluginRuntimeError("GITHUB_REDIRECT_REJECTED")
        if response.status_code >= 400:
            return response.status_code, b"", False
        body = b"".join(response.iter_bytes())
    if len(body) <= max_bytes:
        return response.status_code, body, False
    return response.status_code, body[:max_bytes], True


def _status(status):
    if status < 400:
        return
    errors = {404: "GITHUB_NOT_FOUND", 401: "GITHUB_ACCESS_DENIED",
              403: "GITHUB_ACCESS_DENIED", 429: "GITHUB_RATE_LIMITED"}
    raise PluginRuntimeError(errors.get(status, "GITHUB_REQUEST_FAILED"))
