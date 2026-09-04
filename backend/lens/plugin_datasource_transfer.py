"""Convert legacy datasource snapshots to current Plugin datasources."""

import uuid
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from django.db import transaction

from lens.datasource_services import normalize_workspace_target_path
from lens.models import Connection, DataSource
from lens.plugins.providers import get_datasource_provider

SNAPSHOT_SCHEMA_VERSION = 1
SUPPORTED_PLUGINS = frozenset({"feishu", "github", "gitlab"})
MAX_DATASOURCES = 10_000
LEGACY_REPOSITORY_RENAMES = {
    ("github", "hyperbdr/hyperfilelens"): "oneprolabs/hyperfilelens",
}


def import_plugin_datasource_snapshot(
    snapshot,
    target_lensnode,
    connections,
    dry_run=False,
):
    """Convert legacy sources while reusing supplied Plugin Connections."""

    _validate_snapshot(snapshot)
    plans = _build_plans(snapshot["datasources"], target_lensnode)
    required_plugins = {plan["plugin_key"] for plan in plans}
    _validate_connections(connections, required_plugins)
    merged_scopes = _merged_connection_scopes(plans, connections)
    providers = {
        plugin_key: get_datasource_provider(plugin_key)
        for plugin_key in required_plugins
    }
    report = {
        "connections": _change_counts(),
        "datasources": _change_counts(),
    }
    with transaction.atomic():
        for plugin_key in sorted(required_plugins):
            connection = connections[plugin_key]
            scope = providers[plugin_key].validate_connection_scope(
                merged_scopes[plugin_key]
            )
            providers[plugin_key].validate_connection(
                connection.endpoint,
                connection.config,
            )
            if connection.allowed_scope == scope:
                report["connections"]["unchanged"] += 1
            else:
                connection.allowed_scope = scope
                connection.save(update_fields=["allowed_scope", "updated_at"])
                report["connections"]["updated"] += 1
        for plan in plans:
            plugin_key = plan["plugin_key"]
            connection = connections[plugin_key]
            datasource_config = providers[
                plugin_key
            ].validate_datasource_config(
                connection.allowed_scope,
                plan["datasource_config"],
            )
            change = _upsert_datasource(
                plan,
                datasource_config,
                connection,
                target_lensnode,
            )
            report["datasources"][change] += 1
        if dry_run:
            transaction.set_rollback(True)
    return report


def required_plugin_keys(snapshot):
    """Return the supported Plugin keys required by one snapshot."""

    _validate_snapshot(snapshot)
    keys = set()
    for item in snapshot["datasources"]:
        _require_mapping(item, "datasource")
        plugin_key = _require_string(
            item,
            "credential_provider",
            "datasource",
        )
        if plugin_key not in SUPPORTED_PLUGINS:
            raise ValueError(
                f'datasource "{item.get("name", "")}" uses an '
                "unsupported credential provider"
            )
        keys.add(plugin_key)
    return keys


def _change_counts():
    return {"created": 0, "updated": 0, "unchanged": 0}


def _validate_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be an object")
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("unsupported datasource snapshot schema version")
    datasources = snapshot.get("datasources")
    if not isinstance(datasources, list):
        raise ValueError("snapshot datasources must be a list")
    if len(datasources) > MAX_DATASOURCES:
        raise ValueError("snapshot contains too many datasources")


def _validate_connections(connections, required_plugins):
    if not isinstance(connections, dict):
        raise ValueError("connections must be an object")
    for plugin_key in required_plugins:
        connection = connections.get(plugin_key)
        if not isinstance(connection, Connection):
            raise ValueError(
                f'current {plugin_key} Connection is required'
            )
        if connection.plugin_key != plugin_key:
            raise ValueError(
                f'current {plugin_key} Connection has the wrong Plugin'
            )
        if connection.status != Connection.Status.ACTIVE:
            raise ValueError(
                f'current {plugin_key} Connection is disabled'
            )
        version = connection.secret_version
        if (
            version is None
            or version.status != "active"
            or version.material.status != "active"
            or not version.encrypted_value
        ):
            raise ValueError(
                f'current {plugin_key} Connection secret is unavailable'
            )


