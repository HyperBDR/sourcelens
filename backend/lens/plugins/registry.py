"""Discover trusted built-in plugin manifests from controlled directories."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

PLUGIN_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
PLUGIN_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
TOOL_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
RESOURCE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
CONNECTION_WRITE_TARGET_PATTERN = re.compile(
    r"^(endpoint|secret_value|config\.[a-z][a-z0-9_-]{0,63}|"
    r"allowed_scope\.[a-z][a-z0-9_-]{0,63})$"
)
SUPPORTED_PROTOCOL_VERSION = 1
ALLOWED_HANDLERS = frozenset(
    {
        "python_v1",
        "github_v1",
        "github_datasource_v1",
        "gitlab_v1",
        "gitlab_datasource_v1",
        "jira_v1",
        "jira_datasource_v1",
    }
)
READ_ONLY_TOOL_CAPABILITIES = frozenset(
    {"issue.read", "jira.issue.search", "repository.read"}
)
DATASOURCE_SOURCE_TYPES = frozenset({"git", "jira"})
SCHEMA_TYPES = frozenset({"array", "boolean", "integer", "string"})
SCHEMA_FORMATS = frozenset(
    {
        "password",
        "provider-resource",
        "provider-resource-option",
        "repository-path",
        "uri",
    }
)


class PluginRegistryError(ValueError):
    """Raised when an installed plugin manifest is invalid or unsafe."""


class PluginNotFoundError(PluginRegistryError):
    """Raised when no installed version matches one Plugin identity."""


@dataclass(frozen=True)
class InstalledPlugin:
    """One validated plugin version available to the platform."""

    key: str
    version: str
    protocol_version: int
    display_name: str
    description: str
    datasource_source_type: str
    connection_schema: dict
    datasource_schema: dict
    control_handler: str
    runtime_handler: str
    datasource_handler: str
    tools: tuple
    path: Path


@dataclass(frozen=True)
class InstalledPluginTool:
    """One validated read-only tool declared by an installed Plugin."""

    key: str
    description: str
    capability: str
    side_effect: str
    input_schema: dict


def discover_plugins():
    """Return validated Plugin versions from configured controlled roots."""

    plugins = []
    identities = set()
    roots = getattr(settings, "LENS_PLUGIN_ROOTS", ["/opt/sourcelens/plugins"])
    for root_value in roots:
        root = Path(root_value).resolve()
        if not root.exists():
            continue
        if not root.is_dir():
            raise PluginRegistryError("plugin root must be a directory")
        for key_dir in sorted(root.iterdir()):
            if not key_dir.is_dir() or key_dir.is_symlink():
                continue
            for version_dir in sorted(key_dir.iterdir()):
                if not version_dir.is_dir() or version_dir.is_symlink():
                    continue
                plugin = _load_plugin(root, key_dir, version_dir)
                identity = (plugin.key, plugin.version)
                if identity in identities:
                    raise PluginRegistryError(
                        "duplicate plugin key and version"
                    )
                identities.add(identity)
                plugins.append(plugin)
    return plugins


def latest_plugin(plugin_key):
    """Return the latest installed version for one Plugin identity."""

    matches = [
        plugin for plugin in discover_plugins() if plugin.key == plugin_key
    ]
    if not matches:
        raise PluginNotFoundError("installed plugin is required")
    return max(
        matches,
        key=lambda plugin: tuple(
            int(part) for part in plugin.version.split(".")
        ),
    )


def installed_plugin(plugin_key, version):
    """Return one exact installed Plugin version."""

    for plugin in discover_plugins():
        if plugin.key == plugin_key and plugin.version == version:
            return plugin
    raise PluginNotFoundError("installed plugin version is required")


def _load_plugin(root, key_dir, version_dir):
    """Load one manifest after validating its controlled directory identity."""

    manifest_path = version_dir / "plugin.json"
    resolved_path = manifest_path.resolve()
    if root not in resolved_path.parents:
        raise PluginRegistryError("plugin manifest is outside configured root")
    if not resolved_path.is_file():
        raise PluginRegistryError("plugin manifest is required")
    try:
        manifest = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PluginRegistryError(
            "plugin manifest must be valid JSON"
        ) from exc
    if not isinstance(manifest, dict):
        raise PluginRegistryError("plugin manifest must be an object")

    key = manifest.get("key")
    version = manifest.get("version")
    protocol_version = manifest.get("protocol_version")
    handlers = manifest.get("handlers")
    if not isinstance(key, str) or not PLUGIN_KEY_PATTERN.fullmatch(key):
        raise PluginRegistryError("plugin key is invalid")
    if not isinstance(version, str) or not PLUGIN_VERSION_PATTERN.fullmatch(
        version
    ):
        raise PluginRegistryError("plugin version is invalid")
    if key != key_dir.name or version != version_dir.name:
        raise PluginRegistryError(
            "plugin manifest does not match directory identity"
        )
    if protocol_version != SUPPORTED_PROTOCOL_VERSION:
        raise PluginRegistryError("plugin protocol version is unsupported")
    if not isinstance(handlers, dict):
        raise PluginRegistryError("plugin handlers are required")
    control_handler = handlers.get("control")
    runtime_handler = handlers.get("runtime")
    datasource_handler = handlers.get("datasource")
    if control_handler == "python_v1":
        datasource_handler = "python_v1"
    elif control_handler is None:
        control_handler = datasource_handler
    if runtime_handler not in ALLOWED_HANDLERS:
        raise PluginRegistryError("plugin runtime handler is not allowed")
    if datasource_handler not in ALLOWED_HANDLERS:
        raise PluginRegistryError("plugin datasource handler is not allowed")
    if control_handler not in ALLOWED_HANDLERS:
        raise PluginRegistryError("plugin control handler is not allowed")
    if control_handler == "python_v1" or runtime_handler == "python_v1":
        _validate_python_entrypoint(version_dir, "control")
        _validate_python_entrypoint(version_dir, "runtime")
    tools = _validate_tools(manifest.get("tools") or [])
    display_name = _bounded_manifest_text(
        manifest.get("display_name") or key,
        "plugin display name",
        160,
    )
    description = _bounded_manifest_text(
        manifest.get("description") or "",
        "plugin description",
        1000,
        required=False,
    )
    datasource_source_type = manifest.get("datasource_source_type", "git")
    if datasource_source_type not in DATASOURCE_SOURCE_TYPES:
        raise PluginRegistryError("plugin datasource source type is invalid")
    connection_schema = _validate_form_schema(
        manifest.get("connection_schema"),
        "connection",
    )
    datasource_schema = _validate_form_schema(
        manifest.get("datasource_schema"),
        "datasource",
    )
    return InstalledPlugin(
        key=key,
        version=version,
        protocol_version=protocol_version,
        display_name=display_name,
        description=description,
        datasource_source_type=datasource_source_type,
        connection_schema=connection_schema,
        datasource_schema=datasource_schema,
        control_handler=control_handler,
        runtime_handler=runtime_handler,
        datasource_handler=datasource_handler,
        tools=tools,
        path=version_dir.resolve(),
    )


def _validate_tools(value):
    """Return trusted read-only tool declarations from one manifest."""

    if not isinstance(value, list):
        raise PluginRegistryError("plugin tools must be a list")
    tools = []
    identities = set()
    for item in value:
        if not isinstance(item, dict):
            raise PluginRegistryError("plugin tool must be an object")
        key = item.get("key")
        description = item.get("description")
        capability = item.get("capability")
        side_effect = item.get("side_effect")
        if (
            not isinstance(key, str)
            or not TOOL_KEY_PATTERN.fullmatch(key)
            or key in identities
        ):
            raise PluginRegistryError("plugin tool is not allowed")
        if (
            not isinstance(description, str)
            or not description.strip()
            or len(description) > 1000
        ):
            raise PluginRegistryError("plugin tool description is invalid")
        if capability not in READ_ONLY_TOOL_CAPABILITIES:
            raise PluginRegistryError("plugin tool capability is not allowed")
        if side_effect != "none":
            raise PluginRegistryError("plugin tool side effect is not allowed")
        schema = _validate_tool_schema(
            key,
            item.get("input_schema"),
        )
        identities.add(key)
        tools.append(
            InstalledPluginTool(
                key=key,
                description=description.strip(),
                capability=capability,
                side_effect=side_effect,
                input_schema=schema,
            )
        )
    return tuple(tools)


def _validate_tool_schema(tool_key, value):
    """Validate the bounded V1 JSON schema subset for model tool inputs."""

    if not isinstance(value, dict) or value.get("type") != "object":
        raise PluginRegistryError("plugin tool input schema is invalid")
    properties = value.get("properties") or {}
    required = value.get("required") or []
    if not isinstance(properties, dict) or not isinstance(required, list):
        raise PluginRegistryError("plugin tool input schema is invalid")
    if (
        len(properties) > 20
        or len(set(required)) != len(required)
        or set(required).difference(properties)
    ):
        raise PluginRegistryError("plugin tool input schema is not allowed")
    normalized = {}
    for name, field in properties.items():
        if (
            not isinstance(name, str)
            or not PLUGIN_KEY_PATTERN.fullmatch(name)
            or not isinstance(field, dict)
            or field.get("type") not in {"boolean", "integer", "string"}
        ):
            raise PluginRegistryError("plugin tool field schema is invalid")
        safe_field = {"type": field["type"]}
        description = field.get("description")
        if description:
            safe_field["description"] = _bounded_manifest_text(
                description,
                "plugin tool field description",
                500,
            )
        for limit_name in ("minLength", "maxLength", "minimum", "maximum"):
            limit = field.get(limit_name)
            if isinstance(limit, int) and not isinstance(limit, bool):
                safe_field[limit_name] = limit
        normalized[name] = safe_field
    return {
        "type": "object",
        "properties": normalized,
        "required": list(required),
        "additionalProperties": False,
    }


def _validate_python_entrypoint(version_dir, name):
    """Require a bounded regular Python file at one fixed package path."""

    path = version_dir / f"{name}.py"
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PluginRegistryError(
            f"plugin {name} entrypoint is required"
        ) from exc
    if (
        path.is_symlink()
        or not resolved.is_file()
        or version_dir.resolve() not in resolved.parents
        or resolved.stat().st_size > 1_000_000
    ):
        raise PluginRegistryError(f"plugin {name} entrypoint is invalid")


def _validate_form_schema(value, label):
    """Return a bounded JSON Schema subset for administrator forms."""

    if value is None:
        return {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }
    if not isinstance(value, dict) or value.get("type") != "object":
        raise PluginRegistryError(f"plugin {label} schema is invalid")
    properties = value.get("properties") or {}
    required = value.get("required") or []
    if (
        not isinstance(properties, dict)
        or len(properties) > 20
        or not isinstance(required, list)
        or len(set(required)) != len(required)
        or set(required).difference(properties)
    ):
        raise PluginRegistryError(f"plugin {label} schema is invalid")
    normalized = {}
    for key, field in properties.items():
        if (
            not isinstance(key, str)
            or not PLUGIN_KEY_PATTERN.fullmatch(key)
            or not isinstance(field, dict)
            or field.get("type") not in SCHEMA_TYPES
        ):
            raise PluginRegistryError(f"plugin {label} field is invalid")
        field_format = field.get("format")
        if field_format is not None and field_format not in SCHEMA_FORMATS:
            raise PluginRegistryError(
                f"plugin {label} field format is invalid"
            )
        safe_field = {
            "type": field["type"],
            "title": _bounded_manifest_text(
                field.get("title") or key,
                f"plugin {label} field title",
                160,
            ),
        }
        description = field.get("description")
        if description:
            safe_field["description"] = _bounded_manifest_text(
                description,
                f"plugin {label} field description",
                500,
            )
        if field_format is not None:
            safe_field["format"] = field_format
        resource = field.get("resource")
        if resource is not None:
            if (
                not isinstance(resource, str)
                or not RESOURCE_KEY_PATTERN.fullmatch(resource)
            ):
                raise PluginRegistryError(
                    f"plugin {label} field resource is invalid"
                )
            safe_field["resource"] = resource
        depends_on = field.get("depends_on")
        if depends_on is not None:
            if (
                not isinstance(depends_on, str)
                or not PLUGIN_KEY_PATTERN.fullmatch(depends_on)
            ):
                raise PluginRegistryError(
                    f"plugin {label} field dependency is invalid"
                )
            safe_field["depends_on"] = depends_on
        if field_format == "provider-resource":
            if resource is None or depends_on is not None:
                raise PluginRegistryError(
                    f"plugin {label} field resource is invalid"
                )
        elif field_format == "provider-resource-option":
            if resource is None or depends_on is None:
                raise PluginRegistryError(
                    f"plugin {label} field dependency is invalid"
                )
        elif resource is not None or depends_on is not None:
            raise PluginRegistryError(
                f"plugin {label} field resource is invalid"
            )
        if "default" in field and isinstance(
            field["default"],
            (str, int, bool),
        ):
            safe_field["default"] = field["default"]
        if field["type"] == "array":
            items = field.get("items")
            if not isinstance(items, dict) or items.get("type") != "string":
                raise PluginRegistryError(
                    f"plugin {label} array field is invalid"
                )
            safe_field["items"] = {"type": "string"}
        write_to = field.get("write_to")
        if write_to is not None:
            if (
                label != "connection"
                or not isinstance(write_to, str)
                or not CONNECTION_WRITE_TARGET_PATTERN.fullmatch(write_to)
            ):
                raise PluginRegistryError(
                    f"plugin {label} field write target is invalid"
                )
            safe_field["write_to"] = write_to
        normalized[key] = safe_field
    for field in normalized.values():
        depends_on = field.get("depends_on")
        if depends_on is None:
            continue
        dependency = normalized.get(depends_on)
        if dependency is None or dependency.get("format") != "provider-resource":
            raise PluginRegistryError(
                f"plugin {label} field dependency is invalid"
            )
    return {
        "type": "object",
        "properties": normalized,
        "required": list(required),
        "additionalProperties": False,
    }


def _bounded_manifest_text(value, label, limit, required=True):
    """Return one bounded display string from an installed manifest."""

    if not isinstance(value, str):
        raise PluginRegistryError(f"{label} is invalid")
    text = value.strip()
    if (required and not text) or len(text) > limit:
        raise PluginRegistryError(f"{label} is invalid")
    return text
