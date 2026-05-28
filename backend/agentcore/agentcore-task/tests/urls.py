from django.urls import include, path

urlpatterns = [
    path("api/v1/tasks/", include("agentcore_task.adapters.django.urls")),
]
