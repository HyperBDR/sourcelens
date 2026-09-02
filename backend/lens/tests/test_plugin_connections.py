from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from lens.models import (
    Connection,
    DataSource,
    LensNode,
    SecretMaterial,
    SecretVersion,
)
from lens.plugins.snapshots import create_datasource_sync_snapshot
from rest_framework.test import APIClient


class PluginConnectionApiTests(TestCase):
    """Verify administrator management of reusable Plugin connections."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="plugin-admin",
            password="password",
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_create_connection_encrypts_secret_and_masks_response(self):
        response = self.client.post(
            "/api/lens/admin/connections/",
            {
                "name": "GitHub readonly",
                "plugin_key": "github",
                "endpoint": "https://github.com/",
                "allowed_scope": {"repositories": ["owner/repo"]},
                "secret_value": "ghp-example",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertNotIn("secret_value", response.data)
        self.assertTrue(response.data["has_secret"])
        connection = Connection.objects.get(uuid=response.data["uuid"])
        self.assertEqual(connection.endpoint, "https://github.com")
        self.assertEqual(connection.secret_version.get_value(), "ghp-example")
        self.assertNotIn(
            "ghp-example", connection.secret_version.encrypted_value
        )

    @patch("lens.views.plugins.get_datasource_provider")
    def test_preview_resources_uses_unsaved_secret_without_persisting(self, provider_factory):
        provider = provider_factory.return_value
        provider.validate_connection.return_value = "https://github.com"
        provider.discover_connection_resources.return_value = {
            "resources": {
                "repositories": {
                    "items": [{"value": "owner/repo", "label": "owner/repo"}]
                }
            },
            "next_cursor": "",
        }

        response = self.client.post(
            "/api/lens/admin/connections/resource-preview/",
            {
                "plugin_key": "github",
                "endpoint": "https://github.com",
                "secret_value": "temporary-token",
                "config": {},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(Connection.objects.count(), 0)
        provider.discover_connection_resources.assert_called_once_with(
            "temporary-token",
            endpoint="https://github.com",
            connection_config={},
            query="",
            cursor="",
            limit=50,
        )

    def test_update_secret_reuses_material_identity(self):
        material = SecretMaterial.objects.create(name="Existing")
        version = SecretVersion(material=material)
        version.set_value("old-secret")
        version.save()
        connection = Connection.objects.create(
            name="GitHub readonly",
            plugin_key="github",
            endpoint="https://github.com",
            allowed_scope={"repositories": ["owner/repo"]},
            secret_version=version,
        )

        response = self.client.patch(
            f"/api/lens/admin/connections/{connection.uuid}/",
            {"secret_value": "new-secret"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        connection.refresh_from_db()
        self.assertEqual(connection.secret_version.material_id, material.pk)
        self.assertEqual(connection.secret_version.get_value(), "new-secret")
        version.refresh_from_db()
        material.refresh_from_db()
        self.assertEqual(version.status, "active")
        self.assertEqual(material.status, "active")
        self.assertEqual(SecretMaterial.objects.count(), 1)

    def test_rotated_secret_only_applies_to_new_execution_snapshots(self):
        connection = self._create_connection()
        node = LensNode.objects.create(name="Node", workspace_path="/workspace")
        datasource = DataSource.objects.create(
            name="Repository",
            source_type=DataSource.SourceType.GIT,
            lensnode=node,
            connection=connection,
            plugin_key="github",
            datasource_config={"repository": "owner/repo"},
        )
        old_version = connection.secret_version
        old_snapshot = create_datasource_sync_snapshot(datasource)

        response = self.client.patch(
            f"/api/lens/admin/connections/{connection.uuid}/",
            {"secret_value": "new-secret"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        connection.refresh_from_db()
        new_snapshot = create_datasource_sync_snapshot(datasource)
        self.assertEqual(old_snapshot.secret_version_id, old_version.pk)
        self.assertEqual(
            new_snapshot.secret_version_id,
            connection.secret_version_id,
        )
        self.assertNotEqual(
            old_snapshot.secret_version_id,
            new_snapshot.secret_version_id,
        )

    def test_create_rejects_non_github_endpoint(self):
        response = self.client.post(
            "/api/lens/admin/connections/",
            {
                "name": "Unsafe",
                "plugin_key": "github",
                "endpoint": "https://evil.example",
                "allowed_scope": {"repositories": ["owner/repo"]},
                "secret_value": "secret",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("endpoint", response.data)

    def test_create_normalizes_repository_scope(self):
        response = self.client.post(
            "/api/lens/admin/connections/",
            {
                "name": "GitHub readonly",
                "plugin_key": "github",
                "endpoint": "https://github.com",
                "allowed_scope": {
                    "repositories": [" owner/repo/", "other/project"],
                },
                "secret_value": "secret",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            response.data["allowed_scope"],
            {"repositories": ["owner/repo", "other/project"]},
        )

    @patch("lens.views.plugins.get_datasource_provider")
    def test_validate_connection_uses_secret_without_returning_it(
        self,
        get_provider,
    ):
        connection = self._create_connection()
        provider = get_provider.return_value
        provider.validate_live_connection.return_value = {
            "account": {"login": "octocat", "name": "The Octocat"},
        }

        response = self.client.post(
            f"/api/lens/admin/connections/{connection.uuid}/validate/",
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        provider.validate_live_connection.assert_called_once_with(
            "stored-secret",
            endpoint="https://github.com",
            connection_config={},
        )
        self.assertEqual(response.data["status"], "success")
        self.assertNotIn("stored-secret", str(response.data))

    @patch("lens.views.plugins.get_datasource_provider")
    def test_resources_only_use_connection_allowed_scope(self, get_provider):
        connection = self._create_connection()
        provider = get_provider.return_value
        provider.discover_resources.return_value = {
            "resources": {
                "repositories": {
                    "items": [
                        {
                            "value": "owner/repo",
                            "label": "owner/repo",
                            "metadata": {"default_branch": "main"},
                            "options": {
                                "branches": [
                                    {"value": "main", "label": "main"},
                                    {"value": "release", "label": "release"},
                                ]
                            },
                        }
                    ]
                }
            }
        }

        response = self.client.get(
            f"/api/lens/admin/connections/{connection.uuid}/resources/"
        )

        self.assertEqual(response.status_code, 200)
        provider.discover_resources.assert_called_once_with(
            {"repositories": ["owner/repo"]},
            "stored-secret",
            endpoint="https://github.com",
            connection_config={},
        )
        self.assertEqual(
            response.data["resources"]["repositories"]["items"][0]["value"],
            "owner/repo",
        )
        self.assertNotIn("stored-secret", str(response.data))

    def test_disabled_connection_cannot_discover_resources(self):
        connection = self._create_connection(status=Connection.Status.DISABLED)

        response = self.client.get(
            f"/api/lens/admin/connections/{connection.uuid}/resources/"
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["detail"], "CONNECTION_DISABLED")

    def _create_connection(self, **overrides):
        material = SecretMaterial.objects.create(name="GitHub PAT")
        version = SecretVersion(material=material)
        version.set_value("stored-secret")
        version.save()
        values = {
            "name": "GitHub readonly",
            "plugin_key": "github",
            "endpoint": "https://github.com",
            "allowed_scope": {"repositories": ["owner/repo"]},
            "secret_version": version,
        }
        values.update(overrides)
        return Connection.objects.create(**values)
