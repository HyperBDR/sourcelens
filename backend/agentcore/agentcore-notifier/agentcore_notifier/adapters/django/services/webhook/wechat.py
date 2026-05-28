"""WeChat Work webhook driver."""
import logging
from typing import Any, Dict

import requests

from agentcore_notifier.constants import DEFAULT_TIMEOUT

from .base import BaseWebhookDriver
from .feishu import _apply_message_prefix, _extract_business_error

logger = logging.getLogger(__name__)


class WeChatWebhookDriver(BaseWebhookDriver):
    """Driver for WeChat Work webhook."""

    provider_type = "wechat"

    def send(
        self, payload: Dict[str, Any], config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """POST payload to WeChat Work webhook URL."""
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
                    f"WeChatWebhookDriver: business error msg={err_msg}"
                )
                return {"success": False, "response": data, "error": err_msg}
            logger.info(f"WeChatWebhookDriver: sent successfully")
            return {"success": True, "response": data, "error": None}
        except requests.exceptions.RequestException as e:
            logger.error(f"WeChatWebhookDriver: failed: {e}")
            return {"success": False, "response": None, "error": str(e)}
