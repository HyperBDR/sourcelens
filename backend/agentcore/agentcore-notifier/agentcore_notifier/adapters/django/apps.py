"""Django app config for agentcore_notifier."""
from django.apps import AppConfig


class AgentcoreNotifierDjangoConfig(AppConfig):
    """App config for agentcore_notifier Django adapter."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "agentcore_notifier.adapters.django"
    label = "agentcore_notifier"
    verbose_name = "Agentcore Notifier"

    def ready(self):
        pass
