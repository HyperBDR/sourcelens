"""
Read and write notifier config from NotifierConfig model (global scope).
Aligned with agentcore_task.services.task_config.
"""
import logging
from typing import Any, Optional

from agentcore_notifier.adapters.django.models import NotifierConfig

logger = logging.getLogger(__name__)


def get_config(key: str) -> Optional[Any]:
    """
    Return value for global config key from NotifierConfig, or None if not set.
    """
    try:
        row = NotifierConfig.objects.filter(
            scope=NotifierConfig.SCOPE_GLOBAL,
            user__isnull=True,
            key=key,
        ).first()
        if row is not None and row.value is not None:
            return row.value
    except Exception as e:
        logger.debug(f"get_config({key}) failed: {e}")
    return None


def set_config(key: str, value: Any) -> None:
    """
    Set global config key in NotifierConfig. Creates or updates the row.
    """
    NotifierConfig.objects.update_or_create(
        scope=NotifierConfig.SCOPE_GLOBAL,
        user=None,
        key=key,
        defaults={"value": value},
    )
