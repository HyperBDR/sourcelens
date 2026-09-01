from django.test import SimpleTestCase

from lens.plugins.providers.github import GitHubDatasourceProvider
from lens.plugins.providers.base import DatasourceProviderError


class GitHubDatasourceProviderTests(SimpleTestCase):
    """Verify GitHub implements the generic datasource contract."""

    def setUp(self):
        self.provider = GitHubDatasourceProvider()
        self.scope = {"repositories": ["HyperBDR/sourcelens"]}

    def test_accepts_a_repository_within_connection_scope(self):
        config = self.provider.validate_datasource_config(
            self.scope,
            {
                "repository": "HyperBDR/sourcelens",
                "branch": "main",
                "directory": "docs",
            },
        )

        self.assertEqual(config["repository"], "HyperBDR/sourcelens")
        self.assertEqual(config["directory"], "docs")

    def test_rejects_a_repository_outside_connection_scope(self):
        with self.assertRaisesMessage(DatasourceProviderError, "scope"):
            self.provider.validate_datasource_config(
                self.scope,
                {"repository": "other/repository"},
            )

    def test_rejects_credential_fields_in_datasource_config(self):
        with self.assertRaisesMessage(DatasourceProviderError, "credentials"):
            self.provider.validate_datasource_config(
                self.scope,
                {
                    "repository": "HyperBDR/sourcelens",
                    "access_token": "not-allowed",
                },
            )

    def test_rejects_non_github_connection_endpoint(self):
        with self.assertRaisesMessage(DatasourceProviderError, "endpoint"):
            self.provider.validate_connection(
                "https://evil.example",
                {},
            )

    def test_normalizes_public_github_connection_endpoint(self):
        self.assertEqual(
            self.provider.validate_connection("https://github.com/", {}),
            "https://github.com",
        )
