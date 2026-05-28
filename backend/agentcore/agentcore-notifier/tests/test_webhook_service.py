"""Tests for WebhookService (config from NotificationChannel)."""
import pytest
from unittest.mock import patch

from agentcore_notifier.adapters.django.models import NotificationChannel
from agentcore_notifier.adapters.django.services.webhook_service import (
    build_exception_response,
    WebhookService,
    build_text_payload,
    build_validation_payload,
    parse_http_response,
    _get_webhook_config,
    build_webhook_config_from_dict,
    get_default_webhook_channel,
    get_webhook_channel_by_uuid,
)


@pytest.mark.django_db
class TestWebhookService:
    """Test WebhookService with NotificationChannel config."""

    class _FakeResponse:
        def __init__(self, status_code, payload=None, text="", json_exc=False):
            self.status_code = status_code
            self._payload = payload
            self.text = text
            self._json_exc = json_exc

        def json(self):
            if self._json_exc:
                raise ValueError("not json")
            return self._payload

    def test_get_webhook_config_empty_when_no_config(self):
        svc = WebhookService()
        assert svc.get_webhook_config() is None

    def test_get_webhook_config_returns_config_when_channel_set(
        self,
        webhook_channel_config,
    ):
        NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            is_active=True,
            config=webhook_channel_config,
        )
        cfg = _get_webhook_config()
        assert cfg is not None
        assert cfg.get("url") == webhook_channel_config["url"]
        assert cfg.get("provider") == "feishu"
        svc = WebhookService()
        assert svc.get_webhook_config() is not None
        assert svc.get_webhook_config()["url"] == webhook_channel_config["url"]

    def test_send_returns_error_when_no_config(self):
        svc = WebhookService()
        result = svc.send(
            payload={"msg_type": "text", "text": {"text": "hi"}},
            source_app="test",
        )
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @patch(
        "agentcore_notifier.adapters.django.services.webhook.feishu."
        "requests.post"
    )
    def test_send_feishu_success(self, mock_post, webhook_channel_config):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"StatusCode": 0}
        mock_post.return_value.raise_for_status = lambda: None

        NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            is_active=True,
            config=webhook_channel_config,
        )
        svc = WebhookService()
        payload = {"msg_type": "text", "text": {"text": "hello"}}
        result = svc.send(payload, provider_type="feishu")
        assert result["success"] is True
        assert result.get("error") is None
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"] == payload
        assert call_kwargs["timeout"] == 10

    @patch(
        "agentcore_notifier.adapters.django.services.webhook.feishu."
        "requests.post"
    )
    def test_send_text_uses_provider_specific_payload(
        self,
        mock_post,
        webhook_channel_config,
    ):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"StatusCode": 0}
        mock_post.return_value.raise_for_status = lambda: None

        NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            is_active=True,
            config=webhook_channel_config,
        )
        svc = WebhookService()
        result = svc.send_text("hello", provider_type="feishu")
        assert result["success"] is True
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"] == {
            "msg_type": "text",
            "content": {"text": "hello"},
        }

    def test_build_text_payload_switches_on_provider(self):
        assert build_text_payload("feishu", "hello") == {
            "msg_type": "text",
            "content": {"text": "hello"},
        }
        assert build_text_payload("wechat", "hello") == {
            "msgtype": "text",
            "text": {"content": "hello"},
        }

    def test_build_validation_payload_switches_on_provider(self):
        feishu_payload = build_validation_payload(
            "feishu",
            "hello",
            "title",
        )
        assert feishu_payload["msg_type"] == "interactive"
        assert feishu_payload["card"]["header"]["title"]["content"] == "title"
        assert (
            feishu_payload["card"]["elements"][0]["text"]["content"]
            == "hello"
        )

        wechat_payload = build_validation_payload(
            "wechat",
            "hello",
            "title",
        )
        assert wechat_payload == {
            "msgtype": "text",
            "text": {"content": "hello"},
        }

    def test_parse_http_response_invalid_json(self):
        response = self._FakeResponse(
            200,
            text="not json",
            json_exc=True,
        )
        error_response, payload = parse_http_response(
            "feishu",
            response,
        )
        assert payload is None
        assert error_response.status_code == 400
        assert "Expected JSON" in error_response.data["message"]

    def test_parse_http_response_http_error(self):
        response = self._FakeResponse(
            500,
            payload={"msg": "boom"},
        )
        error_response, payload = parse_http_response(
            "feishu",
            response,
        )
        assert payload is None
        assert error_response.status_code == 400
        assert "HTTP status 500" in error_response.data["message"]

    def test_build_exception_response(self):
        error_response = build_exception_response(
            "connection reset"
        )
        assert error_response.status_code == 400
        assert "connection reset" in error_response.data["message"]


