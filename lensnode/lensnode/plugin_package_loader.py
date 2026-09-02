"""Load trusted, versioned Plugin runtimes from fixed entrypoints."""

import hashlib
import importlib.util
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PLUGIN_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
PLUGIN_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
MAX_RUNTIME_BYTES = 2 * 1024 * 1024


class PluginPackageLoadError(RuntimeError):
    """Raised when installed Plugin code violates the host contract."""


@dataclass(frozen=True)
class PluginRuntimeContract:
    """Validated runtime exports for one exact installed Plugin version."""

    plugin_key: str
    plugin_version: str
    build_tool: object
    execute_tool: object
    build_datasource_command: object


def load_runtime_contract(plugin_key, plugin_version, roots=None):
    """Load one exact Plugin runtime from controlled package roots."""

    if (
        not isinstance(plugin_key, str)
        or not PLUGIN_KEY_PATTERN.fullmatch(plugin_key)
        or not isinstance(plugin_version, str)
        or not PLUGIN_VERSION_PATTERN.fullmatch(plugin_version)
    ):
        raise PluginPackageLoadError("plugin runtime identity is invalid")
    for root_value in roots or _configured_roots():
        root = Path(root_value).resolve()
        package = root / plugin_key / plugin_version
        if not package.exists():
            continue
        if package.is_symlink() or not package.is_dir():
            raise PluginPackageLoadError("plugin package is invalid")
        resolved_package = package.resolve(strict=True)
        if root != resolved_package and root not in resolved_package.parents:
            raise PluginPackageLoadError("plugin package is outside root")
        runtime_path = package / "runtime.py"
        return _runtime_contract(
            runtime_path,
            plugin_key,
            plugin_version,
        )
    raise PluginPackageLoadError("installed plugin runtime is required")


def _configured_roots():
    """Return runtime roots, including the source-tree root for development."""

    configured = [
        value.strip()
        for value in os.getenv("LENS_PLUGIN_ROOTS", "").split(",")
        if value.strip()
    ]
    if configured:
        return configured
    source_root = Path(__file__).resolve().parents[2] / "plugins"
    return [Path("/opt/plugins"), source_root]


def _runtime_contract(path, plugin_key, plugin_version):
    """Validate a fixed runtime entrypoint and its structural interface."""

    if path.is_symlink():
        raise PluginPackageLoadError("plugin runtime entrypoint is invalid")
    try:
        resolved = path.resolve(strict=True)
        size = resolved.stat().st_size
        content_digest = hashlib.sha256(
            resolved.read_bytes()
        ).hexdigest()[:16]
    except OSError as exc:
        raise PluginPackageLoadError(
            "plugin runtime entrypoint is required"
        ) from exc
    if not resolved.is_file() or size > MAX_RUNTIME_BYTES:
        raise PluginPackageLoadError("plugin runtime entrypoint is invalid")
    module = _load_runtime_module(
        str(resolved),
        plugin_key,
        plugin_version,
        content_digest,
    )
    if (
        getattr(module, "PLUGIN_API_VERSION", None) != 1
        or getattr(module, "PLUGIN_KEY", None) != plugin_key
        or getattr(module, "PLUGIN_VERSION", None) != plugin_version
    ):
        raise PluginPackageLoadError("plugin runtime identity is invalid")
    exports = (
        getattr(module, "build_tool", None),
        getattr(module, "execute_tool", None),
        getattr(module, "build_datasource_command", None),
    )
    if any(not callable(item) for item in exports):
        raise PluginPackageLoadError("plugin runtime contract is invalid")
    return PluginRuntimeContract(
        plugin_key=plugin_key,
        plugin_version=plugin_version,
        build_tool=exports[0],
        execute_tool=exports[1],
        build_datasource_command=exports[2],
    )


@lru_cache(maxsize=128)
def _load_runtime_module(
    path_value,
    plugin_key,
    plugin_version,
    content_digest,
):
    """Execute a fixed regular file under an opaque module identity."""

    module_name = (
        f"_sourcelens_runtime_{plugin_key}_{plugin_version}_{content_digest}"
        .replace("-", "_")
        .replace(".", "_")
    )
    spec = importlib.util.spec_from_file_location(module_name, path_value)
    if spec is None or spec.loader is None:
        raise PluginPackageLoadError("plugin runtime entrypoint is invalid")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise PluginPackageLoadError("plugin runtime failed to load") from exc
    return module
