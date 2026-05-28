"""
Read and write metering config from MeteringConfig model (global scope).

Used by conf.py for retention_days, cleanup_enabled, cleanup_crontab, etc.
"""
import logging
from typing import Any, Optional

from agentcore_metering.adapters.django.models import MeteringConfig

logger = logging.getLogger(__name__)


def get_global_config(key: str) -> Optional[Any]:
    """
    Return value for global config key from MeteringConfig, or None if not set.
    """
    try:
        row = MeteringConfig.objects.filter(
            scope=MeteringConfig.SCOPE_GLOBAL,
            key=key,
        ).first()
        if row is None or row.value is None:
            return None
        return row.value
    except Exception as e:
        logger.debug(f"get_global_config {key}: {e}")
        return None


def set_global_config(key: str, value: Any) -> None:
    """
    Set global config key in MeteringConfig. Creates or updates the row.
    """
    MeteringConfig.objects.update_or_create(
        scope=MeteringConfig.SCOPE_GLOBAL,
        key=key,
        defaults={"value": value},
    )
