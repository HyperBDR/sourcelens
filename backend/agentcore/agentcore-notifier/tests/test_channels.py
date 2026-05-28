"""Tests for notification channel API (list, create, get, validate)."""
import pytest
from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework.test import APIClient

from agentcore_notifier.adapters.django.models import NotificationChannel


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="admin",
        email="admin@test.com",
        password="adminpass",
    )


@pytest.fixture
def api_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.mark.django_db
class TestNotificationChannelListCreate:
    """Test GET/POST channels/."""

    def test_list_channels_empty(self, api_client):
        response = api_client.get("/channels/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["results"] == []

    def test_list_channels_filter_by_type(
        self, api_client, webhook_channel_config
    ):
        NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            is_active=True,
            config=webhook_channel_config,
        )
        NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_EMAIL,
            is_active=True,
            config={"smtp_host": "smtp.example.com", "from_email": "a@b.com"},
        )
        response = api_client.get("/channels/?channel_type=webhook")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["results"][0]["channel_type"] == "webhook"

    def test_create_webhook_channel(self, api_client, webhook_channel_config):
        response = api_client.post(
            "/channels/",
            data={
                "channel_type": "webhook",
                "name": "Feishu",
                "config": webhook_channel_config,
            },
            format="json",
        )
        assert response.status_code == 201
        data = response.json()
        assert data["channel_type"] == "webhook"
        assert data["name"] == "Feishu"
        assert data["config"]["url"] == webhook_channel_config["url"]
        assert NotificationChannel.objects.filter(
            channel_type=NotificationChannel.TYPE_WEBHOOK
        ).count() == 1

    def test_create_email_channel(self, api_client, email_channel_config):
        response = api_client.post(
            "/channels/",
            data={
                "channel_type": "email",
                "name": "SMTP",
                "config": email_channel_config,
            },
            format="json",
        )
        assert response.status_code == 201
        data = response.json()
        assert data["channel_type"] == "email"
        assert data["config"]["smtp_host"] == email_channel_config["smtp_host"]

    def test_create_channel_invalid_type_returns_400(self, api_client):
        response = api_client.post(
            "/channels/",
            data={"channel_type": "sms", "config": {}},
            format="json",
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestNotificationChannelDetail:
    """Test GET/PUT/DELETE channels/<uuid>/."""

    def test_get_channel_by_uuid(self, api_client, webhook_channel_config):
        ch = NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            name="Test",
            config=webhook_channel_config,
        )
        response = api_client.get(f"/channels/{ch.uuid}/")
        assert response.status_code == 200
        assert response.json()["uuid"] == str(ch.uuid)
        assert response.json()["name"] == "Test"

    def test_get_channel_404(self, api_client):
        response = api_client.get(
            "/channels/00000000-0000-0000-0000-000000000000/"
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestChannelValidateView:
    """Test POST channels/validate/."""

    @patch(
        "agentcore_notifier.adapters.django.services.webhook.feishu."
        "requests.post"
    )
    def test_validate_webhook_success(self, mock_post, api_client):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"StatusCode": 0}
        mock_post.return_value.raise_for_status = lambda: None
        response = api_client.post(
            "/channels/validate/",
            data={
                "channel_type": "webhook",
                "config": {
                    "url": "https://open.feishu.cn/webhook/xxx",
                    "provider_type": "feishu",
                },
            },
            format="json",
        )
        assert response.status_code == 200
        assert response.json() == {"success": True}

    @patch(
        "agentcore_notifier.adapters.django.services.webhook.feishu."
        "requests.post"
    )
    def test_validate_wecom_uses_msgtype_payload(self, mock_post, api_client):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"errcode": 0}
        mock_post.return_value.raise_for_status = lambda: None
        webhook_url = (
            "https://qyapi.weixin.qq.com/"
            "cgi-bin/webhook/send?key=xxx"
        )
        response = api_client.post(
            "/channels/validate/",
            data={
                "channel_type": "webhook",
                "config": {
                    "url": webhook_url,
                    "provider_type": "wecom",
                },
            },
            format="json",
        )
        assert response.status_code == 200
        assert response.json() == {"success": True}
        call_kwargs = mock_post.call_args[1]
        expected_content = "[Agentcore Notifier] Channel validation test"
        assert call_kwargs["json"] == {
            "msgtype": "text",
            "text": {"content": expected_content},
        }

    def test_validate_webhook_missing_url_returns_400(self, api_client):
        response = api_client.post(
            "/channels/validate/",
            data={"channel_type": "webhook", "config": {}},
            format="json",
        )
        assert response.status_code == 400
        data = response.json()
        assert "success" not in data or data.get("success") is False

    def test_validate_email_invalid_type_returns_400(self, api_client):
        response = api_client.post(
            "/channels/validate/",
            data={"channel_type": "invalid", "config": {}},
            format="json",
        )
        assert response.status_code == 400
        assert "webhook or email" in response.json().get("detail", "").lower()
