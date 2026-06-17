from django.contrib.auth import get_user_model
from rest_framework import serializers

from .datasource_services import (
    DataSourceDispatchError,
    DataSourcePathError,
    normalize_workspace_target_path,
    validate_datasource_lensnode,
)
from .model_checks import check_assistant_model_refs
from .models import (
    Assistant,
    AssistantMCP,
    AssistantSkill,
    DataSource,
    DataSourceCredential,
    GlobalSetting,
    MCPServer,
    Message,
    LensNode,
    Run,
    RunExecution,
    RunStep,
    ScheduledTask,
    Session,
    Skill,
)
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


class AssistantSerializer(serializers.ModelSerializer):
    """Assistant serializer with LensNode and capability validation."""

    lensnode_uuid = serializers.UUIDField(write_only=True, required=False)
    lensnode = serializers.UUIDField(source="lensnode.uuid", read_only=True)
    skill_bindings = SkillBindingsField(required=False)
    mcp_bindings = McpBindingsField(required=False)
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
            "skill_bindings",
            "mcp_bindings",
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

    def create(self, validated_data):
        """Create assistant and optional bindings."""

        skill_bindings = validated_data.pop("skill_bindings", None)
        mcp_bindings = validated_data.pop("mcp_bindings", None)
        workspace_guide = validated_data.pop("workspace_guide", None)
        assistant = Assistant.objects.create(**validated_data)
        self._sync_bindings(
            assistant,
            {
                "skill_bindings": skill_bindings,
                "mcp_bindings": mcp_bindings,
            },
        )
        sync_workspace_guide_skill(assistant, workspace_guide)
        check_assistant_model_refs(assistant)
        return assistant

    def update(self, instance, validated_data):
        """Update assistant and optional bindings."""

        workspace_guide = validated_data.pop("workspace_guide", None)
        self._sync_bindings(instance, validated_data)
        assistant = super().update(instance, validated_data)
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
                DataSourceCredential.AuthType.HTTPS_TOKEN,
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
    has_secret = serializers.BooleanField(read_only=True)
    datasource_count = serializers.SerializerMethodField()
    datasource_bindings = serializers.SerializerMethodField()
    masked_app_id = serializers.SerializerMethodField()
    masked_secret = serializers.SerializerMethodField()

    class Meta:
        model = DataSourceCredential
        fields = [
            "uuid",
            "name",
            "provider",
            "auth_type",
            "secret",
            "app_id",
            "app_secret",
            "has_secret",
            "datasource_count",
            "datasource_bindings",
            "masked_app_id",
            "masked_secret",
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

    def validate(self, attrs):
        """Validate secret inputs by credential auth type."""

        auth_type = attrs.get(
            "auth_type",
            getattr(self.instance, "auth_type", ""),
        )
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
            if has_app_id != has_app_secret:
                raise serializers.ValidationError(
                    {"app_secret": "app_id and app_secret must be submitted together"}
                )
            if not has_feishu and (not has_existing or auth_type_changed):
                raise serializers.ValidationError(
                    {"app_secret": "app_id and app_secret are required"}
                )
        elif not has_secret and (not has_existing or auth_type_changed):
            raise serializers.ValidationError(
                {"secret": "secret is required"}
            )
        return attrs

    def create(self, validated_data):
        """Create a credential and encrypt the supplied secret."""

        secret = _credential_secret_from_validated_data(validated_data)
        credential = DataSourceCredential(**validated_data)
        credential.set_secret(secret)
        credential.save()
        return credential

    def update(self, instance, validated_data):
        """Update metadata and optionally replace the encrypted secret."""

        secret = _credential_secret_from_validated_data(validated_data)
        for field, value in validated_data.items():
            setattr(instance, field, value)
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


def _credential_provider(repo_url):
    """Infer credential provider from a Git repository URL."""

    value = str(repo_url or "").lower()
    if "github.com" in value:
        return DataSourceCredential.Provider.GITHUB
    if "gitlab" in value:
        return DataSourceCredential.Provider.GITLAB
    return DataSourceCredential.Provider.GENERIC


def _validate_sync_policy(sync_policy):
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


def _validate_datasource_credential_type(credential, auth_type):
    """Validate that a selected credential matches the datasource type."""

    if credential is None:
        return
    if credential.auth_type != auth_type:
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
    if not config.get("repo_url"):
        raise serializers.ValidationError(
            {"config": "git config.repo_url is required"}
        )
    auth_scheme = config.get("auth_scheme", "none")
    if auth_scheme not in ["none", "token"]:
        raise serializers.ValidationError(
            {"config": "git auth_scheme must be none or token"}
        )
    if auth_scheme == "none" and credential:
        raise serializers.ValidationError(
            {"credential_uuid": "Git credential must not be set without auth"}
        )
    if auth_scheme == "token" and not credential:
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
        if not (config.get("folder_url") or config.get("folder_token")):
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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]


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
            "lensnode.health.offline_threshold_s": "offline_threshold_s",
            "lensnode_cleanup.interval_seconds": "interval_seconds",
            "lensnode_health.interval_seconds": "interval_seconds",
            "run_retention.interval_seconds": "interval_seconds",
            "lens.datasource_sync.timeout_s": "timeout_s",
        }
        if key in positive_integer_keys:
            if not isinstance(value, int) or value <= 0:
                name = positive_integer_keys[key]
                raise serializers.ValidationError(
                    {"value": f"{name} must be a positive integer"}
                )

        if key == "lens.skills.generator_model_ref":
            if value not in [None, ""] and not isinstance(value, str):
                raise serializers.ValidationError(
                    {"value": "generator_model_ref must be a string or empty"}
                )

        return attrs

    class Meta:
        model = GlobalSetting
        fields = ["key", "value", "description", "updated_at"]
        read_only_fields = ["updated_at"]


class MessageSerializer(serializers.ModelSerializer):
    """Session message serializer."""

    run = serializers.UUIDField(source="run.uuid", read_only=True)
    thinking = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "uuid",
            "role",
            "content",
            "sequence",
            "run",
            "thinking",
            "created_at",
        ]
        read_only_fields = [
            "uuid",
            "role",
            "content",
            "sequence",
            "run",
            "thinking",
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
        return Session.objects.create(
            assistant=assistant,
            user=request.user,
            title=validated_data.get("title", ""),
        )


class RunCreateSerializer(serializers.Serializer):
    """Run creation payload."""

    question = serializers.CharField()
    idempotency_key = serializers.CharField(required=False, allow_blank=True)
    enqueue = serializers.BooleanField(required=False, default=True)
    run_inline = serializers.BooleanField(required=False, default=False)

    def create(self, validated_data):
        session = self.context["session"]
        run_inline = validated_data.get("run_inline", False)
        run = create_execution_run(
            session=session,
            question=validated_data["question"],
            idempotency_key=validated_data.get("idempotency_key", ""),
            enqueue=validated_data.get("enqueue", True) and not run_inline,
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
