"""
LLM Usage model for tracking token consumption and cost analysis.
"""
import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class LLMUsage(models.Model):
    """
    Stores LLM API token usage records for statistics and cost analysis.

    Each record represents a single LLM API call for tracking token
    consumption and supporting admin cost analysis.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="llm_usages",
        db_index=True,
        help_text="User who triggered this LLM call",
    )

    model = models.CharField(
        max_length=200,
        db_index=True,
        help_text="LLM model name used for this call",
    )
    prompt_tokens = models.IntegerField(
        default=0,
        help_text="Number of input/prompt tokens used",
    )
    completion_tokens = models.IntegerField(
        default=0,
        help_text="Number of output/completion tokens generated",
    )
    total_tokens = models.IntegerField(
        default=0,
        db_index=True,
        help_text="Total tokens used (prompt + completion)",
    )
    cached_tokens = models.IntegerField(
        default=0,
        help_text="Number of cached tokens (if applicable)",
    )
    reasoning_tokens = models.IntegerField(
        default=0,
        help_text="Number of reasoning tokens (for o1 models)",
    )
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Cost amount (use with cost_currency for multi-currency)"
        ),
    )
    cost_currency = models.CharField(
        max_length=10,
        default="USD",
        blank=True,
        db_index=True,
        help_text="ISO 4217 currency code (e.g. USD, CNY). LiteLLM uses USD.",
    )
    success = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether the LLM call succeeded",
    )
    error = models.TextField(
        blank=True,
        null=True,
        help_text="Error message if the call failed",
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Context and source info: node_name, source_type, source_task_id, "
            "source_path, etc. Flat structure for flexible querying."
        ),
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "When the LLM request started (t_start). Used for E2E latency."
        ),
    )
    is_streaming = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether the call was made in streaming mode",
    )
    first_chunk_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "When the first content chunk arrived (streaming only). "
            "Used for TTFT = first_chunk_at - started_at."
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the record was saved after call completed (t_end).",
    )

    class Meta:
        db_table = "llm_tracker_usage"
        ordering = ["-created_at"]
        verbose_name = _("LLM Usage")
        verbose_name_plural = _("LLM Usages")
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["model", "-created_at"]),
            models.Index(fields=["total_tokens", "-created_at"]),
            models.Index(fields=["success", "-created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        node_name = self.metadata.get("node_name", "")
        node_info = f"{node_name} - " if node_name else ""
        return (
            f"{node_info}{self.model} "
            f"({self.total_tokens} tokens) - {self.created_at}"
        )


class LLMUsageSeries(models.Model):
    """
    Pre-aggregated time-series per (granularity, bucket, model) for charts.

    Populated by a scheduled task from LLMUsage. Supports day (hourly buckets),
    month (daily buckets), year (monthly buckets). Used for performance
    curves (e2e, ttft, output_tps), token trend, and cost trend by model.
    """

    class Granularity(models.TextChoices):
        HOUR = "hour", _("Hour (for day view)")
        DAY = "day", _("Day (for month view)")
        MONTH = "month", _("Month (for year view)")

    granularity = models.CharField(
        max_length=10,
        choices=Granularity.choices,
        db_index=True,
    )
    bucket = models.DateTimeField(
        db_index=True,
        help_text="Truncated time bucket (hour/day/month).",
    )
    model = models.CharField(max_length=200, db_index=True)

    call_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)

    avg_e2e_latency_sec = models.FloatField(null=True, blank=True)
    avg_ttft_sec = models.FloatField(null=True, blank=True)
    avg_output_tps = models.FloatField(null=True, blank=True)

    total_prompt_tokens = models.BigIntegerField(default=0)
    total_completion_tokens = models.BigIntegerField(default=0)
    total_tokens = models.BigIntegerField(default=0)
    total_cached_tokens = models.BigIntegerField(default=0)
    total_reasoning_tokens = models.BigIntegerField(default=0)

    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
    )
    cost_currency = models.CharField(max_length=10, default="USD", blank=True)

    class Meta:
        db_table = "llm_usage_series"
        verbose_name = _("LLM Usage Series")
        verbose_name_plural = _("LLM Usage Series")
        ordering = ["granularity", "bucket", "model"]
        constraints = [
            models.UniqueConstraint(
                fields=["granularity", "bucket", "model"],
                name="llm_usage_series_unique_bucket_model",
            ),
        ]
        indexes = [
            models.Index(fields=["granularity", "bucket"]),
            models.Index(fields=["granularity", "model", "bucket"]),
        ]

    def __str__(self) -> str:
        return f"{self.granularity} {self.bucket} {self.model}"


class LLMConfig(models.Model):
    """
    LLM provider configuration: multiple entries per scope (global or user).

    Each row is one model config (provider + credentials). model_type aligns
    with LiteLLM: completion (llm), embedding, image_generation.
    is_active controls whether the config is used. Default resolution
    uses the earliest enabled config by created_at.
    """

    class Scope(models.TextChoices):
        GLOBAL = "global", _("Global")
        USER = "user", _("User")

    MODEL_TYPE_LLM = "llm"
    MODEL_TYPE_EMBEDDING = "embedding"
    MODEL_TYPE_IMAGE_GENERATION = "image_generation"
    MODEL_TYPES = (
        MODEL_TYPE_LLM,
        MODEL_TYPE_EMBEDDING,
        MODEL_TYPE_IMAGE_GENERATION,
    )

    scope = models.CharField(
        max_length=20,
        choices=Scope.choices,
        db_index=True,
        help_text="global = site default; user = per-user override",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="llm_configs",
        help_text="Null for global config; set for user override",
    )
    model_type = models.CharField(
        max_length=30,
        default=MODEL_TYPE_LLM,
        db_index=True,
        help_text=(
            "LiteLLM call type: llm (completion), embedding, image_generation."
        ),
    )
    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Public identifier for API operations.",
    )
    provider = models.CharField(
        max_length=50,
        default="openai",
        db_index=True,
        help_text="Provider key, e.g. openai, azure_openai, gemini.",
    )
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Provider-specific config (api_key, model, api_base, etc.).",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="If false, this config is not used when resolving.",
    )
    is_default = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "If true, this global config is used when model_uuid is not set. "
            "Only one global LLM config should be default; setting one clears "
            "others. Ignored for user-scope configs."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agentcore_metering_llm_config"
        verbose_name = _("LLM Config")
        verbose_name_plural = _("LLM Configs")
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        if self.scope == self.Scope.GLOBAL:
            return f"LLM config (global) {self.provider}"
        return f"LLM config (user {self.user_id}) {self.provider}"


class MeteringConfig(models.Model):
    """
    Global config for metering: retention_days, cleanup_crontab,
    cleanup_enabled, aggregation schedules. Used by periodic tasks
    and config API (frontend).
    """

    SCOPE_GLOBAL = "global"
    SCOPE_CHOICES = [(SCOPE_GLOBAL, "Global")]

    scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default=SCOPE_GLOBAL,
        db_index=True,
    )
    key = models.CharField(max_length=128, db_index=True)
    value = models.JSONField(
        default=dict,
        help_text="Config payload, e.g. {\"retention_days\": 365}.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agentcore_metering_config"
        verbose_name = _("Metering Config")
        verbose_name_plural = _("Metering Configs")
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "key"],
                name="agentcore_metering_config_scope_key_uniq",
            ),
        ]
        indexes = [models.Index(fields=["scope", "key"])]

    def __str__(self) -> str:
        return f"MeteringConfig(scope={self.scope}, key={self.key})"