def _build_plans(items, target_lensnode):
    plans = []
    identities = set()
    for item in items:
        _require_mapping(item, "datasource")
        source_uuid = _parse_uuid(item.get("uuid"), "datasource uuid")
        name = _require_string(item, "name", "datasource")
        source_type = _require_string(item, "source_type", "datasource")
        plugin_key = _require_string(
            item,
            "credential_provider",
            "datasource",
        )
        if plugin_key not in SUPPORTED_PLUGINS:
            raise ValueError(
                f'datasource "{name}" uses an unsupported credential provider'
            )
        config = _require_json_object(item, "config", "datasource")
        sync_policy = _require_json_object(
            item,
            "sync_policy",
            "datasource",
        )
        target_path = normalize_workspace_target_path(
            _require_string(item, "target_path", "datasource"),
            target_lensnode.workspace_path,
        )
        status = _require_choice(
            item,
            "status",
            DataSource.Status.values,
            "datasource",
        )
        if plugin_key == "feishu":
            if source_type != DataSource.SourceType.FEISHU:
                raise ValueError(f'datasource "{name}" has the wrong type')
            item_plans = [
                _feishu_plan(
                    source_uuid,
                    name,
                    config,
                    sync_policy,
                    target_path,
                    status,
                )
            ]
        else:
            if source_type != DataSource.SourceType.GIT:
                raise ValueError(f'datasource "{name}" has the wrong type')
            item_plans = _git_plans(
                source_uuid,
                name,
                plugin_key,
                item.get("credential_endpoint_url", ""),
                config,
                sync_policy,
                target_path,
                status,
                target_lensnode.workspace_path,
            )
        for plan in item_plans:
            identity = str(plan["uuid"])
            if identity in identities:
                raise ValueError(
                    "snapshot contains duplicate datasource identities"
                )
            identities.add(identity)
            plans.append(plan)
    return plans


def _feishu_plan(
    source_uuid,
    name,
    config,
    sync_policy,
    target_path,
    status,
):
    folder_url = str(config.get("folder_url") or "").strip()
    if not folder_url:
        raise ValueError(f'datasource "{name}" has no Feishu folder URL')
    return {
        "uuid": source_uuid,
        "name": name,
        "plugin_key": "feishu",
        "source_type": DataSource.SourceType.FEISHU,
        "datasource_config": {
            "resource_urls": [folder_url],
            "recursive": config.get("recursive", True),
            "max_depth": config.get("max_depth", 10),
            "incremental": config.get("feishu_incremental", True),
            "delete_missing": config.get("feishu_delete_missing", False),
        },
        "sync_policy": sync_policy,
        "target_path": target_path,
        "status": status,
    }


def _git_plans(
    source_uuid,
    name,
    plugin_key,
    endpoint,
    config,
    sync_policy,
    target_path,
    status,
    workspace_path,
):
    repositories = config.get("repositories")
    is_collection = isinstance(repositories, list) and bool(repositories)
    if is_collection:
        entries = [
            entry
            for entry in repositories
            if isinstance(entry, dict) and entry.get("enabled", True)
        ]
    else:
        entries = [config]
    if not entries:
        raise ValueError(f'datasource "{name}" has no enabled repositories')
    plans = []
    for entry in entries:
        repository = _git_resource_identity(
            plugin_key,
            endpoint,
            entry.get("repo_url"),
        )
        datasource_config = {
            "repository" if plugin_key == "github" else "project": repository
        }
        branch = str(entry.get("branch") or config.get("branch") or "").strip()
        if branch:
            datasource_config["branch"] = branch
        directory = str(
            entry.get("directory") or config.get("directory") or ""
        ).strip()
        if directory:
            datasource_config["directory"] = directory
        item_target_path = target_path
        if is_collection:
            target_subdir = _target_subdir(entry, repository)
            item_target_path = normalize_workspace_target_path(
                str(PurePosixPath(target_path) / target_subdir),
                workspace_path,
            )
        split = len(entries) > 1
        plan_uuid = (
            uuid.uuid5(source_uuid, repository) if split else source_uuid
        )
        plan_name = _split_datasource_name(name, repository) if split else name
        plans.append(
            {
                "uuid": plan_uuid,
                "name": plan_name,
                "plugin_key": plugin_key,
                "source_type": DataSource.SourceType.GIT,
                "datasource_config": datasource_config,
                "sync_policy": sync_policy,
                "target_path": item_target_path,
                "status": status,
            }
        )
    return plans


