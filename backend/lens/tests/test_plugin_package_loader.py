import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from lens.plugins.package_loader import (
    PluginPackageLoadError,
    load_control_contract,
)
from lens.plugins.providers import get_datasource_provider
from lens.plugins.registry import (
    PluginRegistryError,
    discover_plugins,
    installed_plugin,
)
from lens.plugins.tool_providers import get_tool_provider


class PluginPackageLoaderTests(SimpleTestCase):
    """Verify fixed, versioned Python entrypoints for trusted packages."""

    def _write_plugin(self, root, *, control_source=None, runtime_source=None):
        path = Path(root) / "example" / "1.2.3"
        path.mkdir(parents=True)
        manifest = {
            "key": "example",
            "version": "1.2.3",
            "protocol_version": 1,
            "handlers": {
                "control": "python_v1",
                "runtime": "python_v1",
            },
            "tools": [
                {
                    "key": "example_read_record",
                    "description": "Read one approved example record.",
                    "capability": "repository.read",
                    "side_effect": "none",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "record_id": {"type": "string"},
                        },
                        "required": ["record_id"],
                    },
                }
            ],
        }
        (path / "plugin.json").write_text(json.dumps(manifest))
        if control_source is not None:
            (path / "control.py").write_text(control_source)
        if runtime_source is not None:
            (path / "runtime.py").write_text(runtime_source)
        return path

    def test_discovers_generic_python_package_and_loads_control_contract(self):
        source = """
PLUGIN_API_VERSION = 1
PLUGIN_KEY = "example"
PLUGIN_VERSION = "1.2.3"

class Provider:
    key = "example"

    def validate_connection(self, *args): pass
    def validate_connection_scope(self, *args): pass
    def validate_live_connection(self, *args, **kwargs): pass
    def discover_resources(self, *args, **kwargs): pass
    def validate_datasource_source_type(self, *args): pass
    def validate_datasource_config(self, *args): pass
    def validate_request(self, *args): pass

DATASOURCE_PROVIDER = Provider()
TOOL_PROVIDER = Provider()
"""
        with tempfile.TemporaryDirectory() as root:
            self._write_plugin(
                root,
                control_source=source,
                runtime_source="PLUGIN_API_VERSION = 1\n",
            )
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                plugin = installed_plugin("example", "1.2.3")
                contract = load_control_contract(plugin)

        self.assertEqual(plugin.control_handler, "python_v1")
        self.assertEqual(plugin.tools[0].key, "example_read_record")
        self.assertEqual(contract.datasource_provider.key, "example")
        self.assertEqual(contract.tool_provider.key, "example")

    def test_rejects_package_without_fixed_runtime_entrypoint(self):
        with tempfile.TemporaryDirectory() as root:
            self._write_plugin(
                root,
                control_source="PLUGIN_API_VERSION = 1\n",
            )
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                with self.assertRaisesMessage(
                    PluginRegistryError,
                    "runtime entrypoint",
                ):
                    discover_plugins()

    def test_rejects_control_contract_with_mismatched_identity(self):
        source = """
PLUGIN_API_VERSION = 1
PLUGIN_KEY = "another-plugin"
PLUGIN_VERSION = "1.2.3"
DATASOURCE_PROVIDER = object()
TOOL_PROVIDER = object()
"""
        with tempfile.TemporaryDirectory() as root:
            self._write_plugin(
                root,
                control_source=source,
                runtime_source="PLUGIN_API_VERSION = 1\n",
            )
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                plugin = installed_plugin("example", "1.2.3")
                with self.assertRaisesMessage(
                    PluginPackageLoadError,
                    "identity",
                ):
                    load_control_contract(plugin)

    def test_rejects_symlinked_python_entrypoint(self):
        with tempfile.TemporaryDirectory() as root:
            path = self._write_plugin(
                root,
                control_source=None,
                runtime_source="PLUGIN_API_VERSION = 1\n",
            )
            outside = Path(root) / "outside.py"
            outside.write_text("PLUGIN_API_VERSION = 1\n")
            (path / "control.py").symlink_to(outside)
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                with self.assertRaisesMessage(
                    PluginRegistryError,
                    "control entrypoint",
                ):
                    discover_plugins()

    def test_provider_registries_resolve_exact_plugin_package_version(self):
        source = """
PLUGIN_API_VERSION = 1
PLUGIN_KEY = "example"
PLUGIN_VERSION = "1.2.3"

class Provider:
    key = "example"

    def validate_connection(self, *args): pass
    def validate_connection_scope(self, *args): pass
    def validate_live_connection(self, *args, **kwargs): pass
    def discover_resources(self, *args, **kwargs): pass
    def validate_datasource_source_type(self, *args): pass
    def validate_datasource_config(self, *args): pass
    def validate_request(self, *args): pass

DATASOURCE_PROVIDER = Provider()
TOOL_PROVIDER = Provider()
"""
        with tempfile.TemporaryDirectory() as root:
            self._write_plugin(
                root,
                control_source=source,
                runtime_source="PLUGIN_API_VERSION = 1\n",
            )
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                datasource = get_datasource_provider("example", "1.2.3")
                tools = get_tool_provider("example", "1.2.3")

        self.assertEqual(datasource.key, "example")
        self.assertEqual(tools.key, "example")
