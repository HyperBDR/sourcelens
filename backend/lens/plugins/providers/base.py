"""Stable contracts for Plugin datasource implementations."""

from abc import ABC, abstractmethod


class DatasourceProviderError(ValueError):
    """Raised when datasource configuration violates a provider contract."""


class DatasourceProvider(ABC):
    """Validate and normalize datasource-specific resource configuration."""

    key = ""

    def validate_connection(self, endpoint, connection_config):
        """Return a normalized endpoint accepted by this provider."""

        del connection_config
        value = str(endpoint or "").strip().rstrip("/")
        if not value:
            raise DatasourceProviderError("connection endpoint is required")
        return value

    @abstractmethod
    def validate_datasource_config(self, connection_scope, datasource_config):
        """Return normalized config that remains within connection scope."""
