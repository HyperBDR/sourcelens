import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from lens.plugins.registry import (
    PluginRegistryError,
    discover_plugins,
    latest_plugin,
)
from rest_framework.test import APIClient

User = get_user_model()


class PluginRegistryTests(TestCase):
    """Verify trusted plugin manifest discovery."""

    def _write_manifest(self, root, version, manifest):
        path = Path(root) / "github" / version
        path.mkdir(parents=True)
        (path / "plugin.json").write_text(json.dumps(manifest))

    def test_bundled_github_plugin_is_discoverable(self):
        plugin = latest_plugin("github")

        self.assertEqual(plugin.key, "github")
        self.assertEqual(plugin.display_name, "GitHub")
        self.assertEqual(plugin.datasource_source_type, "git")
        self.assertEqual(plugin.connection_schema["type"], "object")
        self.assertEqual(plugin.datasource_schema["type"], "object")
        self.assertEqual(
            plugin.datasource_schema["properties"]["repository"]["resource"],
            "repositories",
        )
        self.assertEqual(
            plugin.datasource_schema["properties"]["branch"]["depends_on"],
            "repository",
        )
        self.assertEqual(
            plugin.connection_schema["properties"]["repositories"]["write_to"],
            "allowed_scope.repositories",
        )

    def test_accepts_bounded_resource_ids_and_field_dependencies(self):
        manifest = {
            "key": "github",
            "version": "1.0.0",
            "protocol_version": 1,
            "handlers": {
                "runtime": "python_v1",
                "datasource": "python_v1",
            },
            "datasource_schema": {
                "type": "object",
                "properties": {
                    "repository": {
                        "type": "string",
                        "format": "provider-resource",
                        "resource": "repositories",
                    },
                    "branch": {
                        "type": "string",
                        "format": "provider-resource-option",
                        "resource": "branches",
                        "depends_on": "repository",
                    },
                },
            },
        }
        with tempfile.TemporaryDirectory() as root:
            self._write_manifest(root, "1.0.0", manifest)
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                plugin = discover_plugins()[0]

        self.assertEqual(
            plugin.datasource_schema["properties"]["branch"],
            {
                "type": "string",
                "title": "branch",
                "format": "provider-resource-option",
                "resource": "branches",
                "depends_on": "repository",
            },
        )

    def test_rejects_unsafe_resource_identifier(self):
        manifest = {
            "key": "github",
            "version": "1.0.0",
            "protocol_version": 1,
            "handlers": {
                "runtime": "python_v1",
                "datasource": "python_v1",
            },
            "datasource_schema": {
                "type": "object",
                "properties": {
                    "repository": {
                        "type": "string",
                        "format": "provider-resource",
                        "resource": "../repositories",
                    }
                },
            },
        }
        with tempfile.TemporaryDirectory() as root:
            self._write_manifest(root, "1.0.0", manifest)
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                with self.assertRaisesMessage(
                    PluginRegistryError,
                    "resource",
                ):
                    discover_plugins()

    def test_rejects_unknown_resource_field_dependency(self):
        manifest = {
            "key": "github",
            "version": "1.0.0",
            "protocol_version": 1,
            "handlers": {
                "runtime": "python_v1",
                "datasource": "python_v1",
            },
            "datasource_schema": {
                "type": "object",
                "properties": {
                    "branch": {
                        "type": "string",
                        "format": "provider-resource-option",
                        "resource": "branches",
                        "depends_on": "repository",
                    }
                },
            },
        }
        with tempfile.TemporaryDirectory() as root:
            self._write_manifest(root, "1.0.0", manifest)
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                with self.assertRaisesMessage(
                    PluginRegistryError,
                    "dependency",
                ):
                    discover_plugins()

    def test_discovers_a_supported_installed_plugin_version(self):
        manifest = {
            "key": "github",
            "version": "1.0.0",
            "protocol_version": 1,
            "handlers": {
                "runtime": "python_v1",
                "datasource": "python_v1",
            },
        }
        with tempfile.TemporaryDirectory() as root:
            self._write_manifest(root, "1.0.0", manifest)
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                plugins = discover_plugins()

        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0].key, "github")
        self.assertEqual(plugins[0].version, "1.0.0")
        self.assertEqual(plugins[0].runtime_handler, "python_v1")

    def test_rejects_a_manifest_with_an_unapproved_handler(self):
        manifest = {
            "key": "github",
            "version": "1.0.0",
            "protocol_version": 1,
            "handlers": {
                "runtime": "os.system",
                "datasource": "python_v1",
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
                "runtime": "python_v1",
                "datasource": "python_v1",
            },
        }
        with tempfile.TemporaryDirectory() as root:
            self._write_manifest(root, "1.0.0", manifest)
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                with self.assertRaisesMessage(
                    PluginRegistryError, "directory"
                ):
                    discover_plugins()

    def test_admin_can_list_installed_plugins_without_handlers_or_paths(self):
        manifest = {
            "key": "github",
            "version": "1.0.0",
            "protocol_version": 1,
            "handlers": {
                "runtime": "python_v1",
                "datasource": "python_v1",
            },
        }
        admin = User.objects.create_user("plugin-admin", is_staff=True)
        client = APIClient()
        client.force_authenticate(admin)
        with tempfile.TemporaryDirectory() as root:
            self._write_manifest(root, "1.0.0", manifest)
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                response = client.get("/api/lens/admin/plugins/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            [
                {
                    "key": "github",
                    "version": "1.0.0",
                    "protocol_version": 1,
                    "display_name": "github",
                    "description": "",
                    "datasource_source_type": "git",
                }
            ],
        )

    def test_admin_can_list_read_only_plugin_tools(self):
        manifest = {
            "key": "github",
            "version": "1.0.0",
            "protocol_version": 1,
            "handlers": {
                "runtime": "python_v1",
                "datasource": "python_v1",
            },
            "tools": [
                {
                    "key": "github_read_file",
                    "description": (
                        "Read a file from an authorized repository."
                    ),
                    "capability": "repository.read",
                    "side_effect": "none",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "repository": {"type": "string"},
                            "path": {"type": "string"},
                        },
                        "required": ["repository", "path"],
                    },
                }
            ],
        }
        admin = User.objects.create_user("tools-admin", is_staff=True)
        client = APIClient()
        client.force_authenticate(admin)
        with tempfile.TemporaryDirectory() as root:
            self._write_manifest(root, "1.0.0", manifest)
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                response = client.get("/api/lens/admin/plugins/github/tools/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["key"], "github_read_file")
        self.assertEqual(response.data[0]["side_effect"], "none")

    def test_admin_can_read_safe_manifest_configuration_schema(self):
        admin = User.objects.create_user("manifest-admin", is_staff=True)
        client = APIClient()
        client.force_authenticate(admin)

        response = client.get("/api/lens/admin/plugins/github/manifest/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["key"], "github")
        self.assertEqual(response.data["display_name"], "GitHub")
        self.assertIn("connection_schema", response.data)
        self.assertIn("datasource_schema", response.data)
        self.assertNotIn("handlers", response.data)
        self.assertNotIn("path", response.data)

    def test_rejects_a_mutating_or_unknown_plugin_tool(self):
        manifest = {
            "key": "github",
            "version": "1.0.0",
            "protocol_version": 1,
            "handlers": {
                "runtime": "python_v1",
                "datasource": "python_v1",
            },
            "tools": [
                {
                    "key": "github_raw_exec",
                    "description": "Execute a command.",
                    "capability": "repository.write",
                    "side_effect": "write",
                    "input_schema": {"type": "object"},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as root:
            self._write_manifest(root, "1.0.0", manifest)
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                with self.assertRaisesMessage(PluginRegistryError, "tool"):
                    discover_plugins()
