"""Create immutable resolved configuration for plugin executions."""

from copy import deepcopy

from django.db import transaction

from lens.models import DataSource, ExecutionSnapshot
from .providers import DatasourceProviderError, get_datasource_provider
from .registry import PluginRegistryError, latest_plugin


SENSITIVE_CONFIG_KEYS = frozenset({
    "access_token",
    "api_key",
    "app_secret",
    "authorization",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
})


def create_datasource_sync_snapshot(datasource):
    """Resolve one external datasource into an immutable execution snapshot."""

    datasource = DataSource.objects.select_related(
        "connection",
        "connection__secret_version",
        "lensnode",
    ).get(pk=datasource.pk)
    connection = datasource.connection
    if connection is None:
        raise PluginRegistryError("datasource connection is required")
    if connection.status != connection.Status.ACTIVE:
        raise PluginRegistryError("datasource connection is disabled")
    if not datasource.plugin_key or datasource.plugin_key != connection.plugin_key:
        raise PluginRegistryError("datasource and connection plugin keys differ")
    if datasource.lensnode is None:
        raise PluginRegistryError("datasource LensNode is required")
    _reject_sensitive_values(connection.config)
    _reject_sensitive_values(connection.allowed_scope)
    _reject_sensitive_values(datasource.datasource_config)
    try:
        provider = get_datasource_provider(datasource.plugin_key)
        endpoint = provider.validate_connection(
            connection.endpoint,
            connection.config,
        )
        datasource_config = provider.validate_datasource_config(
            connection.allowed_scope,
            datasource.datasource_config,
        )
    except DatasourceProviderError as exc:
        raise PluginRegistryError(str(exc)) from exc
    plugin = latest_plugin(datasource.plugin_key)
    resolved_config = {
        "endpoint": endpoint,
        "connection_config": deepcopy(connection.config),
        "connection_scope": deepcopy(connection.allowed_scope),
        "datasource_config": datasource_config,
        "sync_policy": deepcopy(datasource.sync_policy),
        "target_path": datasource.target_path,
        "lensnode_uuid": str(datasource.lensnode.uuid),
    }
    with transaction.atomic():
        return ExecutionSnapshot.objects.create(
            kind=ExecutionSnapshot.Kind.DATASOURCE_SYNC,
            connection=connection,
            datasource=datasource,
            secret_version=connection.secret_version,
            plugin_key=plugin.key,
            plugin_version=plugin.version,
            protocol_version=plugin.protocol_version,
            resolved_config=resolved_config,
        )


def _reject_sensitive_values(value):
    """Reject credential-shaped keys from persisted non-secret config."""

    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in SENSITIVE_CONFIG_KEYS:
                raise PluginRegistryError("plugin config cannot contain credentials")
            _reject_sensitive_values(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_sensitive_values(nested)
