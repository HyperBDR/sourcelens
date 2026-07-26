import asyncio
import json
import logging
import re
import threading
from urllib.parse import urlparse

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import StructuredTool

from .gateway_model import neutralize_untrusted_text

LOGGER = logging.getLogger("lensnode")

MCP_TOOL_PREFIX = "mcp__"
MCP_TOOL_NAME_MAX_CHARS = 64
MCP_SEARCH_LIMIT = 5
MCP_MAX_SERVERS = 20
MCP_MAX_TOOLS = 100


class DeferredMCPToolMiddleware(AgentMiddleware):
    """Hide MCP schemas until tool_search promotes matching tools."""

    def __init__(self, mcp_tools):
        self._mcp_tools = {tool.name: tool for tool in mcp_tools}
        self._promoted = set()
        self._lock = threading.Lock()
        self.search_tool = StructuredTool.from_function(
            func=self._search,
            name="tool_search",
            description=(
                "Search available remote MCP tools by capability. Matching "
                "tools become available on the next model turn."
            ),
        )

    def _search(self, query: str):
        """Promote remote tools whose names or descriptions match a query."""

        terms = [term for term in re.split(r"\W+", query.lower()) if term]
        matches = []
        for tool in self._mcp_tools.values():
            haystack = f"{tool.name} {tool.description}".lower()
            score = sum(term in haystack for term in terms)
            if score:
                matches.append((score, tool.name, tool))
        matches.sort(key=lambda item: (-item[0], item[1]))
        selected = [item[2] for item in matches[:MCP_SEARCH_LIMIT]]
        with self._lock:
            self._promoted.update(tool.name for tool in selected)
        return json.dumps(
            {
                "ok": True,
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                    }
                    for tool in selected
                ],
            },
            ensure_ascii=False,
        )

    def _filter_tools(self, tools):
        """Return base tools, tool_search, and promoted MCP tools."""

        with self._lock:
            promoted = set(self._promoted)
        return [
            tool
            for tool in tools
            if not _is_mcp_tool(tool)
            or tool.name in promoted
        ]

    def wrap_model_call(self, request, handler):
        """Filter synchronous model requests."""

        request = request.override(tools=self._filter_tools(request.tools))
        return handler(request)

    async def awrap_model_call(self, request, handler):
        """Filter asynchronous model requests."""

        request = request.override(tools=self._filter_tools(request.tools))
        return await handler(request)


def load_mcp_tools(
    server_configs,
    *,
    discovery_timeout_s=30,
    tool_timeout_s=60,
    emit_event=None,
):
    """Discover safe URL MCP tools with per-server failure isolation."""

    if not server_configs:
        return []
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        _emit(
            emit_event,
            "mcp.runtime.unavailable",
            {"reason": "langchain_mcp_adapters_missing"},
        )
        return []

    server_configs = list(server_configs)
    if len(server_configs) > MCP_MAX_SERVERS:
        _emit(
            emit_event,
            "mcp.runtime.limited",
            {
                "reason": "server_limit",
                "configured": len(server_configs),
                "loaded": MCP_MAX_SERVERS,
            },
        )

    prepared = []
    used_server_names = set()
    for config in server_configs[:MCP_MAX_SERVERS]:
        display_name = str(config.get("name") or "MCP server")
        transport = str(config.get("transport") or "").lower()
        if transport == "stdio":
            _emit(
                emit_event,
                "mcp.server.skipped",
                {
                    "server": display_name,
                    "reason": "stdio_disabled",
                },
            )
            continue
        if transport != "url":
            _emit(
                emit_event,
                "mcp.server.skipped",
                {
                    "server": display_name,
                    "reason": "unsupported_transport",
                },
            )
            continue

        server_name = _unique_identifier(display_name, used_server_names)
        try:
            params = _url_server_params(config)
            client = MultiServerMCPClient(
                {server_name: params},
                tool_name_prefix=True,
            )
        except Exception as exc:
            LOGGER.warning(
                "Skipping MCP server %s after discovery failed (%s)",
                display_name,
                type(exc).__name__,
            )
            _emit(
                emit_event,
                "mcp.server.failed",
                {
                    "server": display_name,
                    "reason": "discovery_failed",
                },
            )
            continue
        prepared.append((config, display_name, server_name, client))

    if not prepared:
        return []
    discovered_servers = asyncio.run(
        _discover_mcp_servers(prepared, discovery_timeout_s)
    )
    tools = []
    used_tool_names = set()
    for prepared_server, discovery in zip(
        prepared,
        discovered_servers,
        strict=True,
    ):
        config, display_name, server_name, _client = prepared_server
        discovered, error = discovery
        if error is not None:
            LOGGER.warning(
                "Skipping MCP server %s after discovery failed (%s)",
                display_name,
                type(error).__name__,
            )
            _emit(
                emit_event,
                "mcp.server.failed",
                {
                    "server": display_name,
                    "reason": "discovery_failed",
                },
            )
            continue

        server_tool_timeout = _positive_float(
            (config.get("load_config") or {}).get("tool_timeout_s"),
            tool_timeout_s,
        )
        for raw_tool in discovered:
            if len(tools) >= MCP_MAX_TOOLS:
                _emit(
                    emit_event,
                    "mcp.runtime.limited",
                    {
                        "reason": "tool_limit",
                        "loaded": MCP_MAX_TOOLS,
                    },
                )
                return tools
            tool = _wrap_mcp_tool(
                raw_tool,
                server_name,
                display_name,
                server_tool_timeout,
                used_tool_names,
            )
            tools.append(tool)
        _emit(
            emit_event,
            "mcp.server.ready",
            {
                "server": display_name,
                "tool_count": len(discovered),
            },
        )
    return tools


