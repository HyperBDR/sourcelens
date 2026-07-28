"""URL configuration for admin batch integration tests."""

from django.urls import path

from core.views.admin_bulk import (
    LLMConfigBulkView,
    NotificationChannelBulkDeleteView,
)

urlpatterns = [
    path(
        "api/v1/admin/notifications/channels/bulk-delete/",
        NotificationChannelBulkDeleteView.as_view(),
    ),
    path(
        "api/v1/admin/llm-config/bulk/",
        LLMConfigBulkView.as_view(),
    ),
]
