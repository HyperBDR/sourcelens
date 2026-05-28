"""
Admin API views split by domain.
"""
from agentcore_metering.adapters.django.views.config_catalog import (
    AdminLLMConfigModelsView,
    AdminLLMConfigProvidersView,
)
from agentcore_metering.adapters.django.views.config_management import (
    AdminLLMConfigAllListView,
    AdminLLMConfigDetailView,
    AdminLLMConfigGlobalView,
    AdminLLMConfigUserDetailView,
    AdminLLMConfigUserListView,
)
from agentcore_metering.adapters.django.views.config_validation import (
    AdminLLMConfigTestCallView,
    AdminLLMConfigTestView,
)
from agentcore_metering.adapters.django.views.metering_config import (
    MeteringConfigAPIView,
)
from agentcore_metering.adapters.django.views.usage import (
    AdminLLMUsageListView,
    AdminTokenStatsView,
)
from agentcore_metering.adapters.django.views.users import AdminUsersListView

__all__ = [
    "AdminLLMConfigAllListView",
    "AdminLLMConfigDetailView",
    "AdminLLMConfigGlobalView",
    "AdminLLMConfigModelsView",
    "AdminLLMConfigProvidersView",
    "AdminLLMConfigTestCallView",
    "AdminLLMConfigTestView",
    "AdminLLMConfigUserDetailView",
    "AdminLLMConfigUserListView",
    "AdminLLMUsageListView",
    "AdminTokenStatsView",
    "AdminUsersListView",
    "MeteringConfigAPIView",
]
