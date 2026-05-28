"""
Serializers for agentcore_metering admin API.

Includes read/write serializers for LLM config and response serializers
for OpenAPI/Swagger documentation (token stats, usage list, errors).
"""
from rest_framework import serializers

from agentcore_metering.adapters.django.models import LLMConfig


def _mask_secrets(config: dict) -> dict:
    if not config or not isinstance(config, dict):
        return config or {}
    out = {}
    for k, v in config.items():
        if isinstance(v, dict):
            out[k] = _mask_secrets(v)
        elif k in ("api_key", "key") and v and isinstance(v, str):
            if len(v) <= 8:
                out[k] = "***"
            else:
                out[k] = v[:4] + "***" + v[-4:]
        else:
            out[k] = v
    return out


class LLMConfigSerializer(serializers.ModelSerializer):
    """
    Read LLM config. On read, api_key (and key) in config are masked.
    is_default is True when this config is the default (earliest enabled
    global config by created_at); frontend can use it to show the default.
    """

    is_default = serializers.BooleanField(
        read_only=True,
        help_text=(
            "True if this config is the one used when model_uuid is not set "
            "(current default). When there is only one active global config, "
            "it is the default."
        ),
    )

    class Meta:
        model = LLMConfig
        fields = [
            "id",
            "uuid",
            "scope",
            "user",
            "model_type",
            "provider",
            "config",
            "is_active",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "uuid",
            "is_default",
            "created_at",
            "updated_at",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.config:
            data["config"] = _mask_secrets(instance.config)
        if instance.user_id:
            data["user_id"] = instance.user_id
            data["username"] = getattr(instance.user, "username", None)
        default_uuid = self.context.get("default_config_uuid")
        data["is_default"] = (
            default_uuid is not None
            and str(instance.uuid) == str(default_uuid)
        )
        return data


class LLMConfigWriteSerializer(serializers.Serializer):
    """
    Payload for creating/updating LLM config: provider + single config dict.
    """

    provider = serializers.CharField(
        default="openai",
        max_length=50,
        help_text=(
            "Provider id (e.g. openai, anthropic, azure_openai). "
            "Default: openai."
        ),
    )
    config = serializers.JSONField(
        required=False,
        default=dict,
        help_text=(
            "Provider-specific config: api_key (required for most), model, "
            "api_base, deployment (Azure), max_tokens, temperature, top_p, "
            "api_version (Azure). Use GET .../llm-config/providers/ for "
            "per-provider required/optional keys."
        ),
    )
    is_active = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Whether this config is active for resolution.",
    )
    is_default = serializers.BooleanField(
        required=False,
        default=False,
        help_text=(
            "If true, set this global config as the default (clears default "
            "on other global configs). Ignored for user-scope configs."
        ),
    )


class ErrorDetailSerializer(serializers.Serializer):
    """Standard error body for 400/404 responses in API docs."""

    detail = serializers.CharField(
        allow_blank=True,
        help_text="Human-readable error message.",
    )


class TokenStatsSummarySerializer(serializers.Serializer):
    """Summary block of token statistics (totals in date range)."""

    total_prompt_tokens = serializers.IntegerField(
        help_text="Sum of prompt tokens",
    )
    total_completion_tokens = serializers.IntegerField(
        help_text="Sum of completion tokens",
    )
    total_tokens = serializers.IntegerField(help_text="Sum of total tokens")
    total_cached_tokens = serializers.IntegerField(
        help_text="Sum of cached tokens",
    )
    total_reasoning_tokens = serializers.IntegerField(
        help_text="Sum of reasoning tokens (if any)",
    )
    total_cost = serializers.FloatField(help_text="Estimated cost in USD")
    total_cost_currency = serializers.CharField(
        help_text="Currency code (e.g. USD)",
    )
    total_calls = serializers.IntegerField(
        help_text="Total number of LLM calls",
    )
    successful_calls = serializers.IntegerField(
        help_text="Number of successful calls",
    )
    failed_calls = serializers.IntegerField(help_text="Number of failed calls")


class TokenStatsByModelItemSerializer(serializers.Serializer):
    """One row of token stats grouped by model."""

    model = serializers.CharField(help_text="Model identifier")
    total_calls = serializers.IntegerField()
    total_prompt_tokens = serializers.IntegerField()
    total_completion_tokens = serializers.IntegerField()
    total_tokens = serializers.IntegerField()
    total_cached_tokens = serializers.IntegerField()
    total_reasoning_tokens = serializers.IntegerField()
    total_cost = serializers.FloatField()
    total_cost_currency = serializers.CharField()


