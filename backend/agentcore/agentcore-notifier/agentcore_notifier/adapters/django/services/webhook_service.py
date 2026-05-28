"""
Webhook service for sending notifications.
Reads config from NotificationChannel (webhook type); dispatches by
provider_type via WebhookDriverRegistry.
"""
import logging
from typing import Any, Dict, Optional, Tuple, Union
from uuid import UUID

from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.response import Response

from agentcore_notifier.adapters.django.models import (
    NotificationChannel,
    NotificationRecord,
)
from agentcore_notifier.adapters.django.services.webhook import (
    get_default_registry,
)
from agentcore_notifier.constants import (
    Channel,
    DEFAULT_PROVIDER_TYPE,
    DEFAULT_SOURCE_APP,
    Provider,
    Status,
)

logger = logging.getLogger(__name__)


def build_text_payload(provider_type: str, text: str) -> Dict[str, Any]:
    """
    Build a canonical text payload for supported webhook providers.

    Feishu uses:
    {"msg_type": "text", "content": {"text": "..."}}
    WeChat Work and WeCom use:
    {"msgtype": "text", "text": {"content": "..."}}
    """
    provider = (provider_type or DEFAULT_PROVIDER_TYPE).strip().lower()
    if provider == Provider.FEISHU:
        return {
            "msg_type": "text",
            "content": {"text": text},
        }
    if provider in (Provider.WECHAT, Provider.WECOM):
        return {
            "msgtype": "text",
            "text": {"content": text},
        }
    return {
        "msg_type": "text",
        "content": {"text": text},
    }


def build_validation_payload(
    provider_type: str,
    text: str,
    title: str = "Webhook Test",
) -> Dict[str, Any]:
    """
    Build the canonical validation payload for supported webhook providers.

    Validation uses a Feishu interactive card for Feishu, and text
    messages for WeChat Work / WeCom.
    """
    provider = (provider_type or DEFAULT_PROVIDER_TYPE).strip().lower()
    if provider == Provider.FEISHU:
        return {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True,
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title,
                    },
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": text,
                        },
                    }
                ],
            },
        }
    return build_text_payload(provider, text)


