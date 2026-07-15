from pathlib import PurePosixPath
from urllib import parse

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from .datasource_services import (
    DataSourceDispatchError,
    DataSourcePathError,
    normalize_workspace_target_path,
    validate_datasource_lensnode,
)
from .model_checks import check_assistant_model_refs
from .models import (
    Assistant,
    AssistantAccess,
    AssistantMCP,
    AssistantSkill,
    DataSource,
    DataSourceCredential,
    GlobalSetting,
    MCPServer,
    Message,
    MessageAttachment,
    LensNode,
    Run,
    RunExecution,
    RunOutputFile,
    RunStep,
    ScheduledTask,
    Session,
    SharedQA,
    Skill,
)
from .attachments import ATTACHMENT_MAX_PER_MESSAGE
from .services import create_execution_run
from .skill_generation import (
    get_workspace_guide_payload,
    sync_workspace_guide_skill,
)

User = get_user_model()


def _task_names(lensnode):
    """Return task names reported by a LensNode."""

    names = set()
    for task in lensnode.tasks or []:
        if isinstance(task, dict) and task.get("name"):
            names.add(task["name"])
    return names


def _dir_paths(lensnode):
    """Return available directory paths reported by a LensNode."""

    paths = set()
    for item in lensnode.available_dirs or []:
        if isinstance(item, str):
            paths.add(item)
        elif isinstance(item, dict) and item.get("path"):
            paths.add(item["path"])
    return paths


def validate_retrieval_scope(value):
    """Validate retrieval_scope JSON."""

    if value is None:
        return None
    if not isinstance(value, dict):
        raise serializers.ValidationError("retrieval_scope must be an object or null")

    list_fields = [
        "include_paths",
        "exclude_paths",
        "exclude_extensions",
    ]
    for field in list_fields:
        items = value.get(field)
        if items is not None and (
            not isinstance(items, list)
            or any(not isinstance(item, str) for item in items)
        ):
            raise serializers.ValidationError(
                f"retrieval_scope.{field} must be a list of strings"
            )

    max_depth = value.get("max_depth")
    if max_depth is not None and (not isinstance(max_depth, int) or max_depth <= 0):
        raise serializers.ValidationError(
            "retrieval_scope.max_depth must be a positive integer"
        )

    return value


def validate_selected_dirs(value, lensnode=None):
    """Validate selected_dirs payload against LensNode availability."""

    if not isinstance(value, list):
        raise serializers.ValidationError("selected_dirs must be a list")

    available = _dir_paths(lensnode) if lensnode else None
    for item in value:
        if not isinstance(item, dict):
            raise serializers.ValidationError("selected_dirs items must be objects")
        path = item.get("path")
        if not isinstance(path, str) or not path:
            raise serializers.ValidationError("selected_dirs.path is required")
        if available is not None and path not in available:
            raise serializers.ValidationError(
                f"selected_dirs path is not available on LensNode: {path}"
            )
        if "retrieval_scope" in item:
            validate_retrieval_scope(item.get("retrieval_scope"))
    return value


class LensNodeSerializer(serializers.ModelSerializer):
    """LensNode serializer."""

    has_token = serializers.SerializerMethodField()

    class Meta:
        model = LensNode
        fields = [
            "uuid",
            "name",
            "status",
            "connection_id",
            "workspace_path",
            "available_dirs",
            "protocol_version",
            "agent_version",
            "tasks",
            "labels",
            "enrollment_status",
            "token_issued_at",
            "token_revoked",
            "has_token",
            "last_authenticated_at",
            "last_heartbeat_at",
            "registered_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "uuid",
            "status",
            "connection_id",
            "token_issued_at",
            "last_authenticated_at",
            "last_heartbeat_at",
            "registered_at",
            "created_at",
            "updated_at",
        ]

    def get_has_token(self, obj):
        """Whether the node currently has a usable (un-revoked) token."""

        return bool(obj.auth_token_hash) and not obj.token_revoked


class SkillBindingsField(serializers.Field):
    """Read/write field for assistant skill bindings."""

    def to_representation(self, bindings):
        bindings = bindings.select_related("skill").all()
        return [
            {
                "skill_uuid": str(binding.skill.uuid),
                "skill_name": binding.skill.name,
                "enabled": binding.enabled,
                "load_config": binding.load_config,
            }
            for binding in bindings
        ]

    def to_internal_value(self, data):
        if not isinstance(data, list):
            raise serializers.ValidationError("Expected a list of bindings.")

        validated = []
        for item in data:
            if not isinstance(item, dict):
                raise serializers.ValidationError("Each binding must be an object.")
            if "skill_uuid" not in item:
                raise serializers.ValidationError("Missing skill_uuid in binding.")
            validated.append(
                {
                    "skill_uuid": item["skill_uuid"],
                    "enabled": item.get("enabled", True),
                    "load_config": item.get("load_config", {}),
                }
            )
        return validated


class McpBindingsField(serializers.Field):
    """Read/write field for assistant MCP bindings."""

    def to_representation(self, bindings):
        bindings = bindings.select_related("mcp").all()
        return [
            {
                "mcp_uuid": str(binding.mcp.uuid),
                "mcp_name": binding.mcp.name,
                "enabled": binding.enabled,
                "load_config": binding.load_config,
            }
            for binding in bindings
        ]

    def to_internal_value(self, data):
        if not isinstance(data, list):
            raise serializers.ValidationError("Expected a list of bindings.")

        validated = []
        for item in data:
            if not isinstance(item, dict):
                raise serializers.ValidationError("Each binding must be an object.")
            if "mcp_uuid" not in item:
                raise serializers.ValidationError("Missing mcp_uuid in binding.")
            validated.append(
                {
                    "mcp_uuid": item["mcp_uuid"],
                    "enabled": item.get("enabled", True),
                    "load_config": item.get("load_config", {}),
                }
            )
        return validated


