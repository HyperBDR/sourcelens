import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from lens.models import PluginRelease
from lens.plugins.registry import installed_plugin
from lens.plugins.releases import (
    PluginReleaseLifecycleError,
    assign_plugin_release_role,
    publish_plugin_release,
    reconcile_plugin_releases,
    retire_plugin_release,
)


User = get_user_model()


def _write_plugin(root, version):
    """Write one minimal versioned Plugin package for lifecycle tests."""

    package = Path(root) / "example" / version
    package.mkdir(parents=True)
    manifest = {
        "key": "example",
        "version": version,
        "protocol_version": 1,
        "capability_family": "plugin",
        "handlers": {
            "control": "python_v1",
            "runtime": "python_v1",
        },
    }
    (package / "plugin.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    identity = (
        'PLUGIN_API_VERSION = 1\n'
        'PLUGIN_KEY = "example"\n'
        f'PLUGIN_VERSION = "{version}"\n'
    )
    (package / "control.py").write_text(identity, encoding="utf-8")
    (package / "runtime.py").write_text(identity, encoding="utf-8")
    return package


class PluginReleaseLifecycleTests(TestCase):
    """Verify installed versions require explicit lifecycle promotion."""

    def test_new_version_stays_debugging_until_published_and_activated(self):
        with tempfile.TemporaryDirectory() as root:
            _write_plugin(root, "1.0.0")
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                reconcile_plugin_releases()
                first = PluginRelease.objects.get(
                    plugin_key="example",
                    version="1.0.0",
                )
                self.assertEqual(
                    first.release_status,
                    PluginRelease.ReleaseStatus.PUBLISHED,
                )
                self.assertEqual(
                    first.deployment_role,
                    PluginRelease.DeploymentRole.ACTIVE,
                )

                _write_plugin(root, "1.1.0")
                reconcile_plugin_releases()
                second = PluginRelease.objects.get(
                    plugin_key="example",
                    version="1.1.0",
                )
                self.assertEqual(
                    second.release_status,
                    PluginRelease.ReleaseStatus.DEBUGGING,
                )
                self.assertEqual(second.deployment_role, "")
                self.assertEqual(installed_plugin("example").version, "1.0.0")

                publish_plugin_release(second, actor=None)
                assign_plugin_release_role(
                    second,
                    PluginRelease.DeploymentRole.CANDIDATE,
                )
                self.assertEqual(installed_plugin("example").version, "1.0.0")

                assign_plugin_release_role(
                    second,
                    PluginRelease.DeploymentRole.ACTIVE,
                )
                self.assertEqual(installed_plugin("example").version, "1.1.0")
                first.refresh_from_db()
                self.assertEqual(first.deployment_role, "")

    def test_published_package_content_is_immutable(self):
        with tempfile.TemporaryDirectory() as root:
            package = _write_plugin(root, "1.0.0")
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                reconcile_plugin_releases()
                (package / "runtime.py").write_text(
                    "# changed after publication\n",
                    encoding="utf-8",
                )

                with self.assertRaisesMessage(
                    PluginReleaseLifecycleError,
                    "PLUGIN_RELEASE_DIGEST_MISMATCH",
                ):
                    installed_plugin("example")

    def test_retired_release_cannot_receive_a_deployment_role(self):
        with tempfile.TemporaryDirectory() as root:
            _write_plugin(root, "1.0.0")
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                reconcile_plugin_releases()
                release = PluginRelease.objects.get(plugin_key="example")
                retire_plugin_release(release)

                with self.assertRaisesMessage(
                    PluginReleaseLifecycleError,
                    "PLUGIN_RELEASE_NOT_PUBLISHED",
                ):
                    assign_plugin_release_role(
                        release,
                        PluginRelease.DeploymentRole.ACTIVE,
                    )


class PluginReleaseApiTests(TestCase):
    """Verify administrators control the release lifecycle through the API."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="plugin-admin",
            password="test-pass",
            is_staff=True,
        )
        self.user = User.objects.create_user(
            username="plugin-user",
            password="test-pass",
        )

    def test_admin_can_publish_and_activate_an_installed_release(self):
        with tempfile.TemporaryDirectory() as root:
            _write_plugin(root, "1.0.0")
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                self.client.force_authenticate(self.admin)
                response = self.client.post(
                    "/api/lens/admin/plugins/releases/reconcile/",
                    {},
                    format="json",
                )
                self.assertEqual(response.status_code, 200)

                _write_plugin(root, "1.1.0")
                self.client.post(
                    "/api/lens/admin/plugins/releases/reconcile/",
                    {},
                    format="json",
                )
                response = self.client.post(
                    "/api/lens/admin/plugins/example/releases/1.1.0/publish/",
                    {},
                    format="json",
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["release_status"], "published")

                response = self.client.post(
                    "/api/lens/admin/plugins/example/releases/1.1.0/role/",
                    {"deployment_role": "active"},
                    format="json",
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["deployment_role"], "active")

                response = self.client.get(
                    "/api/lens/admin/plugins/releases/",
                )
                self.assertEqual(response.status_code, 200)
                versions = {
                    row["version"]: row
                    for row in response.data
                    if row["plugin_key"] == "example"
                }
                self.assertEqual(
                    versions["1.0.0"]["deployment_role"],
                    "",
                )
                self.assertEqual(
                    versions["1.1.0"]["deployment_role"],
                    "active",
                )

    def test_active_digest_mismatch_returns_a_stable_conflict(self):
        with tempfile.TemporaryDirectory() as root:
            package = _write_plugin(root, "1.0.0")
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                reconcile_plugin_releases()
                (package / "runtime.py").write_text(
                    "# changed after publication\n",
                    encoding="utf-8",
                )
                self.client.force_authenticate(self.admin)

                for path in (
                    "/api/lens/admin/plugins/",
                    "/api/lens/admin/plugins/example/tools/",
                    "/api/lens/admin/plugins/example/manifest/",
                    "/api/lens/admin/plugins/example/icon/",
                ):
                    with self.subTest(path=path):
                        response = self.client.get(path)
                        self.assertEqual(response.status_code, 409)
                        self.assertEqual(
                            response.data["detail"],
                            "PLUGIN_RELEASE_DIGEST_MISMATCH",
                        )

    def test_non_admin_cannot_manage_plugin_releases(self):
        self.client.force_authenticate(self.user)

        response = self.client.get("/api/lens/admin/plugins/releases/")

        self.assertEqual(response.status_code, 403)
