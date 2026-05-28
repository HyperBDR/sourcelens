"""
Registry of webhook drivers by provider type.
Allows registering custom drivers and dispatching send by provider_type.
"""
import logging
from typing import Any, Dict, Type

from .base import BaseWebhookDriver

logger = logging.getLogger(__name__)


class WebhookDriverRegistry:
    """
    Registry of webhook drivers.
    Map provider_type (e.g. feishu, wechat) to driver class.
    """

    def __init__(self):
        self._drivers: Dict[str, Type[BaseWebhookDriver]] = {}

    def register(self, driver_class: Type[BaseWebhookDriver]) -> None:
        """Register a driver for its provider_type."""
        pt = getattr(driver_class, "provider_type", None)
        if not pt:
            logger.warning(
                f"WebhookDriverRegistry: skipping driver without "
                f"provider_type: {driver_class}"
            )
            return
        self._drivers[pt] = driver_class
        logger.debug(f"WebhookDriverRegistry: registered driver for {pt}")

    def get_driver_class(
        self, provider_type: str
    ) -> Type[BaseWebhookDriver] | None:
        """Return driver class for provider_type, or None if unknown."""
        return self._drivers.get(provider_type)

    def send(
        self,
        provider_type: str,
        payload: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Send payload via the driver for the given provider_type.
        Returns result dict from driver, or error dict if no driver.
        """
        driver_cls = self.get_driver_class(provider_type)
        if not driver_cls:
            return {
                "success": False,
                "response": None,
                "error": (
                    f"Unsupported webhook provider type: {provider_type}"
                ),
            }
        driver = driver_cls()
        return driver.send(payload, config)

    def supported_provider_types(self):
        """Return set of registered provider types."""
        return set(self._drivers.keys())


def get_default_registry() -> WebhookDriverRegistry:
    """Build registry with built-in drivers (feishu, wecom, wechat)."""
    # NOTE(Ray): Lazy import to avoid circular import (registry <- service).
    from agentcore_notifier.constants import FEISHU_PROVIDERS, Provider

    from .feishu import FeishuWebhookDriver
    from .wechat import WeChatWebhookDriver

    reg = WebhookDriverRegistry()
    reg.register(FeishuWebhookDriver)
    reg.register(WeChatWebhookDriver)
    for pt in FEISHU_PROVIDERS:
        if pt != FeishuWebhookDriver.provider_type:
            reg._drivers[pt] = FeishuWebhookDriver
    if Provider.WECHAT not in reg._drivers:
        reg._drivers[Provider.WECHAT] = WeChatWebhookDriver
    return reg
