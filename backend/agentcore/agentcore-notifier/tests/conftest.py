"""Pytest fixtures for agentcore_notifier tests."""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")

import django
django.setup()

import pytest


@pytest.fixture
def webhook_config_value():
    """Sample webhook config dict for NotifierConfig value."""
    return {
        "is_active": True,
        "url": "https://open.feishu.cn/webhook/test",
        "provider": "feishu",
        "headers": {},
        "timeout": 10,
        "language": "zh-hans",
    }


@pytest.fixture
def webhook_channel_config():
    """Config dict for NotificationChannel (channel_type=webhook)."""
    return {
        "url": "https://open.feishu.cn/webhook/test",
        "provider_type": "feishu",
        "headers": {},
        "timeout": 10,
    }


@pytest.fixture
def email_channel_config():
    """Config dict for NotificationChannel (channel_type=email)."""
    return {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "use_tls": True,
        "from_email": "noreply@example.com",
        "from_name": "Agentcore Notifier",
    }
