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
    Session,
    Run,
)
from lens.plugins.providers.base import (
    DatasourceProviderError,
)
from lens.plugins.providers import get_datasource_provider
from lens.plugins.registry import installed_plugin
from lens.plugins.tool_providers import ToolProviderError, get_tool_provider
from lens.plugins.tool_snapshots import _resource_summary
from lens.services import create_execution_run
from rest_framework.test import APIClient


class JiraPluginManifestTests(TestCase):
    """Verify the bundled Jira Plugin contract is installed."""

    def test_bundled_jira_plugin_is_discoverable(self):
        plugin = installed_plugin("jira")

        self.assertEqual(plugin.version, "1.0.0")
        self.assertEqual(plugin.display_name, "Jira")
        self.assertIsNone(plugin.datasource_source_type)
        self.assertIsNone(plugin.datasource)
        self.assertIsNone(plugin.datasource_schema)
        self.assertEqual(
            [tool.key for tool in plugin.tools],
            [
                "jira_get_issue",
                "jira_search_issues",
                "jira_activity_summary",
            ],
        )


class JiraConnectionProviderTests(SimpleTestCase):
    """Verify Jira implements the Connection Provider contract."""

    def setUp(self):
        self.provider = get_datasource_provider("jira")
        self.config = {"email": "admin@example.com"}
        self.scope = {"projects": ["SL", "OPS"]}

    def test_accepts_cloud_and_self_hosted_root_endpoints(self):
        endpoints = {
            "https://company.atlassian.net/": (
                "https://company.atlassian.net"
            ),
            "http://office.oneprocloud.com.cn:9005/": (
                "http://office.oneprocloud.com.cn:9005"
            ),
        }

        for endpoint, expected in endpoints.items():
            with self.subTest(endpoint=endpoint):
                self.assertEqual(
                    self.provider.validate_connection(endpoint, self.config),
                    expected,
                )

        for endpoint in [
            "ftp://jira.internal.example",
            "https://company.atlassian.net/wiki",
            "https://user@jira.internal.example",
        ]:
            with self.subTest(endpoint=endpoint):
                with self.assertRaisesMessage(
                    DatasourceProviderError,
                    "endpoint",
                ):
                    self.provider.validate_connection(endpoint, self.config)

    def test_accepts_account_without_email_format(self):
        endpoint = self.provider.validate_connection(
            "https://company.atlassian.net",
            {"email": "jira-admin"},
        )

        self.assertEqual(endpoint, "https://company.atlassian.net")

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

    def test_self_hosted_validation_uses_v2_api(self):
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(
                200,
                json={"name": "jira-admin", "displayName": "Admin"},
                request=request,
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = self.provider.validate_live_connection(
                "api-token",
                endpoint="http://office.oneprocloud.com.cn:9005",
                connection_config={"email": "jira-admin"},
                client=client,
            )

        self.assertEqual(
            seen,
            [
                "http://office.oneprocloud.com.cn:9005/"
                "rest/api/2/myself"
            ],
        )
        self.assertEqual(result["account"]["account_id"], "jira-admin")

    def test_discovers_projects_visible_on_self_hosted_jira(self):
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(
                200,
                json=[
                    {"key": "SL", "name": "SourceLens"},
                    {"key": "OPS", "name": "Operations"},
                ],
                request=request,
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            resources = self.provider.discover_connection_resources(
                "api-token",
                endpoint="http://office.oneprocloud.com.cn:9005",
                connection_config={"email": "jira-admin"},
                query="source",
                limit=50,
                client=client,
            )

        self.assertEqual(
            seen,
            ["http://office.oneprocloud.com.cn:9005/rest/api/2/project"],
        )
        self.assertEqual(
            resources["resources"]["projects"]["items"],
            [
                {
                    "value": "SL",
                    "label": "SL · SourceLens",
                    "metadata": {"name": "SourceLens"},
                }
            ],
        )

    def test_discovers_projects_visible_on_jira_cloud(self):
        seen = {}

        def handler(request):
            seen["path"] = request.url.path
            seen["params"] = dict(request.url.params)
            return httpx.Response(
                200,
                json={
                    "values": [{"key": "SL", "name": "SourceLens"}],
                    "isLast": True,
                },
                request=request,
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            resources = self.provider.discover_connection_resources(
                "api-token",
                endpoint="https://company.atlassian.net",
                connection_config=self.config,
                query="source",
                limit=25,
                client=client,
            )

        self.assertEqual(seen["path"], "/rest/api/3/project/search")
        self.assertEqual(seen["params"]["query"], "source")
        self.assertEqual(resources["next_cursor"], "")


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

    def test_activity_summary_accepts_only_allowed_projects(self):
        endpoint, arguments = self.provider.validate_request(
            "https://company.atlassian.net",
            {"projects": ["SL", "OPS"]},
            "jira_activity_summary",
            {
                "projects": ["ops", "SL"],
                "since": "2026-09-01T16:00:00Z",
                "until": "2026-09-02T15:59:59Z",
                "max_results": 50,
            },
        )

        self.assertEqual(endpoint, "https://company.atlassian.net")
        self.assertEqual(arguments["projects"], ["OPS", "SL"])

        with self.assertRaisesMessage(ToolProviderError, "scope"):
            self.provider.validate_request(
                endpoint,
                {"projects": ["SL"]},
                "jira_activity_summary",
                {
                    "projects": ["OPS"],
                    "since": "2026-09-01T16:00:00Z",
                    "until": "2026-09-02T15:59:59Z",
                },
            )

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

        self.assertEqual(
            _resource_summary(
                {
                    "projects": ["SL", "OPS"],
                    "since": "2026-09-01T16:00:00Z",
                    "until": "2026-09-02T15:59:59Z",
                }
            ),
            {"projects": ["SL", "OPS"]},
        )


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
class JiraPluginIntegrationTests(TestCase):
    """Verify Jira Connections and Tool execution snapshots."""

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

    def test_api_rejects_jira_datasource(self):
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

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(
            response.data["plugin_key"][0],
            "Plugin does not support datasources",
        )

    def test_manifest_exposes_jira_as_tool_only(self):
        response = self.client.get(
            "/api/lens/admin/plugins/jira/manifest/"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["datasource_source_type"])
        self.assertIsNone(response.data["datasource"])
        self.assertIsNone(response.data["datasource_schema"])
        self.assertEqual(
            [tool["key"] for tool in response.data["tools"]],
            [
                "jira_get_issue",
                "jira_search_issues",
                "jira_activity_summary",
            ],
        )

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
