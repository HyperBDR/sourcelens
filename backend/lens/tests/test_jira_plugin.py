import httpx
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from lens.lensnode_auth import issue_lensnode_token
from lens.models import (
    Assistant,
    AssistantPluginBinding,
    Connection,
    DataSource,
    ExecutionSnapshot,
    LensNode,
    Session,
    Run,
)
from lens.plugins.providers.base import (
    DatasourceProviderError,
    PluginRequestContext,
)
from lens.plugins.providers.jira import JiraDatasourceProvider
from lens.plugins.registry import latest_plugin
from lens.plugins.snapshots import create_datasource_sync_snapshot
from lens.plugins.tool_providers import ToolProviderError, get_tool_provider
from lens.plugins.tool_snapshots import _resource_summary
from lens.services import create_execution_run
from rest_framework.test import APIClient


class JiraPluginManifestTests(TestCase):
    """Verify the bundled Jira Cloud Plugin contract is installed."""

    def test_bundled_jira_plugin_is_discoverable(self):
        plugin = latest_plugin("jira")

        self.assertEqual(plugin.display_name, "Jira Cloud")
        self.assertEqual(plugin.datasource_source_type, "jira")
        self.assertEqual(
            [tool.key for tool in plugin.tools],
            ["jira_get_issue", "jira_search_issues"],
        )