class TokenStatsSeriesItemSerializer(serializers.Serializer):
    """One time bucket in the series (hour/day/month)."""

    bucket = serializers.CharField(
        allow_null=True,
        help_text="ISO datetime or date string for the bucket",
    )
    total_calls = serializers.IntegerField()
    total_prompt_tokens = serializers.IntegerField()
    total_completion_tokens = serializers.IntegerField()
    total_tokens = serializers.IntegerField()
    total_cached_tokens = serializers.IntegerField()
    total_reasoning_tokens = serializers.IntegerField()
    total_cost = serializers.FloatField()


class TokenStatsSeriesSerializer(serializers.Serializer):
    """Optional time series when granularity query param is set."""

    granularity = serializers.CharField(help_text="day | month | year")
    items = TokenStatsSeriesItemSerializer(many=True)


class TokenStatsSeriesByModelItemSerializer(serializers.Serializer):
    """
    One (bucket, model) row from pre-aggregated LLMUsageSeries.
    Used for performance curves (e2e, ttft, output_tps), token and cost trend.
    """

    bucket = serializers.CharField(allow_null=True)
    model = serializers.CharField()
    call_count = serializers.IntegerField()
    success_count = serializers.IntegerField()
    avg_e2e_latency_sec = serializers.FloatField(allow_null=True)
    avg_ttft_sec = serializers.FloatField(allow_null=True)
    avg_output_tps = serializers.FloatField(allow_null=True)
    total_prompt_tokens = serializers.IntegerField()
    total_completion_tokens = serializers.IntegerField()
    total_tokens = serializers.IntegerField()
    total_cached_tokens = serializers.IntegerField()
    total_reasoning_tokens = serializers.IntegerField()
    total_cost = serializers.FloatField(allow_null=True)
    cost_currency = serializers.CharField()


class TokenStatsResponseSerializer(serializers.Serializer):
    """Full response shape for GET .../token-stats/."""

    summary = TokenStatsSummarySerializer(
        help_text="Aggregate stats in the date range",
    )
    by_model = TokenStatsByModelItemSerializer(
        many=True,
        help_text="Stats per model, ordered by total_tokens desc",
    )
    series = TokenStatsSeriesSerializer(
        allow_null=True,
        required=False,
        help_text=(
            "Present only when granularity is set "
            "(day=hourly, month=daily, year=monthly)",
        ),
    )
    series_by_model = TokenStatsSeriesByModelItemSerializer(
        many=True,
        required=False,
        allow_null=True,
        help_text=(
            "Pre-aggregated (bucket, model) series when use_series=1 and "
            "granularity + date range set; for performance and cost charts.",
        ),
    )
    expected_buckets = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_null=True,
        help_text=(
            "Full ordered bucket list (ISO) for granularity and range; "
            "charts use this for complete x-axis."
        ),
    )


class MeteringConfigSerializer(serializers.Serializer):
    """Effective metering config (GET response)."""

    retention_days = serializers.IntegerField(min_value=1)
    cleanup_enabled = serializers.BooleanField()
    cleanup_crontab = serializers.CharField()
    aggregation_crontab = serializers.CharField()


class MeteringConfigUpdateSerializer(serializers.Serializer):
    """Request body for PATCH metering config (optional fields)."""

    retention_days = serializers.IntegerField(
        min_value=1, max_value=3650, required=False
    )
    cleanup_enabled = serializers.BooleanField(required=False)
    cleanup_crontab = serializers.CharField(required=False, allow_blank=False)
    aggregation_crontab = serializers.CharField(
        required=False, allow_blank=False
    )


class LLMUsageItemSerializer(serializers.Serializer):
    """One LLM usage record in the paginated list."""

    id = serializers.CharField(help_text="Usage record id")
    user_id = serializers.IntegerField(allow_null=True)
    username = serializers.CharField(allow_null=True)
    model = serializers.CharField()
    prompt_tokens = serializers.IntegerField(allow_null=True)
    completion_tokens = serializers.IntegerField(allow_null=True)
    total_tokens = serializers.IntegerField(allow_null=True)
    cost = serializers.FloatField(allow_null=True)
    cost_currency = serializers.CharField(allow_null=True)
    success = serializers.BooleanField()
    error = serializers.CharField(allow_null=True)
    created_at = serializers.CharField(allow_null=True)
    metadata = serializers.JSONField(allow_null=True)


class LLMUsageListResponseSerializer(serializers.Serializer):
    """Response shape for GET .../llm-usage/ (paginated)."""

    results = LLMUsageItemSerializer(
        many=True,
        help_text="Page of usage records",
    )
    total = serializers.IntegerField(help_text="Total count matching filters")
    page = serializers.IntegerField(help_text="Current page (1-based)")
    page_size = serializers.IntegerField(help_text="Page size used")


