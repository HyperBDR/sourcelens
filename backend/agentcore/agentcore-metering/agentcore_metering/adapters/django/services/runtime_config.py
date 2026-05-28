"""
LLM call params from DB (global/per-user) for LiteLLM.

Resolution: DB user config -> DB global config. No settings fallback;
config must exist in DB (managed via admin API).
Returns dict of kwargs for litellm.completion(
    model=..., messages=..., **kwargs).
All providers support api_base (URL). Use official default when not set.
Supported: OpenAI, Azure, Gemini, Anthropic, Mistral, Qwen, DeepSeek, xAI,
Meta Llama, Amazon Nova, NVIDIA NIM, MiniMax, Moonshot, Z.AI, Volcengine,
OpenRouter.
"""
import logging
from decimal import Decimal
from typing import Any, Dict, Generator, Optional, Tuple

from django.utils import timezone
from django.utils.translation import activate, gettext as _
import litellm
from litellm import completion_cost

from agentcore_metering.adapters.django.models import LLMConfig, LLMUsage
from agentcore_metering.adapters.django.services.config_source import (
    get_config_from_db,
)
from agentcore_metering.adapters.django.services.litellm_params import (
    _litellm_kwargs_from_config,
    _validate_config,
    build_litellm_params_from_config,
    get_provider_params_schema,
)
from agentcore_metering.adapters.django.utils import (
    _read_field,
    _read_nested_int,
    _safe_int,
)
from agentcore_metering.constants import (
    DEFAULT_COST_CURRENCY,
    LITELLM_REQUEST_TIMEOUT,
    TEST_MAX_TOKENS,
)

logger = logging.getLogger(__name__)

TASK_VALIDATE_LLM_CONFIG = "validate_llm_config"
TASK_RUN_TEST_CALL = "run_test_call"

# Error keys for connection test; backend translates via gettext (.po files).
# Key -> default English message (msgid for gettext).
VALIDATION_MESSAGE_IDS: Dict[str, str] = {
    "invalid_api_key": (
        "Invalid or expired API key. Please check and try again."
    ),
    "auth_failed": (
        "Authentication failed. Check API key or account permissions."
    ),
    "rate_limit": "Rate limit or quota exceeded. Please try again later.",
    "not_found": (
        "Model or endpoint not found. Check model name and API base URL."
    ),
    "timeout": "Connection timed out. Check network and API base URL.",
    "network_error": (
        "Cannot reach the service. Check API base URL and network."
    ),
    "permission_denied": (
        "Access denied. Check API key or account permissions."
    ),
    "unknown": (
        "Connection test failed. Check your configuration and try again."
    ),
}


def get_validation_message(key: str, language: Optional[str] = None) -> str:
    """
    Return translated connection-test error message for the given key.
    Uses Django gettext; language is e.g. request.LANGUAGE_CODE (zh-hans, en).
    Falls back to key if unknown.
    """
    if not key:
        return key or ""
    if language:
        activate(language)
    msgid = VALIDATION_MESSAGE_IDS.get(key) or key
    return _(msgid)


def _user_friendly_validation_error(exc: Exception) -> str:
    """
    Map LiteLLM/API exceptions to an error key for connection test.
    Returns key only; view calls get_validation_message(key,
    request.LANGUAGE_CODE).
    """
    msg = str(exc).strip()
    msg_lower = msg.lower()
    type_name = type(exc).__name__

    if (
        "401" in msg
        or "authentication" in type_name
        or "authentication" in msg_lower
    ):
        if (
            "invalid" in msg_lower
            or "token" in msg_lower
            or "key" in msg_lower
            or "expired" in msg_lower
        ):
            return "invalid_api_key"
        return "auth_failed"
    if "429" in msg or "rate" in msg_lower or "limit" in msg_lower:
        return "rate_limit"
    if "404" in msg or "not found" in msg_lower or "not_found" in msg_lower:
        return "not_found"
    if "timeout" in msg_lower or "timed out" in msg_lower:
        return "timeout"
    if (
        "connection" in msg_lower
        or "network" in msg_lower
        or "unreachable" in msg_lower
    ):
        return "network_error"
    if "invalid_api_key" in msg_lower or "incorrect api key" in msg_lower:
        return "invalid_api_key"
    if "permission" in msg_lower or "forbidden" in msg_lower or "403" in msg:
        return "permission_denied"

    return "unknown"


