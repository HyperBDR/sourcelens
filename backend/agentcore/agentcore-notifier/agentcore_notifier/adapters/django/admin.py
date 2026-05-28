"""Admin for agentcore_notifier Django adapter."""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from agentcore_notifier.adapters.django.models import (
    NotificationChannel,
    NotificationRecord,
    NotifierConfig,
)


@admin.register(NotificationRecord)
class NotificationRecordAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "provider_type",
        "source_app",
        "source_type",
        "status",
        "created_at",
        "sent_at",
    ]
    list_filter = ["provider_type", "status", "source_app", "created_at"]
    search_fields = ["source_app", "source_type", "source_id"]
    readonly_fields = ["created_at", "sent_at"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]


@admin.register(NotifierConfig)
class NotifierConfigAdmin(admin.ModelAdmin):
    list_display = ["scope", "user", "key", "updated_at"]
    list_filter = ["scope", "key"]
    search_fields = ["key"]
    raw_id_fields = ["user"]
    ordering = ["scope", "key"]


@admin.register(NotificationChannel)
class NotificationChannelAdmin(admin.ModelAdmin):
    list_display = [
        "id", "channel_type", "name", "is_active", "is_default",
        "ordering", "created_at",
    ]
    list_filter = ["channel_type", "is_active", "is_default"]
    search_fields = ["name"]
    ordering = ["ordering", "created_at"]
