import hashlib
import io
import json
import tarfile
import tempfile
import threading
import uuid
import zipfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, patch

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.storage import default_storage, storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection
from django.test import (
    SimpleTestCase,
    TestCase,
    TransactionTestCase,
    override_settings,
)
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from agentcore_metering.adapters.django.models import LLMConfig, LLMUsage
from agentcore_task.adapters.django.models import TaskExecution

from accounts.models import Role
from lens.datasource_services import (
    DataSourceDispatchError,
    test_datasource_connection,
)
from lens.lensnode_auth import hash_lensnode_token
from lens.models import (
    Assistant,
    AssistantAccess,
    AssistantSkill,
    DataSource,
    DataSourceCredential,
    EnvironmentVariableSet,
    GlobalSetting,
    LensNode,
    MCPServer,
    MessageAttachment,
    Run,
    RunExecution,
    RunStep,
    ScheduledTask,
    Session,
    SharedQA,
    Skill,
)
from lens.serializers import (
    AssistantSerializer,
    validate_retrieval_policy,
    validate_retrieval_scope,
)
from lens.services import (
    LensNodeDispatchError,
    build_loaded_skills,
    create_execution_run,
    resolve_loaded_skill_environment,
    validate_run_dispatch,
)
from lens.skill_packages import package_zip_bytes
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


def skill_zip_upload(
    name,
    body,
    environment=None,
    api=None,
    artifacts=None,
    transforms=None,
    package_files=None,
):
    """Return an uploaded zip containing one SKILL.md."""

    buffer = io.BytesIO()
    skill_md = (
        "---\n"
        f"name: {name}\n"
        f"description: {name} description\n"
        "---\n"
        f"{body}\n"
    )
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{name}/SKILL.md", skill_md)
        for path, content in (package_files or {}).items():
            archive.writestr(f"{name}/{path}", content)
        if any(
            value is not None
            for value in (environment, api, artifacts, transforms)
        ):
            config = {}
            if environment is not None:
                config["environment"] = environment
            if api is not None:
                config["api"] = api
            if artifacts is not None:
                config["artifacts"] = artifacts
            if transforms is not None:
                config["transforms"] = transforms
            archive.writestr(
                f"{name}/sourcelens.json",
                json.dumps(config),
            )
    buffer.seek(0)
    return SimpleUploadedFile(
        f"{name}.zip",
        buffer.read(),
        content_type="application/zip",
    )


def skill_zip_upload_with_file(name, file_size):
    """Return a compressed Skill zip containing one generated package file."""

    buffer = io.BytesIO()
    skill_md = (
        "---\n"
        f"name: {name}\n"
        f"description: {name} description\n"
        "---\n"
        "Use the bundled executable.\n"
    )
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{name}/SKILL.md", skill_md)
        archive.writestr(f"{name}/bin/tool", b"\0" * file_size)
    buffer.seek(0)
    return SimpleUploadedFile(
        f"{name}.zip",
        buffer.read(),
        content_type="application/zip",
    )


def datasource_zip_upload(files, name="documents.zip"):
    """Return one datasource ZIP upload containing the requested members."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return SimpleUploadedFile(
        name,
        buffer.getvalue(),
        content_type="application/zip",
    )


def datasource_zip_many_members(member_count):
    """Return a ZIP with many empty members."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for index in range(member_count):
            archive.writestr(f"entry-{index}.txt", b"")
    return SimpleUploadedFile(
        "many.zip",
        buffer.getvalue(),
        content_type="application/zip",
    )


def datasource_tar_many_members(member_count):
    """Return a TAR.GZ with many empty members."""

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for index in range(member_count):
            archive.addfile(tarfile.TarInfo(f"entry-{index}.txt"))
    return SimpleUploadedFile(
        "many.tar.gz",
        buffer.getvalue(),
        content_type="application/gzip",
    )


