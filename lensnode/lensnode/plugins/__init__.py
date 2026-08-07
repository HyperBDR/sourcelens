"""In-process LensNode capability plugins.

Plugins contribute optional capabilities (MCP servers today, skills or
tools later) behind a stable internal boundary. Built-in adapters ship
inside this package; external plugins remain a deferred decision (see
docs/decisions/001-platform-connections-and-credentials.md).
"""


class LensNodePlugin:
    """Base class for an in-process capability plugin.

    A plugin reports whether it may run for a given config and
    contributes MCP server configs; future capability types add their
    own contribute_* methods with default no-op implementations.
    """

    name = "base"

    def enabled(self, config):
        """Return whether this plugin may run for the given config."""

        return True

    def contribute_mcp_servers(self, config, emit_event=None):
        """Return MCP server configs this plugin contributes."""

        return []


def collect_mcp_servers(config, mcp_configs, emit_event=None):
    """Merge plugin-contributed MCP servers, deduplicating by name.

    Configured servers always win over plugin contributions sharing the
    same name.
    """

    from .codegraph import CodeGraphPlugin

    plugins = (CodeGraphPlugin(),)
    servers = list(mcp_configs)
    for plugin in plugins:
        if not plugin.enabled(config):
            continue
        for server in plugin.contribute_mcp_servers(
            config,
            emit_event=emit_event,
        ):
            name = str(server.get("name") or "").lower()
            if any(
                str(item.get("name") or "").lower() == name
                for item in servers
            ):
                continue
            servers.append(server)
    return servers