class TestCallRequestSerializer(serializers.Serializer):
    """Request body for POST .../llm-config/test-call/."""

    config_uuid = serializers.UUIDField(
        required=False,
        help_text="LLMConfig uuid to use for the call",
    )
    config_id = serializers.IntegerField(
        required=False,
        help_text="Deprecated: LLMConfig integer id (use config_uuid instead)",
    )
    prompt = serializers.CharField(
        allow_blank=False,
        help_text="User message to send to the model",
    )
    max_tokens = serializers.IntegerField(
        required=False,
        default=512,
        min_value=1,
        max_value=4096,
        help_text="Max tokens for the completion (default 512, max 4096)",
    )
    stream = serializers.BooleanField(
        required=False,
        default=False,
        help_text=(
            "If true, response is SSE stream "
            "(chunk events then done with usage)."
        ),
    )

    def validate(self, attrs):
        if not attrs.get("config_uuid") and attrs.get("config_id") is None:
            raise serializers.ValidationError(
                "Either config_uuid or config_id is required; "
                "config_uuid is preferred (config_id is deprecated)."
            )
        return attrs


class TestCallUsageSerializer(serializers.Serializer):
    """Usage block in test-call response."""

    model = serializers.CharField()
    prompt_tokens = serializers.IntegerField()
    completion_tokens = serializers.IntegerField()
    total_tokens = serializers.IntegerField()
    cached_tokens = serializers.IntegerField(required=False, default=0)
    reasoning_tokens = serializers.IntegerField(required=False, default=0)
    cost = serializers.FloatField(allow_null=True)
    cost_currency = serializers.CharField(allow_null=True)


class TestCallResponseSerializer(serializers.Serializer):
    """Response shape for POST .../llm-config/test-call/ (200)."""

    ok = serializers.BooleanField(
        help_text="True if the completion succeeded",
    )
    content = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Model reply when ok is true",
    )
    detail = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Error message when ok is false",
    )
    usage = TestCallUsageSerializer(
        allow_null=True,
        required=False,
        help_text="Token and cost info when ok is true",
    )


class ConfigTestResponseSerializer(serializers.Serializer):
    """Response shape for POST .../llm-config/test/ (200)."""

    ok = serializers.BooleanField(
        help_text="True if validation/completion succeeded",
    )
    detail = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Error message when ok is false",
    )


class ProviderParamSchemaEntrySerializer(serializers.Serializer):
    """Per-provider param schema (one entry in GET .../providers/)."""

    required = serializers.ListField(
        child=serializers.CharField(),
        help_text=(
            "Required config keys (e.g. api_key, or "
            "api_key+api_base+deployment for Azure)",
        ),
    )
    optional = serializers.ListField(
        child=serializers.CharField(),
        help_text=(
            "Optional config keys (e.g. model, api_base, max_tokens, "
            "temperature, top_p)",
        ),
    )
    editable_params = serializers.ListField(
        child=serializers.CharField(),
        help_text="All configurable keys in suggested order",
    )
    default_model = serializers.CharField(
        allow_null=True,
        help_text="Default model id when not set in config",
    )
    default_api_base = serializers.CharField(
        allow_null=True,
        help_text="Official API base URL when not set in config",
    )
    default_temperature = serializers.FloatField(
        allow_null=True,
        required=False,
        help_text="Provider default temperature",
    )
    default_top_p = serializers.FloatField(
        allow_null=True,
        required=False,
        help_text="Provider default top_p",
    )
    default_max_tokens = serializers.IntegerField(
        allow_null=True,
        required=False,
        help_text="Provider default max_tokens",
    )


class ProvidersResponseSerializer(serializers.Serializer):
    """Response for GET .../llm-config/providers/. Keys are provider ids."""

    providers = serializers.DictField(
        child=ProviderParamSchemaEntrySerializer(),
        help_text=(
            "Map of provider id to param schema (required, optional, "
            "default_model, default_api_base)",
        ),
    )


class ModelCapabilitySerializer(serializers.Serializer):
    """One capability tag (e.g. text-to-text, vision, reasoning)."""

    id = serializers.CharField()
    name = serializers.CharField(allow_null=True, required=False)


class ModelEntrySerializer(serializers.Serializer):
    """One model under a provider in GET .../llm-config/models/."""

    id = serializers.CharField(help_text="Model id (e.g. gpt-4o-mini)")
    name = serializers.CharField(allow_null=True, required=False)
    capabilities = ModelCapabilitySerializer(many=True, required=False)


class ProviderModelsEntrySerializer(serializers.Serializer):
    """One provider block in GET .../llm-config/models/."""

    id = serializers.CharField(help_text="Provider id")
    name = serializers.CharField(allow_null=True, required=False)
    models = ModelEntrySerializer(many=True)
    default_api_base = serializers.CharField(allow_null=True, required=False)


class ModelsResponseSerializer(serializers.Serializer):
    """Response shape for GET .../llm-config/models/."""

    providers = serializers.ListField(
        child=ProviderModelsEntrySerializer(),
        help_text=(
            "List of providers with models and capability tags "
            "(e.g. text-to-text, vision, code, reasoning)",
        ),
    )