class JiraDatasourceProviderTests(SimpleTestCase):
    """Verify Jira Cloud implements the datasource Provider contract."""

    def setUp(self):
        self.provider = JiraDatasourceProvider()
        self.config = {"email": "admin@example.com"}
        self.scope = {"projects": ["SL", "OPS"]}

    def test_accepts_project_within_connection_scope(self):
        config = self.provider.validate_datasource_config(
            self.scope,
            {"project": "sl", "max_issues": 50},
        )

        self.assertEqual(config, {"project": "SL", "max_issues": 50})

    def test_rejects_project_outside_connection_scope(self):
        with self.assertRaisesMessage(DatasourceProviderError, "scope"):
            self.provider.validate_datasource_config(
                self.scope,
                {"project": "OTHER"},
            )

    def test_accepts_only_atlassian_cloud_https_endpoint(self):
        self.assertEqual(
            self.provider.validate_connection(
                "https://company.atlassian.net/",
                self.config,
            ),
            "https://company.atlassian.net",
        )

        for endpoint in [
            "http://company.atlassian.net",
            "https://jira.internal.example",
            "https://company.atlassian.net/wiki",
        ]:
            with self.subTest(endpoint=endpoint):
                with self.assertRaisesMessage(
                    DatasourceProviderError,
                    "endpoint",
                ):
                    self.provider.validate_connection(endpoint, self.config)

    def test_live_validation_uses_basic_auth_without_redirects(self):
        seen = {}

        def handler(request):
            seen["authorization"] = request.headers["Authorization"]
            return httpx.Response(
                200,
                json={"accountId": "account-1", "displayName": "Admin"},
                request=request,
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = self.provider.validate_live_connection(
                "api-token",
                endpoint="https://company.atlassian.net",
                connection_config=self.config,
                client=client,
            )

        self.assertTrue(seen["authorization"].startswith("Basic "))
        self.assertNotIn("api-token", seen["authorization"])
        self.assertEqual(result["account"]["account_id"], "account-1")

    def test_discovers_only_explicitly_allowed_projects(self):
        def handler(request):
            key = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200,
                json={"key": key, "name": f"Project {key}"},
                request=request,
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            resources = self.provider.discover_resources(
                self.scope,
                "api-token",
                endpoint="https://company.atlassian.net",
                connection_config=self.config,
                client=client,
            )

        items = resources["resources"]["projects"]["items"]
        self.assertEqual([item["value"] for item in items], ["SL", "OPS"])

    def test_discovery_returns_partial_results_and_warnings(self):
        def handler(request):
            project = request.url.path.rsplit("/", 1)[-1]
            if project == "OPS":
                return httpx.Response(404, request=request)
            return httpx.Response(
                200,
                json={"key": "SL", "name": "SourceLens"},
                request=request,
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            resources = self.provider.discover_resources(
                self.scope,
                "api-token",
                endpoint="https://company.atlassian.net",
                connection_config=self.config,
                client=client,
                request_context=PluginRequestContext(max_retries=0),
            )

        self.assertEqual(
            resources["resources"]["projects"]["items"][0]["value"],
            "SL",
        )
        self.assertEqual(
            resources["warnings"],
            [
                {
                    "resource": "OPS",
                    "label": "project",
                    "code": "JIRA_NOT_FOUND",
                }
            ],
        )


class JiraToolProviderTests(SimpleTestCase):
    """Verify Jira model Tool requests remain within Connection scope."""

    def setUp(self):
        self.provider = get_tool_provider("jira")
        self.scope = {"projects": ["SL"]}

    def test_accepts_issue_from_allowed_project(self):
        endpoint, arguments = self.provider.validate_request(
            "https://company.atlassian.net",
            self.scope,
            "jira_get_issue",
            {"issue_key": "SL-488"},
        )

        self.assertEqual(endpoint, "https://company.atlassian.net")
        self.assertEqual(arguments, {"issue_key": "SL-488"})

    def test_rejects_issue_from_project_outside_scope(self):
        with self.assertRaisesMessage(ToolProviderError, "scope"):
            self.provider.validate_request(
                "https://company.atlassian.net",
                self.scope,
                "jira_get_issue",
                {"issue_key": "OPS-1"},
            )

    def test_search_requires_explicit_allowed_project(self):
        endpoint, arguments = self.provider.validate_request(
            "https://company.atlassian.net",
            self.scope,
            "jira_search_issues",
            {"project": "sl", "query": "plugin", "max_results": 10},
        )

        self.assertEqual(endpoint, "https://company.atlassian.net")
        self.assertEqual(arguments["project"], "SL")

    def test_audit_summary_keeps_only_jira_resource_identity(self):
        self.assertEqual(
            _resource_summary(
                {
                    "project": "SL",
                    "query": "secret search text",
                    "max_results": 10,
                }
            ),
            {"project": "SL"},
        )


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
class JiraPluginIntegrationTests(TestCase):
    """Verify Jira connections, datasources, and execution snapshots."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="jira-plugin-admin",
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.node = LensNode.objects.create(
            name="Jira node",
            workspace_path="/workspace",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            tasks=[{"name": "general_chat"}],
        )

    def _create_connection(self):
        response = self.client.post(
            "/api/lens/admin/connections/",
            {
                "name": "Jira Cloud readonly",
                "plugin_key": "jira",
                "endpoint": "https://company.atlassian.net/",
                "config": {"email": "admin@example.com"},
                "allowed_scope": {"projects": ["sl"]},
                "secret_value": "jira-api-token",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return Connection.objects.get(uuid=response.data["uuid"])

    def test_api_creates_jira_datasource_and_snapshot_without_secret(self):
        connection = self._create_connection()
        response = self.client.post(
            "/api/lens/admin/datasources/",
            {
                "name": "Jira issues",
                "source_type": "jira",
                "lensnode_uuid": str(self.node.uuid),
                "connection_uuid": str(connection.uuid),
                "plugin_key": "jira",
                "datasource_config": {"project": "sl", "max_issues": 50},
                "config": {},
                "sync_policy": {},
                "target_path": "/workspace/jira",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        datasource = DataSource.objects.get(uuid=response.data["uuid"])
        snapshot = create_datasource_sync_snapshot(datasource)

        self.assertEqual(datasource.source_type, DataSource.SourceType.JIRA)
        self.assertEqual(
            snapshot.resolved_config["connection_config"],
            {"email": "admin@example.com"},
        )
        self.assertNotIn("jira-api-token", str(snapshot.resolved_config))

    def test_jira_tool_snapshot_accepts_non_repository_read_capability(self):
        connection = self._create_connection()
        assistant = Assistant.objects.create(
            name="Jira Assistant",
            slug="jira-tool-assistant",
            lensnode=self.node,
            selected_task="general_chat",
            visibility=Assistant.Visibility.PUBLIC,
        )
        AssistantPluginBinding.objects.create(
            assistant=assistant,
            connection=connection,
            tools=["jira_get_issue", "jira_search_issues"],
        )
        session = Session.objects.create(
            assistant=assistant,
            user=self.admin,
        )
        run = create_execution_run(session, "Read Jira", enqueue=False)
        run.status = Run.Status.STREAMING
        run.save(update_fields=["status"])

        response = APIClient().post(
            "/api/lens/plugin-runtime/tool-snapshots/",
            {
                "run_uuid": str(run.uuid),
                "connection_uuid": str(connection.uuid),
                "tool_key": "jira_get_issue",
                "call_id": "jira-call-1",
                "arguments": {"issue_key": "SL-488"},
            },
            format="json",
            HTTP_AUTHORIZATION=(
                f"Bearer {issue_lensnode_token(self.node)}"
            ),
        )

        self.assertEqual(response.status_code, 201, response.data)
        snapshot = ExecutionSnapshot.objects.get(
            uuid=response.data["snapshot_uuid"]
        )
        self.assertEqual(snapshot.resolved_config["connection_config"], {
            "email": "admin@example.com",
        })