def build_error_response(message: str) -> Response:
    """Build a standard DRF validation error response for webhooks."""
    return Response(
        {
            "code": 400,
            "message": message,
            "data": {
                "valid": False,
                "errors": [message],
            },
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def parse_http_response(
    provider_type: str,
    http_response: Any,
) -> Tuple[Optional[Response], Any]:
    """
    Parse a webhook validation HTTP response and normalize provider errors.
    """
    try:
        response = http_response.json()
    except ValueError:
        error_msg = _(
            "Invalid response format from webhook. Expected JSON but got: {}"
        ).format(http_response.text[:100])
        return build_error_response(error_msg), None

    if http_response.status_code >= 400:
        body_key = (
            "msg"
            if (provider_type or "").strip().lower() == Provider.FEISHU
            else "errmsg"
        )
        error_msg = _(
            "Webhook request failed with HTTP status {}. Response: {}"
        ).format(
            http_response.status_code,
            response.get(body_key, str(response)),
        )
        return build_error_response(error_msg), None

    return None, response


def build_exception_response(error_msg: str) -> Response:
    """Build a standard response for transport/runtime validation failures."""
    friendly_msg = _(
        "Webhook validation failed: {}. Please check if the webhook URL is "
        "correct, or verify security settings (e.g., IP whitelist, API key)."
    ).format(error_msg)
    return build_error_response(friendly_msg)


# Backward-compatible aliases.
build_webhook_text_payload = build_text_payload
build_webhook_validation_payload = build_validation_payload
build_webhook_validation_error_response = build_error_response
parse_webhook_validation_http_response = parse_http_response
build_webhook_validation_exception_response = build_exception_response


def build_webhook_config_from_dict(
    cfg: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Build internal webhook config dict from a raw config dict (e.g. from
    application layer or NotificationChannel.config). Callers can pass
    channel config at call time for maximum flexibility.
    Returns None if url is missing or empty.
    """
    if not cfg:
        return None
    url = (cfg.get("url") or "").strip()
    if not url:
        return None
    return {
        "is_active": True,
        "provider": (
            cfg.get("provider_type")
            or cfg.get("provider")
            or DEFAULT_PROVIDER_TYPE
        ),
        "url": url,
        "headers": cfg.get("headers") or {},
        "message_prefix": (
            (cfg.get("message_prefix") or "").strip() or None
        ),
        "sign_secret": (cfg.get("sign_secret") or "").strip() or None,
        "timeout": cfg.get("timeout"),
    }


def get_default_webhook_channel():
    """
    Get webhook channel for sending: first active channel ordered by
    created_at (earliest first). Name/ordering changes do not affect default.
    Returns (channel, config) or (None, None).
    """
    qs = (
        NotificationChannel.objects.filter(
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            is_active=True,
        )
        .order_by("created_at")
    )
    channel = qs.first()
    if not channel or not channel.config:
        return None, None
    config = build_webhook_config_from_dict(channel.config)
    if not config:
        return None, None
    return channel, config


def get_webhook_channel_by_uuid(
    channel_uuid: Union[str, UUID],
) -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
    """
    Get webhook channel by UUID for application-layer channel selection.
    Use UUID so that channel name changes do not break references.
    Returns (channel, config) or (None, None) if not found or inactive.
    """
    try:
        uuid_val = (
            UUID(str(channel_uuid))
            if isinstance(channel_uuid, str)
            else channel_uuid
        )
    except (ValueError, TypeError):
        return None, None
    channel = (
        NotificationChannel.objects.filter(
            uuid=uuid_val,
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            is_active=True,
        )
        .first()
    )
    if not channel or not channel.config:
        return None, None
    config = build_webhook_config_from_dict(channel.config)
    if not config:
        return None, None
    return channel, config


def _get_webhook_config() -> Optional[Dict[str, Any]]:
    """Get active webhook config dict (for backward compat)."""
    _channel, config = get_default_webhook_channel()
    return config


class WebhookService:
    """
    Service for webhook notifications.
    Config from NotificationChannel (webhook); send via driver registry.
    """

    def __init__(self, registry=None):
        self._webhook_config: Optional[Dict[str, Any]] = None
        self._registry = registry or get_default_registry()

    def get_webhook_config(self) -> Optional[Dict[str, Any]]:
        """Get webhook configuration from NotificationChannel table."""
        if self._webhook_config is None:
            self._webhook_config = _get_webhook_config()
        return self._webhook_config

    def get_webhook_channel_and_config(self):
        """Return (channel, config) for active webhook or (None, None)."""
        channel, config = get_default_webhook_channel()
        return channel, config

    def _get_config(
        self, channel_config: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        if channel_config is not None:
            return channel_config
        config = self.get_webhook_config()
        if not config:
            logger.warning(
                f"WebhookService._get_config: no active webhook channel in "
                f"NotificationChannel table"
            )
        return config

    def _record_notification(
        self,
        provider_type: str,
        payload: Dict[str, Any],
        result: Dict[str, Any],
        source_app: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        user: Optional[Any] = None,
        channel_id: Optional[int] = None,
        channel_config: Optional[Dict[str, Any]] = None,
    ) -> Optional[NotificationRecord]:
        """Record notification send result."""
        config = self._get_config(channel_config=channel_config)
        status = Status.SUCCESS if result.get("success") else Status.FAILED
        metadata = {}
        if config:
            metadata = {
                "url": config.get("url", ""),
                "headers": config.get("headers", {}),
            }
        try:
            record = NotificationRecord.objects.create(
                provider_type=provider_type,
                channel=Channel.WEBHOOK,
                channel_link_id=channel_id,
                user=user,
                source_app=source_app or DEFAULT_SOURCE_APP,
                source_type=source_type or "",
                source_id=source_id or "",
                payload=payload,
                status=status,
                response=result.get("response"),
                error_message=result.get("error") or "",
                metadata=metadata,
                sent_at=timezone.now() if status == Status.SUCCESS else None,
            )
            return record
        except Exception as e:
            logger.warning(
                f"WebhookService._record_notification: failed: {e}"
            )
            return None

    def send(
        self,
        payload: Dict[str, Any],
        provider_type: Optional[str] = None,
        source_app: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        user: Optional[Any] = None,
        channel_id: Optional[int] = None,
        channel_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send notification by provider type via driver registry.
        When channel_config is provided (e.g. from application layer), use it
        instead of default webhook channel; otherwise use NotificationChannel.
        """
        config = self._get_config(channel_config=channel_config)
        if not config:
            result = {
                "success": False,
                "response": None,
                "error": "Webhook config not found or not active",
            }
            if source_app:
                self._record_notification(
                    DEFAULT_PROVIDER_TYPE,
                    payload,
                    result,
                    source_app,
                    source_type,
                    source_id,
                    user,
                    channel_id=channel_id,
                    channel_config=channel_config,
                )
            return result

        if provider_type is None:
            provider_type = config.get("provider", DEFAULT_PROVIDER_TYPE)

        result = self._registry.send(provider_type, payload, config)

        if source_app:
            record = self._record_notification(
                provider_type,
                payload,
                result,
                source_app,
                source_type,
                source_id,
                user,
                channel_id=channel_id,
                channel_config=channel_config,
            )
            if record:
                result["record_uuid"] = str(record.uuid)

        return result

    def send_text(
        self,
        text: str,
        provider_type: Optional[str] = None,
        source_app: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        user: Optional[Any] = None,
        channel_id: Optional[int] = None,
        channel_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send a canonical text notification without exposing payload
        structure to callers.
        """
        config = self._get_config(channel_config=channel_config)
        if not config:
            result = {
                "success": False,
                "response": None,
                "error": "Webhook config not found or not active",
            }
            if source_app:
                self._record_notification(
                    DEFAULT_PROVIDER_TYPE,
                    build_webhook_text_payload(DEFAULT_PROVIDER_TYPE, text),
                    result,
                    source_app,
                    source_type,
                    source_id,
                    user,
                    channel_id=channel_id,
                    channel_config=channel_config,
                )
            return result

        effective_provider = (
            provider_type or config.get("provider", DEFAULT_PROVIDER_TYPE)
        )
        payload = build_webhook_text_payload(effective_provider, text)
        return self.send(
            payload=payload,
            provider_type=effective_provider,
            source_app=source_app,
            source_type=source_type,
            source_id=source_id,
            user=user,
            channel_id=channel_id,
            channel_config=channel_config,
        )
