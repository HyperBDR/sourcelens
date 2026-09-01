import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from lens.plugins.registry import PluginRegistryError, discover_plugins


class PluginRegistryTests(SimpleTestCase):
    """Verify trusted plugin manifest discovery."""

    def _write_manifest(self, root, version, manifest):
        path = Path(root) / "github" / version
        path.mkdir(parents=True)
        (path / "plugin.json").write_text(json.dumps(manifest))

    def test_discovers_a_supported_installed_plugin_version(self):
        manifest = {
            "key": "github",
            "version": "1.0.0",
            "protocol_version": 1,
            "handlers": {
                "runtime": "github_v1",
                "datasource": "github_datasource_v1",
            },
        }
        with tempfile.TemporaryDirectory() as root:
            self._write_manifest(root, "1.0.0", manifest)
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                plugins = discover_plugins()

        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0].key, "github")
        self.assertEqual(plugins[0].version, "1.0.0")
        self.assertEqual(plugins[0].runtime_handler, "github_v1")

    def test_rejects_a_manifest_with_an_unapproved_handler(self):
        manifest = {
            "key": "github",
            "version": "1.0.0",
            "protocol_version": 1,
            "handlers": {
                "runtime": "os.system",
                "datasource": "github_datasource_v1",
            },
        }
        with tempfile.TemporaryDirectory() as root:
            self._write_manifest(root, "1.0.0", manifest)
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                with self.assertRaisesMessage(PluginRegistryError, "handler"):
                    discover_plugins()

    def test_rejects_a_manifest_outside_its_directory_identity(self):
        manifest = {
            "key": "gitlab",
            "version": "1.0.0",
            "protocol_version": 1,
            "handlers": {
                "runtime": "github_v1",
                "datasource": "github_datasource_v1",
            },
        }
        with tempfile.TemporaryDirectory() as root:
            self._write_manifest(root, "1.0.0", manifest)
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                with self.assertRaisesMessage(PluginRegistryError, "directory"):
                    discover_plugins()
