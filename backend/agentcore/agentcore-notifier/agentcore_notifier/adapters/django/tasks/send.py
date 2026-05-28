"""
Celery tasks: send webhook or email (merge/silence from channel config).
"""
import logging
from typing import Any, Dict, List, Optional

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from agentcore_notifier.adapters.django.conf import (
    get_merge_enabled,
    get_merge_window_minutes,
)
from agentcore_notifier.adapters.django.models import NotificationRecord
from agentcore_notifier.adapters.django.services import merge_and_silence
from agentcore_notifier.adapters.django.services.email_service import (
    get_default_email_channel,
    get_email_channel_by_uuid,
    EmailService,
)
from agentcore_notifier.adapters.django.services.webhook_service import (
    get_default_webhook_channel,
    get_webhook_channel_by_uuid,
    WebhookService,
)
from agentcore_notifier.constants import Channel, Provider, Status

logger = logging.getLogger(__name__)


_TASK_SEND_NAME = (
    "agentcore_notifier.adapters.django.tasks.send.send_webhook_notification"
)


def _write_record_with_channel(
    provider_type: str,
    source_app: str,
    source_type: str,
    source_id: str,
    user_id: Optional[int],
    status: str,
    channel_id: Optional[int] = None,
    channel: str = Channel.WEBHOOK,
    payload: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
):
    """Create NotificationRecord (merged/silenced) with optional channel_id."""
    NotificationRecord.objects.create(
        provider_type=provider_type,
        channel=channel,
        channel_link_id=channel_id,
        user_id=user_id,
        source_app=source_app,
        source_type=source_type,
        source_id=source_id or "",
        payload=payload or {},
        status=status,
        response=result.get("response") if result else None,
        error_message=result.get("error", "") if result else "",
        sent_at=timezone.now() if status == Status.SUCCESS else None,
    )


@shared_task(name=_TASK_SEND_NAME)
def send_webhook_notification(
    payload: Dict[str, Any],
    provider_type: str,
    source_app: str,
    source_type: str = "",
    source_id: str = "",
    user_id: Optional[int] = None,
    channel_uuid: Optional[str] = None,
):
    """
    Send webhook notification. When channel_uuid is provided, the channel
    is resolved by UUID and used; otherwise the default webhook channel
    (first active by created_at) is used. Type is always webhook; channel
    selection is by UUID or default.
    """
    if channel_uuid:
        channel, resolved_config = get_webhook_channel_by_uuid(channel_uuid)
        resolved_channel_id = channel.id if channel else None
        raw_channel_config = (channel.config or {}) if channel else {}
    else:
        channel, resolved_config = get_default_webhook_channel()
        resolved_channel_id = channel.id if channel else None
        raw_channel_config = (channel.config or {}) if channel else {}

    # Resolve silence window from channel config
    silence_window = None
    if raw_channel_config:
        try:
            silence_window = int(
                raw_channel_config.get("silence_window_minutes") or 0
            )
        except (TypeError, ValueError):
            silence_window = 0
    if silence_window and silence_window > 0:
        if merge_and_silence.should_skip_due_to_merge(
            provider_type,
            source_app,
            source_type,
            source_id,
            silence_window,
            channel_id=resolved_channel_id,
            user_id=user_id,
        ):
            logger.info(
                f"send_webhook_notification: silenced "
                f"(same alert within {silence_window}min) "
                f"provider_type={provider_type} "
                f"source={source_app}:{source_type}:{source_id}"
            )
            _write_record_with_channel(
                provider_type,
                source_app,
                source_type,
                source_id,
                user_id,
                Status.SILENCED,
                channel_id=resolved_channel_id,
            )
            return {"skipped": True, "reason": "silenced"}

    # Resolve merge settings from channel or global config
    merge_enabled = (
        raw_channel_config.get("merge_enabled")
        if raw_channel_config
        else False
    )
    merge_window = (
        raw_channel_config.get("merge_window_minutes")
        if raw_channel_config
        else None
    )
    if not merge_enabled or not merge_window or merge_window <= 0:
        merge_enabled = get_merge_enabled(provider_type)
        merge_window = get_merge_window_minutes(provider_type)

    if merge_enabled and merge_window and merge_window > 0:
        if merge_and_silence.should_skip_due_to_merge(
            provider_type,
            source_app,
            source_type,
            source_id,
            merge_window,
            channel_id=resolved_channel_id,
            user_id=user_id,
        ):
            logger.info(
                f"send_webhook_notification: merged "
                f"provider_type={provider_type} "
                f"source={source_app}:{source_type}:{source_id}"
            )
            _write_record_with_channel(
                provider_type,
                source_app,
                source_type,
                source_id,
                user_id,
                Status.MERGED,
                channel_id=resolved_channel_id,
            )
            return {"skipped": True, "reason": "merged"}

    # Send via WebhookService and return result
    if not resolved_config:
        err_msg = "Webhook config not found or invalid"
        _write_record_with_channel(
            provider_type,
            source_app,
            source_type,
            source_id,
            user_id,
            Status.FAILED,
            channel_id=resolved_channel_id,
            result={"success": False, "error": err_msg},
        )
        return {"success": False, "response": None, "error": err_msg}

    svc = WebhookService()
    user = None if user_id is None else _user_from_id(user_id)
    result = svc.send(
        payload=payload,
        provider_type=provider_type,
        source_app=source_app,
        source_type=source_type,
        source_id=source_id,
        user=user,
        channel_id=resolved_channel_id,
        channel_config=resolved_config,
    )
    return result


