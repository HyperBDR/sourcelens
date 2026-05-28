"""
Task lock API: acquire, release, check, prevent_duplicate_task decorator.
Re-exported by services/__init__.py; use from agentcore_task.adapters.django.
"""
from agentcore_task.adapters.django.services.lock import (
    acquire_task_lock,
    is_task_locked,
    prevent_duplicate_task,
    release_task_lock,
)

__all__ = [
    "acquire_task_lock",
    "release_task_lock",
    "is_task_locked",
    "prevent_duplicate_task",
]