@pytest.mark.django_db
class TestBuildWebhookConfigFromDict:
    """Test build_webhook_config_from_dict."""

    def test_returns_none_when_empty(self):
        assert build_webhook_config_from_dict({}) is None
        assert build_webhook_config_from_dict(None) is None

    def test_returns_none_when_url_missing(self):
        assert build_webhook_config_from_dict(
            {"provider_type": "feishu"}
        ) is None
        assert build_webhook_config_from_dict({"url": ""}) is None
        assert build_webhook_config_from_dict({"url": "   "}) is None

    def test_returns_config_when_url_present(self):
        cfg = {
            "url": "https://example.com/webhook",
            "provider_type": "feishu",
            "headers": {"X-Custom": "v"},
        }
        out = build_webhook_config_from_dict(cfg)
        assert out is not None
        assert out["url"] == "https://example.com/webhook"
        assert out["provider"] == "feishu"
        assert out["headers"] == {"X-Custom": "v"}

    def test_accepts_provider_or_provider_type(self):
        out = build_webhook_config_from_dict({
            "url": "https://x.com",
            "provider": "wechat",
        })
        assert out is not None
        assert out["provider"] == "wechat"


@pytest.mark.django_db
class TestGetDefaultWebhookChannel:
    """Test get_default_webhook_channel (first active by created_at)."""

    def test_returns_none_when_no_channel(self):
        channel, config = get_default_webhook_channel()
        assert channel is None
        assert config is None

    def test_returns_earliest_created_at_channel(self, webhook_channel_config):
        first = NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            is_active=True,
            config=webhook_channel_config,
        )
        second = NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            is_active=True,
            config={
                **webhook_channel_config,
                "url": "https://second.example.com",
            },
        )
        channel, config = get_default_webhook_channel()
        assert channel is not None
        assert config is not None
        assert channel.created_at <= second.created_at
        assert channel.id == first.id
        assert config["url"] == webhook_channel_config["url"]

    def test_ignores_inactive_channel(self, webhook_channel_config):
        NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            is_active=False,
            config=webhook_channel_config,
        )
        channel, config = get_default_webhook_channel()
        assert channel is None
        assert config is None


@pytest.mark.django_db
class TestGetWebhookChannelByUuid:
    """Test get_webhook_channel_by_uuid (app-layer channel selection)."""

    def test_returns_none_for_invalid_uuid(self):
        channel, config = get_webhook_channel_by_uuid("not-a-uuid")
        assert channel is None
        assert config is None
        channel, config = get_webhook_channel_by_uuid("")
        assert channel is None
        assert config is None

    def test_returns_none_when_not_found(self, webhook_channel_config):
        import uuid
        channel, config = get_webhook_channel_by_uuid(uuid.uuid4())
        assert channel is None
        assert config is None

    def test_returns_channel_when_found_by_str_uuid(
        self, webhook_channel_config
    ):
        ch = NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            is_active=True,
            config=webhook_channel_config,
        )
        channel, config = get_webhook_channel_by_uuid(str(ch.uuid))
        assert channel is not None
        assert channel.id == ch.id
        assert config is not None
        assert config["url"] == webhook_channel_config["url"]

    def test_returns_channel_when_found_by_uuid_type(
        self, webhook_channel_config
    ):
        ch = NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            is_active=True,
            config=webhook_channel_config,
        )
        channel, config = get_webhook_channel_by_uuid(ch.uuid)
        assert channel is not None
        assert channel.id == ch.id
        assert config is not None

    def test_returns_none_when_channel_inactive(self, webhook_channel_config):
        ch = NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            is_active=False,
            config=webhook_channel_config,
        )
        channel, config = get_webhook_channel_by_uuid(str(ch.uuid))
        assert channel is None
        assert config is None
