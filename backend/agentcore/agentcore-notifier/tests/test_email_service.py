"""Tests for EmailService and get_default_email_channel."""
from unittest.mock import patch

import pytest

from agentcore_notifier.adapters.django.models import (
    NotificationChannel,
    NotificationRecord,
)
from agentcore_notifier.adapters.django.services.email_service import (
    EmailService,
    get_default_email_channel,
)
from agentcore_notifier.constants import Channel, Provider, Status


def _make_mock_smtp(mock_class, use_starttls=True):
    """
    Attach __enter__, __exit__, sendmail to mock SMTP class.
    If use_starttls, add starttls no-op.
    """
    mock_class.return_value.__enter__ = lambda self: self
    mock_class.return_value.__exit__ = lambda *a: None
    mock_class.return_value.sendmail = lambda *a, **k: None
    if use_starttls:
        mock_class.return_value.starttls = lambda: None


@pytest.mark.django_db
class TestGetDefaultEmailChannel:
    """Test get_default_email_channel."""

    def test_returns_none_when_no_channel(self):
        """When no email channel exists, return None, None."""
        ch, cfg = get_default_email_channel()
        assert ch is None
        assert cfg is None

    def test_returns_none_when_channel_has_no_smtp_host(
        self, email_channel_config
    ):
        """When channel config has empty smtp_host, return None, None."""
        c = dict(email_channel_config)
        c["smtp_host"] = ""
        NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_EMAIL,
            is_active=True,
            config=c,
        )
        ch, cfg = get_default_email_channel()
        assert ch is None
        assert cfg is None

    def test_returns_channel_and_config_when_set(self, email_channel_config):
        """When an active email channel exists, return it and merged config."""
        ch = NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_EMAIL,
            is_active=True,
            config=email_channel_config,
        )
        ch_out, cfg = get_default_email_channel()
        assert ch_out is not None
        assert ch_out.id == ch.id
        assert cfg is not None
        assert cfg["smtp_host"] == email_channel_config["smtp_host"]
        assert cfg["smtp_port"] == 587
        assert cfg["from_email"] == email_channel_config["from_email"]


@pytest.mark.django_db
class TestEmailService:
    """Test EmailService send and record."""

    def test_send_returns_error_when_no_channel(self):
        """Send fails with error when no active email channel is configured."""
        svc = EmailService()
        result = svc.send(
            subject="Test",
            body="Body",
            to=["a@b.com"],
            source_app="test",
        )
        assert result["success"] is False
        err = result["error"].lower()
        assert "not found" in err or "not active" in err

    def test_send_returns_error_when_no_valid_recipients(
        self, email_channel_config
    ):
        """Send fails when to list is empty or has no valid addresses."""
        NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_EMAIL,
            is_active=True,
            config=email_channel_config,
        )
        svc = EmailService()
        result = svc.send(
            subject="Test",
            body="Body",
            to=[],
            source_app="test",
        )
        assert result["success"] is False
        assert "recipient" in result["error"].lower()

    @patch(
        "agentcore_notifier.adapters.django.services.email_service."
        "smtplib.SMTP"
    )
    def test_send_success_and_record(
        self, mock_smtp_class, email_channel_config
    ):
        """Send succeeds and creates NotificationRecord with expected data."""
        _make_mock_smtp(mock_smtp_class, use_starttls=True)

        NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_EMAIL,
            is_active=True,
            config=email_channel_config,
        )
        svc = EmailService()
        result = svc.send(
            subject="Test Subject",
            body="Test body",
            to=["user@example.com"],
            source_app="test_app",
            source_type="alert",
            source_id="1",
        )
        assert result["success"] is True
        assert "record_uuid" in result
        rec = NotificationRecord.objects.filter(
            channel=Channel.EMAIL,
            provider_type=Provider.EMAIL,
            source_app="test_app",
        ).first()
        assert rec is not None
        assert rec.status == Status.SUCCESS
        assert rec.payload.get("subject") == "Test Subject"
        assert "user@example.com" in rec.payload.get("to", [])

    @patch(
        "agentcore_notifier.adapters.django.services.email_service."
        "smtplib.SMTP_SSL"
    )
    def test_send_uses_smtp_ssl_when_use_ssl_enabled(
        self, mock_smtp_ssl_class, email_channel_config
    ):
        """Send uses SMTP_SSL when channel config has use_ssl True."""
        _make_mock_smtp(mock_smtp_ssl_class, use_starttls=False)

        config = {
            **email_channel_config,
            "smtp_port": 465,
            "use_ssl": True,
        }
        NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_EMAIL,
            is_active=True,
            config=config,
        )
        svc = EmailService()
        result = svc.send(
            subject="SSL Test",
            body="Body",
            to=["user@example.com"],
            source_app="test_app",
        )
        assert result["success"] is True
        assert mock_smtp_ssl_class.called
