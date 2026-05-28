"""Tests for notification_config service."""
import pytest

from agentcore_notifier.adapters.django.models import NotifierConfig
from agentcore_notifier.adapters.django.services import notification_config


@pytest.mark.django_db
class TestNotificationConfig:
    """Test get_config / set_config (global scope)."""

    def test_get_config_missing_returns_none(self):
        assert notification_config.get_config("nonexistent") is None

    def test_set_and_get_config(self, webhook_config_value):
        notification_config.set_config("webhook", webhook_config_value)
        out = notification_config.get_config("webhook")
        assert out == webhook_config_value
        row = NotifierConfig.objects.filter(
            scope=NotifierConfig.SCOPE_GLOBAL,
            user__isnull=True,
            key="webhook",
        ).first()
        assert row is not None
        assert row.value == webhook_config_value

    def test_set_config_updates_existing(self, webhook_config_value):
        notification_config.set_config("webhook", webhook_config_value)
        updated = dict(webhook_config_value)
        updated["timeout"] = 20
        notification_config.set_config("webhook", updated)
        out = notification_config.get_config("webhook")
        assert out["timeout"] == 20
        assert NotifierConfig.objects.filter(key="webhook").count() == 1
