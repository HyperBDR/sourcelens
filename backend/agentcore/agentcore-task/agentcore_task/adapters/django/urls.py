"""
URL configuration for agentcore_task task API.

Include under tasks prefix, e.g.:
    path('api/v1/tasks/', include(
        'agentcore_task.adapters.django.urls')),
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from agentcore_task.adapters.django.views import TaskExecutionViewSet
from agentcore_task.adapters.django.views.config import TaskConfigAPIView

router = DefaultRouter()
router.register(
    r"executions",
    TaskExecutionViewSet,
    basename="task-execution",
)

urlpatterns = [
    path("config/", TaskConfigAPIView.as_view(), name="task-config"),
    path("", include(router.urls)),
]
