"""Resolve Tool validation from installed Plugin control packages."""

from .contracts import ToolProviderError
from .package_loader import PluginPackageLoadError, load_control_contract
from .registry import PluginRegistryError, installed_plugin


def get_tool_provider(plugin_key, plugin_version=None):
    """Return the Tool Provider for one installed Plugin release."""

    try:
        plugin = installed_plugin(plugin_key, plugin_version)
        if plugin.control_handler != "python_v1":
            raise ToolProviderError("tool provider is unsupported")
        return load_control_contract(plugin).tool_provider
    except ToolProviderError:
        raise
    except (PluginPackageLoadError, PluginRegistryError) as exc:
        raise ToolProviderError("tool provider is unavailable") from exc


__all__ = ["ToolProviderError", "get_tool_provider"]
