"""Model-facing tools backed by trusted built-in Plugin runtimes."""

import json
import time
from typing import Annotated
from urllib.parse import quote

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
        if (
            plugin.get("plugin_key") != "github"
            or plugin.get("protocol_version") != 1
        ):
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
            registered = _build_github_tool(
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


def _execute_plugin_tool(
    command,
    config,
    http_client,
    connection_uuid,
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
            "plugin": "github",
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
        normalized_arguments = _validate_snapshot(
            resolved,
            command.get("run_uuid"),
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
            material.get("plugin_key") != "github"
            or material.get("endpoint") != "https://github.com"
        ):
            raise PluginRuntimeError("PLUGIN_MATERIAL_MISMATCH")
        result = handler(
            http_client,
            normalized_arguments,
            material["value"],
        )
    except PluginRuntimeError as exc:
        error = str(exc)
        result = {"ok": False, "error": error}
    except httpx.HTTPError:
        error = "GITHUB_REQUEST_FAILED"
        result = {"ok": False, "error": error}
    finally:
        if material is not None:
            material["value"] = ""
        _emit(
            emit_event,
            "tool.plugin.done",
            {
                "plugin": "github",
                "tool": tool_key,
                "invocation_id": call_id,
                "ok": not error,
                "error": error,
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
        )
    return _json(result)


def _validate_snapshot(snapshot, run_uuid, tool_key, call_id):
    """Return normalized arguments from the matching control-plane snapshot."""

    resolved_config = snapshot.get("resolved_config")
    if (
        str(snapshot.get("run_uuid") or "") != str(run_uuid or "")
        or snapshot.get("plugin_key") != "github"
        or snapshot.get("tool_key") != tool_key
        or str(snapshot.get("invocation_id") or "") != call_id
        or not isinstance(resolved_config, dict)
        or resolved_config.get("endpoint") != "https://github.com"
        or not isinstance(resolved_config.get("arguments"), dict)
    ):
        raise PluginRuntimeError("PLUGIN_SNAPSHOT_MISMATCH")
    return resolved_config["arguments"]


def _github_read_file(client, arguments, token):
    """Read one text file from the fixed public GitHub REST API host."""

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


def _github_search_code(client, arguments, token):
    """Search the default branch and return only bounded result metadata."""

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


def _github_error(status_code):
    """Map provider status codes without returning third-party bodies."""

    if status_code == 404:
        return "GITHUB_NOT_FOUND"
    if status_code in {401, 403}:
        return "GITHUB_ACCESS_DENIED"
    if status_code == 429:
        return "GITHUB_RATE_LIMITED"
    return "GITHUB_REQUEST_FAILED"


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
