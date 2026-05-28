"""Tests for WeChat webhook driver."""
from unittest.mock import patch

from agentcore_notifier.adapters.django.services.webhook.wechat import (
    WeChatWebhookDriver,
)


class TestWeChatDriverSend:
    """Test WeChatWebhookDriver.send business code handling."""

    def test_send_success_when_errcode_zero(self):
        driver = WeChatWebhookDriver()
        config = {"url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"}
        payload = {"msgtype": "text", "text": {"content": "hi"}}
        with patch(
            "agentcore_notifier.adapters.django.services.webhook.wechat."
            "requests.post"
        ) as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "errcode": 0,
                "errmsg": "ok",
            }
            mock_post.return_value.raise_for_status = lambda: None
            result = driver.send(payload, config)
        assert result["success"] is True

    def test_send_failed_when_errcode_non_zero(self):
        driver = WeChatWebhookDriver()
        config = {"url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"}
        payload = {"msgtype": "text", "text": {"content": "hi"}}
        with patch(
            "agentcore_notifier.adapters.django.services.webhook.wechat."
            "requests.post"
        ) as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "errcode": 40013,
                "errmsg": "invalid appid",
            }
            mock_post.return_value.raise_for_status = lambda: None
            result = driver.send(payload, config)
        assert result["success"] is False
        assert "invalid appid" in (result["error"] or "")
