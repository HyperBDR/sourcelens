"""
Build LiteLLM completion params from provider + config.

Provider defaults come from YAML (llm_static/providers/*.yaml).
Used by runtime_config for validation, test-call, and get_litellm_params.
"""
from typing import Any, Dict, Optional

from agentcore_metering.adapters.django.llm_static.load import (
    get_provider_defaults,
)
from agentcore_metering.constants import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
)

_yaml_defaults = get_provider_defaults()
OFFICIAL_API_BASES: Dict[str, Optional[str]] = {
    p: d.get("default_api_base") for p, d in _yaml_defaults.items()
}
OFFICIAL_DEFAULT_TEMPERATURES: Dict[str, Optional[float]] = {
    p: d.get("default_temperature") for p, d in _yaml_defaults.items()
}
OFFICIAL_DEFAULT_TOP_P: Dict[str, Optional[float]] = {
    p: d.get("default_top_p") for p, d in _yaml_defaults.items()
}
OFFICIAL_DEFAULT_MAX_TOKENS: Dict[str, Optional[int]] = {
    p: d.get("default_max_tokens") for p, d in _yaml_defaults.items()
}
DEFAULT_MODELS: Dict[str, str] = {
    p: d.get("default_model")
    for p, d in _yaml_defaults.items()
    if d.get("default_model")
}
PROVIDER_SETTINGS_KEYS: Dict[str, str] = {
    p: d.get("settings_key")
    for p, d in _yaml_defaults.items()
    if d.get("settings_key")
}
PROVIDERS_REQUIRING_API_BASE = frozenset(
    p for p, d in _yaml_defaults.items() if d.get("requires_api_base")
)


def _model_string(provider: str, config: dict) -> str:
    """
    Build LiteLLM model string. Default to each platform's smallest/cheapest
    model to avoid cost from misconfiguration.
    """
    provider = (provider or "openai").strip().lower()
    model = (config.get("model") or "").strip() or DEFAULT_MODELS.get(
        provider, "gpt-4o-mini"
    )
    if provider == "openai_compatible":
        return model
    if provider == "azure_openai":
        deployment = config.get("deployment") or model
        return f"azure/{deployment}"
    if provider == "gemini":
        return f"gemini/{model}" if "/" not in model else model
    if provider == "moonshot":
        # LiteLLM needs the provider prefix to resolve Moonshot correctly.
        # Accept a legacy prefixed value and normalize it once.
        if model.startswith("moonshot/"):
            return model
        return f"moonshot/{model}"
    if provider in (
        "anthropic",
        "mistral",
        "dashscope",
        "deepseek",
        "xai",
        "meta_llama",
        "amazon_nova",
        "nvidia_nim",
        "minimax",
        "zai",
        "volcengine",
        "openrouter",
    ):
        if "/" not in model or provider == "nvidia_nim":
            return f"{provider}/{model}"
        return model
    return model


def _litellm_kwargs_from_config(provider: str, config: dict) -> Dict[str, Any]:
    provider = (provider or "openai").strip().lower()
    config = config or {}
    model = _model_string(provider, config)
    # For OpenAI-compatible gateways using custom model ids
    # (e.g. numeric ids), LiteLLM requires explicit provider prefix.
    if provider == "openai" and model and "/" not in model:
        model = f"openai/{model}"
    api_base = (
        (config.get("api_base") or "").strip()
        or OFFICIAL_API_BASES.get(provider)
    )
    kwargs = {
        "model": model,
        "api_key": config.get("api_key") or None,
        "api_base": api_base,
    }
    if provider == "openai_compatible":
        kwargs["custom_llm_provider"] = "openai"
    if provider == "azure_openai":
        kwargs["api_version"] = config.get("api_version")
    defaults = (
        (
            "max_tokens",
            OFFICIAL_DEFAULT_MAX_TOKENS.get(provider),
            DEFAULT_MAX_TOKENS,
        ),
        (
            "temperature",
            OFFICIAL_DEFAULT_TEMPERATURES.get(provider),
            DEFAULT_TEMPERATURE,
        ),
        ("top_p", OFFICIAL_DEFAULT_TOP_P.get(provider), DEFAULT_TOP_P),
    )
    for key, provider_default, fallback_default in defaults:
        value = config.get(key)
        default = (
            provider_default
            if provider_default is not None
            else fallback_default
        )
        kwargs[key] = default if value is None else value
    kwargs["drop_params"] = True
    return {k: v for k, v in kwargs.items() if v is not None}


def _validate_config(provider: str, config: dict) -> None:
    """Raise ValueError if required keys are missing for the provider."""
    provider = (provider or "openai").strip().lower()
    if provider in PROVIDERS_REQUIRING_API_BASE:
        if not config.get("api_key") or not config.get("api_base"):
            if provider == "openai_compatible":
                raise ValueError(
                    "OpenAI Compatible configuration is incomplete. "
                    "Set api_key and api_base."
                )
            raise ValueError(
                "Azure OpenAI configuration is incomplete. "
                "Set api_key and api_base."
            )
        return
    if provider == "openrouter":
        if not config.get("api_key"):
            raise ValueError(
                "OpenRouter configuration is incomplete. Set api_key."
            )
        return
    if provider in DEFAULT_MODELS:
        if not config.get("api_key"):
            name = (
                "OpenAI"
                if provider == "openai"
                else provider.replace("_", " ").title()
            )
            raise ValueError(
                f"{name} configuration is incomplete. Set api_key."
            )
        return
    if not config.get("api_key"):
        raise ValueError(
            f"Provider '{provider}' requires api_key in config."
        )


def build_litellm_params_from_config(
    provider: str, config: dict
) -> Dict[str, Any]:
    """
    Build litellm.completion() kwargs from given provider and config dict.
    Same defaults as get_litellm_params. Use for validation without DB.

    Raises:
        ValueError: If required config (e.g. api_key) is missing.
    """
    provider = (provider or "openai").strip().lower()
    config = config or {}
    _validate_config(provider, config)
    return _litellm_kwargs_from_config(provider, config)


def get_provider_params_schema() -> Dict[str, Any]:
    """
    Per-provider param metadata for UI: required keys, optional keys,
    default model and default api_base. api_base is first in optional
    so UI can show it at top. editable_params lists all configurable keys.
    """
    optional_common = [
        "api_base",
        "model",
        "max_tokens",
        "temperature",
        "top_p",
    ]
    editable_common = [
        "api_base",
        "api_key",
        "model",
        "max_tokens",
        "temperature",
        "top_p",
    ]
    providers = {}
    for p in DEFAULT_MODELS:
        required = ["api_key"]
        if p == "azure_openai":
            required = ["api_key", "api_base", "deployment"]
            optional = [
                "api_base",
                "model",
                "api_version",
                "max_tokens",
                "temperature",
                "top_p",
            ]
            editable = [
                "api_base",
                "api_key",
                "deployment",
                "model",
                "api_version",
                "max_tokens",
                "temperature",
                "top_p",
            ]
        else:
            optional = optional_common.copy()
            editable = editable_common.copy()
        providers[p] = {
            "required": required,
            "optional": optional,
            "editable_params": editable,
            "default_model": DEFAULT_MODELS.get(p),
            "default_api_base": OFFICIAL_API_BASES.get(p),
            "default_temperature": OFFICIAL_DEFAULT_TEMPERATURES.get(p),
            "default_top_p": OFFICIAL_DEFAULT_TOP_P.get(p),
            "default_max_tokens": OFFICIAL_DEFAULT_MAX_TOKENS.get(p),
        }
    return {"providers": providers}