def _extract_usage_from_response(response: Any, params: dict) -> Tuple[
    str, int, int, int, int, int, Optional[Decimal]
]:
    """
    Extract actual_model, token counts, and cost from LiteLLM completion
    response. Returns (actual_model, prompt_tokens, completion_tokens,
    total_tokens, cached_tokens, reasoning_tokens, cost).
    """
    usage_obj = getattr(response, "usage", None)
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    cached_tokens = 0
    reasoning_tokens = 0
    if usage_obj:
        prompt_tokens = _safe_int(_read_field(usage_obj, "prompt_tokens", 0))
        completion_tokens = _safe_int(
            _read_field(usage_obj, "completion_tokens", 0)
        )
        total_tokens = (
            _safe_int(_read_field(usage_obj, "total_tokens", 0))
            or (prompt_tokens + completion_tokens)
        )
        cached_tokens = _safe_int(_read_field(usage_obj, "cached_tokens", 0))
        reasoning_tokens = _safe_int(
            _read_field(usage_obj, "reasoning_tokens", 0)
        )
        if cached_tokens == 0:
            prompt_details = (
                _read_field(usage_obj, "prompt_tokens_details", None)
                or _read_field(usage_obj, "input_token_details", None)
            )
            cached_tokens = _read_nested_int(
                prompt_details,
                ("cached_tokens", "cache_read_tokens", "cache_read"),
                0,
            )
        if reasoning_tokens == 0:
            completion_details = (
                _read_field(usage_obj, "completion_tokens_details", None)
                or _read_field(usage_obj, "output_token_details", None)
            )
            reasoning_tokens = _read_nested_int(
                completion_details,
                ("reasoning_tokens", "reasoning"),
                0,
            )

    actual_model = (
        getattr(response, "model", None) or params.get("model", "unknown")
    )
    cost = None
    try:
        raw_cost = completion_cost(completion_response=response)
        if raw_cost is not None:
            cost = Decimal(str(raw_cost))
    except (TypeError, ValueError) as e:
        logger.debug(f"completion_cost or Decimal failed: {e}")
    except Exception as e:
        logger.debug(f"completion_cost failed: {e}")
    return (
        actual_model, prompt_tokens, completion_tokens, total_tokens,
        cached_tokens, reasoning_tokens, cost,
    )


def _create_usage_record(
    user: Optional[Any],
    actual_model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cached_tokens: int,
    reasoning_tokens: int,
    cost: Optional[Decimal],
    metadata_node_name: str,
    started_at: Optional[Any] = None,
) -> None:
    """
    Persist one usage record for runtime validation and test calls.
    started_at: when the LLM request started (for E2E latency).
    """
    LLMUsage.objects.create(
        user=user,
        model=actual_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
        cost=cost,
        cost_currency=DEFAULT_COST_CURRENCY,
        success=True,
        error=None,
        metadata={"node_name": metadata_node_name},
        started_at=started_at,
    )


