"""Persist secret-free audit records for authorized Plugin executions."""

from copy import deepcopy

from lens.models import PluginInvocation


def create_invocation_audit(
    snapshot,
    *,
    lensnode,
    actor=None,
    capability="",
    resource_summary=None,
):
    """Create the one immutable audit identity associated with a snapshot."""

    return PluginInvocation.objects.create(
        snapshot=snapshot,
        connection=snapshot.connection,
        datasource=snapshot.datasource,
        run=snapshot.run,
        actor=actor,
        lensnode=lensnode,
        kind=snapshot.kind,
        plugin_key=snapshot.plugin_key,
        tool_key=snapshot.tool_key,
        capability=capability,
        resource_summary=deepcopy(resource_summary or {}),
    )
