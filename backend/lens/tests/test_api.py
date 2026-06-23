from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from agentcore_metering.adapters.django.models import LLMConfig
from agentcore_task.adapters.django.models import TaskExecution

from lens.lensnode_auth import hash_lensnode_token
from lens.models import (
    Assistant,
    AssistantAccess,
    AssistantSkill,
    DataSource,
    DataSourceCredential,
    GlobalSetting,
    LensNode,
    MCPServer,
    ScheduledTask,
    SharedQA,
    Skill,
)
from lens.tasks import acquire_datasource_lock, release_datasource_lock

User = get_user_model()

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
}

TEST_CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}


async def _collect_async_stream(streaming_content, limit=None):
    """Collect bytes from an async streaming response."""

    chunks = []
    count = 0
    async for chunk in streaming_content:
        chunks.append(chunk)
        count += 1
        if limit is not None and count >= limit:
            break
    return b"".join(chunks)


def collect_stream(streaming_content, limit=None):
    """Collect bytes from sync or async streaming response content."""

    if hasattr(streaming_content, "__aiter__"):
        return async_to_sync(_collect_async_stream)(streaming_content, limit)

    chunks = []
    for count, chunk in enumerate(streaming_content, start=1):
        chunks.append(chunk)
        if limit is not None and count >= limit:
            break
    return b"".join(chunks)


def bearer_header(user):
    """Return an Authorization header for native Django streaming views."""

    return f"Bearer {AccessToken.for_user(user)}"