class AccessGrantsField(serializers.Field):
    """Read/write field for assistant access grants (group or user)."""

    def to_representation(self, grants):
        grants = grants.select_related("group", "user").all()
        result = []
        for grant in grants:
            if grant.group_id:
                result.append(
                    {
                        "type": "group",
                        "id": grant.group_id,
                        "name": grant.group.name,
                    }
                )
            elif grant.user_id:
                result.append(
                    {
                        "type": "user",
                        "id": grant.user_id,
                        "name": grant.user.get_username(),
                    }
                )
        return result

    def to_internal_value(self, data):
        if not isinstance(data, list):
            raise serializers.ValidationError("Expected a list of grants.")

        validated = []
        seen = set()
        for item in data:
            if not isinstance(item, dict):
                raise serializers.ValidationError(
                    "Each grant must be an object."
                )
            grant_type = item.get("type")
            grant_id = item.get("id")
            if grant_type not in ("group", "user") or grant_id is None:
                raise serializers.ValidationError(
                    "Each grant needs type (group|user) and id."
                )
            key = (grant_type, grant_id)
            if key in seen:
                continue
            seen.add(key)
            validated.append({"type": grant_type, "id": grant_id})
        return validated


class AssistantSerializer(serializers.ModelSerializer):
    """Assistant serializer with LensNode and capability validation."""

    lensnode_uuid = serializers.UUIDField(write_only=True, required=False)
    lensnode = serializers.UUIDField(source="lensnode.uuid", read_only=True)
    skill_bindings = SkillBindingsField(required=False)
    mcp_bindings = McpBindingsField(required=False)
    access_grants = AccessGrantsField(required=False)
    workspace_guide = serializers.JSONField(required=False)
    skill_summary = serializers.SerializerMethodField()
    mcp_summary = serializers.SerializerMethodField()

    class Meta:
        model = Assistant
        fields = [
            "uuid",
            "name",
            "slug",
            "lensnode",
            "lensnode_uuid",
            "selected_task",
            "selected_dirs",
            "multimodal_model_ref",
            "agent_model_ref",
            "agent_rounds",
            "max_concurrency",
            "settings",
            "status",
            "visibility",
            "skill_bindings",
            "mcp_bindings",
            "access_grants",
            "workspace_guide",
            "skill_summary",
            "mcp_summary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "uuid",
            "lensnode",
            "skill_summary",
            "mcp_summary",
            "created_at",
            "updated_at",
        ]

    def get_skill_summary(self, assistant):
        """Return skill binding summary for list views."""

        enabled = assistant.skill_bindings.filter(enabled=True).count()
        return {
            "total": assistant.skill_bindings.count(),
            "enabled": enabled,
        }

    def get_mcp_summary(self, assistant):
        """Return MCP binding summary for list views."""

        enabled = assistant.mcp_bindings.filter(enabled=True).count()
        return {
            "total": assistant.mcp_bindings.count(),
            "enabled": enabled,
        }

    def to_representation(self, instance):
        """Return assistant data including generated Workspace Guide state."""

        data = super().to_representation(instance)
        data["workspace_guide"] = get_workspace_guide_payload(instance)
        return data

    def validate(self, attrs):
        """Validate selected task and directories against LensNode reports."""

        lensnode_uuid = attrs.pop("lensnode_uuid", None)
        if lensnode_uuid is not None:
            attrs["lensnode"] = LensNode.objects.get(uuid=lensnode_uuid)
        lensnode = attrs.get(
            "lensnode",
            getattr(self.instance, "lensnode", None),
        )
        if lensnode is None:
            raise serializers.ValidationError(
                {"lensnode_uuid": "lensnode_uuid is required"}
            )

        selected_task = attrs.get(
            "selected_task",
            getattr(self.instance, "selected_task", ""),
        )
        if selected_task not in _task_names(lensnode):
            raise serializers.ValidationError(
                {"selected_task": "selected_task is not available on LensNode"}
            )

        selected_dirs = attrs.get(
            "selected_dirs",
            getattr(self.instance, "selected_dirs", []),
        )
        if selected_task == "general_chat":
            attrs["selected_dirs"] = []
            skill_bindings = attrs.get("skill_bindings")
            if skill_bindings is None and self.instance is not None:
                has_enabled_skill = self.instance.skill_bindings.filter(
                    enabled=True,
                    skill__enabled=True,
                ).exists()
            else:
                enabled_skill_uuids = [
                    binding.get("skill_uuid")
                    for binding in (skill_bindings or [])
                    if binding.get("enabled", True)
                ]
                has_enabled_skill = Skill.objects.filter(
                    uuid__in=enabled_skill_uuids,
                    enabled=True,
                ).exists()
            if not has_enabled_skill:
                raise serializers.ValidationError(
                    {
                        "skill_bindings": (
                            "general_chat requires at least one enabled skill"
                        )
                    }
                )
        else:
            validate_selected_dirs(selected_dirs, lensnode)
        return attrs

    def _sync_bindings(self, assistant, validated_data):
        skill_bindings = validated_data.pop("skill_bindings", None)
        mcp_bindings = validated_data.pop("mcp_bindings", None)

        if skill_bindings is not None:
            assistant.skill_bindings.all().delete()
            for binding in skill_bindings:
                skill = Skill.objects.get(uuid=binding["skill_uuid"])
                AssistantSkill.objects.create(
                    assistant=assistant,
                    skill=skill,
                    enabled=binding.get("enabled", True),
                    load_config=binding.get("load_config", {}),
                )

        if mcp_bindings is not None:
            assistant.mcp_bindings.all().delete()
            for binding in mcp_bindings:
                mcp = MCPServer.objects.get(uuid=binding["mcp_uuid"])
                AssistantMCP.objects.create(
                    assistant=assistant,
                    mcp=mcp,
                    enabled=binding.get("enabled", True),
                    load_config=binding.get("load_config", {}),
                )

    def _sync_access_grants(self, assistant, grants):
        if grants is None:
            return
        request = self.context.get("request")
        granted_by = getattr(request, "user", None)
        if granted_by is not None and not granted_by.is_authenticated:
            granted_by = None
        assistant.access_grants.all().delete()
        for grant in grants:
            if grant["type"] == "group":
                group = Group.objects.filter(pk=grant["id"]).first()
                if group is None:
                    raise serializers.ValidationError(
                        {"access_grants": f"Group {grant['id']} not found."}
                    )
                AssistantAccess.objects.create(
                    assistant=assistant,
                    group=group,
                    granted_by=granted_by,
                )
            else:
                user = get_user_model().objects.filter(pk=grant["id"]).first()
                if user is None:
                    raise serializers.ValidationError(
                        {"access_grants": f"User {grant['id']} not found."}
                    )
                AssistantAccess.objects.create(
                    assistant=assistant,
                    user=user,
                    granted_by=granted_by,
                )

    def create(self, validated_data):
        """Create assistant and optional bindings."""

        skill_bindings = validated_data.pop("skill_bindings", None)
        mcp_bindings = validated_data.pop("mcp_bindings", None)
        access_grants = validated_data.pop("access_grants", None)
        workspace_guide = validated_data.pop("workspace_guide", None)
        assistant = Assistant.objects.create(**validated_data)
        self._sync_bindings(
            assistant,
            {
                "skill_bindings": skill_bindings,
                "mcp_bindings": mcp_bindings,
            },
        )
        self._sync_access_grants(assistant, access_grants)
        sync_workspace_guide_skill(assistant, workspace_guide)
        check_assistant_model_refs(assistant)
        return assistant

    def update(self, instance, validated_data):
        """Update assistant and optional bindings."""

        access_grants = validated_data.pop("access_grants", None)
        workspace_guide = validated_data.pop("workspace_guide", None)
        self._sync_bindings(instance, validated_data)
        assistant = super().update(instance, validated_data)
        self._sync_access_grants(assistant, access_grants)
        sync_workspace_guide_skill(assistant, workspace_guide)
        check_assistant_model_refs(assistant)
        return assistant


