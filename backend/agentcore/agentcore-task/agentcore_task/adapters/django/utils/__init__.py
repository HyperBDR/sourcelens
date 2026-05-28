# Re-export from services (single source for public API).
from agentcore_task.adapters.django.services.task_tracker import (
    register_task_execution,
)

__all__ = ["register_task_execution"]
