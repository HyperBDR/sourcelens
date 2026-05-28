"""
URL configuration for agentcore_metering admin API.

Include under an admin prefix, e.g.:
    path('api/v1/admin/', include('agentcore_metering.adapters.django.urls')),
"""
from django.urls import path

from agentcore_metering.adapters.django.views import (
    AdminLLMConfigAllListView,
    MeteringConfigAPIView,
    AdminLLMConfigDetailView,
    AdminLLMConfigGlobalView,
    AdminLLMConfigModelsView,
    AdminLLMConfigProvidersView,
    AdminLLMConfigTestCallView,
    AdminLLMConfigTestView,
    AdminLLMConfigUserDetailView,
    AdminLLMConfigUserListView,
    AdminLLMUsageListView,
    AdminTokenStatsView,
    AdminUsersListView,
)

app_name = "agentcore_metering"

urlpatterns = [
    path("users/", AdminUsersListView.as_view(), name="users"),
    path(
        "metering-config/",
        MeteringConfigAPIView.as_view(),
        name="metering-config",
    ),
    path("token-stats/", AdminTokenStatsView.as_view(), name="token-stats"),
    path("llm-usage/", AdminLLMUsageListView.as_view(), name="llm-usage"),
    path(
        "llm-config/providers/",
        AdminLLMConfigProvidersView.as_view(),
        name="llm-config-providers",
    ),
    path(
        "llm-config/models/",
        AdminLLMConfigModelsView.as_view(),
        name="llm-config-models",
    ),
    path(
        "llm-config/test/",
        AdminLLMConfigTestView.as_view(),
        name="llm-config-test",
    ),
    path(
        "llm-config/test-call/",
        AdminLLMConfigTestCallView.as_view(),
        name="llm-config-test-call",
    ),
    path(
        "llm-config/all/",
        AdminLLMConfigAllListView.as_view(),
        name="llm-config-all",
    ),
    path(
        "llm-config/<uuid:config_ref>/",
        AdminLLMConfigDetailView.as_view(),
        name="llm-config-detail",
    ),
    path(
        "llm-config/<int:config_ref>/",
        AdminLLMConfigDetailView.as_view(),
        name="llm-config-detail-legacy",
    ),
    path(
        "llm-config/",
        AdminLLMConfigGlobalView.as_view(),
        name="llm-config-global",
    ),
    path(
        "llm-config/users/",
        AdminLLMConfigUserListView.as_view(),
        name="llm-config-users",
    ),
    path(
        "llm-config/users/<int:user_id>/",
        AdminLLMConfigUserDetailView.as_view(),
        name="llm-config-user-detail",
    ),
]
