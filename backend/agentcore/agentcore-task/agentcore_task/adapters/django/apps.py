"""Django app config for agentcore_task (task execution)."""
from django.apps import AppConfig


class AgentcoreTaskDjangoConfig(AppConfig):
    """App config for agentcore_task Django adapter."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "agentcore_task.adapters.django"
    label = "agentcore_task_tracker"
    verbose_name = "Agentcore Task"

    def ready(self):
        pass