def _user_from_id(user_id: int):
    """Return User instance for user_id or None."""
    return get_user_model().objects.filter(pk=user_id).first()


_TASK_SEND_EMAIL_NAME = (
    "agentcore_notifier.adapters.django.tasks.send.send_email_notification"
)


@shared_task(name=_TASK_SEND_EMAIL_NAME)
def send_email_notification(
    subject: str,
    body: str,
    to: List[str],
    source_app: str,
    source_type: str = "",
    source_id: str = "",
    user_id: Optional[int] = None,
    channel_uuid: Optional[str] = None,
):
    """
    Send email notification. When channel_uuid is provided, that channel is
    used; otherwise the default email channel. Recipients must be provided
    explicitly via `to`.
    """
    if channel_uuid:
        channel, smtp_config = get_email_channel_by_uuid(channel_uuid)
        channel_id = channel.id if channel else None
        raw_config = (channel.config or {}) if channel else {}
        to_list = [a.strip() for a in (to or []) if (a or "").strip()]
    else:
        channel, smtp_config = get_default_email_channel()
        channel_id = channel.id if channel else None
        raw_config = (channel.config or {}) if channel else {}
        to_list = [a.strip() for a in (to or []) if (a or "").strip()]

    channel_config = raw_config

    # Resolve silence window from channel config
    silence_window = None
    if channel_config:
        try:
            silence_window = int(
                channel_config.get("silence_window_minutes") or 0
            )
        except (TypeError, ValueError):
            silence_window = 0
    if silence_window and silence_window > 0:
        if merge_and_silence.should_skip_due_to_merge(
            Provider.EMAIL,
            source_app,
            source_type,
            source_id,
            silence_window,
            channel_id=channel_id,
            user_id=user_id,
        ):
            logger.info(
                f"send_email_notification: silenced "
                f"(same alert within {silence_window}min) "
                f"source={source_app}:{source_type}:{source_id}"
            )
            _write_record_with_channel(
                Provider.EMAIL,
                source_app,
                source_type,
                source_id,
                user_id,
                Status.SILENCED,
                channel_id=channel_id,
                channel=Channel.EMAIL,
            )
            return {"skipped": True, "reason": "silenced"}

    # Send via EmailService and return result
    if not smtp_config and not channel:
        err_msg = "Email channel not found or invalid"
        _write_record_with_channel(
            Provider.EMAIL,
            source_app,
            source_type,
            source_id,
            user_id,
            Status.FAILED,
            channel_id=channel_id,
            channel=Channel.EMAIL,
            result={"success": False, "error": err_msg},
        )
        return {"success": False, "response": None, "error": err_msg}

    svc = EmailService()
    user = None if user_id is None else _user_from_id(user_id)
    result = svc.send(
        subject=subject,
        body=body,
        to=to_list,
        source_app=source_app,
        source_type=source_type,
        source_id=source_id,
        user=user,
        channel_id=channel_id,
        channel_config=smtp_config if channel_uuid and smtp_config else None,
    )
    return result


