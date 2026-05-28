"""Admin for LLM usage and config (agentcore_metering Django adapter)."""
from django.contrib import admin

from agentcore_metering.adapters.django.models import (
    LLMConfig,
    LLMUsage,
    MeteringConfig,
)


@admin.register(LLMUsage)
class LLMUsageAdmin(admin.ModelAdmin):
    """Admin interface for LLMUsage model."""

    list_display = (
        "id",
        "model",
        "user",
        "total_tokens",
        "cost",
        "cost_currency",
        "prompt_tokens",
        "completion_tokens",
        "success",
        "created_at",
    )
    list_filter = ("success", "model", "created_at")
    search_fields = ("model", "user__username", "metadata")
    readonly_fields = (
        "id",
        "user",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost",
        "cost_currency",
        "cached_tokens",
        "reasoning_tokens",
        "success",
        "error",
        "metadata",
        "created_at",
    )
    ordering = ["-created_at"]


@admin.register(MeteringConfig)
class MeteringConfigAdmin(admin.ModelAdmin):
    """Admin interface for MeteringConfig (global retention, cleanup, cron)."""

    list_display = ("scope", "key", "value", "updated_at")
    list_filter = ("scope", "key")
    ordering = ["scope", "key"]


@admin.register(LLMConfig)
class LLMConfigAdmin(admin.ModelAdmin):
    """Admin interface for LLMConfig (global and per-user)."""

    list_display = ("id", "scope", "user", "provider", "updated_at")
    list_filter = ("scope", "provider")
    search_fields = ("user__username",)
    ordering = ["-updated_at"]