class DataSourceSerializer(serializers.ModelSerializer):
    """Datasource serializer."""

    lensnode_uuid = serializers.UUIDField(write_only=True, required=False)
    credential_uuid = serializers.UUIDField(
        write_only=True,
        required=False,
        allow_null=True,
    )
    lensnode = serializers.UUIDField(source="lensnode.uuid", read_only=True)
    lensnode_name = serializers.CharField(
        source="lensnode.name",
        read_only=True,
    )
    credential = serializers.UUIDField(
        source="credential.uuid",
        read_only=True,
    )
    credential_configured = serializers.SerializerMethodField()
    current_sync = serializers.SerializerMethodField()
    sync_state = serializers.SerializerMethodField()

    def validate(self, attrs):
        """Validate datasource config by source type."""

        source_type = attrs.get(
            "source_type",
            getattr(self.instance, "source_type", ""),
        )
        config = attrs.get("config", getattr(self.instance, "config", {}))
        sync_policy = attrs.get(
            "sync_policy",
            getattr(self.instance, "sync_policy", {}),
        )
        target_path = attrs.get(
            "target_path",
            getattr(self.instance, "target_path", ""),
        )
        lensnode_uuid = attrs.pop("lensnode_uuid", None)
        if lensnode_uuid is not None:
            try:
                attrs["lensnode"] = LensNode.objects.get(uuid=lensnode_uuid)
            except LensNode.DoesNotExist:
                raise serializers.ValidationError(
                    {"lensnode_uuid": "LensNode does not exist"}
                )
        lensnode = attrs.get(
            "lensnode",
            getattr(self.instance, "lensnode", None),
        )
        credential_uuid = attrs.pop("credential_uuid", None)
        if "credential_uuid" in self.initial_data and credential_uuid is None:
            attrs["credential"] = None
        elif credential_uuid is not None:
            try:
                attrs["credential"] = DataSourceCredential.objects.get(
                    uuid=credential_uuid
                )
            except DataSourceCredential.DoesNotExist:
                raise serializers.ValidationError(
                    {"credential_uuid": "Credential does not exist"}
                )

        if not isinstance(config, dict):
            raise serializers.ValidationError({"config": "config must be an object"})
        if not isinstance(sync_policy, dict):
            raise serializers.ValidationError(
                {"sync_policy": "sync_policy must be an object"}
            )

        _validate_datasource_config_secret_fields(config)
        _validate_sync_policy(sync_policy)
        try:
            validate_datasource_lensnode(lensnode)
            attrs["target_path"] = normalize_workspace_target_path(
                target_path,
                lensnode.workspace_path,
            )
            _validate_unique_datasource_target_path(
                attrs["target_path"],
                lensnode,
                self.instance,
            )
        except (DataSourcePathError, DataSourceDispatchError) as exc:
            raise serializers.ValidationError({"target_path": str(exc)})

        credential = (
            attrs["credential"]
            if "credential" in attrs
            else getattr(self.instance, "credential", None)
        )
        if source_type == DataSource.SourceType.GIT:
            _validate_datasource_credential_type(
                credential,
                {
                    DataSourceCredential.AuthType.HTTPS_TOKEN,
                    DataSourceCredential.AuthType.NONE,
                },
            )
            _validate_git_config(
                config,
                self.instance,
                credential,
            )
        elif source_type == DataSource.SourceType.FEISHU:
            _validate_datasource_credential_type(
                credential,
                DataSourceCredential.AuthType.FEISHU_APP,
            )
            _validate_feishu_config(
                config,
                self.instance,
                credential,
            )
        else:
            raise serializers.ValidationError(
                {"source_type": "source_type must be git or feishu"}
            )

        return attrs

    def get_credential_configured(self, datasource):
        """Return whether a datasource has a stored credential."""

        credential = getattr(datasource, "credential", None)
        return bool(credential and credential.has_secret)

    def get_current_sync(self, datasource):
        """Return the latest running datasource sync task, if any."""

        from agentcore_task.adapters.django.models import TaskExecution
        from agentcore_task.constants import TaskStatus

        task = (
            TaskExecution.objects.filter(
                module="lens_datasource",
                metadata__datasource_uuid=str(datasource.uuid),
                status__in=[
                    TaskStatus.PENDING,
                    *TaskStatus.get_running_statuses(),
                ],
            )
            .order_by("-created_at")
            .first()
        )
        if task is None:
            return None
        return {
            "id": task.id,
            "task_id": task.task_id,
            "task_name": task.task_name,
            "status": task.status,
            "started_at": task.started_at,
            "created_at": task.created_at,
            "progress_step": (task.metadata or {}).get("progress_step", ""),
            "progress_message": (task.metadata or {}).get(
                "progress_message",
                "",
            ),
            "progress_percent": (task.metadata or {}).get(
                "progress_percent",
                None,
            ),
        }

    def get_sync_state(self, datasource):
        """Return datasource sync status independent from enabled state."""

        from .periodic_tasks import estimate_datasource_next_run

        record = ScheduledTask.objects.filter(
            task_type=ScheduledTask.TaskType.SOURCE_SYNC,
            target_type="datasource",
            target_id=datasource.uuid,
        ).first()
        if record is None:
            return {
                "enabled": datasource.status != DataSource.Status.DISABLED,
                "last_status": "",
                "last_error": datasource.last_error,
                "last_run_at": None,
                "last_metrics": {},
                "next_run_at": None,
            }
        return {
            "enabled": record.enabled,
            "last_status": record.last_status or "",
            "last_error": record.last_error or datasource.last_error,
            "last_run_at": record.last_run_at,
            "last_metrics": record.last_metrics or {},
            "next_run_at": estimate_datasource_next_run(datasource, record),
        }

    def to_representation(self, instance):
        """Return datasource data without plaintext credential values."""

        data = super().to_representation(instance)
        config = dict(data.get("config") or {})
        config.pop("access_token", None)
        config.pop("app_id", None)
        config.pop("app_secret", None)
        config.pop("app_token", None)
        data["config"] = config
        return data

    def create(self, validated_data):
        """Create a datasource bound to reusable credentials."""

        return DataSource.objects.create(**validated_data)

    def update(self, instance, validated_data):
        """Update datasource metadata and credential binding."""

        return super().update(instance, validated_data)

    class Meta:
        model = DataSource
        fields = [
            "uuid",
            "name",
            "source_type",
            "lensnode",
            "lensnode_uuid",
            "lensnode_name",
            "credential",
            "credential_uuid",
            "config",
            "credential_configured",
            "current_sync",
            "sync_state",
            "sync_policy",
            "target_path",
            "last_synced_at",
            "last_error",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "uuid",
            "credential",
            "credential_configured",
            "current_sync",
            "sync_state",
            "last_error",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "target_path": {
                "allow_blank": True,
                "required": False,
            },
        }