def _git_resource_identity(plugin_key, endpoint, repo_url):
    parsed = urlsplit(str(repo_url or "").strip())
    expected = urlsplit(str(endpoint or "").strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("legacy repository URL is invalid")
    if plugin_key == "github":
        if parsed.scheme != "https" or parsed.hostname != "github.com":
            raise ValueError("legacy GitHub repository URL is invalid")
    elif (
        not expected.hostname
        or parsed.scheme != expected.scheme
        or parsed.hostname != expected.hostname
        or parsed.port != expected.port
    ):
        raise ValueError("legacy GitLab repository endpoint differs")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if parts and parts[-1].endswith(".git"):
        parts[-1] = parts[-1][:-4]
    if plugin_key == "github" and len(parts) != 2:
        raise ValueError("legacy GitHub repository path is invalid")
    if plugin_key == "gitlab" and len(parts) < 2:
        raise ValueError("legacy GitLab project path is invalid")
    if not all(parts):
        raise ValueError("legacy repository path is invalid")
    identity = "/".join(parts)
    return LEGACY_REPOSITORY_RENAMES.get(
        (plugin_key, identity.casefold()),
        identity,
    )


def _target_subdir(entry, repository):
    value = str(
        entry.get("target_subdir")
        or entry.get("name")
        or repository.rsplit("/", 1)[-1]
    ).strip()
    path = PurePosixPath(value)
    if len(path.parts) != 1 or path.parts[0] in {"", ".", ".."}:
        raise ValueError("legacy repository target subdirectory is invalid")
    return value


def _split_datasource_name(name, repository):
    suffix = f" / {repository}"
    prefix = name[: max(1, 160 - len(suffix))]
    return f"{prefix}{suffix}"[:160]


def _merged_connection_scopes(plans, connections):
    resources = {"github": [], "gitlab": []}
    for plan in plans:
        plugin_key = plan["plugin_key"]
        if plugin_key == "github":
            resources[plugin_key].append(
                plan["datasource_config"]["repository"]
            )
        elif plugin_key == "gitlab":
            resources[plugin_key].append(
                plan["datasource_config"]["project"]
            )
    scopes = {}
    for plugin_key in {plan["plugin_key"] for plan in plans}:
        if plugin_key == "feishu":
            scopes[plugin_key] = {}
            continue
        scope_key = "repositories" if plugin_key == "github" else "projects"
        current = connections[plugin_key].allowed_scope.get(scope_key, [])
        current = [
            LEGACY_REPOSITORY_RENAMES.get(
                (plugin_key, str(value).casefold()),
                value,
            )
            for value in current
        ]
        scopes[plugin_key] = {
            scope_key: _casefold_union(current, resources[plugin_key])
        }
    return scopes


def _casefold_union(existing, added):
    values = []
    identities = set()
    for value in [*existing, *added]:
        identity = str(value).casefold()
        if identity in identities:
            continue
        identities.add(identity)
        values.append(value)
    return values


def _upsert_datasource(
    plan,
    datasource_config,
    connection,
    target_lensnode,
):
    datasource = DataSource.objects.filter(uuid=plan["uuid"]).first()
    if datasource is None:
        name_matches = list(
            DataSource.objects.filter(
                lensnode=target_lensnode,
                name=plan["name"],
            )[:2]
        )
        path_matches = list(
            DataSource.objects.filter(
                lensnode=target_lensnode,
                target_path=plan["target_path"],
            )[:2]
        )
        if len(name_matches) > 1 or len(path_matches) > 1:
            raise ValueError(
                f'datasource "{plan["name"]}" has ambiguous matches'
            )
        name_match = name_matches[0] if name_matches else None
        path_match = path_matches[0] if path_matches else None
        if name_match and path_match and name_match.pk != path_match.pk:
            raise ValueError(
                f'datasource "{plan["name"]}" has ambiguous matches'
            )
        datasource = name_match or path_match
    if datasource is not None and (
        datasource.connection_id
        and datasource.connection_id != connection.pk
    ):
        raise ValueError(
            f'datasource "{plan["name"]}" uses a different Connection'
        )
    if datasource is not None and (
        datasource.plugin_key
        and datasource.plugin_key != plan["plugin_key"]
    ):
        raise ValueError(
            f'datasource "{plan["name"]}" uses a different Plugin'
        )
    values = {
        "name": plan["name"],
        "source_type": plan["source_type"],
        "lensnode": target_lensnode,
        "config": {},
        "sync_policy": plan["sync_policy"],
        "target_path": plan["target_path"],
        "credential": None,
        "connection": connection,
        "plugin_key": plan["plugin_key"],
        "datasource_config": datasource_config,
        "status": plan["status"],
    }
    if datasource is None:
        DataSource.objects.create(uuid=plan["uuid"], **values)
        return "created"
    changed = any(
        getattr(datasource, field_name) != value
        for field_name, value in values.items()
    )
    if not changed:
        return "unchanged"
    for field_name, value in values.items():
        setattr(datasource, field_name, value)
    datasource.save()
    return "updated"


def _require_mapping(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")


def _parse_uuid(value, label):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} is invalid") from exc


def _require_string(item, key, label):
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} {key} must be a non-empty string")
    return value.strip()


def _require_choice(item, key, choices, label):
    value = _require_string(item, key, label)
    if value not in choices:
        raise ValueError(f"{label} {key} is unsupported")
    return value


def _require_json_object(item, key, label):
    value = item.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"{label} {key} must be an object")
    return value
