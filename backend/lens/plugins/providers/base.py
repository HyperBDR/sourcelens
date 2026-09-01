"""Stable contracts for Plugin datasource implementations."""

from abc import ABC, abstractmethod


class DatasourceProviderError(ValueError):
    """Raised when datasource configuration violates a provider contract."""


class DatasourceProvider(ABC):
    """Validate and normalize datasource-specific resource configuration."""

    key = ""

    @abstractmethod
    def validate_datasource_config(self, connection_scope, datasource_config):
        """Return normalized config that remains within connection scope."""
