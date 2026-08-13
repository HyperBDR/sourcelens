"""Resolve the image capability of a configured LLM safely."""

from .llm import (
    VISION_SUPPORTED,
    VISION_UNKNOWN,
    model_supports_vision,
)

VISION_CAPABILITY_SOURCES = {
    "catalog",
    "explicit",
    "unknown",
}


def resolve_model_capability(model_ref):
    """Return a stable, serializable vision capability contract."""

    if not model_ref:
        return {
            "supports_vision": False,
            "vision_capability": "unsupported",
            "vision_capability_source": "unknown",
        }
    try:
        from agentcore_metering.adapters.django.models import LLMConfig

        config = LLMConfig.objects.filter(uuid=model_ref).first()
        if config is None:
            return {
                "supports_vision": False,
                "vision_capability": "unknown",
                "vision_capability_source": "unknown",
            }
        data = config.config or {}
        explicit = data.get("supports_vision")
        if explicit is None:
            explicit = data.get("vision")
        state = model_supports_vision(model_ref)
        source = "explicit" if isinstance(explicit, bool) else "catalog"
        if state == VISION_UNKNOWN:
            source = "unknown"
        return {
            "supports_vision": state == VISION_SUPPORTED,
            "vision_capability": state,
            "vision_capability_source": source,
            "enabled": bool(config.is_active),
        }
    except Exception:
        return {
            "supports_vision": False,
            "vision_capability": "unknown",
            "vision_capability_source": "unknown",
        }


def validate_vision_model_ref(model_ref):
    """Return a stable validation error for a new vision assignment."""

    if not model_ref:
        return None
    capability = resolve_model_capability(model_ref)
    if not capability.get("enabled"):
        return "VISION_MODEL_DISABLED"
    if capability.get("vision_capability") != VISION_SUPPORTED:
        return "MODEL_NOT_VISION_CAPABLE"
    return None
