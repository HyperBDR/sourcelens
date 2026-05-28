"""
Root URLconf for tests: mount agentcore_metering admin API under api/v1/admin/.
"""
from django.urls import path, include

urlpatterns = [
    path("api/v1/admin/", include("agentcore_metering.adapters.django.urls")),
]
