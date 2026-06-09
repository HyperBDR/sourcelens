from django.contrib.auth import get_user_model
from rest_framework import serializers

from .model_checks import check_assistant_model_refs
from .models import (
    Assistant,
    AssistantMCP,
    AssistantSkill,
    DataSource,
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

    max_file_size = value.get("max_file_size")
    if max_file_size is not None and (
        not isinstance(max_file_size, int) or max_file_size <= 0
    ):
        raise serializers.ValidationError(
            "retrieval_scope.max_file_size must be a positive integer"
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
            "preprocess_model_ref",
            "postprocess_model_ref",
            "multimodal_model_ref",
            "agent_model_ref",
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

        if not isinstance(config, dict):
            raise serializers.ValidationError({"config": "config must be an object"})
        if not isinstance(sync_policy, dict):
            raise serializers.ValidationError(
                {"sync_policy": "sync_policy must be an object"}
            )

        _validate_no_inline_datasource_credentials(config)
        _validate_sync_policy(sync_policy)

        if source_type == DataSource.SourceType.GIT:
            if not config.get("repo_url"):
                raise serializers.ValidationError(
                    {"config": "git config.repo_url is required"}
                )
        elif source_type == DataSource.SourceType.JIRA:
            _validate_jira_config(config)
        elif source_type == DataSource.SourceType.FEISHU:
            _validate_feishu_config(config)

        return attrs

    class Meta:
        model = DataSource
        fields = [
            "uuid",
            "name",
            "source_type",
            "config",
            "sync_policy",
            "target_path",
            "last_synced_at",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]
        extra_kwargs = {
            "target_path": {
                "allow_blank": True,
                "required": False,
            },
        }


def _validate_no_inline_datasource_credentials(config):
    forbidden_keys = {
        "password",
        "token",
        "access_token",
        "secret",
        "private_key",
    }
    for key, value in config.items():
        if key in forbidden_keys:
            raise serializers.ValidationError(
                {"config": "inline datasource credentials are forbidden"}
            )
        if isinstance(value, dict):
            _validate_no_inline_datasource_credentials(value)


def _validate_sync_policy(sync_policy):
    interval = sync_policy.get("interval_seconds")
    if interval is not None and (not isinstance(interval, int) or interval <= 0):
        raise serializers.ValidationError(
            {"sync_policy": "interval_seconds must be a positive integer"}
        )


def _validate_jira_config(config):
    if not config.get("base_url"):
        raise serializers.ValidationError(
            {"config": "jira config.base_url is required"}
        )
    auth_scheme = config.get("auth_scheme", "bearer")
    if auth_scheme not in ["bearer", "basic"]:
        raise serializers.ValidationError(
            {"config": "jira auth_scheme must be bearer or basic"}
        )
    query_rules = config.get("query_rules", {})
    field_mapping = config.get("field_mapping", {})
    if not isinstance(query_rules, dict):
        raise serializers.ValidationError(
            {"config": "jira query_rules must be an object"}
        )
    if not isinstance(field_mapping, dict):
        raise serializers.ValidationError(
            {"config": "jira field_mapping must be an object"}
        )


def _validate_feishu_config(config):
    if not config.get("app_token"):
        raise serializers.ValidationError(
            {"config": "feishu config.app_token is required"}
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

    class Meta:
        model = Message
        fields = [
            "uuid",
            "role",
            "content",
            "sequence",
            "run",
            "created_at",
        ]
        read_only_fields = [
            "uuid",
            "role",
            "content",
            "sequence",
            "run",
            "created_at",
        ]


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
