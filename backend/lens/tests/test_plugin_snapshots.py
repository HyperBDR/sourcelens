import json
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

from lens.models import Connection, DataSource, LensNode, SecretMaterial, SecretVersion
from lens.plugins.registry import PluginRegistryError
from lens.plugins.snapshots import create_datasource_sync_snapshot


class PluginSnapshotTests(TestCase):
    """Verify resolved datasource execution snapshots."""

    def setUp(self):
        material = SecretMaterial.objects.create(name="GitHub PAT")
        version = SecretVersion.objects.create(
            material=material,
            encrypted_value="encrypted",
        )
        self.connection = Connection.objects.create(
            name="GitHub readonly",
            plugin_key="github",
            endpoint="https://github.com",
            allowed_scope={"repositories": ["HyperBDR/sourcelens"]},
            secret_version=version,
        )
        self.node = LensNode.objects.create(
            name="Node",
            workspace_path="/workspace",
        )
        self.datasource = DataSource.objects.create(
            name="SourceLens repository",
            source_type=DataSource.SourceType.GIT,
            lensnode=self.node,
            connection=self.connection,
            plugin_key="github",
            datasource_config={
                "repository": "HyperBDR/sourcelens",
                "branch": "main",
            },
            sync_policy={"interval_seconds": 3600},
            target_path="/workspace/sourcelens",
        )

    def test_snapshot_contains_complete_resolved_sync_config(self):
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
            path = Path(root) / "github" / "1.0.0"
            path.mkdir(parents=True)
            (path / "plugin.json").write_text(json.dumps(manifest))
            with override_settings(LENS_PLUGIN_ROOTS=[root]):
                snapshot = create_datasource_sync_snapshot(self.datasource)

        self.assertEqual(snapshot.plugin_version, "1.0.0")
        self.assertEqual(snapshot.secret_version, self.connection.secret_version)
        self.assertEqual(snapshot.resolved_config["endpoint"], "https://github.com")
        self.assertEqual(
            snapshot.resolved_config["datasource_config"]["branch"],
            "main",
        )
        self.assertEqual(snapshot.resolved_config["target_path"], "/workspace/sourcelens")
        self.assertNotIn("encrypted", json.dumps(snapshot.resolved_config))

    def test_snapshot_rejects_credential_shaped_datasource_config(self):
        self.datasource.datasource_config["access_token"] = "must-not-be-here"
        self.datasource.save(update_fields=["datasource_config"])

        with self.assertRaisesMessage(PluginRegistryError, "credentials"):
            create_datasource_sync_snapshot(self.datasource)
