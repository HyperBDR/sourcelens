"""Datasource Provider contracts and trusted built-in implementations."""

from .base import DatasourceProviderError
from .github import GitHubDatasourceProvider


PROVIDERS = {
    "github": GitHubDatasourceProvider(),
}


def get_datasource_provider(plugin_key):
    """Return the trusted datasource provider for one installed plugin key."""

    try:
        return PROVIDERS[plugin_key]
    except KeyError as exc:
        raise DatasourceProviderError("datasource provider is unsupported") from exc