def _validate_datasource_config_secret_fields(config):
    """Reject secret-like config fields outside the credential input."""

    forbidden_keys = {
        "access_token",
        "app_id",
        "app_secret",
        "app_token",
        "password",
        "private_key",
        "secret",
        "token",
    }
    for key, value in config.items():
        if key in forbidden_keys:
            raise serializers.ValidationError(
                {"config": "secret fields must be stored as credentials"}
            )
        if isinstance(value, dict):
            _validate_datasource_config_secret_fields(value)


class DataSourceCredentialSerializer(serializers.ModelSerializer):
    """Credential serializer that never exposes plaintext secrets."""

    secret = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    app_id = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    app_secret = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    folder_url = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    folder_token = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    organization_url = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    has_secret = serializers.BooleanField(read_only=True)
    datasource_count = serializers.SerializerMethodField()
    datasource_bindings = serializers.SerializerMethodField()
    masked_app_id = serializers.SerializerMethodField()
    masked_secret = serializers.SerializerMethodField()
    scope_summary = serializers.SerializerMethodField()

    class Meta:
        model = DataSourceCredential
        fields = [
            "uuid",
            "name",
            "provider",
            "auth_type",
            "endpoint_url",
            "sync_scope",
            "scope_config",
            "secret",
            "app_id",
            "app_secret",
            "folder_url",
            "folder_token",
            "organization_url",
            "has_secret",
            "datasource_count",
            "datasource_bindings",
            "masked_app_id",
            "masked_secret",
            "scope_summary",
            "validation_status",
            "validation_message",
            "validated_at",
            "last_used_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "uuid",
            "has_secret",
            "datasource_count",
            "datasource_bindings",
            "masked_app_id",
            "masked_secret",
            "scope_summary",
            "validation_status",
            "validation_message",
            "validated_at",
            "last_used_at",
            "created_at",
            "updated_at",
        ]

    def get_datasource_count(self, credential):
        """Return how many datasources reference this credential."""

        return credential.datasources.count()

    def get_datasource_bindings(self, credential):
        """Return datasources currently bound to this credential."""

        return [
            {
                "uuid": str(datasource.uuid),
                "name": datasource.name,
                "source_type": datasource.source_type,
                "status": datasource.status,
            }
            for datasource in credential.datasources.all()
        ]

    def get_masked_app_id(self, credential):
        """Return Feishu App ID without exposing App Secret."""

        if (
            credential.auth_type == DataSourceCredential.AuthType.FEISHU_APP
            and credential.has_secret
        ):
            app_id, _, _ = credential.get_secret().partition(":")
            return app_id
        return ""

    def get_masked_secret(self, credential):
        """Return a placeholder for encrypted credential secret."""

        return "********" if credential.has_secret else ""

    def get_scope_summary(self, credential):
        """Return a compact credential scope summary."""

        config = credential.scope_config or {}
        return {
            "endpoint_url": credential.endpoint_url,
            "sync_scope": credential.sync_scope,
            "folder_url": config.get("folder_url") or "",
            "folder_token": config.get("folder_token") or "",
            "organization_url": config.get("organization_url") or "",
        }

    def validate(self, attrs):
        """Validate secret inputs by credential auth type."""

        auth_type = attrs.get(
            "auth_type",
            getattr(self.instance, "auth_type", ""),
        )
        provider = attrs.get(
            "provider",
            getattr(self.instance, "provider", ""),
        )
        endpoint_url = str(
            attrs.get(
                "endpoint_url",
                getattr(self.instance, "endpoint_url", ""),
            )
            or ""
        ).strip()
        scope_config = dict(
            attrs.get(
                "scope_config",
                getattr(self.instance, "scope_config", {}),
            )
            or {}
        )
        folder_url = str(attrs.pop("folder_url", "") or "").strip()
        folder_token = str(attrs.pop("folder_token", "") or "").strip()
        organization_url = str(
            attrs.pop("organization_url", "") or ""
        ).strip()
        if folder_url:
            scope_config["folder_url"] = folder_url
        if folder_token:
            scope_config["folder_token"] = folder_token
        if organization_url:
            scope_config["organization_url"] = organization_url
        attrs["scope_config"] = scope_config
        if provider == DataSourceCredential.Provider.GITHUB and not endpoint_url:
            attrs["endpoint_url"] = "https://github.com"
        elif provider == DataSourceCredential.Provider.GITLAB and not endpoint_url:
            attrs["endpoint_url"] = "https://gitlab.com"
        elif provider == DataSourceCredential.Provider.FEISHU and not endpoint_url:
            attrs["endpoint_url"] = "https://open.feishu.cn"
        elif endpoint_url:
            attrs["endpoint_url"] = endpoint_url

        has_existing = bool(self.instance and self.instance.has_secret)
        has_secret = bool(str(attrs.get("secret") or "").strip())
        has_app_id = bool(str(attrs.get("app_id") or "").strip())
        has_app_secret = bool(str(attrs.get("app_secret") or "").strip())
        has_feishu = bool(
            has_app_id and has_app_secret
        )
        auth_type_changed = bool(
            self.instance and auth_type != self.instance.auth_type
        )
        if auth_type == DataSourceCredential.AuthType.FEISHU_APP:
            if provider != DataSourceCredential.Provider.FEISHU:
                raise serializers.ValidationError(
                    {"provider": "feishu app credential requires feishu provider"}
                )
            folder_url_value = scope_config.get("folder_url") or ""
            if folder_url_value and not _is_feishu_drive_folder_url(
                folder_url_value
            ):
                raise serializers.ValidationError(
                    {
                        "folder_url": (
                            "Feishu URL must be a Drive folder URL, for "
                            "example https://xxx.feishu.cn/drive/folder/..."
                        )
                    }
                )
            attrs["sync_scope"] = attrs.get("sync_scope") or "feishu_folder"
            if has_app_id != has_app_secret:
                raise serializers.ValidationError(
                    {"app_secret": "app_id and app_secret must be submitted together"}
                )
            if not has_feishu and (not has_existing or auth_type_changed):
                raise serializers.ValidationError(
                    {"app_secret": "app_id and app_secret are required"}
                )
        elif auth_type not in {
            DataSourceCredential.AuthType.HTTPS_TOKEN,
            DataSourceCredential.AuthType.NONE,
        }:
            raise serializers.ValidationError(
                {"auth_type": "credential auth_type is not supported"}
            )
        elif provider not in {
            DataSourceCredential.Provider.GITHUB,
            DataSourceCredential.Provider.GITLAB,
            DataSourceCredential.Provider.GENERIC,
        }:
            raise serializers.ValidationError(
                {"provider": "git credential provider must be github or gitlab"}
            )
        elif (
            auth_type == DataSourceCredential.AuthType.HTTPS_TOKEN
            and not has_secret
            and (not has_existing or auth_type_changed)
        ):
            raise serializers.ValidationError(
                {"secret": "secret is required"}
            )
        if auth_type in {
            DataSourceCredential.AuthType.HTTPS_TOKEN,
            DataSourceCredential.AuthType.NONE,
        }:
            attrs["sync_scope"] = attrs.get("sync_scope") or "service"
        return attrs

    def create(self, validated_data):
        """Create a credential and encrypt the supplied secret."""

        secret = _credential_secret_from_validated_data(validated_data)
        credential = DataSourceCredential(**validated_data)
        if secret:
            credential.set_secret(secret)
        credential.save()
        return credential

    def update(self, instance, validated_data):
        """Update metadata and optionally replace the encrypted secret."""

        secret = _credential_secret_from_validated_data(validated_data)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if (
            instance.auth_type == DataSourceCredential.AuthType.NONE
            and instance.encrypted_secret
        ):
            instance.encrypted_secret = ""
        if secret:
            instance.set_secret(secret)
        instance.save()
        return instance


