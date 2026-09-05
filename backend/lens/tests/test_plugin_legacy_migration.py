from django.test import TestCase

from lens.models import (
    Connection,
    DataSource,
    DataSourceCredential,
    LegacyIntegrationMigration,
    LensNode,
)
from lens.plugins.legacy_migration import (
    migrate_legacy_github_integrations,
    rollback_legacy_github_integrations,
)


class LegacyPluginMigrationTests(TestCase):
    """Verify conservative and reversible GitHub legacy migration."""

    def setUp(self):
        self.node = LensNode.objects.create(
            name="Node",
            workspace_path="/workspace",
        )

    def test_migrates_unambiguous_github_token_datasource(self):
        credential = self._credential()
        datasource = DataSource.objects.create(
            name="Repository",
            source_type=DataSource.SourceType.GIT,
            lensnode=self.node,
            credential=credential,
            config={
                "repo_url": "https://github.com/HyperBDR/sourcelens.git",
                "branch": "main",
                "auth_scheme": "token",
            },
            target_path="/workspace/repository",
        )

        report = migrate_legacy_github_integrations()

        self.assertEqual(report, {"migrated": 2, "manual_review": 0, "skipped": 0})
        datasource.refresh_from_db()
        self.assertEqual(datasource.plugin_key, "github")
        self.assertEqual(
            datasource.datasource_config,
            {"repository": "HyperBDR/sourcelens", "branch": "main"},
        )
        self.assertEqual(datasource.credential, credential)
        self.assertEqual(
            datasource.config["repo_url"],
            "https://github.com/HyperBDR/sourcelens.git",
        )
        connection = datasource.connection
        self.assertEqual(
            connection.allowed_scope,
            {"repositories": ["HyperBDR/sourcelens"]},
        )
        self.assertEqual(connection.secret_version.get_value(), "legacy-token")
        self.assertEqual(
            LegacyIntegrationMigration.objects.filter(
                status=LegacyIntegrationMigration.Status.MIGRATED
            ).count(),
            2,
        )

    def test_marks_organization_datasource_for_manual_review(self):
        credential = self._credential()
        datasource = DataSource.objects.create(
            name="Organization",
            source_type=DataSource.SourceType.GIT,
            lensnode=self.node,
            credential=credential,
            config={
                "scope_type": "organization",
                "repositories": [
                    {
                        "repo_url": "https://github.com/HyperBDR/sourcelens",
                        "branch": "main",
                        "target_subdir": "sourcelens",
                    }
                ],
            },
        )

        report = migrate_legacy_github_integrations()

        self.assertEqual(report["migrated"], 0)
        self.assertEqual(report["manual_review"], 2)
        datasource.refresh_from_db()
        self.assertIsNone(datasource.connection)
        record = LegacyIntegrationMigration.objects.get(
            source_kind=LegacyIntegrationMigration.SourceKind.DATASOURCE,
            source_uuid=datasource.uuid,
        )
        self.assertEqual(record.reason, "ORGANIZATION_DATASOURCE_AMBIGUOUS")

    def test_dry_run_does_not_write_and_rollback_restores_legacy_path(self):
        credential = self._credential()
        datasource = DataSource.objects.create(
            name="Repository",
            source_type=DataSource.SourceType.GIT,
            lensnode=self.node,
            credential=credential,
            config={
                "repo_url": "https://github.com/HyperBDR/sourcelens",
                "auth_scheme": "token",
            },
        )

        dry_report = migrate_legacy_github_integrations(dry_run=True)

        self.assertEqual(dry_report["migrated"], 2)
        self.assertFalse(Connection.objects.exists())
        self.assertFalse(LegacyIntegrationMigration.objects.exists())

        migrate_legacy_github_integrations()
        connection = Connection.objects.get()
        rollback_report = rollback_legacy_github_integrations()

        self.assertEqual(rollback_report, {"rolled_back": 1})
        datasource.refresh_from_db()
        connection.refresh_from_db()
        self.assertIsNone(datasource.connection)
        self.assertEqual(datasource.plugin_key, "")
        self.assertEqual(datasource.datasource_config, {})
        self.assertEqual(datasource.credential, credential)
        self.assertTrue(datasource.config)
        self.assertEqual(connection.status, Connection.Status.DISABLED)

    def _credential(self):
        credential = DataSourceCredential.objects.create(
            name="Legacy GitHub",
            provider=DataSourceCredential.Provider.GITHUB,
            auth_type=DataSourceCredential.AuthType.HTTPS_TOKEN,
            endpoint_url="https://github.com",
            scope_config={"organization_url": "https://github.com/HyperBDR/"},
        )
        credential.set_secret("legacy-token")
        credential.save()
        return credential
