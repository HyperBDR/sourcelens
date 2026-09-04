import copy
import os
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from lens.models import (
    Connection,
    DataSource,
    DataSourceCredential,
    LensNode,
    SecretMaterial,
    SecretVersion,
)
from lens.plugin_datasource_transfer import (
    import_plugin_datasource_snapshot,
)


class PluginDataSourceTransferTests(TestCase):
    """Verify legacy production sources reuse current Plugin Connections."""

    def setUp(self):
        self.node = LensNode.objects.create(
            name="local-dev-lensnode",
            workspace_path="/workspace",
        )
        self.connections = {
            "feishu": self._connection(
                "OnePro",
                "feishu",
                "https://open.feishu.cn",
                config={"app_id": "cli_example"},
            ),
            "github": self._connection(
                "Current GitHub",
                "github",
                "https://github.com",
                allowed_scope={"repositories": ["existing/repository"]},
            ),
            "gitlab": self._connection(
                "Current GitLab",
                "gitlab",
                "https://gitlab.example.com",
                allowed_scope={"projects": ["existing/project"]},
            ),
        }
        self.snapshot = {
            "schema_version": 1,
            "datasources": [
                {
                    "uuid": "11111111-1111-4111-8111-111111111111",
                    "name": "Production Feishu",
                    "source_type": "feishu",
                    "credential_provider": "feishu",
                    "config": {
                        "folder_url": (
                            "https://tenant.feishu.cn/drive/folder/"
                            "FolderToken?from=share"
                        ),
                        "recursive": True,
                        "max_depth": 8,
                        "feishu_incremental": True,
                        "feishu_delete_missing": False,
                    },
                    "sync_policy": {
                        "mode": "interval",
                        "interval_seconds": 3600,
                    },
                    "target_path": "/workspace/feishu",
                    "status": "active",
                },
                {
                    "uuid": "22222222-2222-4222-8222-222222222222",
                    "name": "Production GitHub",
                    "source_type": "git",
                    "credential_provider": "github",
                    "credential_endpoint_url": "https://github.com",
                    "config": {
                        "repositories": [
                            {
                                "repo_url": (
                                    "https://github.com/HyperBDR/docs.git"
                                ),
                                "branch": "main",
                                "target_subdir": "docs",
                                "enabled": True,
                            }
                        ]
                    },
                    "sync_policy": {"mode": "crontab", "cron": "0 2 * * *"},
                    "target_path": "/workspace/github",
                    "status": "active",
                },
                {
                    "uuid": "33333333-3333-4333-8333-333333333333",
                    "name": "Production GitLab",
                    "source_type": "git",
                    "credential_provider": "gitlab",
                    "credential_endpoint_url": "https://gitlab.example.com",
                    "config": {
                        "repositories": [
                            {
                                "repo_url": (
                                    "https://gitlab.example.com/group/a.git"
                                ),
                                "branch": "qa",
                                "target_subdir": "a",
                                "enabled": True,
                            },
                            {
                                "repo_url": (
                                    "https://gitlab.example.com/group/b.git"
                                ),
                                "branch": "qa",
                                "target_subdir": "b",
                                "enabled": True,
                            },
                        ]
                    },
                    "sync_policy": {
                        "mode": "interval",
                        "interval_seconds": 7200,
                    },
                    "target_path": "/workspace/gitlab",
                    "status": "active",
                },
            ],
        }

    def test_reuses_connections_and_splits_multi_repository_sources(self):
        secret_version_ids = {
            key: connection.secret_version_id
            for key, connection in self.connections.items()
        }

        report = import_plugin_datasource_snapshot(
            self.snapshot,
            target_lensnode=self.node,
            connections=self.connections,
        )

        self.assertEqual(report["connections"]["created"], 0)
        self.assertEqual(report["connections"]["updated"], 2)
        self.assertEqual(report["datasources"]["created"], 4)
        self.assertEqual(DataSource.objects.count(), 4)
        self.assertFalse(DataSourceCredential.objects.exists())
        for key, connection in self.connections.items():
            connection.refresh_from_db()
            self.assertEqual(
                connection.secret_version_id,
                secret_version_ids[key],
            )
            self.assertTrue(
                DataSource.objects.filter(connection=connection).exists()
            )
        self.assertEqual(
            self.connections["github"].allowed_scope,
            {
                "repositories": [
                    "existing/repository",
                    "HyperBDR/docs",
                ]
            },
        )
        self.assertEqual(
            self.connections["gitlab"].allowed_scope,
            {
                "projects": [
                    "existing/project",
                    "group/a",
                    "group/b",
                ]
            },
        )
        gitlab_paths = set(
            DataSource.objects.filter(plugin_key="gitlab").values_list(
                "target_path",
                flat=True,
            )
        )
        self.assertEqual(
            gitlab_paths,
            {"/workspace/gitlab/a", "/workspace/gitlab/b"},
        )

    def test_normalizes_feishu_resource_without_copying_credentials(self):
        import_plugin_datasource_snapshot(
            self.snapshot,
            target_lensnode=self.node,
            connections=self.connections,
        )

        datasource = DataSource.objects.get(plugin_key="feishu")
        self.assertEqual(datasource.connection, self.connections["feishu"])
        self.assertEqual(
            datasource.datasource_config["resource_urls"],
            ["https://tenant.feishu.cn/drive/folder/FolderToken"],
        )
        self.assertEqual(
            datasource.datasource_config["resources"],
            [{"kind": "folder", "token": "FolderToken"}],
        )
        self.assertIsNone(datasource.credential)
        self.assertEqual(datasource.config, {})

    def test_second_import_does_not_create_or_update_resources(self):
        import_plugin_datasource_snapshot(
            self.snapshot,
            target_lensnode=self.node,
            connections=self.connections,
        )

        report = import_plugin_datasource_snapshot(
            self.snapshot,
            target_lensnode=self.node,
            connections=self.connections,
        )

        self.assertEqual(DataSource.objects.count(), 4)
        self.assertEqual(report["connections"]["created"], 0)
        self.assertEqual(report["connections"]["updated"], 0)
        self.assertEqual(report["connections"]["unchanged"], 3)
        self.assertEqual(report["datasources"]["created"], 0)
        self.assertEqual(report["datasources"]["updated"], 0)
        self.assertEqual(report["datasources"]["unchanged"], 4)

    def test_reuses_existing_datasource_target_path(self):
        datasource = DataSource.objects.create(
            name="Local name",
            source_type=DataSource.SourceType.GIT,
            lensnode=self.node,
            connection=self.connections["github"],
            plugin_key="github",
            datasource_config={"repository": "old/repository"},
            target_path="/workspace/github/docs",
        )

        report = import_plugin_datasource_snapshot(
            self.snapshot,
            target_lensnode=self.node,
            connections=self.connections,
        )

        datasource.refresh_from_db()
        self.assertEqual(DataSource.objects.count(), 4)
        self.assertEqual(datasource.name, "Production GitHub")
        self.assertEqual(
            datasource.datasource_config,
            {"repository": "HyperBDR/docs", "branch": "main"},
        )
        self.assertEqual(report["datasources"]["created"], 3)
        self.assertEqual(report["datasources"]["updated"], 1)

    def test_maps_known_renamed_github_repository(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["datasources"] = [snapshot["datasources"][1]]
        self.connections["github"].allowed_scope = {
            "repositories": [
                "existing/repository",
                "HyperBDR/hyperfilelens",
            ]
        }
        self.connections["github"].save(update_fields=["allowed_scope"])
        snapshot["datasources"][0]["config"]["repositories"][0][
            "repo_url"
        ] = "https://github.com/HyperBDR/hyperfilelens.git"

        import_plugin_datasource_snapshot(
            snapshot,
            target_lensnode=self.node,
            connections=self.connections,
        )

        datasource = DataSource.objects.get()
        self.assertEqual(
            datasource.datasource_config["repository"],
            "oneprolabs/hyperfilelens",
        )
        self.assertEqual(
            self.connections["github"].allowed_scope,
            {
                "repositories": [
                    "existing/repository",
                    "oneprolabs/hyperfilelens",
                ]
            },
        )

    def test_conflicting_connection_rolls_back_the_import(self):
        other = self._connection(
            "Other GitHub",
            "github",
            "https://github.com",
            allowed_scope={"repositories": ["old/repository"]},
        )
        DataSource.objects.create(
            name="Local name",
            source_type=DataSource.SourceType.GIT,
            lensnode=self.node,
            connection=other,
            plugin_key="github",
            datasource_config={"repository": "old/repository"},
            target_path="/workspace/github/docs",
        )

        with self.assertRaisesMessage(
            ValueError,
            "uses a different Connection",
        ):
            import_plugin_datasource_snapshot(
                self.snapshot,
                target_lensnode=self.node,
                connections=self.connections,
            )

        self.connections["github"].refresh_from_db()
        self.assertEqual(DataSource.objects.count(), 1)
        self.assertEqual(
            self.connections["github"].allowed_scope,
            {"repositories": ["existing/repository"]},
        )

    def test_dry_run_rolls_back_connections_and_datasources(self):
        original_scopes = {
            key: copy.deepcopy(connection.allowed_scope)
            for key, connection in self.connections.items()
        }

        report = import_plugin_datasource_snapshot(
            self.snapshot,
            target_lensnode=self.node,
            connections=self.connections,
            dry_run=True,
        )

        self.assertEqual(report["datasources"]["created"], 4)
        self.assertFalse(DataSource.objects.exists())
        for key, connection in self.connections.items():
            connection.refresh_from_db()
            self.assertEqual(connection.allowed_scope, original_scopes[key])

    def _connection(
        self,
        name,
        plugin_key,
        endpoint,
        config=None,
        allowed_scope=None,
    ):
        material = SecretMaterial.objects.create(name=f"{name} secret")
        version = SecretVersion(material=material)
        version.set_value(f"{plugin_key}-secret")
        version.save()
        return Connection.objects.create(
            name=name,
            plugin_key=plugin_key,
            endpoint=endpoint,
            config=config or {},
            allowed_scope=allowed_scope or {},
            secret_version=version,
        )


class SyncPluginDataSourceSnapshotCommandTests(TestCase):
    """Verify production snapshot import requires local opt-in."""

    def test_command_requires_explicit_environment_opt_in(self):
        with patch.dict(
            os.environ,
            {"SOURCELENS_ALLOW_DATASOURCE_IMPORT": ""},
        ):
            with self.assertRaisesMessage(
                CommandError,
                "explicit local-development opt-in",
            ):
                call_command("sync_plugin_datasource_snapshot")