def _credential_secret_from_validated_data(validated_data):
    """Remove write-only secret fields and return the secret payload."""

    secret = str(validated_data.pop("secret", "") or "").strip()
    app_id = str(validated_data.pop("app_id", "") or "").strip()
    app_secret = str(validated_data.pop("app_secret", "") or "").strip()
    if app_id or app_secret:
        return f"{app_id}:{app_secret}"
    return secret


def _is_feishu_drive_folder_url(value):
    """Return whether a URL points to a Feishu Drive folder."""

    parsed = parse.urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc.endswith(".feishu.cn"):
        return False
    parts = [part for part in parsed.path.split("/") if part]
    return len(parts) >= 3 and parts[0] == "drive" and parts[1] == "folder"


def _credential_provider(repo_url):
    """Infer credential provider from a Git repository URL."""

    value = str(repo_url or "").lower()
    if "github.com" in value:
        return DataSourceCredential.Provider.GITHUB
    if "gitlab" in value:
        return DataSourceCredential.Provider.GITLAB
    return DataSourceCredential.Provider.GENERIC


def _validate_sync_policy(sync_policy):
    """Validate datasource schedule and conversion policy."""

    _validate_conversion_policy(sync_policy.get("conversion") or {})
    mode = sync_policy.get("mode") or "interval"
    if mode not in {"interval", "crontab"}:
        raise serializers.ValidationError(
            {"sync_policy": "mode must be interval or crontab"}
        )
    if mode == "crontab":
        _validate_cron_expression(sync_policy.get("cron"))
        timezone = sync_policy.get("timezone")
        if timezone is not None and not isinstance(timezone, str):
            raise serializers.ValidationError(
                {"sync_policy": "timezone must be a string"}
            )
        return
    interval = sync_policy.get("interval_seconds")
    if interval is not None and (
        not isinstance(interval, int) or interval <= 0
    ):
        raise serializers.ValidationError(
            {"sync_policy": "interval_seconds must be a positive integer"}
        )


