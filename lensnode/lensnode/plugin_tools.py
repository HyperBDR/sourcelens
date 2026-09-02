"""Model-facing tools backed by versioned Plugin runtime packages."""

import json
import time

import httpx
from langchain_core.tools import StructuredTool

from .plugin_package_loader import (
    PluginPackageLoadError,
    load_runtime_contract,
)
from .plugin_runtime import (
    PluginRuntimeError,
    acquire_plugin_lease,
    create_plugin_tool_snapshot,
    fetch_plugin_snapshot,
    retrieve_plugin_material,
)


class PluginToolError(RuntimeError):
    """Raised when a frozen Plugin Tool cannot be safely registered."""


RESULT_MAX_BYTES = 900_000
GUIDANCE_MAX_OUTPUT_BYTES = 12_000


def build_plugin_guidance_tool(command):
    """Build a bounded helper for progressive Plugin instructions."""

    entries = {}
    for binding in command.get("loaded_plugins") or []:
        if not isinstance(binding, dict):
            continue
        plugin_key = str(binding.get("plugin_key") or "").strip()
        guidance = binding.get("assistant_guidance")
        if not plugin_key or not isinstance(guidance, dict):
            continue
        if (
            guidance.get("summary")
            or guidance.get("when_to_use")
            or guidance.get("topics")
        ):
            entries[plugin_key] = {
                "plugin_key": plugin_key,
                "plugin_display_name": str(
                    binding.get("plugin_display_name") or plugin_key
                )[:160],
                "guidance": guidance,
            }
    if not entries:
        return None

    def plugin_help(plugin: str = "", topic: str = "", query: str = ""):
        """Return progressive, advisory guidance for bound Plugins."""

        plugin = str(plugin or "").strip()[:128]
        topic = str(topic or "").strip()[:128]
        query = str(query or "").strip()[:256]
        selected = list(entries.values())
        if plugin:
            selected = [
                item
                for item in selected
                if item["plugin_key"].lower() == plugin.lower()
                or item["plugin_display_name"].lower() == plugin.lower()
            ]
        if not selected:
            return _guidance_json(
                {
                    "ok": False,
                    "error": "PLUGIN_GUIDANCE_NOT_FOUND",
                }
            )
        terms = [term for term in query.lower().split() if term]
        result = []
        for item in selected:
            guidance = item["guidance"]
            topics = guidance.get("topics") or []
            if topic:
                topics = [
                    value
                    for value in topics
                    if isinstance(value, dict)
                    and str(value.get("key") or "").lower() == topic.lower()
                ]
                if not topics:
                    continue
            elif terms:
                topics = [
                    value
                    for value in topics
                    if _guidance_matches(value, terms)
                ]
            result.append(
                {
                    "plugin": item["plugin_key"],
                    "display_name": item["plugin_display_name"],
                    "summary": str(guidance.get("summary") or "")[:600],
                    "when_to_use": [
                        str(value)[:240]
                        for value in (guidance.get("when_to_use") or [])[:8]
                    ],
                    "topics": [
                        {
                            "key": str(value.get("key") or "")[:64],
                            "summary": str(value.get("summary") or "")[:600],
                            "details": str(value.get("details") or "")[:6000],
                        }
                        for value in topics[:24]
                        if isinstance(value, dict)
                    ],
                }
            )
        if not result:
            return _guidance_json(
                {
                    "ok": False,
                    "error": "PLUGIN_GUIDANCE_TOPIC_NOT_FOUND",
                }
            )
        return _guidance_json({"ok": True, "plugins": result})

    tool = StructuredTool.from_function(
        func=plugin_help,
        name="plugin_help",
        description=(
            "Get concise, progressive usage guidance for a bound built-in "
            "Plugin. Use a Plugin key and optional topic or query."
        ),
    )
    tool.metadata = {
        "capability_family": "plugin",
        "plugin_key": "guidance",
        "capability": "plugin.guidance",
    }
    return tool


def _guidance_matches(topic, terms):
    """Return whether a guidance topic matches all requested terms."""

    if not isinstance(topic, dict):
        return False
    haystack = " ".join(
        str(topic.get(key) or "")
        for key in ("key", "summary", "details", "tool_keys")
    ).lower()
    return all(term in haystack for term in terms)


def _guidance_json(value):
    """Serialize one bounded guidance response."""

    payload = json.dumps(value, ensure_ascii=False)
    if len(payload.encode("utf-8")) <= GUIDANCE_MAX_OUTPUT_BYTES:
        return payload
    if isinstance(value, dict):
        compact = dict(value)
        plugins = []
        for item in value.get("plugins") or []:
            if not isinstance(item, dict):
                continue
            reduced = {
                key: item.get(key)
                for key in (
                    "plugin",
                    "display_name",
                    "summary",
                    "when_to_use",
                )
                if key in item
            }
            reduced["topics"] = [
                {
                    "key": topic.get("key"),
                    "summary": topic.get("summary"),
                }
                for topic in (item.get("topics") or [])[:8]
                if isinstance(topic, dict)
            ]
            plugins.append(reduced)
        compact["plugins"] = plugins
        payload = json.dumps(compact, ensure_ascii=False)
    if len(payload.encode("utf-8")) <= GUIDANCE_MAX_OUTPUT_BYTES:
        return payload
    return json.dumps(
        {
            "ok": False,
            "error": "PLUGIN_GUIDANCE_TOO_LARGE",
        }
    )


