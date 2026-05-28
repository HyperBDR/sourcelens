"""
LLM call tracker using LiteLLM: completion + usage and cost tracking.

Uses litellm.completion(); token/cost extraction is delegated to llm_usage.
Applies LiteLLM global retry and timeout at module load. Handles
AuthenticationError, RateLimitError, and APIError with distinct logging.
"""
import logging
import json
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Generator, Optional, Tuple, Union

from django.db import transaction
from django.utils import timezone
import litellm
from litellm import APIError, AuthenticationError, RateLimitError
from json_repair import repair_json

from agentcore_metering.adapters.django.models import LLMUsage
from agentcore_metering.adapters.django.services.runtime_config import (
    get_litellm_params,
)
from agentcore_metering.adapters.django.trackers.llm_usage import (
    fill_usage_with_token_fallback,
    usage_from_response,
    usage_from_stream_chunk,
)
from agentcore_metering.constants import (
    DEFAULT_COST_CURRENCY,
    LITELLM_NUM_RETRIES,
    LITELLM_REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)

TASK_LLM_CALL = "llm_call"
JSON_RETRY_BASE_DELAY_SECONDS = 0.5

litellm.num_retries = LITELLM_NUM_RETRIES
litellm.request_timeout = LITELLM_REQUEST_TIMEOUT


def _default_usage_dict(model: str) -> Dict[str, Any]:
    """Zero usage dict when no chunk/response usage is available."""
    return {
        "model": model,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
        "cost": None,
        "cost_currency": DEFAULT_COST_CURRENCY,
    }


def _record_failed_llm_call(
    *,
    effective_state: Dict[str, Any],
    state: Optional[Dict],
    request_started_at: Any,
    node_name: str,
    is_streaming: bool,
    error_msg: str,
) -> None:
    """Record a failed LLM call into state and DB. Does not raise."""
    if state is not None:
        state.setdefault("llm_calls", []).append({
            "node": node_name,
            "model": "unknown",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "success": False,
            "error": error_msg,
        })
    LLMTracker._save_usage_to_db(
        state=effective_state,
        model="unknown",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        cached_tokens=0,
        reasoning_tokens=0,
        cost=None,
        cost_currency=DEFAULT_COST_CURRENCY,
        success=False,
        error=error_msg,
        started_at=request_started_at,
        is_streaming=is_streaming,
    )


def _repair_json_obj(content: str) -> str:
    """
    Repair and validate LLM JSON output as an object.

    Returns repaired JSON string when validation succeeds.
    Raises ValueError when content cannot be repaired to valid JSON object.
    """
    if not content or not str(content).strip():
        raise ValueError("LLM returned empty response")

    normalized = str(content).strip()
    if normalized.startswith("```json"):
        normalized = normalized[7:]
    if normalized.startswith("```"):
        normalized = normalized[3:]
    if normalized.endswith("```"):
        normalized = normalized[:-3]
    normalized = normalized.strip()

    try:
        repaired = repair_json(normalized)
    except Exception as e:
        raise ValueError(f"JSON repair failed: {e}") from e

    try:
        parsed = json.loads(repaired)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Failed to parse JSON after repair: {e.msg} "
            f"at line {e.lineno} column {e.colno}"
        ) from e

    if not isinstance(parsed, dict):
        raise ValueError(
            f"LLM returned {type(parsed).__name__} instead of object"
        )

    return repaired