class RetrievalPolicyValidationTests(SimpleTestCase):
    def test_hidden_file_retrieval_options_accept_booleans(self):
        self.assertEqual(
            validate_retrieval_scope({"include_hidden": True}),
            {"include_hidden": True},
        )
        self.assertEqual(
            validate_retrieval_policy({"include_hidden": False}),
            {"include_hidden": False},
        )

    def test_hidden_file_retrieval_options_reject_non_booleans(self):
        for value in ("true", None, 1):
            with self.subTest(scope_value=value):
                with self.assertRaisesRegex(
                    ValidationError,
                    "retrieval_scope.include_hidden must be a boolean",
                ):
                    validate_retrieval_scope({"include_hidden": value})

            with self.subTest(policy_value=value):
                with self.assertRaisesRegex(
                    ValidationError,
                    "settings.retrieval_policy.include_hidden must be "
                    "a boolean",
                ):
                    validate_retrieval_policy({"include_hidden": value})


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
                },
                {
                    "name": "general_chat",
                    "description": "Chat with bound Skills",
                },
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
            "description": "Explore API behavior and implementation.",
            "slug": "api-explorer",
            "lensnode_uuid": str(self.lensnode.uuid),
            "selected_task": "knowledge_qa",
            "selected_dirs": [{"path": "/workspace/repo"}],
            "token_budget_profile": "deep",
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
        self.assertEqual(assistant.token_budget_profile, "deep")
        self.assertEqual(response.data["token_budget_profile"], "deep")
        self.assertEqual(assistant.lensnode, self.lensnode)
        self.assertEqual(
            assistant.description,
            "Explore API behavior and implementation.",
        )
        self.assertEqual(response.data["description"], assistant.description)
        self.assertEqual(assistant.selected_task, "knowledge_qa")
        self.assertEqual(assistant.skill_bindings.count(), 1)
        self.assertEqual(assistant.mcp_bindings.count(), 1)
        self.assertEqual(
            assistant.settings["_model_check"]["agent_model_ref"]["status"],
            "skipped",
        )

    def test_assistant_create_accepts_unlimited_token_budget_profile(self):
        response = self.client.post(
            "/api/lens/assistants/",
            {
                "name": "Unlimited Budget",
                "slug": "unlimited-budget",
                "lensnode_uuid": str(self.lensnode.uuid),
                "selected_task": "knowledge_qa",
                "selected_dirs": [{"path": "/workspace/repo"}],
                "token_budget_profile": "unlimited",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        assistant = Assistant.objects.get(slug="unlimited-budget")
        self.assertEqual(assistant.token_budget_profile, "unlimited")
        self.assertEqual(response.data["token_budget_profile"], "unlimited")

    def test_assistant_update_saves_description(self):
        response = self.client.patch(
            f"/api/lens/assistants/{self.assistant.uuid}/",
            {"description": "Updated assistant description."},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assistant.refresh_from_db()
        self.assertEqual(
            self.assistant.description,
            "Updated assistant description.",
        )
        self.assertEqual(
            response.data["description"],
            "Updated assistant description.",
        )

    def test_assistant_serializer_rejects_non_boolean_hidden_options(self):
        scope_serializer = AssistantSerializer(
            self.assistant,
            data={
                "selected_dirs": [
                    {
                        "path": "/workspace/repo",
                        "retrieval_scope": {"include_hidden": "true"},
                    }
                ]
            },
            partial=True,
        )
        policy_serializer = AssistantSerializer(
            self.assistant,
            data={
                "settings": {
                    "retrieval_policy": {"include_hidden": "false"},
                }
            },
            partial=True,
        )

        self.assertFalse(scope_serializer.is_valid())
        self.assertFalse(policy_serializer.is_valid())
        self.assertIn("include_hidden", str(scope_serializer.errors))
        self.assertIn("include_hidden", str(policy_serializer.errors))

    def test_assistant_archive_moves_it_to_archived_list(self):
        response = self.client.post(
            f"/api/lens/assistants/{self.assistant.uuid}/archive/",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "archived")
        self.assistant.refresh_from_db()
        self.assertEqual(self.assistant.status, "archived")

        active_response = self.client.get("/api/lens/assistants/")
        active_slugs = [
            assistant["slug"] for assistant in active_response.data["results"]
        ]
        self.assertNotIn(self.assistant.slug, active_slugs)

        archived_response = self.client.get(
            "/api/lens/assistants/",
            {"archived": "true"},
        )
        archived_slugs = [
            assistant["slug"]
            for assistant in archived_response.data["results"]
        ]
        self.assertIn(self.assistant.slug, archived_slugs)

    def test_assistant_restore_returns_it_to_active_list(self):
        self.assistant.status = "archived"
        self.assistant.save(update_fields=["status"])

        response = self.client.post(
            f"/api/lens/assistants/{self.assistant.uuid}/restore/",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "active")
        self.assistant.refresh_from_db()
        self.assertEqual(self.assistant.status, "active")
        active_slugs = [
            assistant["slug"]
            for assistant in self.client.get(
                "/api/lens/assistants/"
            ).data["results"]
        ]
        self.assertIn(self.assistant.slug, active_slugs)

    def test_assistant_status_cannot_bypass_lifecycle_actions(self):
        response = self.client.patch(
            f"/api/lens/assistants/{self.assistant.uuid}/",
            {"status": "archived"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assistant.refresh_from_db()
        self.assertEqual(self.assistant.status, Assistant.Status.ACTIVE)

    def test_assistant_delete_is_not_available(self):
        response = self.client.delete(
            f"/api/lens/assistants/{self.assistant.uuid}/",
        )

        self.assertEqual(response.status_code, 405)
        self.assertTrue(
            Assistant.objects.filter(uuid=self.assistant.uuid).exists()
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

    def test_global_setting_list_returns_every_setting(self):
        GlobalSetting.objects.bulk_create(
            [
                GlobalSetting(
                    key=f"pagination.test.{index}",
                    value=index,
                )
                for index in range(11)
            ]
        )

        response = self.client.get("/api/lens/admin/global-settings/")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 11)

    def test_skill_beautify_requires_generator_model(self):
        response = self.client.post(
            "/api/lens/admin/skills/beautify/",
            {"name": "Demo", "content": "draft"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_manual_skill_allows_empty_environment_schema(self):
        response = self.client.post(
            "/api/lens/admin/skills/",
            {
                "name": "Jira Connector",
                "slug": "jira-connector",
                "definition": {"content": "Use Jira.", "environment": []},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            response.data["definition"]["environment"],
            [],
        )

    def test_manual_skill_update_accepts_legacy_definition_without_environment(
        self,
    ):
        legacy_skill = Skill.objects.create(
            name="Legacy Skill",
            slug="legacy-skill",
            definition={"content": "Old instructions."},
        )

        response = self.client.patch(
            f"/api/lens/admin/skills/{legacy_skill.uuid}/",
            {
                "definition": {
                    "content": "Updated instructions.",
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data["definition"],
            {
                "content": "Updated instructions.",
                "environment": [],
            },
        )

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

    def test_skill_delete_impact_and_force_delete_bound_skill(self):
        AssistantSkill.objects.create(
            assistant=self.assistant,
            skill=self.skill,
            enabled=True,
        )

        impact_response = self.client.get(
            f"/api/lens/admin/skills/{self.skill.uuid}/delete-impact/",
        )

        self.assertEqual(impact_response.status_code, 200)
        self.assertEqual(impact_response.data["bound_count"], 1)
        self.assertEqual(
            impact_response.data["bound_assistants"][0]["name"],
            self.assistant.name,
        )

        delete_response = self.client.post(
            f"/api/lens/admin/skills/{self.skill.uuid}/force-delete/",
            {"confirmation_name": self.skill.name},
            format="json",
        )

        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(Skill.objects.filter(pk=self.skill.pk).exists())
        self.assertFalse(
            AssistantSkill.objects.filter(assistant=self.assistant).exists()
        )

    def test_uploaded_skill_reads_environment_schema(self):
        environment = [
            {
                "name": "JIRA_API_TOKEN",
                "description": "Jira token",
                "required": True,
                "secret": True,
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    "/api/lens/admin/skills/upload/",
                    {
                        "file": skill_zip_upload(
                            "jira-connector",
                            "Use the Jira API.",
                            environment,
                        )
                    },
                    format="multipart",
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["definition"]["environment"],
            environment,
        )

    def test_uploaded_skill_accepts_ten_megabyte_package_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    "/api/lens/admin/skills/upload/",
                    {
                        "file": skill_zip_upload_with_file(
                            "binary-skill",
                            10 * 1024 * 1024,
                        )
                    },
                    format="multipart",
                )

        self.assertEqual(response.status_code, 200)

    def test_uploaded_skill_rejects_package_file_over_ten_megabytes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    "/api/lens/admin/skills/upload/",
                    {
                        "file": skill_zip_upload_with_file(
                            "oversized-binary-skill",
                            10 * 1024 * 1024 + 1,
                        )
                    },
                    format="multipart",
                )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["detail"],
            "Skill package contains an oversized file.",
        )

    def test_uploaded_skill_accepts_environment_schema_override(self):
        environment = [
            {
                "name": "JIRA_API_TOKEN",
                "description": "Jira token",
                "required": True,
                "secret": True,
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    "/api/lens/admin/skills/upload/",
                    {
                        "file": skill_zip_upload(
                            "jira-connector",
                            "Use the Jira API.",
                        ),
                        "environment": json.dumps(environment),
                    },
                    format="multipart",
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["definition"]["environment"],
            environment,
        )

    def test_uploaded_skill_rejects_invalid_environment_schema_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    "/api/lens/admin/skills/upload/",
                    {
                        "file": skill_zip_upload(
                            "jira-connector",
                            "Use the Jira API.",
                        ),
                        "environment": "{invalid",
                    },
                    format="multipart",
                )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["detail"],
            "Environment variables must be valid JSON.",
        )
        self.assertFalse(
            Skill.objects.filter(slug="jira-connector").exists()
        )

    def test_uploaded_skill_reads_api_access_policy(self):
        environment = [
            {
                "name": "JIRA_BASE_URL",
                "required": True,
                "secret": False,
            }
        ]
        api = {
            "base_url_env": "JIRA_BASE_URL",
            "routes": [
                {"path": "/rest/api/3/myself", "methods": ["GET"]},
                {
                    "path_prefix": "/rest/api/3/search/",
                    "methods": ["GET", "POST"],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    "/api/lens/admin/skills/upload/",
                    {
                        "file": skill_zip_upload(
                            "jira-api",
                            "Use the Jira API.",
                            environment,
                            api,
                        )
                    },
                    format="multipart",
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["definition"]["api"], api)

    def test_uploaded_skill_reads_and_enables_declared_artifact(self):
        artifact_content = b"#!/bin/sh\nprintf artifact-ok\\n"
        artifact_hash = hashlib.sha256(artifact_content).hexdigest()
        artifacts = {
            "income": {
                "type": "executable",
                "entrypoints": [
                    {
                        "os": "linux",
                        "arch": "arm64",
                        "path": "bin/linux-arm64/income",
                        "sha256": artifact_hash,
                    }
                ],
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    "/api/lens/admin/skills/upload/",
                    {
                        "file": skill_zip_upload(
                            "income-cli",
                            "Run the declared Income artifact.",
                            artifacts=artifacts,
                            package_files={
                                "bin/linux-arm64/income": artifact_content,
                            },
                        )
                    },
                    format="multipart",
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.data["definition"]["artifacts"],
                    artifacts,
                )
                skill = Skill.objects.get(slug="income-cli")
                artifact_path = (
                    Path(skill.package_path)
                    / "bin"
                    / "linux-arm64"
                    / "income"
                )
                self.assertEqual(artifact_path.stat().st_mode & 0o777, 0o755)
                with zipfile.ZipFile(package_zip_bytes(skill)) as archive:
                    info = archive.getinfo(
                        "income-cli/bin/linux-arm64/income"
                    )
                    self.assertEqual(
                        (info.external_attr >> 16) & 0o777,
                        0o755,
                    )

    def test_uploaded_skill_recursively_enables_scripts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    "/api/lens/admin/skills/upload/",
                    {
                        "file": skill_zip_upload(
                            "script-permissions",
                            "Run the bundled script.",
                            package_files={
                                "scripts/nested/run": b"#!/bin/sh\n",
                                "scripts/helper.py": b"print('ok')\n",
                            },
                        )
                    },
                    format="multipart",
                )

                self.assertEqual(response.status_code, 200)
                skill = Skill.objects.get(slug="script-permissions")
                package_root = Path(skill.package_path)
                self.assertEqual(
                    (package_root / "scripts/nested/run").stat().st_mode
                    & 0o777,
                    0o755,
                )
                self.assertEqual(
                    (package_root / "scripts/helper.py").stat().st_mode
                    & 0o777,
                    0o755,
                )

    def test_uploaded_skill_reads_declared_transform(self):
        transforms = {
            "summarize-orders": {
                "entrypoint": "scripts/summarize_orders.py",
                "input_format": "json",
                "environment": [],
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    "/api/lens/admin/skills/upload/",
                    {
                        "file": skill_zip_upload(
                            "order-transform",
                            "Summarize an order result reference.",
                            transforms=transforms,
                            package_files={
                                "scripts/summarize_orders.py": (
                                    b"import json, sys\n"
                                ),
                            },
                        )
                    },
                    format="multipart",
                )

                self.assertEqual(response.status_code, 200)
                saved_transform = response.data["definition"][
                    "transforms"
                ]["summarize-orders"]
                self.assertEqual(
                    saved_transform["entrypoint"],
                    "scripts/summarize_orders.py",
                )
                self.assertEqual(saved_transform["input_format"], "json")
                self.assertEqual(saved_transform["environment"], [])
                self.assertEqual(
                    saved_transform["sha256"],
                    hashlib.sha256(b"import json, sys\n").hexdigest(),
                )
                skill = Skill.objects.get(slug="order-transform")
                with zipfile.ZipFile(package_zip_bytes(skill)) as archive:
                    config = json.loads(
                        archive.read(
                            "order-transform/sourcelens.json"
                        ).decode("utf-8")
                    )
                self.assertEqual(config["transforms"], transforms)

    def test_uploaded_skill_rejects_transform_outside_scripts(self):
        transforms = {
            "summarize-orders": {
                "entrypoint": "bin/summarize_orders.py",
                "input_format": "json",
                "environment": [],
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    "/api/lens/admin/skills/upload/",
                    {
                        "file": skill_zip_upload(
                            "unsafe-transform",
                            "Run a transform.",
                            transforms=transforms,
                            package_files={
                                "bin/summarize_orders.py": b"print('no')\n",
                            },
                        )
                    },
                    format="multipart",
                )

        self.assertEqual(response.status_code, 400)
        self.assertIn("scripts/", response.data["detail"])

    def test_uploaded_skill_rejects_transform_undeclared_environment(self):
        transforms = {
            "summarize-orders": {
                "entrypoint": "scripts/summarize_orders.py",
                "input_format": "json",
                "environment": ["ORDER_TOKEN"],
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    "/api/lens/admin/skills/upload/",
                    {
                        "file": skill_zip_upload(
                            "unsafe-transform-env",
                            "Run a transform.",
                            transforms=transforms,
                            package_files={
                                "scripts/summarize_orders.py": (
                                    b"print('no')\n"
                                ),
                            },
                        )
                    },
                    format="multipart",
                )

        self.assertEqual(response.status_code, 400)
        self.assertIn("ORDER_TOKEN", response.data["detail"])

    def test_uploaded_skill_revalidates_transform_environment_override(self):
        transforms = {
            "summarize-orders": {
                "entrypoint": "scripts/summarize_orders.py",
                "input_format": "json",
                "environment": ["ORDER_TOKEN"],
            }
        }
        environment = [
            {
                "name": "ORDER_TOKEN",
                "required": True,
                "secret": True,
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    "/api/lens/admin/skills/upload/",
                    {
                        "file": skill_zip_upload(
                            "transform-override",
                            "Run a transform.",
                            environment=environment,
                            transforms=transforms,
                            package_files={
                                "scripts/summarize_orders.py": (
                                    b"print('ok')\n"
                                ),
                            },
                        ),
                        "environment": json.dumps([]),
                    },
                    format="multipart",
                )

        self.assertEqual(response.status_code, 400)
        self.assertIn("ORDER_TOKEN", response.data["detail"])

    def test_uploaded_skill_rejects_artifact_outside_bin(self):
        content = b"#!/bin/sh\n"
        artifacts = {
            "income": {
                "type": "executable",
                "entrypoints": [
                    {
                        "os": "linux",
                        "arch": "arm64",
                        "path": "scripts/income",
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                ],
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    "/api/lens/admin/skills/upload/",
                    {
                        "file": skill_zip_upload(
                            "unsafe-artifact",
                            "Run an artifact.",
                            artifacts=artifacts,
                            package_files={"scripts/income": content},
                        )
                    },
                    format="multipart",
                )

        self.assertEqual(response.status_code, 400)
        self.assertIn("bin/", response.data["detail"])

    def test_uploaded_skill_rejects_artifact_hash_mismatch(self):
        artifacts = {
            "income": {
                "type": "executable",
                "entrypoints": [
                    {
                        "os": "linux",
                        "arch": "arm64",
                        "path": "bin/linux-arm64/income",
                        "sha256": "0" * 64,
                    }
                ],
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    "/api/lens/admin/skills/upload/",
                    {
                        "file": skill_zip_upload(
                            "tampered-artifact",
                            "Run an artifact.",
                            artifacts=artifacts,
                            package_files={
                                "bin/linux-arm64/income": b"unexpected",
                            },
                        )
                    },
                    format="multipart",
                )

        self.assertEqual(response.status_code, 400)
        self.assertIn("SHA-256", response.data["detail"])

    def test_manual_skill_rejects_api_route_with_path_traversal(self):
        response = self.client.post(
            "/api/lens/admin/skills/",
            {
                "name": "Unsafe Connector",
                "slug": "unsafe-connector",
                "definition": {
                    "content": "Use the connector.",
                    "environment": [
                        {
                            "name": "API_BASE_URL",
                            "required": True,
                            "secret": False,
                        }
                    ],
                    "api": {
                        "base_url_env": "API_BASE_URL",
                        "routes": [
                            {
                                "path_prefix": "/api/%252e%252e/admin/",
                                "methods": ["GET"],
                            }
                        ],
                    },
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("path traversal", str(response.data).lower())

    def test_uploaded_skill_update_preserves_assistant_binding(self):
        skill = Skill.objects.create(
            name="package-skill",
            slug="package-skill",
            definition={"content": "old"},
            source_type="upload",
        )
        AssistantSkill.objects.create(
            assistant=self.assistant,
            skill=skill,
            enabled=True,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    f"/api/lens/admin/skills/{skill.uuid}/update-upload/",
                    {"file": skill_zip_upload("package-skill", "new body")},
                    format="multipart",
                )

        self.assertEqual(response.status_code, 200)
        skill.refresh_from_db()
        self.assertEqual(skill.definition["content"], "new body")
        self.assertEqual(skill.source_type, "upload")
        self.assertTrue(skill.package_hash)
        self.assertTrue(
            AssistantSkill.objects.filter(
                assistant=self.assistant,
                skill=skill,
            ).exists()
        )

    def test_uploaded_skill_update_accepts_environment_schema_override(self):
        skill = Skill.objects.create(
            name="package-skill",
            slug="package-skill",
            definition={"content": "old", "environment": []},
            source_type="upload",
        )
        environment = [
            {
                "name": "PACKAGE_TOKEN",
                "description": "Package token",
                "required": True,
                "secret": True,
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(STORAGE_ROOT=temp_dir):
                response = self.client.post(
                    f"/api/lens/admin/skills/{skill.uuid}/update-upload/",
                    {
                        "file": skill_zip_upload(
                            "package-skill",
                            "new body",
                        ),
                        "environment": json.dumps(environment),
                    },
                    format="multipart",
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["definition"]["environment"],
            environment,
        )

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

    def test_general_chat_create_allows_empty_dirs_with_skill(self):
        payload = {
            "name": "Skill Runner",
            "slug": "skill-runner",
            "lensnode_uuid": str(self.lensnode.uuid),
            "selected_task": "general_chat",
            "selected_dirs": [],
            "skill_bindings": [{"skill_uuid": str(self.skill.uuid)}],
        }

        response = self.client.post(
            "/api/lens/assistants/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        assistant = Assistant.objects.get(slug="skill-runner")
        self.assertEqual(assistant.selected_task, "general_chat")
        self.assertEqual(assistant.selected_dirs, [])
        self.assertEqual(assistant.skill_bindings.count(), 1)

    def test_general_chat_create_requires_enabled_skill(self):
        payload = {
            "name": "Skill Runner",
            "slug": "skill-runner-empty",
            "lensnode_uuid": str(self.lensnode.uuid),
            "selected_task": "general_chat",
            "selected_dirs": [],
            "skill_bindings": [],
        }

        response = self.client.post(
            "/api/lens/assistants/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("skill_bindings", response.data)

    def test_general_chat_create_rejects_globally_disabled_skill(self):
        self.skill.enabled = False
        self.skill.save(update_fields=["enabled"])
        payload = {
            "name": "Skill Runner",
            "slug": "skill-runner-disabled",
            "lensnode_uuid": str(self.lensnode.uuid),
            "selected_task": "general_chat",
            "selected_dirs": [],
            "skill_bindings": [{"skill_uuid": str(self.skill.uuid)}],
        }

        response = self.client.post(
            "/api/lens/assistants/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("skill_bindings", response.data)

    def test_loaded_skills_snapshot_excludes_package_file_bytes(self):
        assistant = Assistant.objects.create(
            name="Skill Snapshot",
            slug="skill-snapshot",
            lensnode=self.lensnode,
            selected_task="general_chat",
            selected_dirs=[],
        )
        AssistantSkill.objects.create(
            assistant=assistant,
            skill=self.skill,
            enabled=True,
        )

        loaded = build_loaded_skills(assistant)

        self.assertEqual(len(loaded), 1)
        self.assertNotIn("package_files", loaded[0])

    def test_environment_variable_set_encrypts_values_and_masks_api(self):
        response = self.client.post(
            "/api/lens/admin/environment-variable-sets/",
            {
                "name": "Jira - Production",
                "values": [
                    {
                        "key": "JIRA_BASE_URL",
                        "value": "https://jira.example.com",
                    },
                    {"key": "JIRA_API_TOKEN", "value": "secret-token"},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        variable_set = EnvironmentVariableSet.objects.get(
            name="Jira - Production"
        )
        self.assertNotIn("secret-token", variable_set.encrypted_values)
        self.assertEqual(
            variable_set.get_values()["JIRA_API_TOKEN"],
            "secret-token",
        )
        self.assertNotIn("values", response.data)
        self.assertEqual(
            response.data["keys"],
            ["JIRA_API_TOKEN", "JIRA_BASE_URL"],
        )

    def test_assistant_skill_requires_declared_environment_values(self):
        self.skill.definition = {
            "environment": [
                {
                    "name": "JIRA_API_TOKEN",
                    "description": "Jira token",
                    "required": True,
                    "secret": True,
                }
            ]
        }
        self.skill.save(update_fields=["definition"])
        response = self.client.post(
            "/api/lens/assistants/",
            {
                "name": "Jira Assistant",
                "slug": "jira-assistant",
                "lensnode_uuid": str(self.lensnode.uuid),
                "selected_task": "knowledge_qa",
                "selected_dirs": [{"path": "/workspace/repo"}],
                "skill_bindings": [{"skill_uuid": str(self.skill.uuid)}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("JIRA_API_TOKEN", str(response.data))

    def test_assistant_create_saves_inline_environment_values(self):
        self.skill.definition = {
            "environment": [
                {
                    "name": "JIRA_API_TOKEN",
                    "description": "Jira token",
                    "required": True,
                    "secret": True,
                }
            ]
        }
        self.skill.save(update_fields=["definition"])

        response = self.client.post(
            "/api/lens/assistants/",
            {
                "name": "Jira Assistant",
                "slug": "jira-inline-environment",
                "lensnode_uuid": str(self.lensnode.uuid),
                "selected_task": "knowledge_qa",
                "selected_dirs": [{"path": "/workspace/repo"}],
                "skill_bindings": [
                    {
                        "skill_uuid": str(self.skill.uuid),
                        "environment_variable_set_name": "Jira - Staging",
                        "environment_values": [
                            {
                                "key": "JIRA_API_TOKEN",
                                "value": "staging-token",
                            }
                        ],
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        assistant = Assistant.objects.get(slug="jira-inline-environment")
        binding = assistant.skill_bindings.get(skill=self.skill)
        self.assertEqual(
            binding.environment_variable_set.name,
            "Jira - Staging",
        )
        self.assertEqual(
            binding.environment_variable_set.get_values(),
            {"JIRA_API_TOKEN": "staging-token"},
        )

    def test_assistant_create_rolls_back_inline_environment_on_failure(self):
        self.skill.definition = {
            "environment": [
                {
                    "name": "JIRA_API_TOKEN",
                    "required": True,
                    "secret": True,
                }
            ]
        }
        self.skill.save(update_fields=["definition"])
        serializer = AssistantSerializer(
            data={
                "name": "Rollback Assistant",
                "slug": "rollback-assistant",
                "lensnode_uuid": str(self.lensnode.uuid),
                "selected_task": "knowledge_qa",
                "selected_dirs": [{"path": "/workspace/repo"}],
                "skill_bindings": [
                    {
                        "skill_uuid": str(self.skill.uuid),
                        "environment_variable_set_name": "Rollback Set",
                        "environment_values": [
                            {
                                "key": "JIRA_API_TOKEN",
                                "value": "temporary-token",
                            }
                        ],
                    }
                ],
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

        with patch(
            "lens.serializers.check_assistant_model_refs",
            side_effect=RuntimeError("forced failure"),
        ):
            with self.assertRaises(RuntimeError):
                serializer.save()

        self.assertFalse(
            Assistant.objects.filter(slug="rollback-assistant").exists()
        )
        self.assertFalse(
            EnvironmentVariableSet.objects.filter(name="Rollback Set").exists()
        )

    def test_assistant_update_forks_shared_environment_set(self):
        self.skill.definition = {
            "environment": [
                {
                    "name": "JIRA_API_TOKEN",
                    "required": True,
                    "secret": True,
                }
            ]
        }
        self.skill.save(update_fields=["definition"])
        variable_set = EnvironmentVariableSet.objects.create(
            name="Jira - Shared"
        )
        variable_set.set_values({"JIRA_API_TOKEN": "shared-token"})
        variable_set.save(update_fields=["encrypted_values"])
        AssistantSkill.objects.create(
            assistant=self.assistant,
            skill=self.skill,
            environment_variable_set=variable_set,
        )
        other_assistant = Assistant.objects.create(
            name="Other Jira Assistant",
            slug="other-jira-assistant",
            lensnode=self.lensnode,
            selected_task="knowledge_qa",
            selected_dirs=[{"path": "/workspace/repo"}],
        )
        AssistantSkill.objects.create(
            assistant=other_assistant,
            skill=self.skill,
            environment_variable_set=variable_set,
        )

        response = self.client.patch(
            f"/api/lens/assistants/{self.assistant.uuid}/",
            {
                "skill_bindings": [
                    {
                        "skill_uuid": str(self.skill.uuid),
                        "environment_variable_set_uuid": str(
                            variable_set.uuid
                        ),
                        "environment_values": [
                            {
                                "key": "JIRA_API_TOKEN",
                                "value": "assistant-token",
                            }
                        ],
                    }
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        variable_set.refresh_from_db()
        self.assertEqual(
            variable_set.get_values(),
            {"JIRA_API_TOKEN": "shared-token"},
        )
        updated_binding = self.assistant.skill_bindings.get(skill=self.skill)
        other_binding = other_assistant.skill_bindings.get(skill=self.skill)
        self.assertNotEqual(
            updated_binding.environment_variable_set_id,
            variable_set.id,
        )
        self.assertEqual(
            other_binding.environment_variable_set_id,
            variable_set.id,
        )
        self.assertEqual(
            updated_binding.environment_variable_set.get_values(),
            {"JIRA_API_TOKEN": "assistant-token"},
        )

    def test_assistant_update_preserves_exclusive_environment_set_uuid(self):
        self.skill.definition = {
            "environment": [
                {
                    "name": "JIRA_API_TOKEN",
                    "required": True,
                    "secret": True,
                }
            ]
        }
        self.skill.save(update_fields=["definition"])
        variable_set = EnvironmentVariableSet.objects.create(
            name="Jira - Exclusive"
        )
        variable_set.set_values({"JIRA_API_TOKEN": "old-token"})
        variable_set.save(update_fields=["encrypted_values"])
        AssistantSkill.objects.create(
            assistant=self.assistant,
            skill=self.skill,
            environment_variable_set=variable_set,
        )

        response = self.client.patch(
            f"/api/lens/assistants/{self.assistant.uuid}/",
            {
                "skill_bindings": [
                    {
                        "skill_uuid": str(self.skill.uuid),
                        "environment_variable_set_uuid": str(
                            variable_set.uuid
                        ),
                        "environment_values": [
                            {
                                "key": "JIRA_API_TOKEN",
                                "value": "new-token",
                            }
                        ],
                    }
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        binding = self.assistant.skill_bindings.get(skill=self.skill)
        self.assertEqual(binding.environment_variable_set_id, variable_set.id)
        variable_set.refresh_from_db()
        self.assertEqual(
            variable_set.get_values(),
            {"JIRA_API_TOKEN": "new-token"},
        )

    def test_assistant_update_locks_environment_set_before_rebinding(self):
        self.skill.definition = {
            "environment": [
                {
                    "name": "JIRA_API_TOKEN",
                    "required": True,
                    "secret": True,
                }
            ]
        }
        self.skill.save(update_fields=["definition"])
        variable_set = EnvironmentVariableSet.objects.create(
            name="Jira - Locked"
        )
        variable_set.set_values({"JIRA_API_TOKEN": "old-token"})
        variable_set.save(update_fields=["encrypted_values"])
        AssistantSkill.objects.create(
            assistant=self.assistant,
            skill=self.skill,
            environment_variable_set=variable_set,
        )

        with CaptureQueriesContext(connection) as queries:
            response = self.client.patch(
                f"/api/lens/assistants/{self.assistant.uuid}/",
                {
                    "skill_bindings": [
                        {
                            "skill_uuid": str(self.skill.uuid),
                            "environment_variable_set_uuid": str(
                                variable_set.uuid
                            ),
                            "environment_values": [
                                {
                                    "key": "JIRA_API_TOKEN",
                                    "value": "new-token",
                                }
                            ],
                        }
                    ]
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.data)
        table_name = EnvironmentVariableSet._meta.db_table.upper()
        lock_queries = [
            query["sql"]
            for query in queries.captured_queries
            if "FOR UPDATE" in query["sql"].upper()
            and table_name in query["sql"].upper()
        ]
        self.assertTrue(lock_queries)

    def test_disabled_binding_does_not_require_environment(self):
        self.skill.definition = {
            "environment": [
                {
                    "name": "JIRA_API_TOKEN",
                    "required": True,
                    "secret": True,
                }
            ]
        }
        self.skill.save(update_fields=["definition"])

        response = self.client.patch(
            f"/api/lens/assistants/{self.assistant.uuid}/",
            {
                "skill_bindings": [
                    {
                        "skill_uuid": str(self.skill.uuid),
                        "enabled": False,
                    }
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        binding = self.assistant.skill_bindings.get(skill=self.skill)
        self.assertFalse(binding.enabled)
        self.assertIsNone(binding.environment_variable_set)

    def test_dispatch_rejects_disabled_environment_variable_set(self):
        self.skill.definition = {
            "environment": [
                {
                    "name": "JIRA_API_TOKEN",
                    "required": True,
                    "secret": True,
                }
            ]
        }
        self.skill.save(update_fields=["definition"])
        variable_set = EnvironmentVariableSet.objects.create(
            name="Jira - Disabled",
            enabled=False,
        )
        variable_set.set_values({"JIRA_API_TOKEN": "disabled-token"})
        variable_set.save(update_fields=["encrypted_values"])
        AssistantSkill.objects.create(
            assistant=self.assistant,
            skill=self.skill,
            environment_variable_set=variable_set,
        )
        session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        run = create_execution_run(session, "Search Jira", enqueue=False)

        with self.assertRaises(LensNodeDispatchError) as context:
            validate_run_dispatch(run)

        self.assertEqual(
            str(context.exception),
            "SKILL_ENVIRONMENT_REQUIRED",
        )
        runtime = resolve_loaded_skill_environment(
            build_loaded_skills(self.assistant)
        )
        self.assertEqual(runtime[0]["environment"], {})

    def test_dispatch_rejects_run_queued_before_assistant_was_archived(self):
        session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        run = create_execution_run(session, "Question", enqueue=False)
        self.assistant.status = Assistant.Status.ARCHIVED
        self.assistant.save(update_fields=["status"])
        run = run.__class__.objects.select_related(
            "session__assistant"
        ).get(pk=run.pk)

        with self.assertRaises(LensNodeDispatchError) as context:
            validate_run_dispatch(run)

        self.assertEqual(str(context.exception), "ASSISTANT_ARCHIVED")

    def test_dispatch_validates_the_frozen_execution_snapshot(self):
        session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        run = create_execution_run(session, "Question", enqueue=False)
        self.assistant.selected_task = "general_chat"
        self.assistant.selected_dirs = []
        self.assistant.save(
            update_fields=["selected_task", "selected_dirs"]
        )
        run = run.__class__.objects.select_related(
            "execution",
            "session__assistant",
        ).get(pk=run.pk)

        validate_run_dispatch(run)

    def test_dispatch_rejects_invalid_frozen_snapshot_after_assistant_edit(self):
        self.assistant.selected_task = "general_chat"
        self.assistant.selected_dirs = []
        self.assistant.save(
            update_fields=["selected_task", "selected_dirs"]
        )
        session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        run = create_execution_run(session, "Question", enqueue=False)
        self.assistant.selected_task = "knowledge_qa"
        self.assistant.selected_dirs = [{"path": "/workspace/repo"}]
        self.assistant.save(
            update_fields=["selected_task", "selected_dirs"]
        )
        run = run.__class__.objects.select_related(
            "execution",
            "session__assistant",
        ).get(pk=run.pk)

        with self.assertRaises(LensNodeDispatchError) as context:
            validate_run_dispatch(run)

        self.assertEqual(
            str(context.exception),
            "GENERAL_CHAT_SKILL_REQUIRED",
        )

    def test_runtime_resolves_environment_without_snapshot_plaintext(self):
        self.skill.definition = {
            "environment": [
                {
                    "name": "JIRA_API_TOKEN",
                    "description": "Jira token",
                    "required": True,
                    "secret": True,
                }
            ]
        }
        self.skill.save(update_fields=["definition"])
        variable_set = EnvironmentVariableSet.objects.create(
            name="Jira - Production"
        )
        variable_set.set_values(
            {"JIRA_API_TOKEN": "secret-token", "UNDECLARED": "hidden"}
        )
        variable_set.save(update_fields=["encrypted_values"])
        AssistantSkill.objects.create(
            assistant=self.assistant,
            skill=self.skill,
            environment_variable_set=variable_set,
        )

        loaded = build_loaded_skills(self.assistant)
        runtime = resolve_loaded_skill_environment(loaded)

        self.assertNotIn("environment", loaded[0])
        self.assertNotIn("secret-token", str(loaded))
        self.assertEqual(
            runtime[0]["environment"],
            {"JIRA_API_TOKEN": "secret-token"},
        )

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

    def test_lensnode_ai_gateway_forwards_run_correlation(self):
        from lens.models import Session
        from lens.services import create_execution_run

        token = "dev-lensnode-token"
        self.lensnode.auth_token_hash = hash_lensnode_token(token)
        self.lensnode.save(update_fields=["auth_token_hash", "updated_at"])
        client = APIClient()
        chat_user = User.objects.create_user(
            username="chat-user",
            email="chat-user@example.com",
            password="pass12345",
        )
        session = Session.objects.create(
            assistant=self.assistant,
            user=chat_user,
        )
        run = create_execution_run(
            session=session,
            question="hello",
            enqueue=False,
        )

        with patch(
            "agentcore_metering.adapters.django.LLMTracker.call_and_track",
            return_value=("ok", {"total_tokens": 1}),
        ) as call_and_track:
            response = client.post(
                "/api/lens/lensnode/ai-gateway/",
                {
                    "model_ref": "016d5cf7-2245-4015-b242-d6323e795b58",
                    "messages": [{"role": "user", "content": "hello"}],
                    "run_uuid": str(run.uuid),
                    "is_subagent": True,
                    "trace_context": {
                        "parent_observation_id": "a" * 16,
                        "generation_name": "llm.agent",
                    },
                },
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )

        self.assertEqual(response.status_code, 200)
        state = call_and_track.call_args.kwargs["state"]
        self.assertEqual(state["user_id"], chat_user.id)
        self.assertEqual(state["metadata"]["run_uuid"], str(run.uuid))
        self.assertTrue(state["metadata"]["is_subagent"])
        self.assertEqual(
            state["litellm_metadata"]["session_id"],
            str(session.uuid),
        )
        self.assertEqual(
            state["litellm_metadata"]["trace_user_id"],
            str(chat_user.id),
        )
        self.assertEqual(
            state["litellm_metadata"]["trace_name"],
            "sourcelens.run",
        )
        self.assertEqual(
            state["litellm_metadata"]["trace_id"],
            run.uuid.hex,
        )
        self.assertEqual(
            state["litellm_metadata"]["existing_trace_id"],
            run.uuid.hex,
        )
        self.assertEqual(
            state["litellm_metadata"]["parent_observation_id"],
            "a" * 16,
        )
        self.assertEqual(
            state["litellm_metadata"]["generation_name"],
            "llm.agent",
        )
        self.assertEqual(
            state["litellm_metadata"]["trace_metadata"],
            {
                "run_uuid": str(run.uuid),
                "is_subagent": True,
            },
        )
        self.assertEqual(
            state["otel_traceparent"],
            f"00-{run.uuid.hex}-{'a' * 16}-01",
        )

    def test_lensnode_ai_gateway_rejects_invalid_trace_context(self):
        token = "dev-lensnode-token"
        self.lensnode.auth_token_hash = hash_lensnode_token(token)
        self.lensnode.save(
            update_fields=["auth_token_hash", "updated_at"]
        )
        client = APIClient()

        with patch(
            "agentcore_metering.adapters.django.LLMTracker.call_and_track"
        ) as call_and_track:
            response = client.post(
                "/api/lens/lensnode/ai-gateway/",
                {
                    "model_ref": "016d5cf7-2245-4015-b242-d6323e795b58",
                    "messages": [{"role": "user", "content": "hello"}],
                    "trace_context": {
                        "parent_observation_id": "not-an-observation-id",
                        "generation_name": "llm.agent",
                    },
                },
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Invalid trace_context.")
        call_and_track.assert_not_called()

    def test_lensnode_ai_gateway_attributes_every_call_to_run_owner(self):
        from lens.models import Session
        from lens.services import create_execution_run

        token = "dev-lensnode-token"
        self.lensnode.auth_token_hash = hash_lensnode_token(token)
        self.lensnode.save(update_fields=["auth_token_hash", "updated_at"])
        chat_user = User.objects.create_user(
            username="usage-chat-user",
            email="usage-chat-user@example.com",
            password="pass12345",
        )
        session = Session.objects.create(
            assistant=self.assistant,
            user=chat_user,
        )
        run = create_execution_run(
            session=session,
            question="hello",
            enqueue=False,
        )
        config = LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"api_key": "test", "model": "gpt-4o-mini"},
            is_active=True,
        )
        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="ok"),
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=2,
                completion_tokens=1,
                total_tokens=3,
                cached_tokens=0,
                reasoning_tokens=0,
            ),
            model="gpt-4o-mini",
        )
        client = APIClient()
        payload = {
            "model_ref": str(config.uuid),
            "messages": [{"role": "user", "content": "hello"}],
            "run_uuid": str(run.uuid),
        }

        with patch("litellm.completion", return_value=completion):
            for _ in range(2):
                response = client.post(
                    "/api/lens/lensnode/ai-gateway/",
                    payload,
                    format="json",
                    HTTP_AUTHORIZATION=f"Bearer {token}",
                )
                self.assertEqual(response.status_code, 200)

        usages = list(LLMUsage.objects.order_by("created_at"))
        self.assertEqual(len(usages), 2)
        self.assertTrue(all(item.user_id == chat_user.id for item in usages))
        self.assertTrue(
            all(
                item.metadata["run_uuid"] == str(run.uuid)
                for item in usages
            )
        )

    def test_lensnode_ai_gateway_rejects_run_from_another_lensnode(self):
        from lens.models import Session
        from lens.services import create_execution_run

        token = "other-lensnode-token"
        LensNode.objects.create(
            name="Other LensNode",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            auth_token_hash=hash_lensnode_token(token),
        )
        session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        run = create_execution_run(
            session=session,
            question="hello",
            enqueue=False,
        )
        client = APIClient()

        with patch(
            "agentcore_metering.adapters.django.LLMTracker.call_and_track"
        ) as call_and_track:
            response = client.post(
                "/api/lens/lensnode/ai-gateway/",
                {
                    "model_ref": "016d5cf7-2245-4015-b242-d6323e795b58",
                    "messages": [{"role": "user", "content": "hello"}],
                    "run_uuid": str(run.uuid),
                },
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )

        self.assertEqual(response.status_code, 403)
        call_and_track.assert_not_called()

    def test_lensnode_ai_gateway_rejects_malformed_run_uuid(self):
        token = "dev-lensnode-token"
        self.lensnode.auth_token_hash = hash_lensnode_token(token)
        self.lensnode.save(update_fields=["auth_token_hash", "updated_at"])
        client = APIClient()

        with patch(
            "agentcore_metering.adapters.django.LLMTracker.call_and_track"
        ) as call_and_track:
            response = client.post(
                "/api/lens/lensnode/ai-gateway/",
                {
                    "model_ref": "016d5cf7-2245-4015-b242-d6323e795b58",
                    "messages": [{"role": "user", "content": "hello"}],
                    "run_uuid": "not-a-uuid",
                },
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["detail"], "Run not found.")
        call_and_track.assert_not_called()

    def test_lensnode_deliverable_upload_records_output_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from lens.models import RunOutputFile, Session
        from lens.services import create_execution_run

        token = "dev-lensnode-token"
        self.lensnode.auth_token_hash = hash_lensnode_token(token)
        self.lensnode.save(update_fields=["auth_token_hash", "updated_at"])
        session = Session.objects.create(
            assistant=self.assistant, user=self.user
        )
        run = create_execution_run(
            session=session, question="q", enqueue=False
        )

        client = APIClient()
        upload = SimpleUploadedFile(
            "brief.html", b"<html>brief</html>", content_type="text/html"
        )
        response = client.post(
            "/api/lens/lensnode/deliverables/",
            {
                "run_uuid": str(run.uuid),
                "file": upload,
                "filename": "brief.html",
                "content_type": "text/html",
            },
            format="multipart",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 201)
        output = RunOutputFile.objects.get(run=run)
        self.assertEqual(output.filename, "brief.html")
        self.assertEqual(output.message_id, run.output_message_id)
        self.assertEqual(output.session_id, session.id)
        self.assertEqual(output.assistant_id, self.assistant.id)
        self.assertTrue(output.file.storage.exists(output.file.name))
        output.file.delete(save=False)

    def test_lensnode_deliverable_upload_rejects_bad_token(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from lens.models import Session
        from lens.services import create_execution_run

        session = Session.objects.create(
            assistant=self.assistant, user=self.user
        )
        run = create_execution_run(
            session=session, question="q", enqueue=False
        )
        response = APIClient().post(
            "/api/lens/lensnode/deliverables/",
            {
                "run_uuid": str(run.uuid),
                "file": SimpleUploadedFile("x.txt", b"x"),
            },
            format="multipart",
            HTTP_AUTHORIZATION="Bearer wrong-token",
        )
        self.assertEqual(response.status_code, 401)

    @override_settings(DELIVERABLE_MAX_BYTES=8)
    def test_lensnode_deliverable_upload_rejects_oversized(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from lens.models import RunOutputFile, Session
        from lens.services import create_execution_run

        token = "dev-lensnode-token"
        self.lensnode.auth_token_hash = hash_lensnode_token(token)
        self.lensnode.save(update_fields=["auth_token_hash", "updated_at"])
        session = Session.objects.create(
            assistant=self.assistant, user=self.user
        )
        run = create_execution_run(
            session=session, question="q", enqueue=False
        )
        response = APIClient().post(
            "/api/lens/lensnode/deliverables/",
            {
                "run_uuid": str(run.uuid),
                "file": SimpleUploadedFile("big.html", b"way too many bytes"),
            },
            format="multipart",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 413)
        self.assertFalse(RunOutputFile.objects.filter(run=run).exists())

    def test_lensnode_deliverable_upload_strips_path_from_filename(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from lens.models import RunOutputFile, Session
        from lens.services import create_execution_run

        token = "dev-lensnode-token"
        self.lensnode.auth_token_hash = hash_lensnode_token(token)
        self.lensnode.save(update_fields=["auth_token_hash", "updated_at"])
        session = Session.objects.create(
            assistant=self.assistant, user=self.user
        )
        run = create_execution_run(
            session=session, question="q", enqueue=False
        )
        response = APIClient().post(
            "/api/lens/lensnode/deliverables/",
            {
                "run_uuid": str(run.uuid),
                "file": SimpleUploadedFile("x.html", b"<html></html>"),
                "filename": "../../../etc/passwd",
            },
            format="multipart",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 201)
        output = RunOutputFile.objects.get(run=run)
        self.assertEqual(output.filename, "passwd")
        self.assertNotIn("..", output.file.name)
        self.assertTrue(
            output.file.name.endswith("passwd")
            or "passwd" in output.file.name
        )
        output.file.delete(save=False)

    def _make_output_file(self, user=None):
        """Create a delivered output file linked to a fresh run."""

        from django.core.files.base import ContentFile
        from lens.models import RunOutputFile, Session
        from lens.services import create_execution_run

        session = Session.objects.create(
            assistant=self.assistant, user=user or self.user
        )
        run = create_execution_run(
            session=session, question="q", enqueue=False
        )
        output = RunOutputFile(
            run=run,
            message=run.output_message,
            session=session,
            assistant=self.assistant,
            filename="brief.html",
            content_type="text/html",
            byte_size=18,
            content_hash=hashlib.sha256(b"<html>brief</html>").hexdigest(),
        )
        output.file.save(
            "brief.html", ContentFile(b"<html>brief</html>"), save=False
        )
        output.save()
        return session, run, output

    def test_lensnode_can_download_prior_same_session_deliverable(self):
        from lens.services import create_execution_run

        token = "dev-lensnode-token"
        self.lensnode.auth_token_hash = hash_lensnode_token(token)
        self.lensnode.save(update_fields=["auth_token_hash", "updated_at"])
        session, prior, output = self._make_output_file()
        prior.status = Run.Status.DONE
        prior.outcome = Run.Outcome.COMPLETED
        prior.save(update_fields=["status", "outcome"])
        current = create_execution_run(
            session=session,
            question="Translate the previous file",
            enqueue=False,
        )

        try:
            response = APIClient().get(
                (
                    f"/api/lens/lensnode/runs/{current.uuid}/"
                    f"history-artifacts/{output.uuid}/"
                ),
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                collect_stream(response.streaming_content),
                b"<html>brief</html>",
            )
            self.assertEqual(
                response["X-Attachment-Hash"],
                output.content_hash,
            )
        finally:
            output.file.delete(save=False)

    def test_lensnode_cannot_download_deliverable_from_other_session(self):
        from lens.models import Session
        from lens.services import create_execution_run

        token = "dev-lensnode-token"
        self.lensnode.auth_token_hash = hash_lensnode_token(token)
        self.lensnode.save(update_fields=["auth_token_hash", "updated_at"])
        other_session, prior, output = self._make_output_file()
        prior.status = Run.Status.DONE
        prior.outcome = Run.Outcome.COMPLETED
        prior.save(update_fields=["status", "outcome"])
        current_session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        current = create_execution_run(
            session=current_session,
            question="Read another conversation",
            enqueue=False,
        )

        try:
            response = APIClient().get(
                (
                    f"/api/lens/lensnode/runs/{current.uuid}/"
                    f"history-artifacts/{output.uuid}/"
                ),
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )
            self.assertEqual(response.status_code, 404)
        finally:
            output.file.delete(save=False)

    def test_output_file_download_returns_attachment_to_owner(self):
        session, run, output = self._make_output_file()

        response = self.client.get(
            f"/api/lens/output-files/{output.uuid}/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("brief.html", response["Content-Disposition"])
        self.assertEqual(
            b"".join(response.streaming_content), b"<html>brief</html>"
        )
        output.file.delete(save=False)

    def test_output_file_download_forbidden_for_other_user(self):
        session, run, output = self._make_output_file()
        other = User.objects.create_user(
            username="intruder",
            email="intruder@example.com",
            password="pass12345",
        )
        client = APIClient()
        client.force_authenticate(other)

        response = client.get(
            f"/api/lens/output-files/{output.uuid}/"
        )

        self.assertEqual(response.status_code, 403)
        output.file.delete(save=False)

    def test_output_file_download_returns_attachment_to_admin(self):
        owner = User.objects.create_user(
            username="file-owner",
            email="file-owner@example.com",
            password="pass12345",
        )
        session, run, output = self._make_output_file(owner)

        response = self.client.get(
            f"/api/lens/output-files/{output.uuid}/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        output.file.delete(save=False)

    def test_session_messages_include_output_files(self):
        session, run, output = self._make_output_file()

        response = self.client.get(
            f"/api/lens/sessions/{session.uuid}/messages/"
        )

        self.assertEqual(response.status_code, 200)
        answer = next(
            m for m in response.data if m["role"] == "assistant"
        )
        self.assertEqual(len(answer["output_files"]), 1)
        chip = answer["output_files"][0]
        self.assertEqual(chip["filename"], "brief.html")
        self.assertIn(
            f"/api/lens/output-files/{output.uuid}/", chip["url"]
        )
        output.file.delete(save=False)

    def test_admin_run_detail_includes_output_files(self):
        session, run, output = self._make_output_file()

        response = self.client.get(
            f"/api/lens/admin/runs/{run.uuid}/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["output_files"]), 1)
        item = response.data["output_files"][0]
        self.assertEqual(item["uuid"], str(output.uuid))
        self.assertEqual(item["filename"], "brief.html")
        self.assertEqual(item["content_type"], "text/html")
        self.assertEqual(item["byte_size"], 18)
        self.assertIsNotNone(item["created_at"])
        self.assertIn(
            f"/api/lens/output-files/{output.uuid}/", item["url"]
        )
        output.file.delete(save=False)

    def test_admin_run_detail_has_empty_output_files(self):
        from lens.models import Session
        from lens.services import create_execution_run

        session = Session.objects.create(
            assistant=self.assistant, user=self.user
        )
        run = create_execution_run(
            session=session, question="q", enqueue=False
        )

        response = self.client.get(
            f"/api/lens/admin/runs/{run.uuid}/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["output_files"], [])

    def test_admin_run_detail_uses_agent_rounds_snapshot(self):
        from lens.models import Session
        from lens.services import create_execution_run

        self.assistant.agent_rounds = "max"
        self.assistant.save(update_fields=["agent_rounds"])
        session = Session.objects.create(
            assistant=self.assistant, user=self.user
        )
        run = create_execution_run(
            session=session, question="q", enqueue=False
        )
        self.assistant.agent_rounds = "flash"
        self.assistant.save(update_fields=["agent_rounds"])

        response = self.client.get(
            f"/api/lens/admin/runs/{run.uuid}/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["agent_rounds"], "max")

    def test_admin_run_detail_separates_executor_and_business_outcomes(self):
        session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        run = create_execution_run(
            session=session,
            question="Query July orders",
            enqueue=False,
        )
        run.status = Run.Status.DONE
        run.outcome = Run.Outcome.COMPLETED
        run.termination_detail = {}
        run.save(update_fields=["status", "outcome", "termination_detail"])
        run.execution.status = RunExecution.Status.COMPLETED
        run.execution.save(update_fields=["status"])
        RunStep.objects.create(
            run=run,
            step_type=RunStep.StepType.GENERAL_CHAT,
            status=RunStep.Status.DONE,
            sequence=3,
            detail={
                "events": [
                    "malformed persisted event",
                    {
                        "agent_event": "deepagents.runtime.outcome",
                        "outcome": "completed",
                        "unresolved_failure_count": 0,
                        "recovered_failure_count": 0,
                        "warning_count": 2,
                        "failures": [
                            {
                                "capability": "skill",
                                "error_type": "tool",
                                "scope": "warning",
                                "required": True,
                                "affects_required_evidence": False,
                                "arguments": {
                                    "authorization": "must-not-leak"
                                },
                            }
                        ],
                    }
                ]
            },
        )

        response = self.client.get(
            f"/api/lens/admin/runs/{run.uuid}/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "done")
        self.assertEqual(response.data["executor_status"], "completed")
        self.assertEqual(response.data["outcome"], "completed")
        self.assertEqual(response.data["termination_detail"], {})
        self.assertEqual(
            response.data["failure_summary"]["warning_count"],
            2,
        )
        failure = response.data["failure_summary"]["failures"][0]
        self.assertTrue(failure["required"])
        self.assertFalse(failure["affects_required_evidence"])
        self.assertEqual(failure["scope"], "warning")
        self.assertNotIn("arguments", failure)

    def test_admin_run_detail_ignores_malformed_failure_collection(self):
        session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        run = create_execution_run(
            session=session,
            question="Query July orders",
            enqueue=False,
        )
        RunStep.objects.create(
            run=run,
            step_type=RunStep.StepType.GENERAL_CHAT,
            status=RunStep.Status.DONE,
            sequence=3,
            detail={
                "events": [
                    {
                        "agent_event": "deepagents.runtime.outcome",
                        "warning_count": 1,
                        "failures": 42,
                    }
                ]
            },
        )

        response = self.client.get(
            f"/api/lens/admin/runs/{run.uuid}/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["failure_summary"]["warning_count"],
            1,
        )
        self.assertEqual(
            response.data["failure_summary"]["failures"],
            [],
        )

    def test_session_messages_use_run_finish_time_for_assistant(self):
        session, run, output = self._make_output_file()
        finished_at = timezone.now()
        run.finished_at = finished_at
        run.save(update_fields=["finished_at"])

        response = self.client.get(
            f"/api/lens/sessions/{session.uuid}/messages/"
        )

        self.assertEqual(response.status_code, 200)
        question = next(m for m in response.data if m["role"] == "user")
        answer = next(
            m for m in response.data if m["role"] == "assistant"
        )
        self.assertIsNone(question["completed_at"])
        self.assertEqual(
            answer["completed_at"],
            finished_at,
        )
        output.file.delete(save=False)

    def test_deleting_session_purges_output_file_bytes(self):
        session, run, output = self._make_output_file()
        storage = output.file.storage
        name = output.file.name
        self.assertTrue(storage.exists(name))

        response = self.client.delete(
            f"/api/lens/sessions/{session.uuid}/"
        )

        self.assertIn(response.status_code, (200, 204))
        self.assertFalse(storage.exists(name))

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

    def test_explicit_retry_is_linked_and_idempotent(self):
        session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        original = create_execution_run(
            session=session,
            question="Retry this question",
            idempotency_key="original-submission",
            enqueue=False,
        )
        payload = {
            "question": "Retry this question",
            "idempotency_key": "retry-submission",
            "retry_of_run_uuid": str(original.uuid),
            "enqueue": False,
        }

        first_response = self.client.post(
            f"/api/lens/sessions/{session.uuid}/runs/",
            payload,
            format="json",
        )
        replay_response = self.client.post(
            f"/api/lens/sessions/{session.uuid}/runs/",
            payload,
            format="json",
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(replay_response.status_code, 201)
        self.assertEqual(
            replay_response.data["uuid"],
            first_response.data["uuid"],
        )
        self.assertEqual(
            first_response.data["retry_of_run_uuid"],
            str(original.uuid),
        )
        self.assertEqual(session.message_set.count(), 4)

    def test_retry_rejects_run_from_another_session(self):
        source_session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        target_session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        original = create_execution_run(
            session=source_session,
            question="Source question",
            enqueue=False,
        )

        response = self.client.post(
            f"/api/lens/sessions/{target_session.uuid}/runs/",
            {
                "question": "Source question",
                "idempotency_key": "cross-session-retry",
                "retry_of_run_uuid": str(original.uuid),
                "enqueue": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(target_session.run_set.count(), 0)
        self.assertEqual(target_session.message_set.count(), 0)

    def test_retry_rejects_inaccessible_run_without_leaking_it(self):
        other_user = User.objects.create_user(
            username="retry-owner",
            email="retry-owner@example.com",
            password="pass12345",
        )
        private_session = Session.objects.create(
            assistant=self.assistant,
            user=other_user,
        )
        private_run = create_execution_run(
            session=private_session,
            question="Private question",
            enqueue=False,
        )
        target_session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )

        response = self.client.post(
            f"/api/lens/sessions/{target_session.uuid}/runs/",
            {
                "question": "Private question",
                "idempotency_key": "inaccessible-retry",
                "retry_of_run_uuid": str(private_run.uuid),
                "enqueue": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["retry_of_run_uuid"][0],
            "Invalid Retry Run.",
        )
        self.assertEqual(target_session.run_set.count(), 0)

    def test_retry_rejects_an_existing_cycle(self):
        session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        first = create_execution_run(
            session=session,
            question="First attempt",
            enqueue=False,
        )
        second = create_execution_run(
            session=session,
            question="Second attempt",
            retry_of_run=first,
            enqueue=False,
        )
        Run.objects.filter(pk=first.pk).update(retry_of_run=second)

        response = self.client.post(
            f"/api/lens/sessions/{session.uuid}/runs/",
            {
                "question": "Third attempt",
                "idempotency_key": "cyclic-retry",
                "retry_of_run_uuid": str(second.uuid),
                "enqueue": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(session.run_set.count(), 2)

    def test_run_created_at_is_read_only(self):
        session_response = self.client.post(
            "/api/lens/sessions/",
            {"assistant_uuid": str(self.assistant.uuid)},
            format="json",
        )
        run_response = self.client.post(
            f"/api/lens/sessions/{session_response.data['uuid']}/runs/",
            {
                "question": "Can the creation time be changed?",
                "idempotency_key": "run-created-at-read-only",
                "enqueue": False,
            },
            format="json",
        )
        self.assertIn("created_at", run_response.data)
        created_at = run_response.data["created_at"]

        update_response = self.client.patch(
            f"/api/lens/runs/{run_response.data['uuid']}/",
            {"created_at": "2000-01-01T00:00:00Z"},
            format="json",
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.data["created_at"], created_at)

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
        self.assertIsNotNone(run_response.data["created_at"])
        Run.objects.filter(uuid=run_response.data["uuid"]).update(
            status=Run.Status.RUNNING,
            resume_by=timezone.now() + timedelta(hours=1),
        )

        cancel_response = self.client.post(
            f"/api/lens/runs/{run_response.data['uuid']}/cancel/"
        )

        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.data["status"], "cancelled")
        self.assertIsNone(cancel_response.data["resume_by"])
        self.assertEqual(
            cancel_response.data["execution"]["status"],
            RunExecution.Status.CANCELLED,
        )

    def test_completed_run_feedback_is_persisted_and_reported(self):
        session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        run = create_execution_run(
            session,
            "Was this answer helpful?",
            enqueue=False,
        )
        run.output_message.content = "Yes, this is the answer."
        run.output_message.run = run
        run.output_message.save(update_fields=["content", "run"])
        run.status = Run.Status.DONE
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at", "updated_at"])

        response = self.client.patch(
            f"/api/lens/runs/{run.uuid}/feedback/",
            {"feedback": Run.Feedback.POSITIVE},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["feedback"], "positive")
        self.assertIsNotNone(response.data["feedback_updated_at"])
        messages = self.client.get(
            f"/api/lens/sessions/{session.uuid}/messages/"
        )
        assistant_message = next(
            item for item in messages.data if item["role"] == "assistant"
        )
        self.assertEqual(assistant_message["feedback"], "positive")
        admin_runs = self.client.get(
            "/api/lens/admin/runs/",
            {"q": "Was this answer helpful?"},
        )
        self.assertEqual(admin_runs.status_code, 200, admin_runs.data)
        self.assertEqual(
            admin_runs.data["results"][0]["feedback"],
            "positive",
        )

        switched = self.client.patch(
            f"/api/lens/runs/{run.uuid}/feedback/",
            {"feedback": Run.Feedback.NEGATIVE},
            format="json",
        )
        cleared = self.client.patch(
            f"/api/lens/runs/{run.uuid}/feedback/",
            {"feedback": ""},
            format="json",
        )

        self.assertEqual(switched.status_code, 200, switched.data)
        self.assertEqual(switched.data["feedback"], "negative")
        self.assertEqual(cleared.status_code, 200, cleared.data)
        self.assertEqual(cleared.data["feedback"], "")

    def test_run_feedback_rejects_invalid_or_unfinished_runs(self):
        session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        run = create_execution_run(
            session,
            "Still running",
            enqueue=False,
        )

        unfinished = self.client.patch(
            f"/api/lens/runs/{run.uuid}/feedback/",
            {"feedback": Run.Feedback.POSITIVE},
            format="json",
        )
        invalid = self.client.patch(
            f"/api/lens/runs/{run.uuid}/feedback/",
            {"feedback": "maybe"},
            format="json",
        )

        self.assertEqual(unfinished.status_code, 400, unfinished.data)
        self.assertEqual(invalid.status_code, 400, invalid.data)

    def test_run_feedback_is_scoped_to_session_owner(self):
        session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        run = create_execution_run(
            session,
            "Private feedback",
            enqueue=False,
        )
        run.status = Run.Status.DONE
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at", "updated_at"])
        other_user = User.objects.create_user(
            username="feedback-user-2",
            email="feedback-user-2@example.com",
            password="pass12345",
        )
        self.client.force_authenticate(other_user)

        response = self.client.patch(
            f"/api/lens/runs/{run.uuid}/feedback/",
            {"feedback": Run.Feedback.NEGATIVE},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

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

    def test_check_datasource_path_blocks_existing_datasource_path(self):
        response = self.client.post(
            f"/api/lens/admin/lensnodes/{self.lensnode.uuid}/"
            "check-datasource-path/",
            {
                "target_path": "/workspace/repo-cache",
                "source_type": "git",
                "config": {"repo_url": "https://example.com/other.git"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "blocked")
        self.assertEqual(
            response.data["message_code"],
            "datasource_path_in_use",
        )
        self.assertEqual(
            response.data["datasource_uuid"],
            str(self.datasource.uuid),
        )

    @patch("lens.views.lensnodes.check_datasource_path")
    def test_check_managed_workspace_path_blocks_nested_datasource(
        self,
        check_path,
    ):
        response = self.client.post(
            f"/api/lens/admin/lensnodes/{self.lensnode.uuid}/"
            "check-datasource-path/",
            {
                "target_path": "/workspace/repo-cache/restored",
                "source_type": "managed_workspace",
                "config": {},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "blocked")
        self.assertEqual(
            response.data["message_code"],
            "datasource_path_in_use",
        )
        check_path.assert_not_called()

    @patch("lens.views.lensnodes.check_datasource_path")
    def test_check_datasource_path_allows_current_datasource_path(
        self,
        check_path,
    ):
        check_path.return_value = {
            "status": "available",
            "message_code": "git_update",
        }

        response = self.client.post(
            f"/api/lens/admin/lensnodes/{self.lensnode.uuid}/"
            "check-datasource-path/",
            {
                "datasource_uuid": str(self.datasource.uuid),
                "target_path": "/workspace/repo-cache",
                "source_type": "git",
                "config": {"repo_url": "https://example.com/repo.git"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "available")
        check_path.assert_called_once()
        self.assertEqual(
            check_path.call_args.kwargs["datasource_uuid"],
            str(self.datasource.uuid),
        )

    def test_datasource_create_enqueues_initial_sync(self):
        payload = {
            "name": "Initial Sync Repo",
            "source_type": "git",
            "lensnode_uuid": str(self.lensnode.uuid),
            "config": {"repo_url": "https://example.com/repo.git"},
            "target_path": "/workspace/initial-sync",
        }

        with patch(
            "lens.views.datasources.source_sync_task.apply_async"
        ) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    "/api/lens/admin/datasources/",
                    payload,
                    format="json",
                )

        self.assertEqual(response.status_code, 201)
        task_id = response.data["initial_sync_task_id"]
        apply_async.assert_called_once_with(
            args=[response.data["uuid"], "initial", task_id],
            task_id=ANY,
        )
        celery_task_id = apply_async.call_args.kwargs["task_id"]
        self.assertNotEqual(celery_task_id, task_id)
        task = TaskExecution.objects.get(task_id=task_id)
        self.assertEqual(task.task_name, "datasource_sync:Initial Sync Repo")
        self.assertEqual(task.module, "lens_datasource")
        self.assertEqual(task.status, "PENDING")
        self.assertEqual(task.created_by, self.user)
        self.assertEqual(task.metadata["celery_task_id"], celery_task_id)

    @patch("lens.serializers.check_datasource_path")
    def test_managed_workspace_create_does_not_enqueue_sync(self, check_path):
        check_path.return_value = {
            "status": "available",
            "exists": True,
            "is_directory": True,
            "message": "Managed workspace directory is available.",
        }
        payload = {
            "name": "Restored Snapshot",
            "source_type": "managed_workspace",
            "lensnode_uuid": str(self.lensnode.uuid),
            "target_path": "/workspace/restores/finance",
            "config": {},
            "sync_policy": {},
        }

        with patch(
            "lens.views.datasources.source_sync_task.apply_async"
        ) as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    "/api/lens/admin/datasources/",
                    payload,
                    format="json",
                )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["availability_status"], "available")
        self.assertNotIn("initial_sync_task_id", response.data)
        apply_async.assert_not_called()
        datasource = DataSource.objects.get(uuid=response.data["uuid"])
        self.assertFalse(
            ScheduledTask.objects.filter(target_id=datasource.uuid).exists()
        )

    @patch("lens.serializers.check_datasource_path")
    def test_managed_workspace_create_requires_existing_directory(
        self,
        check_path,
    ):
        check_path.return_value = {
            "status": "blocked",
            "exists": False,
            "is_directory": False,
            "message": "Managed workspace directory does not exist.",
        }

        response = self.client.post(
            "/api/lens/admin/datasources/",
            {
                "name": "Missing Snapshot",
                "source_type": "managed_workspace",
                "lensnode_uuid": str(self.lensnode.uuid),
                "target_path": "/workspace/restores/missing",
                "config": {},
                "sync_policy": {},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["target_path"][0],
            "MANAGED_WORKSPACE_DIRECTORY_REQUIRED",
        )

    def test_managed_workspace_rejects_path_outside_workspace(self):
        response = self.client.post(
            "/api/lens/admin/datasources/",
            {
                "name": "Outside Snapshot",
                "source_type": "managed_workspace",
                "lensnode_uuid": str(self.lensnode.uuid),
                "target_path": "/etc/data",
                "config": {},
                "sync_policy": {},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["target_path"][0],
            "LENS_SOURCE_TARGET_PATH_INVALID",
        )

    @patch("lens.serializers.check_datasource_path")
    def test_managed_workspace_rejects_overlapping_datasource_path(
        self,
        check_path,
    ):
        response = self.client.post(
            "/api/lens/admin/datasources/",
            {
                "name": "Managed Parent",
                "source_type": "managed_workspace",
                "lensnode_uuid": str(self.lensnode.uuid),
                "target_path": "/workspace",
                "config": {},
                "sync_policy": {},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        check_path.assert_not_called()

        response = self.client.post(
            "/api/lens/admin/datasources/",
            {
                "name": "Managed Child",
                "source_type": "managed_workspace",
                "lensnode_uuid": str(self.lensnode.uuid),
                "target_path": "/workspace/repo-cache/restored",
                "config": {},
                "sync_policy": {},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("overlapping", response.data["target_path"][0])
        check_path.assert_not_called()

    def test_managed_workspace_manual_sync_is_rejected(self):
        datasource = DataSource.objects.create(
            name="Managed Snapshot",
            source_type=DataSource.SourceType.MANAGED_WORKSPACE,
            lensnode=self.lensnode,
            target_path="/workspace/restores/finance",
        )

        with patch(
            "lens.views.datasources.source_sync_task.apply_async"
        ) as apply_async:
            response = self.client.post(
                f"/api/lens/admin/datasources/{datasource.uuid}/sync/",
                {},
                format="json",
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data["detail"],
            "DATASOURCE_SYNC_NOT_SUPPORTED",
        )
        apply_async.assert_not_called()

    def test_managed_workspace_conversion_registers_trackable_task(self):
        datasource = DataSource.objects.create(
            name="Managed Snapshot",
            source_type=DataSource.SourceType.MANAGED_WORKSPACE,
            lensnode=self.lensnode,
            target_path="/workspace/restores/finance",
        )

        with patch(
            "lens.views.datasources.datasource_conversion_task.apply_async"
        ) as apply_async:
            response = self.client.post(
                f"/api/lens/admin/datasources/{datasource.uuid}/convert/",
                {
                    "conversion": {
                        "document": True,
                        "max_file_size_mb": 100,
                    },
                    "force": False,
                },
                format="json",
            )

        self.assertEqual(response.status_code, 202, response.data)
        task_id = response.data["task_id"]
        task = TaskExecution.objects.get(task_id=task_id)
        self.assertEqual(response.data["task_execution_id"], task.id)
        self.assertEqual(task.module, "lens_datasource_conversion")
        self.assertEqual(task.status, "PENDING")
        self.assertEqual(task.created_by, self.user)
        self.assertEqual(
            task.metadata["conversion"],
            {"document": True, "max_file_size_mb": 100},
        )
        apply_async.assert_called_once_with(
            args=[
                str(datasource.uuid),
                {"document": True, "max_file_size_mb": 100},
                False,
                task_id,
            ],
            task_id=ANY,
        )
        datasource.refresh_from_db()
        self.assertEqual(datasource.last_conversion_status, "PENDING")
        self.assertIsNone(datasource.last_conversion_at)
        detail = self.client.get(
            f"/api/lens/admin/datasources/{datasource.uuid}/"
        )
        self.assertEqual(detail.data["last_conversion_status"], "PENDING")
        self.assertIsNone(detail.data["last_conversion_at"])
        tasks = self.client.get(
            f"/api/lens/admin/datasources/{datasource.uuid}/"
            "conversion-tasks/"
        )
        self.assertEqual(tasks.status_code, 200)
        self.assertEqual(tasks.data["results"][0]["task_id"], task_id)

    def test_non_managed_datasource_conversion_is_rejected(self):
        with patch(
            "lens.views.datasources.datasource_conversion_task.apply_async"
        ) as apply_async:
            response = self.client.post(
                f"/api/lens/admin/datasources/{self.datasource.uuid}/convert/",
                {"conversion": {"document": True}},
                format="json",
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data["detail"],
            "DATASOURCE_CONVERSION_NOT_SUPPORTED",
        )
        apply_async.assert_not_called()

    def test_managed_workspace_conversion_validates_policy(self):
        datasource = DataSource.objects.create(
            name="Managed Snapshot",
            source_type=DataSource.SourceType.MANAGED_WORKSPACE,
            lensnode=self.lensnode,
            target_path="/workspace/restores/finance",
        )

        response = self.client.post(
            f"/api/lens/admin/datasources/{datasource.uuid}/convert/",
            {"conversion": {"document": "yes"}},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("conversion.document", response.data["conversion"][0])

    def test_managed_workspace_conversion_requires_admin(self):
        datasource = DataSource.objects.create(
            name="Managed Snapshot",
            source_type=DataSource.SourceType.MANAGED_WORKSPACE,
            lensnode=self.lensnode,
            target_path="/workspace/restores/finance",
        )
        user = User.objects.create_user(
            username="regular-user",
            email="regular-user@example.com",
            password="pass12345",
        )
        self.client.force_authenticate(user)

        response = self.client.post(
            f"/api/lens/admin/datasources/{datasource.uuid}/convert/",
            {"conversion": {"document": True}},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_cancel_managed_workspace_conversion_releases_lock(self):
        datasource = DataSource.objects.create(
            name="Managed Snapshot",
            source_type=DataSource.SourceType.MANAGED_WORKSPACE,
            lensnode=self.lensnode,
            target_path="/workspace/restores/finance",
            last_conversion_status="STARTED",
        )
        task = TaskExecution.objects.create(
            task_id="running-conversion",
            task_name="datasource_convert:Managed Snapshot",
            module="lens_datasource_conversion",
            status="STARTED",
            metadata={
                "datasource_uuid": str(datasource.uuid),
                "lock_token": "running-conversion",
                "celery_task_id": "celery-conversion",
            },
        )
        acquire_datasource_lock(
            datasource.uuid,
            token="running-conversion",
            ttl_s=60,
        )

        with (
            patch("core.celery.app.control.revoke") as revoke,
            patch(
                "lens.views.datasources."
                "cancel_datasource_conversion_on_lensnode"
            ) as cancel,
        ):
            response = self.client.post(
                f"/api/lens/admin/datasources/{datasource.uuid}/"
                "cancel-conversion/",
                {},
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.data)
        revoke.assert_called_once_with("celery-conversion", terminate=False)
        cancel.assert_called_once_with(self.lensnode, "running-conversion")
        task.refresh_from_db()
        datasource.refresh_from_db()
        self.assertEqual(task.status, "REVOKED")
        self.assertEqual(datasource.last_conversion_status, "REVOKED")
        self.assertIsNotNone(datasource.last_conversion_at)

        acquire_datasource_lock(
            datasource.uuid,
            token="new-conversion",
            ttl_s=60,
        )
        release_datasource_lock(
            datasource.uuid,
            token="new-conversion",
        )

    @patch("lens.views.datasources.check_datasource_path")
    def test_managed_workspace_refresh_updates_availability(self, check_path):
        datasource = DataSource.objects.create(
            name="Managed Snapshot",
            source_type=DataSource.SourceType.MANAGED_WORKSPACE,
            lensnode=self.lensnode,
            target_path="/workspace/restores/finance",
            availability_status=DataSource.AvailabilityStatus.AVAILABLE,
        )
        check_path.return_value = {
            "status": "blocked",
            "exists": False,
            "is_directory": False,
            "message": "Managed workspace directory does not exist.",
        }

        response = self.client.post(
            f"/api/lens/admin/datasources/{datasource.uuid}/"
            "refresh-availability/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["availability_status"], "unavailable")
        datasource.refresh_from_db()
        self.assertIsNotNone(datasource.availability_checked_at)

        check_path.side_effect = DataSourceDispatchError("LENSNODE_OFFLINE")
        response = self.client.post(
            f"/api/lens/admin/datasources/{datasource.uuid}/"
            "refresh-availability/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["availability_status"], "error")
        self.assertEqual(
            response.data["availability_message"],
            "LENSNODE_OFFLINE",
        )

    @patch("lens.serializers.check_datasource_path")
    def test_managed_workspace_metadata_update_skips_path_check(
        self,
        check_path,
    ):
        datasource = DataSource.objects.create(
            name="Managed Snapshot",
            source_type=DataSource.SourceType.MANAGED_WORKSPACE,
            lensnode=self.lensnode,
            target_path="/workspace/restores/finance",
        )

        response = self.client.patch(
            f"/api/lens/admin/datasources/{datasource.uuid}/",
            {"name": "Renamed Snapshot"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        check_path.assert_not_called()

    def test_managed_workspace_delete_only_removes_catalog_record(self):
        datasource = DataSource.objects.create(
            name="Managed Snapshot",
            source_type=DataSource.SourceType.MANAGED_WORKSPACE,
            lensnode=self.lensnode,
            target_path="/workspace/restores/finance",
        )

        with patch("lens.datasource_services._send_lensnode_command") as send:
            response = self.client.delete(
                f"/api/lens/admin/datasources/{datasource.uuid}/"
            )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(DataSource.objects.filter(pk=datasource.pk).exists())
        send.assert_not_called()

    def test_datasource_manual_sync_registers_task(self):
        with patch(
            "lens.views.datasources.source_sync_task.apply_async"
        ) as apply_async:
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
            args=[str(self.datasource.uuid), "manual", task_id],
            task_id=ANY,
        )
        celery_task_id = apply_async.call_args.kwargs["task_id"]
        self.assertNotEqual(celery_task_id, task_id)
        task = TaskExecution.objects.get(task_id=task_id)
        self.assertEqual(task.task_name, "datasource_sync:Repo Cache")
        self.assertEqual(task.module, "lens_datasource")
        self.assertEqual(task.status, "PENDING")
        self.assertEqual(task.created_by, self.user)
        self.assertEqual(task.metadata["celery_task_id"], celery_task_id)

    def test_disabled_datasource_rejects_manual_sync(self):
        self.datasource.status = DataSource.Status.DISABLED
        self.datasource.save(update_fields=["status", "updated_at"])

        with patch(
            "lens.views.datasources.source_sync_task.apply_async"
        ) as apply_async:
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
                "celery_task_id": "celery-sync",
            },
        )
        acquire_datasource_lock(
            self.datasource.uuid,
            token="running-sync",
            ttl_s=60,
        )

        with (
            patch("core.celery.app.control.revoke") as revoke,
            patch(
                "lens.views.datasources.cancel_datasource_sync_on_lensnode"
            ) as cancel,
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
            "celery-sync",
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

    def test_datasource_allows_git_no_auth_credential_binding(self):
        credential = DataSourceCredential.objects.create(
            name="Public GitHub repo",
            provider=DataSourceCredential.Provider.GITHUB,
            auth_type=DataSourceCredential.AuthType.NONE,
            endpoint_url="https://github.com",
            scope_config={
                "organization_url": "https://github.com/example/repo"
            },
        )
        payload = {
            "name": "Public Repo",
            "source_type": "git",
            "lensnode_uuid": str(self.lensnode.uuid),
            "credential_uuid": str(credential.uuid),
            "config": {
                "repo_url": "https://github.com/example/repo.git",
                "auth_scheme": "none",
            },
            "target_path": "/workspace/public-repo",
        }

        response = self.client.post(
            "/api/lens/admin/datasources/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertFalse(credential.has_secret)
        datasource = DataSource.objects.get(uuid=response.data["uuid"])
        self.assertEqual(datasource.credential, credential)
        self.assertNotIn("access_token", datasource.config)

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
            "lens.views.lensnodes.test_datasource_connection",
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

    def test_git_connection_test_injects_github_token_credential(self):
        credential = DataSourceCredential.objects.create(
            name="GitHub token",
            provider=DataSourceCredential.Provider.GITHUB,
            auth_type=DataSourceCredential.AuthType.HTTPS_TOKEN,
            endpoint_url="https://github.com",
            sync_scope="service",
            scope_config={
                "organization_url": "https://github.com/CarltonXu/"
            },
        )
        credential.set_secret("ghp_example")
        credential.save()
        sent_payloads = []

        def capture_command(_lensnode, payload):
            sent_payloads.append(payload)

        with (
            patch(
                "lens.datasource_services._send_lensnode_command",
                side_effect=capture_command,
            ),
            patch(
                "lens.datasource_services._wait_cache_result",
                return_value={"status": "success"},
            ),
        ):
            test_datasource_connection(
                self.lensnode,
                "git",
                config={
                    "repo_url": "https://github.com/CarltonXu/",
                    "auth_scheme": "token",
                },
                credential_uuid=str(credential.uuid),
            )

        config = sent_payloads[0]["config"]
        self.assertEqual(config["provider"], "github")
        self.assertEqual(config["endpoint_url"], "https://github.com")
        self.assertEqual(config["access_token"], "ghp_example")
        self.assertEqual(
            config["credential_scope"]["organization_url"],
            "https://github.com/CarltonXu/",
        )

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
            description="Answers private workspace questions.",
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
        self.assertEqual(resp.data["description"], self.assistant.description)

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

    def test_archived_assistant_cannot_start_new_conversations(self):
        self.assistant.visibility = Assistant.Visibility.PUBLIC
        self.assistant.status = "archived"
        self.assistant.save(update_fields=["visibility", "status"])
        client = self._client(self.member)

        response = client.post(
            "/api/lens/sessions/",
            {"assistant_uuid": str(self.assistant.uuid)},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_public_qa_requires_login_for_private_assistant(self):
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
        self.assertEqual(list_resp.status_code, 403)
        self.assertEqual(
            list_resp.data["code"],
            "AUTHENTICATION_REQUIRED",
        )
        single_resp = self.client.get(
            f"/api/lens/public/qa/{share.token}/"
        )
        self.assertEqual(single_resp.status_code, 403)
        self.assertEqual(
            single_resp.data["code"],
            "AUTHENTICATION_REQUIRED",
        )

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

    def test_user_access_grants_include_selector_metadata(self):
        user = User.objects.create_user(
            username="selector-user",
            email="selector@example.com",
            password="x",
        )
        client = self._client(self.admin)
        resp = client.patch(
            f"/api/lens/assistants/{self.assistant.uuid}/",
            {
                "visibility": "private",
                "access_grants": [{"type": "user", "id": user.pk}],
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.data["access_grants"],
            [
                {
                    "type": "user",
                    "id": user.pk,
                    "name": "selector-user",
                    "username": "selector-user",
                    "email": "selector@example.com",
                }
            ],
        )

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

        archive = client.post(
            f"/api/lens/assistants/{self.assistant.uuid}/archive/",
        )
        self.assertEqual(archive.status_code, 403)


class AdminAccessSubjectTests(TestCase):
    """Admin user/group insights and stable history filters."""

    def setUp(self):
        self.node = LensNode.objects.create(
            name="Access detail node",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            tasks=[{"name": "general_chat", "description": "chat"}],
        )
        self.admin = User.objects.create_user(
            username="access-admin",
            password="x",
            is_staff=True,
        )
        self.user = User.objects.create_user(
            username="detail-user",
            email="detail@example.com",
            password="x",
        )
        self.group = Group.objects.create(name="Detail group")
        self.user.groups.add(self.group)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _assistant(self, name, slug, visibility="private"):
        return Assistant.objects.create(
            name=name,
            slug=slug,
            lensnode=self.node,
            selected_task="general_chat",
            visibility=visibility,
        )

    def test_user_detail_combines_access_sources_and_activity(self):
        direct = self._assistant("Direct", "detail-direct")
        grouped = self._assistant("Grouped", "detail-grouped")
        public = self._assistant(
            "Public",
            "detail-public",
            Assistant.Visibility.PUBLIC,
        )
        history = self._assistant("History", "detail-history")
        AssistantAccess.objects.create(assistant=direct, user=self.user)
        AssistantAccess.objects.create(assistant=grouped, group=self.group)
        session = Session.objects.create(
            assistant=history,
            user=self.user,
        )
        create_execution_run(session, "History question", enqueue=False)

        response = self.client.get(
            f"/api/lens/admin/access/users/{self.user.pk}/"
        )

        self.assertEqual(response.status_code, 200, response.data)
        rows = {item["slug"]: item for item in response.data["assistants"]}
        self.assertEqual(rows[direct.slug]["access_sources"], ["direct"])
        self.assertEqual(rows[grouped.slug]["access_sources"], ["group"])
        self.assertEqual(rows[public.slug]["access_sources"], ["public"])
        self.assertEqual(rows[history.slug]["access_sources"], ["history"])
        self.assertEqual(rows[history.slug]["conversations"], 1)
        self.assertEqual(rows[history.slug]["qa_records"], 1)
        self.assertEqual(response.data["stats"]["conversations"], 1)
        self.assertEqual(response.data["stats"]["qa_records"], 1)

    def test_group_detail_paginates_searches_and_counts(self):
        second = User.objects.create_user(
            username="another-member",
            email="another@example.com",
            password="x",
        )
        second.groups.add(self.group)
        assistant = self._assistant("Group assistant", "group-assistant")
        AssistantAccess.objects.create(assistant=assistant, group=self.group)
        role = Role.objects.create(
            name="Group admin",
            visible_features=["admin_console"],
        )
        role.groups.add(self.group)

        response = self.client.get(
            f"/api/lens/admin/access/groups/{self.group.pk}/",
            {"search": "detail@", "page": 1, "page_size": 1},
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["stats"]["members"], 2)
        self.assertEqual(response.data["stats"]["assigned_assistants"], 1)
        self.assertEqual(response.data["stats"]["roles"], 1)
        self.assertEqual(response.data["members"]["count"], 1)
        self.assertEqual(
            response.data["members"]["results"][0]["id"],
            self.user.pk,
        )
        self.assertEqual(
            response.data["assistants"][0]["access_sources"],
            ["group"],
        )

    def test_history_filters_by_exact_user_group_and_assistant(self):
        assistant = self._assistant("Filtered", "filtered-assistant")
        other = User.objects.create_user(
            username="other-detail-user",
            password="x",
        )
        other.groups.add(self.group)
        first_session = Session.objects.create(
            assistant=assistant,
            user=self.user,
        )
        second_session = Session.objects.create(
            assistant=assistant,
            user=other,
        )
        first = create_execution_run(
            first_session,
            "First question",
            enqueue=False,
        )
        create_execution_run(second_session, "Second question", enqueue=False)

        response = self.client.get(
            "/api/lens/admin/runs/",
            {
                "user_id": self.user.pk,
                "group_id": self.group.pk,
                "assistant": assistant.slug,
            },
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["results"][0]["uuid"], str(first.uuid))

    def test_role_granted_admin_can_open_detail_and_history(self):
        role = Role.objects.create(
            name="Role granted admin",
            visible_features=["admin_console"],
        )
        role.users.add(self.user)
        client = APIClient()
        client.force_authenticate(self.user)

        detail = client.get(
            f"/api/lens/admin/access/users/{self.user.pk}/"
        )
        history = client.get("/api/lens/admin/runs/")

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(history.status_code, 200)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class AssistantArchiveConcurrencyTests(TransactionTestCase):
    """Serialize assistant archival with creation of new work."""

    def setUp(self):
        self.lensnode = LensNode.objects.create(
            name="Archive Race Node",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            workspace_path="/workspace",
        )
        self.assistant = Assistant.objects.create(
            name="Archive Race Assistant",
            slug="archive-race-assistant",
            lensnode=self.lensnode,
            selected_task="knowledge_qa",
            selected_dirs=[{"path": "/workspace/repo"}],
            visibility=Assistant.Visibility.PUBLIC,
            multimodal_model_ref=uuid.uuid4(),
        )
        self.user = User.objects.create_user(
            username="archive-race-user",
            password="x",
        )
        self.admin = User.objects.create_user(
            username="archive-race-admin",
            password="x",
            is_staff=True,
        )

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def _race_new_work_with_archive(self, create_request):
        check_entered = threading.Event()
        release_check = threading.Event()
        archive_finished = threading.Event()
        responses = {}
        errors = []
        original_check = Assistant.is_runnable_by

        def pause_after_check(assistant, user):
            allowed = original_check(assistant, user)
            if threading.current_thread().name == "new-assistant-work":
                check_entered.set()
                if not release_check.wait(timeout=5):
                    raise TimeoutError("Timed out waiting to resume creation")
            return allowed

        def run_create_request():
            close_old_connections()
            try:
                responses["create"] = create_request()
            except Exception as exc:
                errors.append(exc)
            finally:
                close_old_connections()

        def run_archive_request():
            close_old_connections()
            try:
                responses["archive"] = self._client(self.admin).post(
                    f"/api/lens/assistants/{self.assistant.uuid}/archive/"
                )
            except Exception as exc:
                errors.append(exc)
            finally:
                archive_finished.set()
                close_old_connections()

        with patch.object(Assistant, "is_runnable_by", pause_after_check):
            create_thread = threading.Thread(
                target=run_create_request,
                name="new-assistant-work",
            )
            archive_thread = threading.Thread(
                target=run_archive_request,
                name="archive-assistant",
            )
            create_thread.start()
            self.assertTrue(check_entered.wait(timeout=5))
            archive_thread.start()
            archive_overtook_creation = archive_finished.wait(timeout=1)
            release_check.set()
            create_thread.join(timeout=5)
            archive_thread.join(timeout=5)

        self.assertFalse(create_thread.is_alive())
        self.assertFalse(archive_thread.is_alive())
        if errors:
            raise errors[0]
        self.assertFalse(archive_overtook_creation)
        self.assertEqual(responses["create"].status_code, 201)
        self.assertEqual(responses["archive"].status_code, 200)
        self.assistant.refresh_from_db()
        self.assertEqual(self.assistant.status, Assistant.Status.ARCHIVED)

    def test_archive_waits_for_session_creation(self):
        initial_count = Session.objects.count()

        self._race_new_work_with_archive(
            lambda: self._client(self.user).post(
                "/api/lens/sessions/",
                {"assistant_uuid": str(self.assistant.uuid)},
                format="json",
            )
        )

        self.assertEqual(Session.objects.count(), initial_count + 1)

    def test_archive_waits_for_run_creation(self):
        session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        initial_count = Run.objects.count()

        self._race_new_work_with_archive(
            lambda: self._client(self.user).post(
                f"/api/lens/sessions/{session.uuid}/runs/",
                {"question": "Explain the race", "enqueue": False},
                format="json",
            )
        )

        self.assertEqual(Run.objects.count(), initial_count + 1)

    def test_archive_waits_for_attachment_creation(self):
        session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
        )
        initial_count = MessageAttachment.objects.count()

        def upload_attachment():
            from PIL import Image

            image = io.BytesIO()
            Image.new("RGB", (2, 2), (120, 200, 80)).save(
                image,
                format="PNG",
            )
            uploaded = SimpleUploadedFile(
                "race.png",
                image.getvalue(),
                content_type="image/png",
            )
            return self._client(self.user).post(
                f"/api/lens/sessions/{session.uuid}/attachments/",
                {"file": uploaded},
                format="multipart",
            )

        self._race_new_work_with_archive(upload_attachment)

        self.assertEqual(
            MessageAttachment.objects.count(),
            initial_count + 1,
        )


@override_settings(CACHES=TEST_CACHES, CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class DataSourceArchiveUploadTests(TestCase):
    """Cover file datasource upload validation and private delivery."""

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.archive_storage = tempfile.TemporaryDirectory()
        storage_settings = {
            **settings.STORAGES,
            "datasource_archives": {
                "BACKEND": "django.core.files.storage.FileSystemStorage",
                "OPTIONS": {"location": self.archive_storage.name},
            },
        }
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media.name,
            STORAGES=storage_settings,
        )
        self.settings_override.enable()
        self.user = User.objects.create_user(
            username="archive-admin",
            email="archive-admin@example.com",
            password="pass12345",
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.token = "archive-node-token"
        self.lensnode = LensNode.objects.create(
            name="Archive LensNode",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            workspace_path="/workspace",
            auth_token_hash=hash_lensnode_token(self.token),
        )

    def tearDown(self):
        self.settings_override.disable()
        self.archive_storage.cleanup()
        self.media.cleanup()

    def _metadata(self, **overrides):
        payload = {
            "name": "Uploaded Documents",
            "lensnode_uuid": str(self.lensnode.uuid),
            "target_path": "/workspace/uploaded-documents",
            "config": {},
            "sync_policy": {"conversion": {"document": True}},
            "status": "active",
        }
        payload.update(overrides)
        return payload

    def test_upload_creates_file_datasource_and_trackable_task(self):
        with patch(
            "lens.views.datasources.source_sync_task.apply_async"
        ) as apply_async:
            response = self.client.post(
                "/api/lens/admin/datasources/upload/",
                {
                    "metadata": json.dumps(self._metadata()),
                    "file": datasource_zip_upload(
                        {"docs/readme.txt": "hello"}
                    ),
                },
                format="multipart",
            )

        self.assertEqual(response.status_code, 201, response.data)
        datasource = DataSource.objects.get(uuid=response.data["uuid"])
        self.assertEqual(datasource.source_type, DataSource.SourceType.FILE)
        self.assertFalse(
            ScheduledTask.objects.filter(target_id=datasource.uuid).exists()
        )
        task = TaskExecution.objects.get(
            task_id=response.data["initial_sync_task_id"]
        )
        self.assertEqual(task.metadata["archive"]["archive_type"], "zip")
        self.assertEqual(len(task.metadata["archive"]["content_hash"]), 64)
        storage_name = task.metadata["archive"]["storage_name"]
        self.assertTrue(
            storages["datasource_archives"].exists(storage_name)
        )
        self.assertFalse(default_storage.exists(storage_name))
        apply_async.assert_called_once()

    def test_upload_rejects_archive_path_traversal(self):
        response = self.client.post(
            "/api/lens/admin/datasources/upload/",
            {
                "metadata": json.dumps(self._metadata()),
                "file": datasource_zip_upload({"../escape.txt": "unsafe"}),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("DATASOURCE_ARCHIVE_PATH_INVALID", str(response.data))
        self.assertFalse(
            DataSource.objects.filter(
                source_type=DataSource.SourceType.FILE
            ).exists()
        )

    def test_upload_rejects_excessive_compression_ratio(self):
        response = self.client.post(
            "/api/lens/admin/datasources/upload/",
            {
                "metadata": json.dumps(self._metadata()),
                "file": datasource_zip_upload(
                    {"highly-compressible.txt": b"0" * (2 * 1024 * 1024)}
                ),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("DATASOURCE_ARCHIVE_RATIO_TOO_HIGH", str(response.data))

    def test_zip_member_limit_is_checked_before_zipfile_materialization(self):
        upload = datasource_zip_many_members(10_001)

        with patch("lens.datasource_archives.zipfile.ZipFile") as zip_file:
            response = self.client.post(
                "/api/lens/admin/datasources/upload/",
                {
                    "metadata": json.dumps(self._metadata()),
                    "file": upload,
                },
                format="multipart",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "DATASOURCE_ARCHIVE_TOO_MANY_MEMBERS",
            str(response.data),
        )
        zip_file.assert_not_called()

    def test_tar_member_limit_does_not_materialize_all_members(self):
        upload = datasource_tar_many_members(10_001)

        with patch.object(
            tarfile.TarFile,
            "getmembers",
            side_effect=AssertionError("getmembers must not be used"),
        ):
            response = self.client.post(
                "/api/lens/admin/datasources/upload/",
                {
                    "metadata": json.dumps(self._metadata()),
                    "file": upload,
                },
                format="multipart",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "DATASOURCE_ARCHIVE_TOO_MANY_MEMBERS",
            str(response.data),
        )

    def test_disabled_file_datasource_allows_metadata_updates(self):
        with patch("lens.views.datasources.source_sync_task.apply_async"):
            created = self.client.post(
                "/api/lens/admin/datasources/upload/",
                {
                    "metadata": json.dumps(self._metadata()),
                    "file": datasource_zip_upload({"readme.txt": "hello"}),
                },
                format="multipart",
            )
        datasource_uuid = created.data["uuid"]
        disabled = self.client.patch(
            f"/api/lens/admin/datasources/{datasource_uuid}/",
            {"status": "disabled"},
            format="json",
        )
        updated = self.client.patch(
            f"/api/lens/admin/datasources/{datasource_uuid}/",
            {"name": "Renamed Upload"},
            format="json",
        )

        self.assertEqual(disabled.status_code, 200, disabled.data)
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["name"], "Renamed Upload")

    def test_reupload_registers_full_replace_task(self):
        with patch("lens.views.datasources.source_sync_task.apply_async"):
            created = self.client.post(
                "/api/lens/admin/datasources/upload/",
                {
                    "metadata": json.dumps(self._metadata()),
                    "file": datasource_zip_upload({"old.txt": "old"}),
                },
                format="multipart",
            )
            response = self.client.post(
                (
                    f"/api/lens/admin/datasources/{created.data['uuid']}/"
                    "reupload/"
                ),
                {
                    "metadata": json.dumps({}),
                    "file": datasource_zip_upload({"new.txt": "new"}),
                },
                format="multipart",
            )

        self.assertEqual(response.status_code, 202, response.data)
        task = TaskExecution.objects.get(task_id=response.data["task_id"])
        self.assertEqual(task.metadata["trigger"], "reupload")
        self.assertEqual(
            task.metadata["archive"]["original_name"],
            "documents.zip",
        )

    def test_archive_download_is_lensnode_and_task_bound(self):
        with patch("lens.views.datasources.source_sync_task.apply_async"):
            response = self.client.post(
                "/api/lens/admin/datasources/upload/",
                {
                    "metadata": json.dumps(self._metadata()),
                    "file": datasource_zip_upload({"readme.txt": "hello"}),
                },
                format="multipart",
            )
        datasource_uuid = response.data["uuid"]
        task_id = response.data["initial_sync_task_id"]
        node_client = APIClient()
        download = node_client.get(
            (
                f"/api/lens/lensnode/datasources/{datasource_uuid}/"
                f"archives/{task_id}/"
            ),
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )

        self.assertEqual(download.status_code, 200)
        self.assertTrue(download["X-Archive-Hash"])
        self.assertTrue(collect_stream(download.streaming_content))

        denied = node_client.get(
            (
                f"/api/lens/lensnode/datasources/{datasource_uuid}/"
                f"archives/{task_id}/"
            ),
            HTTP_AUTHORIZATION="Bearer wrong-token",
        )
        self.assertEqual(denied.status_code, 401)