async def _discover_mcp_servers(prepared, timeout_s):
    """Discover all validated MCP servers concurrently."""

    timeout = max(float(timeout_s), 0.001)

    async def discover(server_name, client):
        try:
            tools = await asyncio.wait_for(
                client.get_tools(server_name=server_name),
                timeout=timeout,
            )
            return tools, None
        except Exception as exc:
            return [], exc

    return await asyncio.gather(
        *(
            discover(server_name, client)
            for _config, _display_name, server_name, client in prepared
        )
    )


def build_deferred_mcp_tools(mcp_tools, *, threshold=12):
    """Return registered MCP tools and optional schema-filter middleware."""

    if len(mcp_tools) <= max(int(threshold), 0):
        return list(mcp_tools), None
    middleware = DeferredMCPToolMiddleware(mcp_tools)
    return [*mcp_tools, middleware.search_tool], middleware


def _url_server_params(config):
    """Build validated adapter parameters for one URL MCP server."""

    endpoint = str(config.get("endpoint") or "").strip()
    parsed = urlparse(endpoint)
    raw_config = config.get("config") or {}
    load_config = config.get("load_config") or {}
    allowed_schemes = {"https"}
    if load_config.get("allow_insecure_http") is True:
        allowed_schemes.add("http")
    if parsed.scheme not in allowed_schemes or not parsed.netloc:
        raise ValueError(
            "URL MCP endpoint must use https; insecure http requires "
            "allow_insecure_http"
        )
    adapter_transport = str(
        load_config.get("transport")
        or raw_config.get("transport")
        or "streamable_http"
    ).lower()
    if adapter_transport == "http":
        adapter_transport = "streamable_http"
    if adapter_transport not in {"sse", "streamable_http"}:
        raise ValueError("URL MCP transport must be sse or streamable_http")
    params = {
        "transport": adapter_transport,
        "url": endpoint,
    }
    headers = raw_config.get("headers")
    if isinstance(headers, dict):
        params["headers"] = {
            str(key): str(value)
            for key, value in headers.items()
        }
    return params


def _wrap_mcp_tool(
    raw_tool,
    server_name,
    display_name,
    timeout_s,
    used_names,
):
    """Wrap an async adapter tool for the synchronous Deep Agent runtime."""

    raw_name = str(getattr(raw_tool, "name", "") or "tool")
    adapter_prefix = f"{server_name}_"
    if raw_name.startswith(adapter_prefix):
        raw_name = raw_name[len(adapter_prefix) :]
    base_name = f"{MCP_TOOL_PREFIX}{server_name}__{_identifier(raw_name)}"
    name = _unique_tool_name(base_name, used_names)

    async def call_async(**kwargs):
        try:
            result = await asyncio.wait_for(
                raw_tool.ainvoke(kwargs),
                timeout=max(float(timeout_s), 0.001),
            )
            return _result_json(True, result=result)
        except TimeoutError:
            return _result_json(
                False,
                error="MCP_TOOL_TIMEOUT",
                detail="The remote MCP tool exceeded its call timeout.",
            )
        except Exception as exc:
            LOGGER.warning(
                "MCP tool %s from %s failed (%s)",
                raw_name,
                display_name,
                type(exc).__name__,
            )
            return _result_json(
                False,
                error="MCP_TOOL_FAILED",
                detail="The remote MCP tool failed.",
            )

    def call_sync(**kwargs):
        return asyncio.run(call_async(**kwargs))

    metadata = dict(getattr(raw_tool, "metadata", None) or {})
    metadata.update(
        {
            "mcp_server": display_name,
            "mcp_remote_content": True,
            "mcp_tool_name": raw_name,
        }
    )
    return StructuredTool(
        name=name,
        description=neutralize_untrusted_text(
            str(getattr(raw_tool, "description", "") or raw_name),
            neutralize_boundaries=True,
        )[:4000],
        args_schema=getattr(raw_tool, "args_schema", None),
        func=call_sync,
        coroutine=call_async,
        metadata=metadata,
    )


def _result_json(ok, **payload):
    """Return a JSON-safe structured MCP tool result."""

    return json.dumps(
        {"ok": ok, **payload},
        ensure_ascii=False,
        default=str,
    )


def _unique_identifier(value, used):
    """Return a stable unique identifier within one MCP load."""

    base = _identifier(value)[:24] or "server"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base[:20]}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _identifier(value):
    """Canonicalize an untrusted MCP name for model tool binding."""

    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value)).strip("_-")
    return normalized.lower() or "tool"


def _unique_tool_name(value, used):
    """Return a unique tool name within provider identifier limits."""

    base = value[:MCP_TOOL_NAME_MAX_CHARS]
    candidate = base
    suffix = 2
    while candidate in used:
        suffix_text = f"_{suffix}"
        candidate = base[: MCP_TOOL_NAME_MAX_CHARS - len(suffix_text)]
        candidate += suffix_text
        suffix += 1
    used.add(candidate)
    return candidate


def _positive_float(value, default):
    """Return a positive float or the supplied default."""

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(default)
    return parsed if parsed > 0 else float(default)


def _is_mcp_tool(tool):
    """Return whether a tool came from the MCP loader."""

    return str(getattr(tool, "name", "")).startswith(MCP_TOOL_PREFIX)


def _emit(emit_event, event, detail):
    """Emit an MCP runtime event when a callback is configured."""

    if emit_event is not None:
        emit_event(event, detail)
