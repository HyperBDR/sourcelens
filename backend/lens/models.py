import base64
import hashlib
import uuid

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models
from django.db.models import Q


class TimestampedUUIDModel(models.Model):
    """Abstract model with a public UUID and timestamps."""

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class LensNode(TimestampedUUIDModel):
    """Long-lived distributed LensNode execution worker."""

    class Status(models.TextChoices):
        ONLINE = "online", "Online"
        OFFLINE = "offline", "Offline"
        DRAINING = "draining", "Draining"

    class EnrollmentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    name = models.CharField(max_length=160)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OFFLINE,
    )
    connection_id = models.CharField(max_length=128, blank=True, default="")
    workspace_path = models.CharField(max_length=500, blank=True, default="")
    available_dirs = models.JSONField(default=list, blank=True)
    protocol_version = models.CharField(max_length=32, blank=True, default="")
    agent_version = models.CharField(max_length=64, blank=True, default="")
    tasks = models.JSONField(default=list, blank=True)
    labels = models.JSONField(default=dict, blank=True)
    enrollment_status = models.CharField(
        max_length=16,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.PENDING,
    )
    auth_token_hash = models.CharField(max_length=128, blank=True, default="")
    token_issued_at = models.DateTimeField(null=True, blank=True)
    token_revoked = models.BooleanField(default=False)
    last_authenticated_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"], name="lens_lensnode_status_idx"),
            models.Index(
                fields=["enrollment_status"],
                name="lens_lensnode_enroll_idx",
            ),
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Assistant(TimestampedUUIDModel):
    """Externally visible capability bound to one LensNode."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DISABLED = "disabled", "Disabled"

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    lensnode = models.ForeignKey(
        LensNode,
        on_delete=models.PROTECT,
        related_name="assistants",
    )
    class AgentRounds(models.TextChoices):
        FLASH    = "flash",    "极速"
        FAST     = "fast",     "快速"
        BALANCED = "balanced", "均衡"
        DEEP     = "deep",     "深度"
        MAX      = "max",      "极限"

    selected_task = models.CharField(max_length=160)
    selected_dirs = models.JSONField(default=list, blank=True)
    preprocess_model_ref = models.UUIDField(null=True, blank=True)
    postprocess_model_ref = models.UUIDField(null=True, blank=True)
    multimodal_model_ref = models.UUIDField(null=True, blank=True)
    agent_model_ref = models.UUIDField(null=True, blank=True)
    agent_rounds = models.CharField(
        max_length=16,
        choices=AgentRounds.choices,
        default=AgentRounds.BALANCED,
    )
    max_concurrency = models.PositiveSmallIntegerField(default=5)
    settings = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    class Meta:
        indexes = [
            models.Index(
                fields=["lensnode"],
                name="lens_assistant_lensnode_idx",
            ),
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Skill(TimestampedUUIDModel):
    """Global skill resource."""

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    definition = models.JSONField(default=dict, blank=True)
    version = models.CharField(max_length=64, blank=True, default="1")
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class MCPServer(TimestampedUUIDModel):
    """Global MCP server resource."""

    class Transport(models.TextChoices):
        URL = "url", "URL"
        STDIO = "stdio", "STDIO"

    name = models.CharField(max_length=160)
    transport = models.CharField(max_length=16, choices=Transport.choices)
    endpoint = models.CharField(max_length=500, blank=True, default="")
    config = models.JSONField(default=dict, blank=True)
    version = models.CharField(max_length=64, blank=True, default="1")
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class DataSource(TimestampedUUIDModel):
    """Independent synchronizer for external sources."""

    class SourceType(models.TextChoices):
        GIT = "git", "Git"
        FEISHU = "feishu", "Feishu"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DISABLED = "disabled", "Disabled"

    name = models.CharField(max_length=160)
    source_type = models.CharField(max_length=32, choices=SourceType.choices)
    lensnode = models.ForeignKey(
        LensNode,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="datasources",
    )
    config = models.JSONField(default=dict, blank=True)
    sync_policy = models.JSONField(default=dict, blank=True)
    target_path = models.CharField(max_length=500, blank=True, default="")
    credential = models.ForeignKey(
        "DataSourceCredential",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="datasources",
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    class Meta:
        indexes = [
            models.Index(fields=["status"], name="lens_datasource_status_idx"),
            models.Index(
                fields=["lensnode"],
                name="lens_datasource_lensnode_idx",
            ),
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


class DataSourceCredential(TimestampedUUIDModel):
    """Encrypted datasource credential used only during node execution."""

    class Provider(models.TextChoices):
        GITHUB = "github", "GitHub"
        GITLAB = "gitlab", "GitLab"
        FEISHU = "feishu", "Feishu"
        GENERIC = "generic", "Generic"

    class AuthType(models.TextChoices):
        HTTPS_TOKEN = "https_token", "HTTPS Token"
        FEISHU_APP = "feishu_app", "Feishu App"

    name = models.CharField(max_length=160)
    provider = models.CharField(
        max_length=32,
        choices=Provider.choices,
        default=Provider.GENERIC,
    )
    auth_type = models.CharField(
        max_length=32,
        choices=AuthType.choices,
        default=AuthType.HTTPS_TOKEN,
    )
    encrypted_secret = models.TextField(blank=True, default="")
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def set_secret(self, value):
        """Encrypt and store a plaintext credential secret."""

        self.encrypted_secret = _datasource_fernet().encrypt(
            str(value or "").encode("utf-8")
        ).decode("utf-8")

    def get_secret(self):
        """Return the decrypted credential secret."""

        if not self.encrypted_secret:
            return ""
        try:
            return _datasource_fernet().decrypt(
                self.encrypted_secret.encode("utf-8")
            ).decode("utf-8")
        except InvalidToken:
            return ""

    @property
    def has_secret(self):
        """Return whether this credential has an encrypted secret."""

        return bool(self.encrypted_secret)

    def __str__(self):
        return self.name


def _datasource_fernet():
    """Return the symmetric encryptor for datasource credentials."""

    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


class AssistantSkill(models.Model):
    """Assistant to skill binding."""

    assistant = models.ForeignKey(
        Assistant,
        on_delete=models.CASCADE,
        related_name="skill_bindings",
    )
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT)
    enabled = models.BooleanField(default=True)
    load_config = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [("assistant", "skill")]


class AssistantMCP(models.Model):
    """Assistant to MCP binding."""

    assistant = models.ForeignKey(
        Assistant,
        on_delete=models.CASCADE,
        related_name="mcp_bindings",
    )
    mcp = models.ForeignKey(MCPServer, on_delete=models.PROTECT)
    enabled = models.BooleanField(default=True)
    load_config = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [("assistant", "mcp")]


class Session(TimestampedUUIDModel):
    """Conversation session for a user and assistant."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    assistant = models.ForeignKey(Assistant, on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=160, blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or str(self.uuid)


