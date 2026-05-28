"""Tests for send_webhook, send_email, send_notification tasks."""
import pytest
from unittest.mock import patch

from agentcore_notifier.adapters.django.models import (
    NotificationChannel,
    NotificationRecord,
)
from agentcore_notifier.adapters.django.tasks.send import (
    send_email_notification,
    send_webhook_notification,
    send_notification,
    _validate_send_notification_params,
    NOTIFICATION_TYPE_WEBHOOK,
    NOTIFICATION_TYPE_EMAIL,
)
from agentcore_notifier.constants import Channel, Provider, Status


@pytest.mark.django_db
class TestSendWebhookNotification:
    """Test send_webhook_notification task."""

    @patch(
        "agentcore_notifier.adapters.django.services.webhook.feishu."
        "requests.post"
    )
    def test_send_webhook_success(self, mock_post, webhook_channel_config):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"StatusCode": 0}
        mock_post.return_value.raise_for_status = lambda: None

        NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            is_active=True,
            config=webhook_channel_config,
        )
        payload = {"msg_type": "text", "content": {"text": "hello"}}
        result = send_webhook_notification(
            payload=payload,
            provider_type="feishu",
            source_app="test_app",
            source_type="alert",
            source_id="1",
        )
        assert result.get("success") is True
        rec = NotificationRecord.objects.filter(
            channel=Channel.WEBHOOK,
            source_app="test_app",
        ).first()
        assert rec is not None
        assert rec.status == Status.SUCCESS

    def test_send_webhook_no_channel_returns_error(self):
        result = send_webhook_notification(
            payload={"msg_type": "text", "content": {"text": "hi"}},
            provider_type="feishu",
            source_app="test_app",
        )
        assert result.get("success") is False

    @patch(
        "agentcore_notifier.adapters.django.services.webhook.feishu."
        "requests.post"
    )
    def test_send_webhook_with_channel_config_channel_uuid(
        self, mock_post, webhook_channel_config
    ):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"StatusCode": 0}
        mock_post.return_value.raise_for_status = lambda: None

        ch = NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            is_active=True,
            config=webhook_channel_config,
        )
        payload = {"msg_type": "text", "content": {"text": "hello"}}
        result = send_webhook_notification(
            payload=payload,
            provider_type="feishu",
            source_app="test_app",
            source_type="alert",
            source_id="1",
            channel_uuid=str(ch.uuid),
        )
        assert result.get("success") is True
        rec = NotificationRecord.objects.filter(
            channel=Channel.WEBHOOK,
            source_app="test_app",
        ).first()
        assert rec is not None
        assert rec.status == Status.SUCCESS
        assert rec.channel_link_id == ch.id


@pytest.mark.django_db
class TestSendEmailNotification:
    """Test send_email_notification task."""

    @patch(
        "agentcore_notifier.adapters.django.services.email_service."
        "smtplib.SMTP"
    )
    def test_send_email_success(self, mock_smtp_class, email_channel_config):
        mock_smtp_class.return_value.__enter__ = lambda self: self
        mock_smtp_class.return_value.__exit__ = lambda *a: None
        mock_smtp_class.return_value.starttls = lambda: None
        mock_smtp_class.return_value.sendmail = lambda *a, **k: None

        NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_EMAIL,
            is_active=True,
            config=email_channel_config,
        )
        result = send_email_notification(
            subject="Test",
            body="Body",
            to=["u@example.com"],
            source_app="test_app",
            source_type="alert",
            source_id="1",
        )
        assert result.get("success") is True
        rec = NotificationRecord.objects.filter(
            channel=Channel.EMAIL,
            provider_type=Provider.EMAIL,
            source_app="test_app",
        ).first()
        assert rec is not None
        assert rec.status == Status.SUCCESS

    def test_send_email_no_channel_returns_error(self):
        result = send_email_notification(
            subject="Test",
            body="Body",
            to=["u@example.com"],
            source_app="test_app",
        )
        assert result.get("success") is False

    def test_send_email_with_channel_uuid_and_empty_to_returns_error(
        self, email_channel_config
    ):
        ch = NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_EMAIL,
            is_active=True,
            config={
                **email_channel_config,
                "default_to": ["fallback@example.com"],
            },
        )
        result = send_email_notification(
            subject="Test",
            body="Body",
            to=[],
            source_app="test_app",
            channel_uuid=str(ch.uuid),
        )
        assert result.get("success") is False
        assert "recipient" in (result.get("error") or "").lower()