def _validate_conversion_policy(conversion):
    """Validate datasource conversion settings."""

    if not isinstance(conversion, dict):
        raise serializers.ValidationError(
            {"sync_policy": "conversion must be an object"}
        )
    for key in [
        "document",
        "image",
        "embedded_image",
        "pdf_extract_images",
        "pdf_extract_images_on_text_pages",
        "pdf_render_scanned_pages",
    ]:
        value = conversion.get(key)
        if value is not None and not isinstance(value, bool):
            raise serializers.ValidationError(
                {"sync_policy": f"conversion.{key} must be a boolean"}
            )
    if conversion.get("embedded_image") and not conversion.get("document"):
        raise serializers.ValidationError(
            {
                "sync_policy": (
                    "conversion.embedded_image requires "
                    "conversion.document"
                )
            }
        )
    for key in [
        "max_images",
        "max_file_size_mb",
        "max_pages",
        "pdf_max_images_per_page",
        "pdf_max_pages",
        "pdf_min_text_chars",
        "pdf_render_dpi",
    ]:
        value = conversion.get(key)
        if value is not None and (
            not isinstance(value, int) or value <= 0
        ):
            raise serializers.ValidationError(
                {"sync_policy": f"conversion.{key} must be positive"}
            )
    ratio = conversion.get("pdf_min_image_area_ratio")
    if ratio is not None and (
        not isinstance(ratio, (int, float)) or ratio <= 0 or ratio > 1
    ):
        raise serializers.ValidationError(
            {
                "sync_policy": (
                    "conversion.pdf_min_image_area_ratio must be "
                    "between 0 and 1"
                )
            }
        )
    for key in ["vision_model_ref", "document_model_ref", "queue"]:
        value = conversion.get(key)
        if value is not None and not isinstance(value, str):
            raise serializers.ValidationError(
                {"sync_policy": f"conversion.{key} must be a string"}
            )


def _validate_unique_datasource_target_path(target_path, lensnode, instance):
    """Reject an exact target path match on the same LensNode."""

    query = DataSource.objects.filter(lensnode=lensnode)
    if instance is not None:
        query = query.exclude(pk=instance.pk)
    target = PurePosixPath(target_path)
    for datasource in query.only("target_path"):
        if not datasource.target_path:
            continue
        existing = PurePosixPath(
            normalize_workspace_target_path(
                datasource.target_path,
                lensnode.workspace_path,
            )
        )
        if existing == target:
            raise serializers.ValidationError(
                {
                    "target_path": (
                        "Another datasource already uses this target path"
                    )
                }
            )


def _validate_datasource_credential_type(credential, auth_type):
    """Validate that a selected credential matches the datasource type."""

    if credential is None:
        return
    allowed_types = (
        set(auth_type)
        if isinstance(auth_type, (list, tuple, set))
        else {auth_type}
    )
    if credential.auth_type not in allowed_types:
        raise serializers.ValidationError(
            {"credential_uuid": "Credential type does not match datasource"}
        )


def _validate_cron_expression(value):
    """Validate a simple five-field crontab expression."""

    parts = str(value or "").split()
    if len(parts) != 5:
        raise serializers.ValidationError(
            {"sync_policy": "cron must contain five fields"}
        )
    for part in parts:
        if not all(char.isdigit() or char in "*,/-" for char in part):
            raise serializers.ValidationError(
                {"sync_policy": "cron contains unsupported characters"}
            )


def _validate_git_config(config, instance=None, credential=None):
    scope_type = config.get("scope_type") or (
        "organization" if config.get("repositories") else "repository"
    )
    if scope_type not in {"repository", "organization"}:
        raise serializers.ValidationError(
            {"config": "git scope_type must be repository or organization"}
        )
    if scope_type == "organization":
        repositories = config.get("repositories") or []
        if not isinstance(repositories, list) or not repositories:
            raise serializers.ValidationError(
                {"config": "git organization repositories are required"}
            )
        seen_targets = set()
        for repository in repositories:
            if not isinstance(repository, dict):
                raise serializers.ValidationError(
                    {"config": "git repository item must be an object"}
                )
            if not repository.get("repo_url"):
                raise serializers.ValidationError(
                    {"config": "git repository repo_url is required"}
                )
            if not repository.get("branch"):
                raise serializers.ValidationError(
                    {"config": "git repository branch is required"}
                )
            target_subdir = str(
                repository.get("target_subdir")
                or repository.get("name")
                or repository.get("path")
                or ""
            ).strip()
            if not target_subdir:
                raise serializers.ValidationError(
                    {"config": "git repository target_subdir is required"}
                )
            if target_subdir in seen_targets:
                raise serializers.ValidationError(
                    {"config": "git repository target_subdir must be unique"}
                )
            seen_targets.add(target_subdir)
    elif not config.get("repo_url"):
        raise serializers.ValidationError(
            {"config": "git config.repo_url is required"}
        )
    auth_scheme = config.get("auth_scheme", "none")
    if auth_scheme not in ["none", "token"]:
        raise serializers.ValidationError(
            {"config": "git auth_scheme must be none or token"}
        )
    if auth_scheme == "none" and credential:
        if credential.auth_type != DataSourceCredential.AuthType.NONE:
            raise serializers.ValidationError(
                {
                    "credential_uuid": (
                        "Git credential must not be set without auth"
                    )
                }
            )
    if auth_scheme == "token" and not credential:
        raise serializers.ValidationError(
            {"credential_uuid": "Git HTTPS Token credential is required"}
        )
    if (
        auth_scheme == "token"
        and credential
        and credential.auth_type != DataSourceCredential.AuthType.HTTPS_TOKEN
    ):
        raise serializers.ValidationError(
            {"credential_uuid": "Git HTTPS Token credential is required"}
        )