def validate_llm_config(
    provider: str,
    config: dict,
    user: Optional[Any] = None,
) -> tuple[bool, str]:
    """
    Test that the given provider + config can complete a minimal LLM call.
    Uses LiteLLM completion with TEST_MAX_TOKENS to avoid model output limits.
    On success, records token usage (and cost if available) to LLMUsage when
    user is provided.
    Returns (True, "") on success, (False, error_message) on failure.
    """
    logger.info(f"Starting {TASK_VALIDATE_LLM_CONFIG} provider={provider}")
    try:
        params = build_litellm_params_from_config(provider, config)
        params["max_tokens"] = TEST_MAX_TOKENS
        params["timeout"] = LITELLM_REQUEST_TIMEOUT
        params["messages"] = [{"role": "user", "content": "Hi"}]
        user_id = getattr(user, "pk", None)
        logger.info(
            "LLM validate request "
            f"provider={provider} user_id={user_id} "
            f"model={params.get('model')} "
            f"max_tokens={params.get('max_tokens')} "
            f"has_api_key={bool(params.get('api_key'))} "
            f"api_base={params.get('api_base')}"
        )
        request_started_at = timezone.now()
        response = litellm.completion(**params)
        logger.info(
            "LLM validate response "
            f"provider={provider} user_id={user_id} "
            f"has_response={response is not None}"
        )

        if response is None:
            return False, "LLM returned no response"

        (
            actual_model, prompt_tokens, completion_tokens, total_tokens,
            cached_tokens, reasoning_tokens, cost,
        ) = _extract_usage_from_response(response, params)
        logger.info(
            "LLM validate usage "
            f"provider={provider} user_id={user_id} model={actual_model} "
            f"prompt_tokens={prompt_tokens} "
            f"completion_tokens={completion_tokens} "
            f"total_tokens={total_tokens}"
        )

        if user is not None:
            try:
                _create_usage_record(
                    user=user,
                    actual_model=actual_model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    cached_tokens=cached_tokens,
                    reasoning_tokens=reasoning_tokens,
                    cost=cost,
                    metadata_node_name="config_test",
                    started_at=request_started_at,
                )
            except Exception as e:
                uid = getattr(user, "pk", None)
                logger.warning(
                    f"Failed to record test-call usage; user={uid}, "
                    f"model={actual_model}, error={e}",
                    exc_info=True,
                )

        logger.info(f"Finished {TASK_VALIDATE_LLM_CONFIG} provider={provider}")
        return True, ""
    except ValueError as e:
        logger.error(
            f"Failed {TASK_VALIDATE_LLM_CONFIG} provider={provider}: {e}"
        )
        return False, str(e)
    except Exception as e:
        error_key = _user_friendly_validation_error(e)
        user_id = getattr(user, "pk", None)
        logger.warning(
            "LLM validate failed "
            f"provider={provider} user_id={user_id} "
            f"error_key={error_key} error={str(e)}"
        )
        logger.debug(
            f"LLM config validation failed provider={provider}: {e}",
            exc_info=True,
        )
        return False, error_key


