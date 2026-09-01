from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from lens.models import Connection, SecretMaterial, SecretVersion


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
        self.assertNotIn("ghp-example", connection.secret_version.encrypted_value)

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
        self.assertEqual(SecretMaterial.objects.count(), 1)

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
