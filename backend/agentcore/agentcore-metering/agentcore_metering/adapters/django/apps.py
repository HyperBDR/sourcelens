"""Django app config for agentcore_metering (LLM observability)."""
from django.apps import AppConfig


class AgentcoreMeteringDjangoConfig(AppConfig):
    """App config for agentcore_metering Django adapter."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "agentcore_metering.adapters.django"
    label = "agentcore_metering"
    verbose_name = "Agentcore Metering (LLM)"
