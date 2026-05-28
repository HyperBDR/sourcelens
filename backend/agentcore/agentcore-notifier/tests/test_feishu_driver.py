"""Tests for Feishu webhook driver (sign and send)."""
import base64
import hmac
import hashlib
from unittest.mock import patch

import pytest

from agentcore_notifier.adapters.django.services.webhook.feishu import (
    FeishuWebhookDriver,
    _feishu_sign,
)


class TestFeishuSign:
    """Test Feishu custom bot sign generation."""

    def test_feishu_sign_is_base64(self):
        out = _feishu_sign("1599360473", "secret-key")
        assert isinstance(out, str)
        assert len(out) > 0
        base64.b64decode(out, validate=True)

    def test_feishu_sign_deterministic(self):
        a = _feishu_sign("1599360473", "secret")
        b = _feishu_sign("1599360473", "secret")
        assert a == b

    def test_feishu_sign_different_for_different_timestamp(self):
        a = _feishu_sign("1599360473", "secret")
        b = _feishu_sign("1599360474", "secret")
        assert a != b

    def test_feishu_sign_matches_official_algorithm(self):
        timestamp = "1599360473"
        secret = "test-secret"
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        expected = base64.b64encode(hmac_code).decode("utf-8")
        assert _feishu_sign(timestamp, secret) == expected


class TestFeishuDriverSend:
    """Test FeishuWebhookDriver.send with optional sign."""

    def test_send_adds_timestamp_and_sign_when_sign_secret_set(self):
        driver = FeishuWebhookDriver()
        config = {
            "url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
            "sign_secret": "my-secret",
        }
        payload = {"msg_type": "text", "text": {"text": "hi"}}
        with patch(
            "agentcore_notifier.adapters.django.services.webhook.feishu."
            "requests.post"
        ) as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {}
            mock_post.return_value.raise_for_status = lambda: None
            with patch(
                "agentcore_notifier.adapters.django.services.webhook."
                "feishu.time.time",
                return_value=1599360473.0,
            ):
                result = driver.send(payload, config)
        assert result["success"] is True
        call_json = mock_post.call_args[1]["json"]
        assert "timestamp" in call_json
        assert call_json["timestamp"] == 1599360473
        assert "sign" in call_json
        expected_sign = _feishu_sign("1599360473", "my-secret")
        assert call_json["sign"] == expected_sign
        assert call_json["msg_type"] == "text"
        assert call_json["text"]["text"] == "hi"

    def test_send_fails_when_status_code_non_zero(self):
        driver = FeishuWebhookDriver()
        config = {
            "url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
        }
        payload = {"msg_type": "text", "text": {"text": "hi"}}
        with patch(
            "agentcore_notifier.adapters.django.services.webhook.feishu."
            "requests.post"
        ) as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "StatusCode": 19001,
                "msg": "invalid token",
            }
            mock_post.return_value.raise_for_status = lambda: None
            result = driver.send(payload, config)
        assert result["success"] is False
        assert "invalid token" in (result["error"] or "")

    def test_send_fails_when_errcode_non_zero(self):
        driver = FeishuWebhookDriver()
        config = {
            "url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
        }
        payload = {"msg_type": "text", "text": {"text": "hi"}}
        with patch(
            "agentcore_notifier.adapters.django.services.webhook.feishu."
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
