"""Discover trusted built-in plugin manifests from controlled directories."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


PLUGIN_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
PLUGIN_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SUPPORTED_PROTOCOL_VERSION = 1
ALLOWED_HANDLERS = frozenset({"github_v1", "github_datasource_v1"})


class PluginRegistryError(ValueError):
    """Raised when an installed plugin manifest is invalid or unsafe."""


@dataclass(frozen=True)
class InstalledPlugin:
    """One validated plugin version available to the platform."""

    key: str
    version: str
    protocol_version: int
    runtime_handler: str
    datasource_handler: str
    path: Path


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
                    raise PluginRegistryError("duplicate plugin key and version")
                identities.add(identity)
                plugins.append(plugin)
    return plugins


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
        raise PluginRegistryError("plugin manifest must be valid JSON") from exc
    if not isinstance(manifest, dict):
        raise PluginRegistryError("plugin manifest must be an object")

    key = manifest.get("key")
    version = manifest.get("version")
    protocol_version = manifest.get("protocol_version")
    handlers = manifest.get("handlers")
    if not isinstance(key, str) or not PLUGIN_KEY_PATTERN.fullmatch(key):
        raise PluginRegistryError("plugin key is invalid")
    if not isinstance(version, str) or not PLUGIN_VERSION_PATTERN.fullmatch(version):
        raise PluginRegistryError("plugin version is invalid")
    if key != key_dir.name or version != version_dir.name:
        raise PluginRegistryError("plugin manifest does not match directory identity")
    if protocol_version != SUPPORTED_PROTOCOL_VERSION:
        raise PluginRegistryError("plugin protocol version is unsupported")
    if not isinstance(handlers, dict):
        raise PluginRegistryError("plugin handlers are required")
    runtime_handler = handlers.get("runtime")
    datasource_handler = handlers.get("datasource")
    if runtime_handler not in ALLOWED_HANDLERS:
        raise PluginRegistryError("plugin runtime handler is not allowed")
    if datasource_handler not in ALLOWED_HANDLERS:
        raise PluginRegistryError("plugin datasource handler is not allowed")
    return InstalledPlugin(
        key=key,
        version=version,
        protocol_version=protocol_version,
        runtime_handler=runtime_handler,
        datasource_handler=datasource_handler,
        path=version_dir.resolve(),
    )
