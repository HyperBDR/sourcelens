"""
Feishu / WeCom webhook driver.

Supports Feishu custom bot message format and optional signature.
See: https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot

Message body: msg_type (text|post|image|...) + content per type.
When sign_secret is set, timestamp and sign added for Feishu verification.
"""
import base64
import copy
import hmac
import hashlib
import logging
import time
from typing import Any, Dict, Optional

import requests

from agentcore_notifier.constants import DEFAULT_TIMEOUT

from .base import BaseWebhookDriver

logger = logging.getLogger(__name__)


def _feishu_sign(timestamp: str, secret: str) -> str:
    """
    Generate Feishu custom bot sign (match official algorithm).
    string_to_sign = timestamp + "\\n" + secret; Base64(HMAC-SHA256).
    """
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def _apply_message_prefix(
    payload: Dict[str, Any], prefix: str
) -> Dict[str, Any]:
    """Prepend prefix to payload text when msg_type is text / text.text."""
    if not prefix or not isinstance(payload.get("text"), dict):
        return payload
    text_obj = payload.get("text") or {}
    if "text" not in text_obj or not isinstance(text_obj["text"], str):
        return payload
    out = copy.deepcopy(payload)
    out["text"] = {**out.get("text", {}), "text": prefix + text_obj["text"]}
    return out


def _extract_business_error(
    data: Dict[str, Any],
) -> tuple[bool, Optional[str]]:
    """
    Extract provider business error from common response code fields.
    Returns (is_error, error_message).
    """
    if not isinstance(data, dict):
        return False, None
    for key in ("code", "StatusCode", "errcode"):
        code = data.get(key)
        if isinstance(code, int):
            if code == 0:
                return False, None
            msg = (
                data.get("msg")
                or data.get("errmsg")
                or f"Webhook error code {code}"
            )
            return True, str(msg)
    return False, None


class FeishuWebhookDriver(BaseWebhookDriver):
    """Driver for Feishu and WeCom webhook (same HTTP semantics)."""

    provider_type = "feishu"

    def send(
        self, payload: Dict[str, Any], config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        POST payload to Feishu/WeCom webhook URL.
        If sign_secret in config, adds timestamp and sign for verification.
        """
        url = config.get("url", "")
        if not url:
            return {
                "success": False,
                "response": None,
                "error": "Webhook URL not configured",
            }
        payload_to_send = _apply_message_prefix(
            payload, config.get("message_prefix") or ""
        )
        sign_secret = (config.get("sign_secret") or "").strip()
        if sign_secret:
            ts_int = int(time.time())
            ts_str = str(ts_int)
            payload_to_send = copy.deepcopy(payload_to_send)
            payload_to_send["timestamp"] = ts_int
            payload_to_send["sign"] = _feishu_sign(ts_str, sign_secret)
        timeout = config.get("timeout", DEFAULT_TIMEOUT)
        headers = {
            "Content-Type": "application/json",
            **config.get("headers", {}),
        }
        try:
            response = requests.post(
                url, json=payload_to_send, headers=headers, timeout=timeout
            )
            response.raise_for_status()
            data = response.json()
            is_error, err_msg = _extract_business_error(data)
            if is_error:
                logger.warning(
                    f"FeishuWebhookDriver: business error msg={err_msg}"
                )
                return {"success": False, "response": data, "error": err_msg}
            logger.info(f"FeishuWebhookDriver: sent successfully")
            return {"success": True, "response": data, "error": None}
        except requests.exceptions.RequestException as e:
            logger.error(f"FeishuWebhookDriver: failed: {e}")
            return {"success": False, "response": None, "error": str(e)}
