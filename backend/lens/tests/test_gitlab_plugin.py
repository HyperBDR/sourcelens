from threading import Barrier

import httpx
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from lens.lensnode_auth import issue_lensnode_token
from lens.models import (
    Assistant,
    AssistantPluginBinding,
    Connection,
    ExecutionSnapshot,
    LensNode,
    Run,
    SecretMaterial,
    SecretVersion,
    Session,
)
from lens.plugins.providers.base import DatasourceProviderError
from lens.plugins.providers import get_datasource_provider
from lens.plugins.registry import latest_plugin
from lens.plugins.tool_providers import ToolProviderError, get_tool_provider
from lens.services import create_execution_run
from rest_framework.test import APIClient


class GitLabPluginManifestTests(TestCase):
    """Verify the bundled GitLab Plugin contract is installed."""

    def test_bundled_gitlab_plugin_is_discoverable(self):
        plugin = latest_plugin("gitlab")

        self.assertEqual(plugin.display_name, "GitLab")
        self.assertEqual(plugin.datasource_source_type, "git")
        self.assertEqual(
            [tool.key for tool in plugin.tools],
            ["gitlab_read_file", "gitlab_search_code"],
        )


class GitLabDatasourceProviderTests(SimpleTestCase):
    """Verify GitLab implements the datasource Provider contract."""

    def setUp(self):
        self.provider = get_datasource_provider("gitlab")
        self.scope = {"projects": ["platform/sourcelens"]}

    def test_accepts_nested_project_within_connection_scope(self):
        config = self.provider.validate_datasource_config(
            {"projects": ["platform/backend/sourcelens"]},
            {
                "project": "platform/backend/sourcelens",
                "branch": "main",
                "directory": "docs",
            },
        )

        self.assertEqual(config["project"], "platform/backend/sourcelens")
        self.assertEqual(config["directory"], "docs")

    def test_rejects_project_outside_connection_scope(self):
        with self.assertRaisesMessage(DatasourceProviderError, "scope"):
            self.provider.validate_datasource_config(
                self.scope,
                {"project": "other/repository"},
            )

    def test_accepts_public_and_self_managed_https_endpoints(self):
        endpoints = [
            "https://gitlab.com/",
            "https://gitlab.internal.example/",
        ]

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                self.assertEqual(
                    self.provider.validate_connection(endpoint, {}),
                    endpoint.rstrip("/"),
                )

    def test_rejects_endpoint_paths_and_non_https_schemes(self):
        endpoints = [
            "http://gitlab.example",
            "https://gitlab.example/nested",
            "https://user@gitlab.example",
        ]

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                with self.assertRaisesMessage(
                    DatasourceProviderError,
                    "endpoint",
                ):
                    self.provider.validate_connection(endpoint, {})

    def test_live_validation_uses_selected_endpoint_without_redirects(self):
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(
                200,
                json={"id": 7, "username": "plugin-admin"},
                request=request,
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = self.provider.validate_live_connection(
                "secret",
                endpoint="https://gitlab.internal.example",
                client=client,
            )

        self.assertEqual(
            seen,
            ["https://gitlab.internal.example/api/v4/user"],
        )
        self.assertEqual(result["account"]["username"], "plugin-admin")

    def test_discovers_allowed_projects_in_parallel(self):
        barrier = Barrier(2, timeout=2)

        def handler(request):
            if request.url.path.endswith("/repository/branches"):
                return httpx.Response(
                    200,
                    json=[{"name": "main"}],
                    request=request,
                )
            barrier.wait()
            project = request.url.path.split("/projects/", 1)[1]
            project = project.replace("%2F", "/")
            return httpx.Response(
                200,
                json={
                    "path_with_namespace": project,
                    "default_branch": "main",
                    "visibility": "private",
                },
                request=request,
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            resources = self.provider.discover_resources(
                {"projects": ["group/one", "group/two"]},
                "secret",
                endpoint="https://gitlab.example",
                client=client,
            )

        items = resources["resources"]["projects"]["items"]
        self.assertEqual([item["value"] for item in items], [
            "group/one",
            "group/two",
        ])


class GitLabToolProviderTests(SimpleTestCase):
    """Verify GitLab model Tool requests remain within Connection scope."""

    def setUp(self):
        self.provider = get_tool_provider("gitlab")
        self.scope = {"projects": ["platform/backend/sourcelens"]}

    def test_normalizes_read_file_request(self):
        endpoint, arguments = self.provider.validate_request(
            "https://gitlab.internal.example",
            self.scope,
            "gitlab_read_file",
            {
                "project": "platform/backend/sourcelens",
                "path": "README.md",
                "ref": "main",
            },
        )

        self.assertEqual(endpoint, "https://gitlab.internal.example")
        self.assertEqual(arguments["path"], "README.md")

    def test_rejects_project_outside_scope(self):
        with self.assertRaisesMessage(ToolProviderError, "scope"):
            self.provider.validate_request(
                "https://gitlab.example",
                self.scope,
                "gitlab_read_file",
                {"project": "other/repository", "path": "README.md"},
            )


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
class GitLabToolSnapshotTests(TestCase):
    """Verify GitLab uses the shared snapshot and lease control plane."""

    def test_node_creates_gitlab_tool_snapshot_without_secret(self):
        user = get_user_model().objects.create_user("gitlab-tool-user")
        node = LensNode.objects.create(
            name="GitLab node",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            tasks=[{"name": "general_chat"}],
        )
        token = issue_lensnode_token(node)
        material = SecretMaterial.objects.create(name="GitLab PAT")
        version = SecretVersion(material=material)
        version.set_value("gitlab-tool-secret")
        version.save()
        connection = Connection.objects.create(
            name="GitLab readonly",
            plugin_key="gitlab",
            endpoint="https://gitlab.internal.example",
            allowed_scope={"projects": ["platform/backend/sourcelens"]},
            secret_version=version,
        )
        assistant = Assistant.objects.create(
            name="GitLab Assistant",
            slug="gitlab-tool-assistant",
            lensnode=node,
            selected_task="general_chat",
            visibility=Assistant.Visibility.PUBLIC,
        )
        AssistantPluginBinding.objects.create(
            assistant=assistant,
            connection=connection,
            tools=["gitlab_read_file", "gitlab_search_code"],
        )
        session = Session.objects.create(assistant=assistant, user=user)
        run = create_execution_run(
            session,
            "Read the README",
            enqueue=False,
        )
        run.status = Run.Status.STREAMING
        run.save(update_fields=["status"])
        client = APIClient()

        response = client.post(
            "/api/lens/plugin-runtime/tool-snapshots/",
            {
                "run_uuid": str(run.uuid),
                "connection_uuid": str(connection.uuid),
                "tool_key": "gitlab_read_file",
                "call_id": "gitlab-call-1",
                "arguments": {
                    "project": "platform/backend/sourcelens",
                    "path": "README.md",
                    "ref": "main",
                },
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 201, response.data)
        snapshot = ExecutionSnapshot.objects.get(
            uuid=response.data["snapshot_uuid"]
        )
        self.assertEqual(snapshot.plugin_key, "gitlab")
        self.assertEqual(
            snapshot.resolved_config["endpoint"],
            "https://gitlab.internal.example",
        )
        self.assertNotIn("gitlab-tool-secret", str(snapshot.resolved_config))