def build_plugin_tools(command, config, http_client, emit_event=None):
    """Build tools from exact runtime versions in frozen Plugin bindings."""

    loaded_plugins = command.get("loaded_plugins") or []
    if not loaded_plugins:
        return []
    if not isinstance(loaded_plugins, list):
        raise PluginToolError("PLUGIN_BINDINGS_INVALID")
    tools = []
    seen_keys = set()
    for binding in loaded_plugins:
        if not isinstance(binding, dict):
            raise PluginToolError("PLUGIN_BINDING_INVALID")
        plugin_key = str(binding.get("plugin_key") or "")
        plugin_version = str(binding.get("plugin_version") or "")
        if binding.get("protocol_version") != 1:
            raise PluginToolError("PLUGIN_RUNTIME_UNSUPPORTED")
        connection_uuid = str(binding.get("connection_uuid") or "")
        if not connection_uuid:
            raise PluginToolError("PLUGIN_CONNECTION_REQUIRED")
        try:
            contract = load_runtime_contract(plugin_key, plugin_version)
        except PluginPackageLoadError as exc:
            raise PluginToolError("PLUGIN_RUNTIME_UNSUPPORTED") from exc
        for definition in binding.get("tools") or []:
            tool_key = str(
                definition.get("key")
                if isinstance(definition, dict)
                else ""
            )
            if not tool_key:
                raise PluginToolError("PLUGIN_TOOL_INVALID")
            capability_family = str(
                definition.get("capability_family") or "plugin"
            )
            if capability_family != "plugin":
                raise PluginToolError("PLUGIN_TOOL_INVALID")
            if tool_key in seen_keys:
                raise PluginToolError("PLUGIN_TOOL_NAME_CONFLICT")

            def executor(
                selected_tool_key,
                arguments,
                runtime,
                *,
                _contract=contract,
                _connection_uuid=connection_uuid,
                _plugin_key=plugin_key,
            ):
                return _execute_plugin_tool(
                    command,
                    config,
                    http_client,
                    _connection_uuid,
                    _plugin_key,
                    selected_tool_key,
                    runtime,
                    arguments,
                    _contract.execute_tool,
                    emit_event,
                )

            try:
                registered = contract.build_tool(definition, executor)
            except Exception as exc:
                raise PluginToolError("PLUGIN_TOOL_INVALID") from exc
            if getattr(registered, "name", None) != tool_key:
                raise PluginToolError("PLUGIN_TOOL_INVALID")
            registered.metadata = {
                **(getattr(registered, "metadata", None) or {}),
                "capability_family": capability_family,
                "plugin_key": plugin_key,
                "plugin_version": plugin_version,
                "capability": str(
                    definition.get("capability") or ""
                ),
            }
            seen_keys.add(tool_key)
            tools.append(registered)
    return tools


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
            or material.get("endpoint", "").rstrip("/")
            != endpoint.rstrip("/")
        ):
            raise PluginRuntimeError("PLUGIN_MATERIAL_MISMATCH")
        result = handler(
            tool_key,
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
        error = "PLUGIN_REQUEST_FAILED"
        result = {"ok": False, "error": error}
    except Exception:
        error = "PLUGIN_EXECUTION_FAILED"
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
    """Return frozen Plugin inputs from the matching snapshot."""

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
    endpoint = str(resolved_config.get("endpoint") or "").rstrip("/")
    connection_config = resolved_config.get("connection_config") or {}
    allowed_scope = resolved_config.get("allowed_scope")
    if (
        not endpoint
        or not isinstance(connection_config, dict)
        or not isinstance(allowed_scope, dict)
    ):
        raise PluginRuntimeError("PLUGIN_SNAPSHOT_MISMATCH")
    connection_config = dict(connection_config)
    connection_config["__allowed_scope"] = allowed_scope
    return resolved_config["arguments"], endpoint, connection_config


def _json(value):
    """Serialize a bounded provider result for model context."""

    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(payload.encode("utf-8")) <= RESULT_MAX_BYTES:
        return payload
    return json.dumps(
        {"ok": False, "error": "PLUGIN_RESULT_TOO_LARGE"},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _emit(callback, event_type, payload):
    """Emit an optional Plugin audit event."""

    if callback is not None:
        callback(event_type, payload)