class LLMTracker:
    """
    LLM call tracker via LiteLLM with usage and cost (reference pricing).
    """

    @staticmethod
    def call_and_track(
        messages: list,
        json_mode: bool = False,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        response_format: Optional[Dict] = None,
        node_name: str = "unknown",
        state: Optional[Dict] = None,
        model_uuid: Optional[str] = None,
        stream: bool = False,
        json_repair: Optional[bool] = None,
        json_attempts: int = 3,
    ) -> Union[
        Tuple[str, Dict[str, Any]],
        Generator[str, None, Dict[str, Any]],
    ]:
        """
        Call LLM via LiteLLM and persist usage + cost.

        When model_uuid is provided, uses that LLM config. Otherwise uses
        the earliest enabled LLM config (user scope then global).

        When stream=False: returns (response_content, usage_dict).
        When stream=True: returns a generator that yields content chunks;
        usage is the generator's return value (StopIteration.value).

        usage_dict contains: model, prompt_tokens, completion_tokens,
        total_tokens, cached_tokens, reasoning_tokens, cost, cost_currency.
        """
        if not messages:
            raise ValueError("Messages cannot be empty")

        user_id = state.get("user_id") if state else None
        params = get_litellm_params(user_id=user_id, model_uuid=model_uuid)
        model = params.get("model", "unknown")

        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if temperature is not None:
            params["temperature"] = temperature
        if top_p is not None:
            params["top_p"] = top_p

        if json_mode:
            if response_format is None:
                response_format = {"type": "json_object"}
            params["response_format"] = response_format
        elif response_format is not None:
            params["response_format"] = response_format

        params["messages"] = messages
        state_node = None
        if isinstance(state, dict):
            state_node = state.get("node_name")
        effective_state = {
            **(state or {}),
            "node_name": (state_node if state_node else node_name),
        }
        logger.info(
            f"Starting {TASK_LLM_CALL} node_name={node_name} "
            f"model={model} message_count={len(messages)}"
        )
        do_json_repair = (
            json_mode if json_repair is None
            else json_repair
        )
        max_json_attempts = max(1, int(json_attempts))

        if stream:
            if do_json_repair and json_mode:
                logger.warning(
                    "JSON repair is skipped for streaming "
                    f"calls; node_name={node_name}"
                )
            request_started_at = timezone.now()
            return LLMTracker._call_and_track_stream(
                params=params,
                effective_state=effective_state,
                request_started_at=request_started_at,
                node_name=node_name,
                state=state,
                model=model,
            )
        if not do_json_repair or not json_mode:
            return LLMTracker._call_and_track_non_stream_once(
                params=params,
                effective_state=effective_state,
                node_name=node_name,
                state=state,
                model=model,
            )

        total_attempts = max_json_attempts
        last_error: Optional[ValueError] = None
        for attempt_idx in range(total_attempts):
            content, usage = LLMTracker._call_and_track_non_stream_once(
                params=params,
                effective_state=effective_state,
                node_name=node_name,
                state=state,
                model=model,
            )
            try:
                repaired_content = _repair_json_obj(content)
                return repaired_content, usage
            except ValueError as e:
                last_error = e
                if attempt_idx >= total_attempts - 1:
                    break
                delay_seconds = JSON_RETRY_BASE_DELAY_SECONDS * (2 ** attempt_idx)
                logger.warning(
                    f"JSON parse validation failed "
                    f"(attempt {attempt_idx + 1}/{total_attempts}) "
                    f"node_name={node_name}: {e}. "
                    f"Retrying in {delay_seconds:.1f}s"
                )
                time.sleep(delay_seconds)

        raise ValueError(
            f"[{node_name}] Invalid JSON response after {total_attempts} "
            f"attempts: {last_error}"
        )

    @staticmethod
    def _call_and_track_non_stream_once(
        params: Dict[str, Any],
        effective_state: Dict[str, Any],
        node_name: str,
        state: Optional[Dict],
        model: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """Single non-stream LLM call + metering persistence."""
        request_started_at = timezone.now()
        try:
            response = litellm.completion(**params)

            if response is None:
                logger.error(f"LiteLLM returned None; node_name={node_name}")
                raise ValueError(
                    f"[{node_name}] LLM service returned None response"
                )

            choice = (response.choices or [None])[0]
            if not choice or not getattr(choice, "message", None):
                raise ValueError("LLM returned empty response")
            msg = choice.message
            content = getattr(msg, "content", None) or ""
            if not (content and str(content).strip()):
                raise ValueError("LLM returned empty response")

            usage = usage_from_response(response, model)
            usage = fill_usage_with_token_fallback(
                usage,
                model,
                messages=params.get("messages"),
                content=str(content).strip() if content else None,
            )
            cost = (
                Decimal(str(usage["cost"]))
                if usage.get("cost") is not None
                else None
            )
            cost_currency = usage.get("cost_currency", DEFAULT_COST_CURRENCY)
            response_model_raw = getattr(response, "model", None)

            if state is not None:
                state.setdefault("llm_calls", []).append({
                    "node": effective_state.get("node_name", "unknown"),
                    "model": usage["model"],
                    "prompt_tokens": usage["prompt_tokens"],
                    "completion_tokens": usage["completion_tokens"],
                    "total_tokens": usage["total_tokens"],
                    "cached_tokens": usage["cached_tokens"],
                    "reasoning_tokens": usage["reasoning_tokens"],
                    "cost": usage.get("cost"),
                    "cost_currency": usage.get("cost_currency"),
                    "success": True,
                    "error": None,
                })

            LLMTracker._save_usage_to_db(
                state=effective_state,
                model=model,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                total_tokens=usage["total_tokens"],
                cached_tokens=usage["cached_tokens"],
                reasoning_tokens=usage["reasoning_tokens"],
                cost=cost,
                cost_currency=cost_currency,
                success=True,
                error=None,
                started_at=request_started_at,
                is_streaming=False,
                response_model=response_model_raw,
            )

            logger.info(
                f"Finished {TASK_LLM_CALL} node_name={node_name} "
                f"model={usage['model']} total_tokens={usage['total_tokens']} "
                f"cost={cost} {cost_currency}"
            )
            return str(content), usage

        except AuthenticationError as e:
            node = effective_state.get("node_name", "unknown")
            logger.error(
                f"Failed {TASK_LLM_CALL} (authentication) "
                f"node_name={node} error={e}"
            )
            logger.exception(e)
            _record_failed_llm_call(
                effective_state=effective_state,
                state=state,
                request_started_at=request_started_at,
                node_name=node,
                is_streaming=False,
                error_msg=str(e),
            )
            raise
        except RateLimitError as e:
            node = effective_state.get("node_name", "unknown")
            logger.warning(
                f"Failed {TASK_LLM_CALL} (rate limit) "
                f"node_name={node} error={e}"
            )
            logger.exception(e)
            _record_failed_llm_call(
                effective_state=effective_state,
                state=state,
                request_started_at=request_started_at,
                node_name=node,
                is_streaming=False,
                error_msg=str(e),
            )
            raise
        except APIError as e:
            node = effective_state.get("node_name", "unknown")
            logger.error(
                f"Failed {TASK_LLM_CALL} (API error) "
                f"node_name={node} error={e}"
            )
            logger.exception(e)
            _record_failed_llm_call(
                effective_state=effective_state,
                state=state,
                request_started_at=request_started_at,
                node_name=node,
                is_streaming=False,
                error_msg=str(e),
            )
            raise
        except Exception as e:
            node = effective_state.get("node_name", "unknown")
            logger.error(
                f"Failed {TASK_LLM_CALL} node_name={node} "
                f"error_type={type(e).__name__} error={e}"
            )
            logger.exception(e)
            _record_failed_llm_call(
                effective_state=effective_state,
                state=state,
                request_started_at=request_started_at,
                node_name=node,
                is_streaming=False,
                error_msg=str(e),
            )
            raise

    @staticmethod
    def _save_usage_to_db(
        state: Optional[Dict] = None,
        node_name: str = "unknown",
        model: str = "unknown",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        cached_tokens: int = 0,
        reasoning_tokens: int = 0,
        cost: Optional[Decimal] = None,
        cost_currency: str = "USD",
        success: bool = True,
        error: Optional[str] = None,
        started_at: Optional[Any] = None,
        is_streaming: bool = False,
        first_chunk_at: Optional[datetime] = None,
        response_model: Optional[str] = None,
    ) -> None:
        """
        Persist one LLM usage record. model is the configured/request model;
        response_model from API (if any) is stored in metadata for reference.
        """
        try:
            state = state or {}
            user_id = state.get("user_id")
            node_name = state.get("node_name", node_name)
            metadata = {}
            if node_name and node_name != "unknown":
                metadata["node_name"] = node_name
            source_type = state.get("source_type")
            if source_type:
                metadata["source_type"] = source_type
            source_task_id = (
                state.get("source_task_id")
                or state.get("celery_task_id")
                or state.get("task_id")
            )
            if source_task_id:
                metadata["source_task_id"] = str(source_task_id)
            source_path = state.get("source_path")
            if source_path:
                metadata["source_path"] = source_path
            if response_model and str(response_model).strip():
                metadata["response_model"] = str(response_model).strip()
            extra = state.get("metadata")
            if isinstance(extra, dict):
                metadata.update(extra)

            with transaction.atomic():
                LLMUsage.objects.create(
                    user_id=user_id,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    cached_tokens=cached_tokens,
                    reasoning_tokens=reasoning_tokens,
                    cost=cost,
                    cost_currency=cost_currency or DEFAULT_COST_CURRENCY,
                    success=success,
                    error=error,
                    metadata=metadata,
                    started_at=started_at,
                    is_streaming=is_streaming,
                    first_chunk_at=first_chunk_at,
                )
        except Exception as e:
            logger.warning(
                f"Failed to save LLM usage; node_name={node_name}, "
                f"model={model}, user_id={user_id}, error={e}",
                exc_info=True,
            )

    @staticmethod
    def _call_and_track_stream(
        params: Dict[str, Any],
        effective_state: Dict[str, Any],
        request_started_at: Any,
        node_name: str,
        state: Optional[Dict],
        model: str,
    ) -> Generator[tuple, None, Dict[str, Any]]:
        """
        Streaming branch: litellm.completion(stream=True), yield (kind, text)
        with kind "reasoning" or "content". first_chunk_at on first non-empty
        chunk, usage from last chunk, then _save_usage_to_db.
        Returns usage as generator return value (StopIteration.value).
        """
        first_chunk_at: Optional[datetime] = None
        last_chunk = None
        streamed_content_len = 0
        streamed_content = ""
        logged_unknown_shape = False

        def _extract_text(value: Any) -> str:
            """
            Central place to adapt provider-specific stream chunk formats.
            When new providers or SDKs return different structures, extend
            only here so the upstream (kind, text) contract stays unchanged.
            Extracts user-visible text from LiteLLM stream delta fields.

            Recommended LiteLLM streaming format (OpenAI ChatCompletions):
            https://docs.litellm.ai/docs/

            In the standard contract, text is streamed via:
            - chunk.choices[0].delta.content (str)
            - optionally chunk.choices[0].delta.reasoning_content (str)

            Everything else should be treated as a non-standard shape. We
            keep a minimal best-effort fallback for safety, but the primary
            path must follow the documented OpenAI-compatible structure.

            Different providers/deployments may return:
            - str
            - list of parts (dict/object) with text-like fields
            - other objects that stringify to something non-useful
            """
            if value is None:
                return ""
            if isinstance(value, dict):
                text = (
                    value.get("text")
                    or value.get("content")
                    or value.get("value")
                )
                return text if isinstance(text, str) else ""
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                parts: list[str] = []
                for part in value:
                    if part is None:
                        continue
                    if isinstance(part, str):
                        parts.append(part)
                        continue
                    if isinstance(part, dict):
                        text = (
                            part.get("text")
                            or part.get("content")
                            or part.get("value")
                        )
                        if isinstance(text, str) and text:
                            parts.append(text)
                        continue
                    text = (
                        getattr(part, "text", None)
                        or getattr(part, "content", None)
                        or getattr(part, "value", None)
                    )
                    if isinstance(text, str) and text:
                        parts.append(text)
                return "".join(parts)
            text = (
                getattr(value, "text", None)
                or getattr(value, "content", None)
                or getattr(value, "value", None)
            )
            if isinstance(text, str):
                return text
            return ""

        def _read_chunk_field(obj: Any, key: str) -> Any:
            """Read field from object-like or dict-like chunk parts."""
            if obj is None:
                return None
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        def _build_usage_and_save(
            _usage: Dict[str, Any],
            _last_chunk: Any,
            _streamed_content: str,
            _first_chunk_at: Optional[datetime],
            success: bool = True,
            error: Optional[str] = None,
        ) -> None:
            usage_in = fill_usage_with_token_fallback(
                _usage,
                model,
                messages=params.get("messages"),
                streamed_content=_streamed_content or None,
            )
            cost = usage_in.get("cost")
            cost_currency = usage_in.get(
                "cost_currency", DEFAULT_COST_CURRENCY
            )
            if cost is not None:
                try:
                    cost = Decimal(str(cost))
                except (TypeError, ValueError):
                    cost = None
            if state is not None and success:
                state.setdefault("llm_calls", []).append({
                    "node": effective_state.get("node_name", "unknown"),
                    "model": usage_in["model"],
                    "prompt_tokens": usage_in["prompt_tokens"],
                    "completion_tokens": usage_in["completion_tokens"],
                    "total_tokens": usage_in["total_tokens"],
                    "cached_tokens": usage_in["cached_tokens"],
                    "reasoning_tokens": usage_in["reasoning_tokens"],
                    "cost": usage_in.get("cost"),
                    "cost_currency": usage_in.get("cost_currency"),
                    "success": True,
                    "error": None,
                })
            response_model_raw = (
                getattr(_last_chunk, "model", None) if _last_chunk else None
            )
            LLMTracker._save_usage_to_db(
                state=effective_state,
                model=model,
                prompt_tokens=usage_in["prompt_tokens"],
                completion_tokens=usage_in["completion_tokens"],
                total_tokens=usage_in["total_tokens"],
                cached_tokens=usage_in["cached_tokens"],
                reasoning_tokens=usage_in["reasoning_tokens"],
                cost=cost,
                cost_currency=cost_currency,
                success=success,
                error=error,
                started_at=request_started_at,
                is_streaming=True,
                first_chunk_at=_first_chunk_at,
                response_model=response_model_raw,
            )

        def _handle_stream_stop() -> None:
            """
            Handle GeneratorExit when client stops consuming the stream.
            """
            usage_partial = (
                usage_from_stream_chunk(last_chunk, model)
                if last_chunk
                else _default_usage_dict(model)
            )
            _build_usage_and_save(
                usage_partial,
                last_chunk,
                streamed_content,
                first_chunk_at,
                success=True,
                error=None,
            )
            logger.info(
                f"Stream stopped by client (stream) "
                f"node_name={node_name} model={model} "
                f"streamed_len={streamed_content_len}"
            )
            raise

        try:
            stream_params = {
                **params,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            stream_response = litellm.completion(**stream_params)
            for chunk in stream_response:
                last_chunk = chunk
                choices = getattr(chunk, "choices", None) or []
                choice = choices[0] if choices else None
                if not choice:
                    continue
                delta = _read_chunk_field(choice, "delta")
                if delta is None:
                    # Some OpenAI-compatible gateways stream under
                    # choices[].message instead of choices[].delta.
                    delta = _read_chunk_field(choice, "message")
                if delta is None:
                    if not logged_unknown_shape:
                        logger.warning(
                            f"LLM stream chunk missing choice.delta; "
                            f"expected OpenAI-compatible streaming format. "
                            f"model={model} choice_type={type(choice).__name__}"
                        )
                        logged_unknown_shape = True
                    continue
                reasoning_raw = (
                    _read_chunk_field(delta, "reasoning_content")
                    or _read_chunk_field(delta, "reasoning")
                )
                if reasoning_raw is not None:
                    text = _extract_text(reasoning_raw)
                    text = str(text).strip() if text else ""
                    if text:
                        streamed_content_len += len(text)
                        streamed_content += text
                        if first_chunk_at is None:
                            first_chunk_at = timezone.now()
                        try:
                            yield ("reasoning", text)
                        except GeneratorExit:
                            _handle_stream_stop()
                content = _read_chunk_field(delta, "content")
                if content is not None:
                    text = _extract_text(content)
                    text = str(text).strip() if text else ""
                    if text:
                        streamed_content_len += len(text)
                        streamed_content += text
                        if first_chunk_at is None:
                            first_chunk_at = timezone.now()
                        try:
                            yield ("content", text)
                        except GeneratorExit:
                            _handle_stream_stop()
                    elif isinstance(content, str):
                        # Some providers emit empty/whitespace string chunks.
                        # This is valid and should not be treated as shape
                        # mismatch.
                        continue
                    elif not logged_unknown_shape:
                        logger.warning(
                            f"LLM stream delta.content had unsupported type; "
                            f"expected str per LiteLLM docs. model={model} "
                            f"delta_type={type(delta).__name__} "
                            f"content_type={type(content).__name__}"
                        )
                        logged_unknown_shape = True
            usage = (
                usage_from_stream_chunk(last_chunk, model)
                if last_chunk
                else _default_usage_dict(model)
            )
            usage = fill_usage_with_token_fallback(
                usage,
                model,
                messages=params.get("messages"),
                streamed_content=streamed_content or None,
            )
            _build_usage_and_save(
                usage,
                last_chunk,
                streamed_content,
                first_chunk_at,
                success=True,
                error=None,
            )
            logger.info(
                f"Finished {TASK_LLM_CALL} (stream) node_name={node_name} "
                f"model={usage['model']} "
                f"total_tokens={usage.get('total_tokens')}"
            )
            return usage
        except GeneratorExit:
            raise
        except AuthenticationError as e:
            node = effective_state.get("node_name", "unknown")
            logger.error(
                f"Failed {TASK_LLM_CALL} (stream, authentication) "
                f"node_name={node} error={e}"
            )
            logger.exception(e)
            _record_failed_llm_call(
                effective_state=effective_state,
                state=state,
                request_started_at=request_started_at,
                node_name=node,
                is_streaming=True,
                error_msg=str(e),
            )
            raise
        except RateLimitError as e:
            node = effective_state.get("node_name", "unknown")
            logger.warning(
                f"Failed {TASK_LLM_CALL} (stream, rate limit) "
                f"node_name={node} error={e}"
            )
            logger.exception(e)
            _record_failed_llm_call(
                effective_state=effective_state,
                state=state,
                request_started_at=request_started_at,
                node_name=node,
                is_streaming=True,
                error_msg=str(e),
            )
            raise
        except APIError as e:
            node = effective_state.get("node_name", "unknown")
            logger.error(
                f"Failed {TASK_LLM_CALL} (stream, API error) "
                f"node_name={node} error={e}"
            )
            logger.exception(e)
            _record_failed_llm_call(
                effective_state=effective_state,
                state=state,
                request_started_at=request_started_at,
                node_name=node,
                is_streaming=True,
                error_msg=str(e),
            )
            raise
        except Exception as e:
            node = effective_state.get("node_name", "unknown")
            logger.error(
                f"Failed {TASK_LLM_CALL} (stream) node_name={node} "
                f"error_type={type(e).__name__} error={e}"
            )
            logger.exception(e)
            _record_failed_llm_call(
                effective_state=effective_state,
                state=state,
                request_started_at=request_started_at,
                node_name=node,
                is_streaming=True,
                error_msg=str(e),
            )
            raise
