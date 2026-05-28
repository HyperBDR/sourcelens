"""URL config for agentcore_notifier tests."""
from django.urls import path, include

urlpatterns = [
    path("", include("agentcore_notifier.adapters.django.urls")),
]
