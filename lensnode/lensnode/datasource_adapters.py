from typing import Callable


class DataSourceAdapter:
    """Base adapter contract for datasource synchronization."""

    source_type = ""

    def sync(self, command, workspace_path, emit=None):
        """Synchronize datasource content and return adapter metrics."""

        raise NotImplementedError


class FunctionDataSourceAdapter(DataSourceAdapter):
    """Adapter wrapper for existing sync functions."""

    def __init__(self, source_type: str, sync_func: Callable):
        self.source_type = source_type
        self.sync_func = sync_func

    def sync(self, command, workspace_path, emit=None):
        """Call the wrapped sync function."""

        return self.sync_func(command, workspace_path, emit)


class DataSourceAdapterRegistry:
    """Registry for datasource adapters."""

    def __init__(self):
        self._adapters = {}

    def register(self, adapter):
        """Register one datasource adapter."""

        self._adapters[adapter.source_type] = adapter

    def get(self, source_type):
        """Return the adapter for a datasource type."""

        return self._adapters.get(source_type)
