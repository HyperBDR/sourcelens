"""Datasource Provider contracts and trusted built-in implementations."""

from .base import DatasourceProviderError

from ..package_loader import PluginPackageLoadError, load_control_contract
from ..registry import PluginRegistryError, installed_plugin, latest_plugin


def get_datasource_provider(plugin_key, plugin_version=None):
    """Return the trusted datasource provider for one installed plugin key."""

    try:
        plugin = (
            installed_plugin(plugin_key, plugin_version)
            if plugin_version
            else latest_plugin(plugin_key)
        )
        if plugin.control_handler == "python_v1":
            return load_control_contract(plugin).datasource_provider
    except (PluginPackageLoadError, PluginRegistryError) as exc:
        raise DatasourceProviderError(
            "datasource provider is unavailable"
        ) from exc
    raise DatasourceProviderError("datasource provider is unsupported")