class TestValidateSendNotificationParams:
    """Unit tests for _validate_send_notification_params."""

    def test_unsupported_notification_type(self):
        ok, err = _validate_send_notification_params("sms", {})
        assert ok is False
        assert err["success"] is False
        assert "notification_type must be one of" in err["error"]
        assert "sms" in err["error"]

    def test_params_not_dict(self):
        ok, err = _validate_send_notification_params(
            NOTIFICATION_TYPE_WEBHOOK, "not a dict"
        )
        assert ok is False
        assert err["error"] == "params must be a dict"

    def test_webhook_missing_payload(self):
        ok, err = _validate_send_notification_params(
            NOTIFICATION_TYPE_WEBHOOK,
            {"provider_type": "feishu"},
        )
        assert ok is False
        assert "payload" in err["error"].lower()

    def test_webhook_payload_not_dict(self):
        ok, err = _validate_send_notification_params(
            NOTIFICATION_TYPE_WEBHOOK,
            {"payload": "string", "provider_type": "feishu"},
        )
        assert ok is False
        assert "payload" in err["error"].lower()

    def test_webhook_missing_provider_type(self):
        ok, err = _validate_send_notification_params(
            NOTIFICATION_TYPE_WEBHOOK,
            {"payload": {"k": "v"}},
        )
        assert ok is False
        assert "provider_type" in err["error"].lower()

    def test_webhook_provider_type_empty_string(self):
        ok, err = _validate_send_notification_params(
            NOTIFICATION_TYPE_WEBHOOK,
            {"payload": {"k": "v"}, "provider_type": ""},
        )
        assert ok is False
        assert "provider_type" in err["error"].lower()

    def test_webhook_valid_params(self):
        ok, err = _validate_send_notification_params(
            NOTIFICATION_TYPE_WEBHOOK,
            {"payload": {"msg_type": "text"}, "provider_type": "feishu"},
        )
        assert ok is True
        assert err is None

    def test_webhook_params_none_treated_as_empty(self):
        ok, err = _validate_send_notification_params(
            NOTIFICATION_TYPE_WEBHOOK, None
        )
        assert ok is False
        assert "payload" in err["error"].lower()

    def test_email_missing_subject(self):
        ok, err = _validate_send_notification_params(
            NOTIFICATION_TYPE_EMAIL,
            {"body": "b", "to": ["a@b.com"]},
        )
        assert ok is False
        assert "subject" in err["error"].lower()

    def test_email_subject_not_string(self):
        ok, err = _validate_send_notification_params(
            NOTIFICATION_TYPE_EMAIL,
            {"subject": 123, "body": "b", "to": ["a@b.com"]},
        )
        assert ok is False
        assert "subject" in err["error"].lower()

    def test_email_missing_body(self):
        ok, err = _validate_send_notification_params(
            NOTIFICATION_TYPE_EMAIL,
            {"subject": "s", "to": ["a@b.com"]},
        )
        assert ok is False
        assert "body" in err["error"].lower()

    def test_email_to_not_list(self):
        ok, err = _validate_send_notification_params(
            NOTIFICATION_TYPE_EMAIL,
            {"subject": "s", "body": "b", "to": "a@b.com"},
        )
        assert ok is False
        assert "to" in err["error"].lower()

    def test_email_to_empty_list(self):
        ok, err = _validate_send_notification_params(
            NOTIFICATION_TYPE_EMAIL,
            {"subject": "s", "body": "b", "to": []},
        )
        assert ok is False
        assert "non-empty" in err["error"].lower()

    def test_email_to_whitespace_only_ignored(self):
        ok, err = _validate_send_notification_params(
            NOTIFICATION_TYPE_EMAIL,
            {"subject": "s", "body": "b", "to": ["  ", ""]},
        )
        assert ok is False
        assert "non-empty" in err["error"].lower()

    def test_email_valid_params(self):
        ok, err = _validate_send_notification_params(
            NOTIFICATION_TYPE_EMAIL,
            {"subject": "Hi", "body": "Body", "to": ["u@example.com"]},
        )
        assert ok is True
        assert err is None


