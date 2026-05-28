"""
Webhook driver abstraction.
Register drivers by provider_type; WebhookService dispatches via registry.
"""
from agentcore_notifier.adapters.django.services.webhook.base import (
    BaseWebhookDriver,
)
from agentcore_notifier.adapters.django.services.webhook.feishu import (
    FeishuWebhookDriver,
)
from agentcore_notifier.adapters.django.services.webhook.registry import (
    WebhookDriverRegistry,
    get_default_registry,
)
from agentcore_notifier.adapters.django.services.webhook.wechat import (
    WeChatWebhookDriver,
)

__all__ = [
    "BaseWebhookDriver",
    "FeishuWebhookDriver",
    "WeChatWebhookDriver",
    "WebhookDriverRegistry",
    "get_default_registry",
]