def _validate_feishu_config(config, instance=None, credential=None):
    if not credential:
        raise serializers.ValidationError(
            {"credential_uuid": "Feishu credential is required"}
        )
    sync_mode = config.get("sync_mode") or "document_list"
    if sync_mode not in {"document_list", "drive_folder"}:
        raise serializers.ValidationError(
            {"config": "feishu sync_mode must be document_list or drive_folder"}
        )
    if sync_mode == "drive_folder":
        scope_config = credential.scope_config or {}
        if not (
            config.get("folder_url")
            or config.get("folder_token")
            or scope_config.get("folder_url")
            or scope_config.get("folder_token")
        ):
            raise serializers.ValidationError(
                {
                    "config": (
                        "feishu config.folder_url or folder_token is required"
                    )
                }
            )
        max_depth = config.get("max_depth", 10)
        if not isinstance(max_depth, int) or max_depth <= 0:
            raise serializers.ValidationError(
                {"config": "feishu max_depth must be a positive integer"}
            )
        return

    if not (
        config.get("document_url")
        or config.get("wiki_token")
        or config.get("doc_ids")
    ):
        raise serializers.ValidationError(
            {
                "config": (
                    "feishu config.document_url, wiki_token or doc_ids "
                    "is required"
                )
            }
        )
    doc_ids = config.get("doc_ids", [])
    if not isinstance(doc_ids, list):
        raise serializers.ValidationError({"config": "feishu doc_ids must be a list"})


class SkillSerializer(serializers.ModelSerializer):
    """Skill serializer."""

    class Meta:
        model = Skill
        fields = [
            "uuid",
            "name",
            "slug",
            "definition",
            "version",
            "enabled",
            "package_hash",
            "package_size",
            "package_manifest",
            "source_type",
            "source_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "uuid",
            "package_hash",
            "package_size",
            "package_manifest",
            "source_type",
            "source_url",
            "created_at",
            "updated_at",
        ]


class MCPServerSerializer(serializers.ModelSerializer):
    """MCP server serializer."""

    class Meta:
        model = MCPServer
        fields = [
            "uuid",
            "name",
            "transport",
            "endpoint",
            "config",
            "version",
            "enabled",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]


class GlobalSettingSerializer(serializers.ModelSerializer):
    """Global setting serializer."""

    def validate(self, attrs):
        """Validate known high-risk setting schemas."""

        key = attrs.get("key", getattr(self.instance, "key", ""))
        value = attrs.get("value", getattr(self.instance, "value", {}))

        positive_integer_keys = {
            "retention.run_days": "run_days",
            "lensnode.defaults.timeout": "timeout",
            "lensnode.defaults.idle_timeout": "idle_timeout",
            "lensnode.health.offline_threshold_s": "offline_threshold_s",
            "lensnode_cleanup.interval_seconds": "interval_seconds",
            "lensnode_health.interval_seconds": "interval_seconds",
            "run_retention.interval_seconds": "interval_seconds",
            "lens.datasource_sync.timeout_s": "timeout_s",
            "lens.datasource_sync.workers": "workers",
        }
        if key in positive_integer_keys:
            if not isinstance(value, int) or value <= 0:
                name = positive_integer_keys[key]
                raise serializers.ValidationError(
                    {"value": f"{name} must be a positive integer"}
                )

        model_ref_keys = {
            "lens.skills.generator_model_ref": "generator_model_ref",
            "lens.datasource_conversion.vision_model_ref": (
                "vision_model_ref"
            ),
            "lens.datasource_conversion.document_model_ref": (
                "document_model_ref"
            ),
        }
        if key in model_ref_keys:
            if value not in [None, ""] and not isinstance(value, str):
                raise serializers.ValidationError(
                    {"value": f"{model_ref_keys[key]} must be a string or empty"}
                )

        return attrs

    class Meta:
        model = GlobalSetting
        fields = ["key", "value", "description", "updated_at"]
        read_only_fields = ["updated_at"]


class MessageAttachmentSerializer(serializers.ModelSerializer):
    """Read serializer for a question image attachment."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = MessageAttachment
        fields = [
            "uuid",
            "url",
            "kind",
            "mime_type",
            "width",
            "height",
            "byte_size",
            "original_name",
            "order",
        ]
        read_only_fields = fields

    def get_url(self, obj):
        """Return the authenticated fetch path for the image bytes."""

        return reverse("lens-attachment", kwargs={"uuid": obj.uuid})


class RunOutputFileSerializer(serializers.ModelSerializer):
    """Read serializer for a delivered run output file."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = RunOutputFile
        fields = [
            "uuid",
            "url",
            "filename",
            "content_type",
            "byte_size",
        ]
        read_only_fields = fields

    def get_url(self, obj):
        """Return the authenticated download path for the file bytes."""

        return reverse(
            "lens-output-file", kwargs={"uuid": obj.uuid}
        )


class MessageSerializer(serializers.ModelSerializer):
    """Session message serializer."""

    run = serializers.UUIDField(source="run.uuid", read_only=True)
    thinking = serializers.SerializerMethodField()
    attachments = MessageAttachmentSerializer(many=True, read_only=True)
    output_files = RunOutputFileSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = [
            "uuid",
            "role",
            "content",
            "sequence",
            "run",
            "thinking",
            "attachments",
            "output_files",
            "created_at",
        ]
        read_only_fields = [
            "uuid",
            "role",
            "content",
            "sequence",
            "run",
            "thinking",
            "attachments",
            "output_files",
            "created_at",
        ]

    def get_thinking(self, obj):
        """Return a persisted reasoning summary for assistant messages.

        Surfaces the run's elapsed time and the accumulated tool-use
        step events so the frontend can render a collapsed "thought for
        Xs" panel on historical messages. Only agent_event/activity are
        included; the friendly wording and grouping happen client-side.
        """

        run = obj.run
        if obj.role != Message.Role.ASSISTANT or run is None:
            return None
        steps = []
        for step in run.steps.all():
            for item in (step.detail or {}).get("events", []):
                if item.get("agent_event") or item.get("activity"):
                    steps.append(
                        {
                            "agent_event": item.get("agent_event"),
                            "activity": item.get("activity"),
                        }
                    )
        if not steps:
            return None
        duration = None
        if run.started_at and run.finished_at:
            duration = (run.finished_at - run.started_at).total_seconds()
        return {"duration_seconds": duration, "steps": steps}


