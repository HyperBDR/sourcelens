from django.test import TestCase

from lens.models import (
    Connection,
    DataSource,
    ExecutionSnapshot,
    LensNode,
    SecretMaterial,
    SecretVersion,
)
from lens.serializers import DataSourceSerializer


class PluginModelTests(TestCase):
    """Verify the persistent boundary for integration plugins."""

    def setUp(self):
        self.secret = SecretMaterial.objects.create(name="GitHub PAT")
        self.version = SecretVersion.objects.create(
            material=self.secret,
            encrypted_value="encrypted",
        )
        self.connection = Connection.objects.create(
            name="GitHub readonly",
            plugin_key="github",
            endpoint="https://github.com",
            allowed_scope={"repositories": ["HyperBDR/sourcelens"]},
            secret_version=self.version,
        )
        self.lensnode = LensNode.objects.create(
            name="Node",
            workspace_path="/workspace",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
        )

    def test_datasource_can_use_a_connection_without_embedding_auth_config(self):
        datasource = DataSource.objects.create(
            name="SourceLens repository",
            source_type=DataSource.SourceType.GIT,
            lensnode=self.lensnode,
            connection=self.connection,
            plugin_key="github",
            datasource_config={"repository": "HyperBDR/sourcelens"},
            target_path="/workspace/sourcelens",
        )

        self.assertEqual(datasource.connection, self.connection)
        self.assertNotIn("access_token", datasource.datasource_config)

    def test_snapshot_keeps_resolved_connection_and_datasource_values(self):
        datasource = DataSource.objects.create(
            name="SourceLens repository",
            source_type=DataSource.SourceType.GIT,
            lensnode=self.lensnode,
            connection=self.connection,
            plugin_key="github",
            datasource_config={"repository": "HyperBDR/sourcelens"},
            target_path="/workspace/sourcelens",
        )
        snapshot = ExecutionSnapshot.objects.create(
            kind=ExecutionSnapshot.Kind.DATASOURCE_SYNC,
            connection=self.connection,
            datasource=datasource,
            secret_version=self.version,
            plugin_key="github",
            plugin_version="1.0.0",
            protocol_version=1,
            resolved_config={
                "endpoint": "https://github.com",
                "repository": "HyperBDR/sourcelens",
            },
        )
        datasource.datasource_config = {"repository": "other/repository"}
        datasource.save(update_fields=["datasource_config"])

        snapshot.refresh_from_db()
        self.assertEqual(
            snapshot.resolved_config["repository"],
            "HyperBDR/sourcelens",
        )

    def test_serializer_accepts_provider_datasource_configuration(self):
        serializer = DataSourceSerializer(data={
            "name": "Repository",
            "source_type": "git",
            "lensnode_uuid": str(self.lensnode.uuid),
            "connection_uuid": str(self.connection.uuid),
            "plugin_key": "github",
            "datasource_config": {"repository": "HyperBDR/sourcelens"},
            "sync_policy": {},
            "target_path": "/workspace/repository",
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["datasource_config"],
            {"repository": "HyperBDR/sourcelens"},
        )
        self.assertIsNone(serializer.validated_data["credential"])
