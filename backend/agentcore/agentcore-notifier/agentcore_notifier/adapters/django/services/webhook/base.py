"""Abstract base for webhook drivers."""
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseWebhookDriver(ABC):
    """Base for webhook drivers. Each driver implements send() per provider."""

    provider_type: str = ""

    @abstractmethod
    def send(
        self, payload: Dict[str, Any], config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send payload with config. Returns dict: success, response, error."""
        raise NotImplementedError("send() must be implemented")