class TestSendNotificationUnified:
    """Tests for unified send_notification task (validation + dispatch)."""

    def test_send_notification_source_app_required(self):
        result = send_notification(
            notification_type=NOTIFICATION_TYPE_WEBHOOK,
            source_app="",
            params={"payload": {}, "provider_type": "feishu"},
        )
        assert result.get("success") is False
        assert "source_app" in result["error"].lower()

    def test_send_notification_source_app_must_be_string(self):
        result = send_notification(
            notification_type=NOTIFICATION_TYPE_WEBHOOK,
            source_app=123,
            params={"payload": {}, "provider_type": "feishu"},
        )
        assert result.get("success") is False
        assert "source_app" in result["error"].lower()

    def test_send_notification_unsupported_type(self):
        result = send_notification(
            notification_type="sms",
            source_app="test_app",
            params={},
        )
        assert result.get("success") is False
        err = result["error"]
        assert "Unsupported notification_type" in err or "sms" in err

    def test_send_notification_webhook_invalid_params_returns_validation_error(
        self,
    ):
        result = send_notification(
            notification_type=NOTIFICATION_TYPE_WEBHOOK,
            source_app="test_app",
            params={"payload": "not a dict", "provider_type": "feishu"},
        )
        assert result.get("success") is False
        assert "payload" in result["error"].lower()

    def test_send_notification_email_invalid_params_returns_validation_error(
        self,
    ):
        result = send_notification(
            notification_type=NOTIFICATION_TYPE_EMAIL,
            source_app="test_app",
            params={"subject": "s", "body": "b"},
        )
        assert result.get("success") is False
        assert "to" in result["error"].lower()

    @patch(
        "agentcore_notifier.adapters.django.tasks.send."
        "send_webhook_notification"
    )
    def test_send_notification_dispatches_webhook_with_params(
        self, mock_webhook
    ):
        mock_webhook.return_value = {
            "success": True,
            "response": None,
            "error": None,
        }
        payload = {"msg_type": "text", "content": {"text": "hi"}}
        result = send_notification(
            notification_type=NOTIFICATION_TYPE_WEBHOOK,
            source_app="cloud_billing",
            source_type="alert",
            source_id="42",
            user_id=1,
            channel_uuid="ch-uuid",
            params={"payload": payload, "provider_type": "feishu"},
        )
        assert result.get("success") is True
        mock_webhook.assert_called_once_with(
            payload=payload,
            provider_type="feishu",
            source_app="cloud_billing",
            source_type="alert",
            source_id="42",
            user_id=1,
            channel_uuid="ch-uuid",
        )

    @patch(
        "agentcore_notifier.adapters.django.tasks.send.send_email_notification"
    )
    def test_send_notification_dispatches_email_with_params(
        self, mock_email
    ):
        mock_email.return_value = {
            "success": True,
            "response": None,
            "error": None,
        }
        result = send_notification(
            notification_type=NOTIFICATION_TYPE_EMAIL,
            source_app="cloud_billing",
            source_type="alert",
            source_id="43",
            user_id=2,
            channel_uuid="email-uuid",
            params={
                "subject": "Alert",
                "body": "Body text",
                "to": ["a@b.com", "b@c.com"],
            },
        )
        assert result.get("success") is True
        mock_email.assert_called_once_with(
            subject="Alert",
            body="Body text",
            to=["a@b.com", "b@c.com"],
            source_app="cloud_billing",
            source_type="alert",
            source_id="43",
            user_id=2,
            channel_uuid="email-uuid",
        )