NOTIFICATION_TYPE_WEBHOOK = "webhook"
NOTIFICATION_TYPE_EMAIL = "email"
SUPPORTED_NOTIFICATION_TYPES = (
    NOTIFICATION_TYPE_WEBHOOK,
    NOTIFICATION_TYPE_EMAIL,
)


def _validate_send_notification_params(
    notification_type: str,
    params: Optional[Dict[str, Any]],
) -> tuple:
    """
    Validate notification_type and type-specific params.
    Returns (True, None) if valid, else (False, error_response_dict).
    """
    if notification_type not in SUPPORTED_NOTIFICATION_TYPES:
        err = (
            f"notification_type must be one of "
            f"{SUPPORTED_NOTIFICATION_TYPES}, got {notification_type!r}"
        )
        return False, {
            "success": False,
            "response": None,
            "error": err,
        }
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return False, {
            "success": False,
            "response": None,
            "error": "params must be a dict",
        }
    if notification_type == NOTIFICATION_TYPE_WEBHOOK:
        payload = params.get("payload")
        provider_type = params.get("provider_type")
        if payload is None or not isinstance(payload, dict):
            return False, {
                "success": False,
                "response": None,
                "error": "params must contain 'payload' (dict) for webhook",
            }
        if not provider_type or not isinstance(provider_type, str):
            return False, {
                "success": False,
                "response": None,
                "error": (
                    "params must contain 'provider_type' (str) for webhook"
                ),
            }
        return True, None
    if notification_type == NOTIFICATION_TYPE_EMAIL:
        subject = params.get("subject")
        body = params.get("body")
        to = params.get("to")
        if subject is None or not isinstance(subject, str):
            return False, {
                "success": False,
                "response": None,
                "error": "params must contain 'subject' (str) for email",
            }
        if body is None or not isinstance(body, str):
            return False, {
                "success": False,
                "response": None,
                "error": "params must contain 'body' (str) for email",
            }
        if to is None:
            to = []
        if not isinstance(to, list):
            return False, {
                "success": False,
                "response": None,
                "error": "params must contain 'to' (list of str) for email",
            }
        to_list = [a.strip() for a in to if (a or "").strip()]
        if not to_list:
            return False, {
                "success": False,
                "response": None,
                "error": (
                    "params 'to' must be a non-empty list of email addresses"
                ),
            }
        return True, None
    return True, None


_TASK_SEND_UNIFIED_NAME = (
    "agentcore_notifier.adapters.django.tasks.send.send_notification"
)


@shared_task(name=_TASK_SEND_UNIFIED_NAME)
def send_notification(
    notification_type: str,
    source_app: str,
    source_type: str = "",
    source_id: str = "",
    user_id: Optional[int] = None,
    channel_uuid: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Unified notification send: validate at entry, then dispatch to webhook or
    email by notification_type. Each type uses its own params dict:
    - webhook: params = {payload: dict, provider_type: str}
    - email: params = {subject: str, body: str, to: list[str]}
    Common args: source_app, source_type, source_id, user_id, channel_uuid.
    """
    if not source_app or not isinstance(source_app, str):
        return {
            "success": False,
            "response": None,
            "error": "source_app is required and must be a non-empty string",
        }
    ok, err = _validate_send_notification_params(notification_type, params)
    if not ok:
        return err
    params = params or {}
    if notification_type == NOTIFICATION_TYPE_WEBHOOK:
        return send_webhook_notification(
            payload=params["payload"],
            provider_type=params["provider_type"],
            source_app=source_app,
            source_type=source_type,
            source_id=source_id,
            user_id=user_id,
            channel_uuid=channel_uuid,
        )
    if notification_type == NOTIFICATION_TYPE_EMAIL:
        return send_email_notification(
            subject=params["subject"],
            body=params["body"],
            to=params["to"],
            source_app=source_app,
            source_type=source_type,
            source_id=source_id,
            user_id=user_id,
            channel_uuid=channel_uuid,
        )
    return {
        "success": False,
        "response": None,
        "error": f"Unsupported notification_type: {notification_type}",
    }
