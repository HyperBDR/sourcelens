from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from lens.lensnode_auth import issue_lensnode_token
from lens.models import (
    Connection,
    DataSource,
    ExecutionSnapshot,
    LensNode,
    SecretMaterial,
    SecretVersion,
)


class PluginLeaseTests(TestCase):
    """Verify node-authenticated, snapshot-bound plugin leases."""

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
            secret_version=version,
        )
        self.node = LensNode.objects.create(
            name="Node",
            workspace_path="/workspace",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
        )
        self.datasource = DataSource.objects.create(
            name="Repository",
            source_type=DataSource.SourceType.GIT,
            lensnode=self.node,
            connection=self.connection,
            plugin_key="github",
            datasource_config={"repository": "owner/repository"},
            target_path="/workspace/repository",
        )
        self.snapshot = ExecutionSnapshot.objects.create(
            kind=ExecutionSnapshot.Kind.DATASOURCE_SYNC,
            connection=self.connection,
            datasource=self.datasource,
            secret_version=version,
            plugin_key="github",
            plugin_version="1.0.0",
            protocol_version=1,
            resolved_config={"repository": "owner/repository"},
        )
        self.token = issue_lensnode_token(self.node)
        self.client = APIClient()

    def test_node_can_issue_a_lease_for_its_snapshot_without_secret_payload(self):
        response = self.client.post(
            "/api/lens/plugin-runtime/leases/",
            {"snapshot_uuid": str(self.snapshot.uuid)},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("lease_uuid", response.data)
        self.assertIn("expires_at", response.data)
        self.assertNotIn("secret", response.data)

    def test_lease_rejects_a_snapshot_for_another_node(self):
        other = LensNode.objects.create(
            name="Other",
            workspace_path="/workspace",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
        )
        self.datasource.lensnode = other
        self.datasource.save(update_fields=["lensnode"])

        response = self.client.post(
            "/api/lens/plugin-runtime/leases/",
            {"snapshot_uuid": str(self.snapshot.uuid)},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(response.status_code, 403)
