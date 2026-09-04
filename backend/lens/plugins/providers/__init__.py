"""Datasource Provider contracts and trusted built-in implementations."""

from .base import DatasourceProviderError

from ..package_loader import PluginPackageLoadError, load_control_contract
from ..registry import PluginRegistryError, installed_plugin


def get_datasource_provider(plugin_key, plugin_version=None):
    """Return the trusted provider for one installed Plugin release."""

    try:
        plugin = installed_plugin(plugin_key, plugin_version)
        if plugin.control_handler == "python_v1":
            return load_control_contract(plugin).datasource_provider
    except (PluginPackageLoadError, PluginRegistryError) as exc:
        raise DatasourceProviderError(
            "datasource provider is unavailable"
        ) from exc
    raise DatasourceProviderError("datasource provider is unsupported")