def run_test_call(
    config_uuid: Optional[str],
    config_id: Optional[int],
    prompt: str,
    user: Any,
    max_tokens: int = 512,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Run one completion with the given LLMConfig and record to LLMUsage.

    Uses LLMTracker.call_and_track so test-call shares the same code path as
    application calls (params resolution, completion, usage + started_at).
    Returns (ok, content_or_detail, usage_dict or None).
    """
    if not (prompt or "").strip():
        return False, "Prompt cannot be empty", None
    max_tokens = min(max(1, max_tokens), 4096)
    llm_config = None
    if config_uuid:
        try:
            llm_config = LLMConfig.objects.get(uuid=config_uuid)
        except (LLMConfig.DoesNotExist, ValueError, TypeError):
            llm_config = None
    if llm_config is None and config_id is not None:
        try:
            llm_config = LLMConfig.objects.get(pk=config_id)
        except (LLMConfig.DoesNotExist, ValueError, TypeError):
            llm_config = None
    if llm_config is None:
        return False, "Config not found", None

    # NOTE(Ray): Import here to avoid circular import; trackers.llm imports
    # get_litellm_params from this module.
    from agentcore_metering.adapters.django.trackers.llm import LLMTracker

    config_uuid_value = str(getattr(llm_config, "uuid", "") or "")
    config_id_value = getattr(llm_config, "id", None)
    logger.info(
        f"Starting {TASK_RUN_TEST_CALL} "
        f"config_uuid={config_uuid_value} config_id={config_id_value}"
    )
    messages = [{"role": "user", "content": (prompt or "").strip()}]
    state = {"node_name": "admin_test_call"}
    if user is not None:
        state["user_id"] = getattr(user, "pk", None)

    try:
        content, usage = LLMTracker.call_and_track(
            messages=messages,
            max_tokens=max_tokens,
            state=state,
            model_uuid=config_uuid_value,
        )
    except ValueError as e:
        msg = str(e).strip().lower()
        if "empty response" in msg or "no response" in msg:
            return False, "LLM returned empty response", None
        return False, str(e), None
    except Exception as e:
        error_key = _user_friendly_validation_error(e)
        logger.warning(
            "LLM test-call failed "
            f"config_uuid={config_uuid_value} config_id={config_id_value} "
            f"error_key={error_key} error={e}",
            exc_info=True,
        )
        return False, error_key, None

    cost = usage.get("cost")
    usage_dict = {
        "model": usage.get("model", ""),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "cached_tokens": usage.get("cached_tokens", 0),
        "reasoning_tokens": usage.get("reasoning_tokens", 0),
        "cost": float(cost) if cost is not None else None,
        "cost_currency": usage.get("cost_currency", DEFAULT_COST_CURRENCY),
    }
    logger.info(
        f"Finished {TASK_RUN_TEST_CALL} "
        f"config_uuid={config_uuid_value} config_id={config_id_value}"
    )
    return True, content, usage_dict


def run_test_call_stream(
    config_uuid: Optional[str],
    config_id: Optional[int],
    prompt: str,
    user: Any,
    max_tokens: int = 512,
) -> Generator[str, None, Optional[Dict[str, Any]]]:
    """
    Stream one completion with the given LLMConfig and record to LLMUsage.

    Yields content chunks; usage dict is the generator's return value
    (see StopIteration.value when the generator is exhausted).
    On validation or LLM error, raises or yields nothing and returns
    (False, detail, None).
    """
    if not (prompt or "").strip():
        raise ValueError("Prompt cannot be empty")
    max_tokens = min(max(1, max_tokens), 4096)
    llm_config = None
    if config_uuid:
        try:
            llm_config = LLMConfig.objects.get(uuid=config_uuid)
        except (LLMConfig.DoesNotExist, ValueError, TypeError):
            llm_config = None
    if llm_config is None and config_id is not None:
        try:
            llm_config = LLMConfig.objects.get(pk=config_id)
        except (LLMConfig.DoesNotExist, ValueError, TypeError):
            llm_config = None
    if llm_config is None:
        raise ValueError("Config not found")

    from agentcore_metering.adapters.django.trackers.llm import LLMTracker

    config_uuid_value = str(getattr(llm_config, "uuid", "") or "")
    config_id_value = getattr(llm_config, "id", None)
    logger.info(
        f"Starting {TASK_RUN_TEST_CALL} (stream) "
        f"config_uuid={config_uuid_value} config_id={config_id_value}"
    )
    messages = [{"role": "user", "content": (prompt or "").strip()}]
    state = {"node_name": "admin_test_call"}
    if user is not None:
        state["user_id"] = getattr(user, "pk", None)

    gen = LLMTracker.call_and_track(
        messages=messages,
        max_tokens=max_tokens,
        state=state,
        model_uuid=config_uuid_value,
        stream=True,
    )
    usage = None
    chunk_count = 0
    try:
        while True:
            chunk = next(gen)
            chunk_count += 1
            if chunk_count == 1:
                logger.info(
                    f"run_test_call (stream) first chunk received "
                    f"config_uuid={config_uuid_value}"
                )
            elif chunk_count % 20 == 0:
                logger.info(
                    f"run_test_call (stream) chunk #{chunk_count} "
                    f"config_uuid={config_uuid_value}"
                )
            yield chunk
    except StopIteration as e:
        usage = e.value
    cost = usage.get("cost") if usage else None
    usage_dict = None
    if usage is not None:
        usage_dict = {
            "model": usage.get("model", ""),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "cached_tokens": usage.get("cached_tokens", 0),
            "reasoning_tokens": usage.get("reasoning_tokens", 0),
            "cost": float(cost) if cost is not None else None,
            "cost_currency": usage.get("cost_currency", DEFAULT_COST_CURRENCY),
        }
    logger.info(
        f"Finished {TASK_RUN_TEST_CALL} (stream) "
        f"config_uuid={config_uuid_value} config_id={config_id_value} "
        f"chunks={chunk_count}"
    )
    return usage_dict


def get_litellm_params(
    user_id: Optional[int] = None,
    model_uuid: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build litellm.completion() kwargs from DB only.

    When model_uuid is provided, uses that LLM config (by uuid). Otherwise
    uses the earliest enabled LLM config (user scope then global). No
    settings fallback; config must exist in DB.

    Returns:
        Dict with "model", "max_tokens", "temperature", "top_p" (defaults
        applied when not in config), and optionally "api_key", "api_base".
        Pass to litellm.completion(..., **params).

    Raises:
        ValueError: If no config in DB or required config (e.g. api_key)
        is missing.
    """
    cfg = get_config_from_db(user_id=user_id, model_uuid=model_uuid)

    if cfg is not None:
        provider = cfg["provider"]
        config = cfg["config"] or {}
        _validate_config(provider, config)
        return _litellm_kwargs_from_config(provider, config)

    if model_uuid is not None:
        raise ValueError(
            "LLM config not found or not usable for "
            f"model_uuid={model_uuid!r}. "
            "Check uuid, is_active=True, and model_type=llm.",
        )

    raise ValueError(
        "No LLM config found in DB. Add a global or user config via the "
        "admin API (e.g. .../llm-config/)."
    )