@override_settings(CACHES=TEST_CACHES, CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class LensApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="lens-admin",
            email="lens-admin@example.com",
            password="pass12345",
            is_staff=True,
        )
        self.client.force_authenticate(self.user)
        self.lensnode = LensNode.objects.create(
            name="Local LensNode",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            workspace_path="/workspace",
            available_dirs=[{"path": "/workspace/repo"}],
            tasks=[
                {
                    "name": "knowledge_qa",
                    "description": "Answer code questions",
                }
            ],
        )
        self.assistant = Assistant.objects.create(
            name="Code Advisor",
            slug="code-advisor",
            lensnode=self.lensnode,
            selected_task="knowledge_qa",
            selected_dirs=[
                {
                    "path": "/workspace/repo",
                    "retrieval_scope": {"include_paths": ["backend/**"]},
                }
            ],
        )
        self.datasource = DataSource.objects.create(
            name="Repo Cache",
            source_type="git",
            lensnode=self.lensnode,
            config={"repo_url": "https://example.com/repo.git"},
            sync_policy={"interval_seconds": 3600},
            target_path="/workspace/repo-cache",
        )
        self.skill = Skill.objects.create(
            name="Code Search",
            slug="code-search",
            definition={"summary": "Search code"},
        )
        self.mcp = MCPServer.objects.create(
            name="GitHub MCP",
            transport="url",
            endpoint="https://mcp.example.com/github",
        )

    def test_assistant_create_saves_lensnode_and_bindings(self):
        payload = {
            "name": "API Explorer",
            "slug": "api-explorer",
            "lensnode_uuid": str(self.lensnode.uuid),
            "selected_task": "knowledge_qa",
            "selected_dirs": [{"path": "/workspace/repo"}],
            "skill_bindings": [
                {
                    "skill_uuid": str(self.skill.uuid),
                    "enabled": True,
                    "load_config": {"mode": "read-only"},
                },
            ],
            "mcp_bindings": [
                {
                    "mcp_uuid": str(self.mcp.uuid),
                    "enabled": True,
                    "load_config": {"stream": True},
                },
            ],
        }

        response = self.client.post(
            "/api/lens/assistants/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        assistant = Assistant.objects.get(slug="api-explorer")
        self.assertEqual(assistant.lensnode, self.lensnode)
        self.assertEqual(assistant.selected_task, "knowledge_qa")
        self.assertEqual(assistant.skill_bindings.count(), 1)
        self.assertEqual(assistant.mcp_bindings.count(), 1)
        self.assertEqual(
            assistant.settings["_model_check"]["agent_model_ref"]["status"],
            "skipped",
        )

    def test_assistant_create_saves_workspace_guide_skill(self):
        payload = {
            "name": "Workspace Aware",
            "slug": "workspace-aware",
            "lensnode_uuid": str(self.lensnode.uuid),
            "selected_task": "knowledge_qa",
            "selected_dirs": [{"path": "/workspace/repo"}],
            "workspace_guide": {
                "enabled": True,
                "content": "- repo is the primary application repository.",
            },
        }

        response = self.client.post(
            "/api/lens/assistants/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        assistant = Assistant.objects.get(slug="workspace-aware")
        binding = AssistantSkill.objects.get(
            assistant=assistant,
            skill__slug="workspace-aware-workspace-guide",
        )
        self.assertTrue(binding.enabled)
        self.assertEqual(
            binding.load_config,
            {"mode": "context", "inject": True},
        )
        self.assertIn(
            "repo is the primary application repository",
            binding.skill.definition["content"],
        )
        self.assertTrue(response.data["workspace_guide"]["enabled"])

    def test_assistant_update_disables_workspace_guide_binding(self):
        create_response = self.client.post(
            "/api/lens/assistants/",
            {
                "name": "Workspace Aware",
                "slug": "workspace-aware",
                "lensnode_uuid": str(self.lensnode.uuid),
                "selected_task": "knowledge_qa",
                "selected_dirs": [{"path": "/workspace/repo"}],
                "workspace_guide": {
                    "enabled": True,
                    "content": "- repo is primary.",
                },
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)

        response = self.client.patch(
            f"/api/lens/assistants/{create_response.data['uuid']}/",
            {
                "workspace_guide": {
                    "enabled": False,
                    "content": "",
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        binding = AssistantSkill.objects.get(
            assistant__uuid=create_response.data["uuid"],
            skill__slug="workspace-aware-workspace-guide",
        )
        self.assertFalse(binding.enabled)

    def test_global_setting_accepts_skill_generator_model_ref(self):
        response = self.client.post(
            "/api/lens/admin/global-settings/",
            {
                "key": "lens.skills.generator_model_ref",
                "value": "016d5cf7-2245-4015-b242-d6323e795b58",
                "description": "Skill generator model",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        setting = GlobalSetting.objects.get(
            key="lens.skills.generator_model_ref",
        )
        self.assertEqual(
            setting.value,
            "016d5cf7-2245-4015-b242-d6323e795b58",
        )

    def test_skill_beautify_requires_generator_model(self):
        response = self.client.post(
            "/api/lens/admin/skills/beautify/",
            {"name": "Demo", "content": "draft"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    @patch("lens.skill_generation.run_completion")
    def test_skill_beautify_returns_polished_content(self, mock_run):
        GlobalSetting.objects.create(
            key="lens.skills.generator_model_ref",
            value="016d5cf7-2245-4015-b242-d6323e795b58",
        )
        mock_run.return_value = type(
            "Result", (), {"content": "```markdown\n# Polished\n```"}
        )()

        response = self.client.post(
            "/api/lens/admin/skills/beautify/",
            {"name": "Demo", "content": "rough draft"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["content"], "# Polished")
        _, kwargs = mock_run.call_args
        self.assertEqual(
            kwargs["model_ref"],
            "016d5cf7-2245-4015-b242-d6323e795b58",
        )
        self.assertEqual(kwargs["node_name"], "lens.skill_beautify")

    def test_assistant_create_rejects_unreported_task(self):
        payload = {
            "name": "Bad Task",
            "slug": "bad-task",
            "lensnode_uuid": str(self.lensnode.uuid),
            "selected_task": "unknown",
            "selected_dirs": [{"path": "/workspace/repo"}],
        }

        response = self.client.post(
            "/api/lens/assistants/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("selected_task", response.data)

    def test_assistant_create_rejects_unreported_dir(self):
        payload = {
            "name": "Bad Dir",
            "slug": "bad-dir",
            "lensnode_uuid": str(self.lensnode.uuid),
            "selected_task": "knowledge_qa",
            "selected_dirs": [{"path": "/workspace/missing"}],
        }

        response = self.client.post(
            "/api/lens/assistants/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("selected_dirs", str(response.data))

    def test_assistant_model_check_uses_agent_model_ref(self):
        config = LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            user=None,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"model": "gpt-test", "api_key": "test-key"},
            is_active=False,
        )

        response = self.client.patch(
            f"/api/lens/assistants/{self.assistant.uuid}/",
            {"agent_model_ref": str(config.uuid)},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        check = response.data["settings"]["_model_check"]
        self.assertEqual(check["agent_model_ref"]["status"], "error")
        self.assertIn("inactive", check["agent_model_ref"]["error"])

    def test_lensnode_issue_and_revoke_token(self):
        response = self.client.post(
            f"/api/lens/admin/lensnodes/{self.lensnode.uuid}/issue-token/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["token"])

        revoke_response = self.client.post(
            f"/api/lens/admin/lensnodes/{self.lensnode.uuid}/revoke-token/"
        )
        self.assertEqual(revoke_response.status_code, 200)
        self.lensnode.refresh_from_db()
        self.assertTrue(self.lensnode.token_revoked)
        self.assertEqual(self.lensnode.status, LensNode.Status.OFFLINE)

    def test_lensnode_ai_gateway_uses_lensnode_bearer_token(self):
        token = "dev-lensnode-token"
        self.lensnode.auth_token_hash = hash_lensnode_token(token)
        self.lensnode.save(update_fields=["auth_token_hash", "updated_at"])
        client = APIClient()

        with patch(
            "agentcore_metering.adapters.django.LLMTracker.call_and_track",
            return_value=("ok", {"total_tokens": 1}),
        ):
            response = client.post(
                "/api/lens/lensnode/ai-gateway/",
                {
                    "model_ref": "016d5cf7-2245-4015-b242-d6323e795b58",
                    "messages": [{"role": "user", "content": "hello"}],
                },
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["content"], "ok")
        self.assertEqual(
            response.data["lensnode_uuid"],
            str(self.lensnode.uuid),
        )

    def test_lensnode_ai_gateway_supports_tool_calling_payload(self):
        token = "dev-lensnode-token"
        self.lensnode.auth_token_hash = hash_lensnode_token(token)
        self.lensnode.save(update_fields=["auth_token_hash", "updated_at"])
        client = APIClient()
        message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "search_workspace",
                        "arguments": "{\"query\":\"test\"}",
                    },
                }
            ],
        }
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_workspace",
                    "parameters": {"type": "object"},
                },
            }
        ]

        with patch(
            "agentcore_metering.adapters.django.LLMTracker.call_and_track",
            return_value=(message, {"total_tokens": 1}),
        ) as call_and_track:
            response = client.post(
                "/api/lens/lensnode/ai-gateway/",
                {
                    "model_ref": "016d5cf7-2245-4015-b242-d6323e795b58",
                    "messages": [{"role": "user", "content": "hello"}],
                    "tools": tools,
                    "tool_choice": "auto",
                    "return_message": True,
                },
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["message"]["tool_calls"][0]["id"],
            "call_1",
        )
        self.assertEqual(response.data["content"], "")
        self.assertEqual(call_and_track.call_args.kwargs["tools"], tools)
        self.assertEqual(
            call_and_track.call_args.kwargs["tool_choice"],
            "auto",
        )
        self.assertTrue(call_and_track.call_args.kwargs["return_message"])

    def test_session_run_flow_returns_completed_run_with_execution(self):
        session_response = self.client.post(
            "/api/lens/sessions/",
            {
                "assistant_uuid": str(self.assistant.uuid),
                "title": "Search code flow",
            },
            format="json",
        )
        self.assertEqual(session_response.status_code, 201)
        session_uuid = session_response.data["uuid"]

        run_response = self.client.post(
            f"/api/lens/sessions/{session_uuid}/runs/",
            {
                "question": "How does SSE work?",
                "idempotency_key": "run-1",
                "run_inline": True,
            },
            format="json",
        )

        self.assertEqual(run_response.status_code, 201)
        self.assertEqual(run_response.data["status"], "done")
        self.assertEqual(run_response.data["execution"]["task"], "knowledge_qa")
        self.assertEqual(
            run_response.data["execution"]["target_dirs"][0]["path"],
            "/workspace/repo",
        )

        stream_response = self.client.get(
            f"/api/lens/runs/{run_response.data['uuid']}/stream/",
            HTTP_AUTHORIZATION=bearer_header(self.user),
        )
        self.assertEqual(stream_response.status_code, 200)
        body = collect_stream(stream_response.streaming_content).decode()
        self.assertIn('"type": "sync"', body)
        self.assertIn('"type": "done"', body)

    def test_run_stream_accepts_event_stream_header(self):
        session_response = self.client.post(
            "/api/lens/sessions/",
            {"assistant_uuid": str(self.assistant.uuid)},
            format="json",
        )
        run_response = self.client.post(
            f"/api/lens/sessions/{session_response.data['uuid']}/runs/",
            {
                "question": "What changed?",
                "idempotency_key": "run-event-stream",
                "run_inline": True,
            },
            format="json",
        )

        stream_response = self.client.get(
            f"/api/lens/runs/{run_response.data['uuid']}/stream/",
            HTTP_ACCEPT="text/event-stream",
            HTTP_AUTHORIZATION=bearer_header(self.user),
        )

        self.assertEqual(stream_response.status_code, 200)
        self.assertTrue(
            stream_response["Content-Type"].startswith("text/event-stream")
        )

    def test_run_detail_is_scoped_to_session_owner(self):
        session_response = self.client.post(
            "/api/lens/sessions/",
            {"assistant_uuid": str(self.assistant.uuid)},
            format="json",
        )
        session_uuid = session_response.data["uuid"]
        run_response = self.client.post(
            f"/api/lens/sessions/{session_uuid}/runs/",
            {
                "question": "How does SSE work?",
                "idempotency_key": "run-private",
                "run_inline": True,
            },
            format="json",
        )

        other_user = User.objects.create_user(
            username="lens-user-2",
            email="lens-user-2@example.com",
            password="pass12345",
        )
        self.client.force_authenticate(other_user)

        response = self.client.get(
            f"/api/lens/runs/{run_response.data['uuid']}/"
        )

        self.assertEqual(response.status_code, 404)

    def test_running_run_can_be_cancelled(self):
        session_response = self.client.post(
            "/api/lens/sessions/",
            {"assistant_uuid": str(self.assistant.uuid)},
            format="json",
        )
        session_uuid = session_response.data["uuid"]
        run_response = self.client.post(
            f"/api/lens/sessions/{session_uuid}/runs/",
            {
                "question": "How does cancellation work?",
                "idempotency_key": "run-running",
                "enqueue": False,
            },
            format="json",
        )

        self.assertEqual(run_response.status_code, 201)
        self.assertEqual(run_response.data["status"], "queued")

        cancel_response = self.client.post(
            f"/api/lens/runs/{run_response.data['uuid']}/cancel/"
        )

        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.data["status"], "cancelled")

    def test_running_run_stream_returns_sync_and_status(self):
        session_response = self.client.post(
            "/api/lens/sessions/",
            {"assistant_uuid": str(self.assistant.uuid)},
            format="json",
        )
        session_uuid = session_response.data["uuid"]
        run_response = self.client.post(
            f"/api/lens/sessions/{session_uuid}/runs/",
            {
                "question": "How does streaming work?",
                "idempotency_key": "run-streaming",
                "enqueue": False,
            },
            format="json",
        )

        stream_response = self.client.get(
            f"/api/lens/runs/{run_response.data['uuid']}/stream/",
            HTTP_AUTHORIZATION=bearer_header(self.user),
        )
        body = collect_stream(stream_response.streaming_content, limit=2).decode()

        self.assertIn('"type": "sync"', body)
        self.assertIn('"type": "status"', body)

    def test_datasource_create_uses_target_path(self):
        payload = {
            "name": "Scheduled Repo",
            "source_type": "git",
            "lensnode_uuid": str(self.lensnode.uuid),
            "config": {"repo_url": "https://example.com/repo.git"},
            "sync_policy": {"interval_seconds": 120},
            "target_path": "/workspace/scheduled",
        }

        response = self.client.post(
            "/api/lens/admin/datasources/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["target_path"],
            "/workspace/scheduled",
        )

    def test_datasource_create_enqueues_initial_sync(self):
        payload = {
            "name": "Initial Sync Repo",
            "source_type": "git",
            "lensnode_uuid": str(self.lensnode.uuid),
            "config": {"repo_url": "https://example.com/repo.git"},
            "target_path": "/workspace/initial-sync",
        }

        with patch("lens.views.source_sync_task.apply_async") as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    "/api/lens/admin/datasources/",
                    payload,
                    format="json",
                )

        self.assertEqual(response.status_code, 201)
        task_id = response.data["initial_sync_task_id"]
        apply_async.assert_called_once_with(
            args=[response.data["uuid"], "initial"],
            task_id=task_id,
        )
        task = TaskExecution.objects.get(task_id=task_id)
        self.assertEqual(task.task_name, "datasource_sync:Initial Sync Repo")
        self.assertEqual(task.module, "lens_datasource")
        self.assertEqual(task.status, "PENDING")
        self.assertEqual(task.created_by, self.user)

    def test_datasource_manual_sync_registers_task(self):
        with patch("lens.views.source_sync_task.apply_async") as apply_async:
            response = self.client.post(
                f"/api/lens/admin/datasources/{self.datasource.uuid}/sync/",
                {},
                format="json",
            )

        self.assertEqual(response.status_code, 202)
        task_id = response.data["task_id"]
        self.assertEqual(
            response.data["task_execution_id"],
            TaskExecution.objects.get(task_id=task_id).id,
        )
        apply_async.assert_called_once_with(
            args=[str(self.datasource.uuid), "manual"],
            task_id=task_id,
        )
        task = TaskExecution.objects.get(task_id=task_id)
        self.assertEqual(task.task_name, "datasource_sync:Repo Cache")
        self.assertEqual(task.module, "lens_datasource")
        self.assertEqual(task.status, "PENDING")
        self.assertEqual(task.created_by, self.user)

    def test_disabled_datasource_rejects_manual_sync(self):
        self.datasource.status = DataSource.Status.DISABLED
        self.datasource.save(update_fields=["status", "updated_at"])

        with patch("lens.views.source_sync_task.apply_async") as apply_async:
            response = self.client.post(
                f"/api/lens/admin/datasources/{self.datasource.uuid}/sync/",
                {},
                format="json",
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["detail"], "DATASOURCE_DISABLED")
        apply_async.assert_not_called()

    def test_cancel_datasource_sync_releases_lock(self):
        task = TaskExecution.objects.create(
            task_id="running-sync",
            task_name="datasource_sync:Repo Cache",
            module="lens_datasource",
            status="STARTED",
            metadata={
                "datasource_uuid": str(self.datasource.uuid),
                "lock_token": "running-sync",
            },
        )
        acquire_datasource_lock(
            self.datasource.uuid,
            token="running-sync",
            ttl_s=60,
        )

        with (
            patch("core.celery.app.control.revoke") as revoke,
            patch("lens.views.cancel_datasource_sync_on_lensnode") as cancel,
        ):
            url = (
                f"/api/lens/admin/datasources/{self.datasource.uuid}"
                "/cancel-sync/"
            )
            response = self.client.post(
                url,
                {},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        revoke.assert_called_once_with(
            "running-sync",
            terminate=True,
            signal="SIGTERM",
        )
        cancel.assert_called_once_with(self.lensnode, "running-sync")
        task.refresh_from_db()
        self.assertEqual(task.status, "REVOKED")

        acquire_datasource_lock(
            self.datasource.uuid,
            token="new-sync",
            ttl_s=60,
        )
        release_datasource_lock(self.datasource.uuid, token="new-sync")

    def test_datasource_create_uses_lensnode_workspace_path(self):
        self.lensnode.workspace_path = "/data/lens-workspace"
        self.lensnode.save(update_fields=["workspace_path", "updated_at"])
        payload = {
            "name": "Custom Workspace Repo",
            "source_type": "git",
            "lensnode_uuid": str(self.lensnode.uuid),
            "config": {"repo_url": "https://example.com/repo.git"},
            "target_path": "repos/custom",
        }

        response = self.client.post(
            "/api/lens/admin/datasources/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["target_path"],
            "/data/lens-workspace/repos/custom",
        )

    def test_datasource_create_rejects_path_outside_lensnode_workspace(self):
        self.lensnode.workspace_path = "/data/lens-workspace"
        self.lensnode.save(update_fields=["workspace_path", "updated_at"])
        payload = {
            "name": "Outside Workspace Repo",
            "source_type": "git",
            "lensnode_uuid": str(self.lensnode.uuid),
            "config": {"repo_url": "https://example.com/repo.git"},
            "target_path": "/workspace/old-root",
        }

        response = self.client.post(
            "/api/lens/admin/datasources/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("LENS_SOURCE_TARGET_PATH_INVALID", str(response.data))

    def test_datasource_rejects_inline_credentials(self):
        payload = {
            "name": "Secret Repo",
            "source_type": "git",
            "lensnode_uuid": str(self.lensnode.uuid),
            "config": {
                "repo_url": "https://example.com/repo.git",
                "token": "secret",
            },
            "target_path": "/workspace/secret",
        }

        response = self.client.post(
            "/api/lens/admin/datasources/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("secret fields", str(response.data))

    def test_datasource_allows_git_credential_binding(self):
        credential = DataSourceCredential.objects.create(
            name="Git token",
            provider=DataSourceCredential.Provider.GENERIC,
            auth_type=DataSourceCredential.AuthType.HTTPS_TOKEN,
        )
        credential.set_secret("ghp_example")
        credential.save()
        payload = {
            "name": "Token Repo",
            "source_type": "git",
            "lensnode_uuid": str(self.lensnode.uuid),
            "credential_uuid": str(credential.uuid),
            "config": {
                "repo_url": "https://example.com/repo.git",
                "auth_scheme": "token",
            },
            "target_path": "/workspace/token-repo",
        }

        response = self.client.post(
            "/api/lens/admin/datasources/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["credential_configured"])
        self.assertNotIn("access_token", response.data["config"])
        datasource = DataSource.objects.get(uuid=response.data["uuid"])
        self.assertNotIn("access_token", datasource.config)
        self.assertEqual(datasource.credential, credential)

    def test_datasource_allows_feishu_drive_folder_credential_binding(self):
        credential = DataSourceCredential.objects.create(
            name="Feishu app",
            provider=DataSourceCredential.Provider.FEISHU,
            auth_type=DataSourceCredential.AuthType.FEISHU_APP,
        )
        credential.set_secret("cli_example:secret_example")
        credential.save()
        payload = {
            "name": "Feishu Folder",
            "source_type": "feishu",
            "lensnode_uuid": str(self.lensnode.uuid),
            "credential_uuid": str(credential.uuid),
            "config": {
                "sync_mode": "drive_folder",
                "folder_url": "https://example.feishu.cn/drive/folder/fld1",
                "recursive": True,
                "max_depth": 5,
            },
            "target_path": "/workspace/feishu-folder",
        }

        response = self.client.post(
            "/api/lens/admin/datasources/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["credential_configured"])
        self.assertNotIn("app_id", response.data["config"])
        self.assertNotIn("app_secret", response.data["config"])
        datasource = DataSource.objects.get(uuid=response.data["uuid"])
        self.assertNotIn("app_id", datasource.config)
        self.assertNotIn("app_secret", datasource.config)
        self.assertEqual(datasource.credential, credential)

    def test_lensnode_tests_datasource_connection(self):
        with patch(
            "lens.views.test_datasource_connection",
            return_value={
                "status": "success",
                "message_code": "git_branch_available",
            },
        ) as test_connection:
            response = self.client.post(
                (
                    "/api/lens/admin/lensnodes/"
                    f"{self.lensnode.uuid}/test-datasource-connection/"
                ),
                {
                    "source_type": "git",
                    "config": {
                        "repo_url": "https://example.com/repo.git",
                        "branch": "main",
                    },
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["message_code"], "git_branch_available")
        test_connection.assert_called_once()

    def test_system_health_returns_node_and_retention_tasks(self):
        ScheduledTask.objects.create(
            name="lensnode_cleanup",
            task_type="lensnode_cleanup",
            enabled=True,
        )
        ScheduledTask.objects.create(
            name="lensnode_health",
            task_type="lensnode_health",
            enabled=True,
        )

        response = self.client.get(
            "/api/lens/admin/global-settings/system-health/"
        )

        self.assertEqual(response.status_code, 200)
        task_types = {item["task_type"] for item in response.data}
        self.assertIn("lensnode_cleanup", task_types)
        self.assertIn("lensnode_health", task_types)

    def test_system_health_patch_updates_enabled_state(self):
        task = ScheduledTask.objects.create(
            name="lensnode_cleanup",
            task_type="lensnode_cleanup",
            enabled=True,
        )

        response = self.client.patch(
            "/api/lens/admin/global-settings/system-health/",
            {
                "task_type": "lensnode_cleanup",
                "enabled": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertFalse(task.enabled)
        self.assertFalse(response.data["enabled"])

    def test_global_setting_interval_syncs_periodic_task(self):
        from django_celery_beat.models import PeriodicTask

        response = self.client.patch(
            "/api/lens/admin/global-settings/"
            "lensnode_cleanup.interval_seconds/",
            {
                "key": "lensnode_cleanup.interval_seconds",
                "value": 7200,
                "description": "Cleanup interval",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        task = PeriodicTask.objects.get(name="lens-lensnode-cleanup")
        self.assertEqual(task.interval.every, 7200)
        self.assertEqual(task.interval.period, "seconds")


class AssistantAccessTests(TestCase):
    """Visibility + group/user authorization for assistants and QA."""

    def setUp(self):
        self.lensnode = LensNode.objects.create(
            name="Node",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            workspace_path="/workspace",
            available_dirs=[{"path": "/workspace/repo"}],
            tasks=[{"name": "knowledge_qa", "description": "qa"}],
        )
        self.assistant = Assistant.objects.create(
            name="Private One",
            slug="private-one",
            lensnode=self.lensnode,
            selected_task="knowledge_qa",
            selected_dirs=[{"path": "/workspace/repo"}],
            status=Assistant.Status.ACTIVE,
            visibility=Assistant.Visibility.PRIVATE,
        )
        self.admin = get_user_model().objects.create_user(
            username="aac-admin", password="x", is_staff=True
        )
        self.member = get_user_model().objects.create_user(
            username="aac-member", password="x"
        )

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_public_view_404_for_private_assistant(self):
        resp = self.client.get(
            f"/api/lens/public/assistants/{self.assistant.slug}/"
        )
        self.assertEqual(resp.status_code, 404)

    def test_public_view_200_when_public(self):
        self.assistant.visibility = Assistant.Visibility.PUBLIC
        self.assistant.save(update_fields=["visibility"])
        resp = self.client.get(
            f"/api/lens/public/assistants/{self.assistant.slug}/"
        )
        self.assertEqual(resp.status_code, 200)

    def test_list_hides_private_from_unauthorized_then_group_grant(self):
        client = self._client(self.member)
        slugs = [a["slug"] for a in client.get(
            "/api/lens/assistants/"
        ).data["results"]]
        self.assertNotIn(self.assistant.slug, slugs)

        group = Group.objects.create(name="team")
        self.member.groups.add(group)
        AssistantAccess.objects.create(assistant=self.assistant, group=group)

        slugs = [a["slug"] for a in client.get(
            "/api/lens/assistants/"
        ).data["results"]]
        self.assertIn(self.assistant.slug, slugs)

    def test_list_shows_private_to_admin(self):
        slugs = [a["slug"] for a in self._client(self.admin).get(
            "/api/lens/assistants/"
        ).data["results"]]
        self.assertIn(self.assistant.slug, slugs)

    def test_session_create_403_then_201_with_user_grant(self):
        client = self._client(self.member)
        payload = {"assistant_uuid": str(self.assistant.uuid)}
        resp = client.post("/api/lens/sessions/", payload, format="json")
        self.assertEqual(resp.status_code, 403)

        AssistantAccess.objects.create(
            assistant=self.assistant, user=self.member
        )
        resp = client.post("/api/lens/sessions/", payload, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_run_blocked_after_access_revoked(self):
        self.assistant.visibility = Assistant.Visibility.PUBLIC
        self.assistant.save(update_fields=["visibility"])
        client = self._client(self.member)
        session = client.post(
            "/api/lens/sessions/",
            {"assistant_uuid": str(self.assistant.uuid)},
            format="json",
        )
        self.assertEqual(session.status_code, 201)
        session_uuid = session.data["uuid"]

        self.assistant.visibility = Assistant.Visibility.PRIVATE
        self.assistant.save(update_fields=["visibility"])

        run = client.post(
            f"/api/lens/sessions/{session_uuid}/runs/",
            {"question": "still there?"},
            format="json",
        )
        self.assertEqual(run.status_code, 403)

    def test_public_qa_404_for_private_assistant(self):
        share = SharedQA.objects.create(
            token="tok-private",
            assistant=self.assistant,
            assistant_name=self.assistant.name,
            assistant_slug=self.assistant.slug,
            question="q",
            answer="a",
            title="t",
            is_listed=True,
            status=SharedQA.Status.PUBLISHED,
        )
        list_resp = self.client.get(
            f"/api/lens/public/assistants/{self.assistant.slug}/qa/"
        )
        self.assertEqual(list_resp.status_code, 404)
        single_resp = self.client.get(
            f"/api/lens/public/qa/{share.token}/"
        )
        self.assertEqual(single_resp.status_code, 404)

    def test_access_grants_round_trip_via_serializer(self):
        group = Group.objects.create(name="grp")
        client = self._client(self.admin)
        resp = client.patch(
            f"/api/lens/assistants/{self.assistant.uuid}/",
            {
                "visibility": "private",
                "access_grants": [{"type": "group", "id": group.pk}],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            self.assistant.access_grants.filter(group=group).count(), 1
        )
        grants = resp.data["access_grants"]
        self.assertEqual(grants, [
            {"type": "group", "id": group.pk, "name": "grp"}
        ])

    def test_write_requires_admin_console(self):
        self.assistant.visibility = Assistant.Visibility.PUBLIC
        self.assistant.save(update_fields=["visibility"])
        client = self._client(self.member)

        update = client.patch(
            f"/api/lens/assistants/{self.assistant.uuid}/",
            {"name": "Renamed"},
            format="json",
        )
        self.assertEqual(update.status_code, 403)

        create = client.post(
            "/api/lens/assistants/",
            {
                "name": "X",
                "slug": "x-new",
                "lensnode_uuid": str(self.lensnode.uuid),
                "selected_task": "knowledge_qa",
                "selected_dirs": [{"path": "/workspace/repo"}],
            },
            format="json",
        )
        self.assertEqual(create.status_code, 403)