class Message(models.Model):
    """Message within a session."""

    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"
        SYSTEM = "system", "System"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    session = models.ForeignKey(Session, on_delete=models.CASCADE)
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField(blank=True, default="")
    run = models.ForeignKey(
        "Run",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="messages",
    )
    sequence = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["session", "sequence"],
                name="lens_message_session_seq_idx",
            ),
        ]
        unique_together = [("session", "sequence")]
        ordering = ["sequence"]


class Run(models.Model):
    """Execution run for a session message."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        STREAMING = "streaming", "Streaming"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    session = models.ForeignKey(Session, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    input_message = models.ForeignKey(
        Message,
        on_delete=models.PROTECT,
        related_name="request_runs",
    )
    output_message = models.ForeignKey(
        Message,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="response_runs",
    )
    lensnode = models.ForeignKey(
        LensNode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="runs",
    )
    metering_ref = models.UUIDField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="lens_run_idem_nonempty_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["session", "status"],
                name="lens_run_session_status_idx",
            ),
            models.Index(fields=["lensnode"], name="lens_run_lensnode_idx"),
        ]
        ordering = ["-started_at", "-created_at"]


class RunStep(models.Model):
    """Execution step for a run."""

    class StepType(models.TextChoices):
        QUERY_REWRITE = "query_rewrite", "Query Rewrite"
        RETRIEVAL = "retrieval", "Retrieval"
        ANSWER = "answer", "Answer"
        STREAM = "stream", "Stream"

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="steps")
    step_type = models.CharField(max_length=32, choices=StepType.choices)
    detail = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    sequence = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["run", "sequence"],
                name="lens_runstep_run_seq_idx",
            ),
        ]
        unique_together = [("run", "sequence")]
        ordering = ["sequence"]


class RunExecution(models.Model):
    """Per-run execution snapshot dispatched to a LensNode."""

    class Status(models.TextChoices):
        DISPATCHED = "dispatched", "Dispatched"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    run = models.OneToOneField(
        Run,
        on_delete=models.CASCADE,
        related_name="execution",
    )
    lensnode = models.ForeignKey(LensNode, on_delete=models.PROTECT)
    task = models.CharField(max_length=160)
    loaded_skills = models.JSONField(default=list, blank=True)
    loaded_mcps = models.JSONField(default=list, blank=True)
    target_dirs = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DISPATCHED,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["lensnode"], name="lens_runexec_lensnode_idx"),
        ]


class ScheduledTask(TimestampedUUIDModel):
    """Scheduled task mirror for UI reporting."""

    class TaskType(models.TextChoices):
        SOURCE_SYNC = "source_sync", "Source Sync"
        LENSNODE_CLEANUP = "lensnode_cleanup", "LensNode Cleanup"
        RUN_RETENTION = "run_retention", "Run Retention"
        LENSNODE_HEALTH = "lensnode_health", "LensNode Health"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        RUNNING = "running", "Running"

    name = models.CharField(max_length=200)
    task_type = models.CharField(max_length=32, choices=TaskType.choices)
    periodic_task_ref = models.IntegerField(null=True, blank=True)
    target_type = models.CharField(max_length=64, null=True, blank=True)
    target_id = models.UUIDField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(
        max_length=16,
        choices=Status.choices,
        null=True,
        blank=True,
    )
    last_error = models.TextField(blank=True, default="")
    last_metrics = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["task_type"],
                name="lens_sched_task_type_idx",
            ),
            models.Index(
                fields=["target_type", "target_id"],
                name="lens_sched_target_idx",
            ),
        ]


class GlobalSetting(models.Model):
    """Global JSON setting."""

    key = models.CharField(max_length=190, primary_key=True)
    value = models.JSONField(default=dict, blank=True)
    description = models.CharField(max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)
