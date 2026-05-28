"""
Re-export cleanup from parent module (single source: django.cleanup).
"""
from agentcore_task.adapters.django.cleanup import cleanup_old_executions

__all__ = ["cleanup_old_executions"]