class RunStepSerializer(serializers.ModelSerializer):
    """Run step serializer."""

    class Meta:
        model = RunStep
        fields = [
            "uuid",
            "step_type",
            "detail",
            "status",
            "sequence",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class RunExecutionSerializer(serializers.ModelSerializer):
    """Run execution snapshot serializer."""

    lensnode = serializers.UUIDField(source="lensnode.uuid", read_only=True)

    class Meta:
        model = RunExecution
        fields = [
            "uuid",
            "lensnode",
            "task",
            "loaded_skills",
            "loaded_mcps",
            "target_dirs",
            "status",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields


class RunSerializer(serializers.ModelSerializer):
    """Run serializer with nested execution details."""

    steps = RunStepSerializer(many=True, read_only=True)
    execution = RunExecutionSerializer(read_only=True)
    lensnode = serializers.UUIDField(source="lensnode.uuid", read_only=True)

    class Meta:
        model = Run
        fields = [
            "uuid",
            "status",
            "input_message",
            "output_message",
            "lensnode",
            "metering_ref",
            "error",
            "started_at",
            "finished_at",
            "idempotency_key",
            "steps",
            "execution",
        ]
        read_only_fields = fields


class SessionSerializer(serializers.ModelSerializer):
    """Session serializer."""

    assistant_name = serializers.CharField(source="assistant.name", read_only=True)
    assistant_slug = serializers.CharField(source="assistant.slug", read_only=True)

    class Meta:
        model = Session
        fields = [
            "uuid",
            "assistant",
            "assistant_name",
            "assistant_slug",
            "user",
            "title",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "user", "created_at", "updated_at"]


class SessionCreateSerializer(serializers.Serializer):
    """Session creation payload."""

    assistant_uuid = serializers.UUIDField()
    title = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        assistant = Assistant.objects.get(uuid=validated_data["assistant_uuid"])
        request = self.context["request"]
        if not assistant.is_accessible_by(request.user):
            raise PermissionDenied(
                "You do not have access to this assistant."
            )
        return Session.objects.create(
            assistant=assistant,
            user=request.user,
            title=validated_data.get("title", ""),
        )


class RunCreateSerializer(serializers.Serializer):
    """Run creation payload."""

    question = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    idempotency_key = serializers.CharField(required=False, allow_blank=True)
    enqueue = serializers.BooleanField(required=False, default=True)
    run_inline = serializers.BooleanField(required=False, default=False)
    attachment_uuids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )

    def validate(self, attrs):
        """Require text or at least one image, and cap attachment count."""

        question = (attrs.get("question") or "").strip()
        attachments = attrs.get("attachment_uuids") or []
        if not question and not attachments:
            raise serializers.ValidationError(
                "Provide a question or at least one image."
            )
        if len(attachments) > ATTACHMENT_MAX_PER_MESSAGE:
            raise serializers.ValidationError(
                f"At most {ATTACHMENT_MAX_PER_MESSAGE} images per message."
            )
        return attrs

    def create(self, validated_data):
        session = self.context["session"]
        run_inline = validated_data.get("run_inline", False)
        run = create_execution_run(
            session=session,
            question=validated_data.get("question", ""),
            idempotency_key=validated_data.get("idempotency_key", ""),
            enqueue=validated_data.get("enqueue", True) and not run_inline,
            attachment_uuids=[
                str(value)
                for value in validated_data.get("attachment_uuids", [])
            ],
        )
        if run_inline:
            from .execution import execute_answer_run

            try:
                execute_answer_run(run, dispatch=False)
            except Exception:
                run.refresh_from_db()
            else:
                run.refresh_from_db()
        return run


def _answer_snippet(text, limit=160):
    """Collapse whitespace and truncate answer text for list previews."""

    return " ".join((text or "").split())[:limit]


class SharedQAPublicSerializer(serializers.ModelSerializer):
    """Public single shared Q&A (anonymous, read-only)."""

    class Meta:
        model = SharedQA
        fields = [
            "token",
            "title",
            "question",
            "answer",
            "assistant_name",
            "assistant_slug",
            "view_count",
            "published_at",
        ]
        read_only_fields = fields


class SharedQAListSerializer(serializers.ModelSerializer):
    """Public list item for an assistant's Q&A gallery."""

    answer_snippet = serializers.SerializerMethodField()

    class Meta:
        model = SharedQA
        fields = [
            "token",
            "title",
            "answer_snippet",
            "view_count",
            "published_at",
        ]
        read_only_fields = fields

    def get_answer_snippet(self, obj):
        """Return a short plain-text preview of the answer."""

        return _answer_snippet(obj.answer)


class SharedQAMineSerializer(serializers.ModelSerializer):
    """A user's own shared Q&A with publish/list state and content."""

    run_uuid = serializers.UUIDField(source="run.uuid", read_only=True)

    class Meta:
        model = SharedQA
        fields = [
            "uuid",
            "token",
            "run_uuid",
            "title",
            "question",
            "answer",
            "assistant_name",
            "assistant_slug",
            "is_listed",
            "status",
            "view_count",
            "published_at",
        ]
        read_only_fields = fields


class SharedQAAdminSerializer(serializers.ModelSerializer):
    """Admin moderation view of a shared Q&A."""

    assistant_visibility = serializers.CharField(
        source="assistant.visibility",
        read_only=True,
        default="",
    )
    published_by = serializers.SerializerMethodField()
    answer_snippet = serializers.SerializerMethodField()

    class Meta:
        model = SharedQA
        fields = [
            "uuid",
            "token",
            "title",
            "answer_snippet",
            "assistant_name",
            "assistant_slug",
            "assistant_visibility",
            "is_listed",
            "status",
            "published_by",
            "view_count",
            "published_at",
            "created_at",
        ]
        read_only_fields = [
            "uuid",
            "token",
            "title",
            "answer_snippet",
            "assistant_name",
            "assistant_slug",
            "assistant_visibility",
            "published_by",
            "view_count",
            "published_at",
            "created_at",
        ]

    def get_published_by(self, obj):
        """Return the publisher's username (internal use only)."""

        return obj.published_by.username if obj.published_by else ""

    def get_answer_snippet(self, obj):
        """Return a short plain-text preview of the answer."""

        return _answer_snippet(obj.answer)
