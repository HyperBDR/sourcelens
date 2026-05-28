# Re-export from services (single source for public API).
from agentcore_task.adapters.django.services.log_collector import (
    TaskLogCollector,
)

__all__ = ["TaskLogCollector"]
