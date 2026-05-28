"""
Tests for trackers.llm.LLMTracker (LiteLLM): call_and_track exception paths.
"""
from datetime import datetime
from types import SimpleNamespace
import pytest
from unittest.mock import MagicMock, patch

from agentcore_metering.adapters.django import LLMTracker


@pytest.mark.unit
class TestCallAndTrackValidation:
    """
    call_and_track raises ValueError for invalid input before calling LLM.
    """

    def test_empty_messages_raises_value_error(self):
        with pytest.raises(ValueError) as exc_info:
            LLMTracker.call_and_track(messages=[])
        err = str(exc_info.value).lower()
        assert "cannot be empty" in err or "empty" in err

    def test_none_messages_raises_value_error(self):
        with pytest.raises(ValueError):
            LLMTracker.call_and_track(messages=[])


@pytest.mark.unit
class TestCallAndTrackServiceReturnsNone:
    """
    When litellm.completion returns None, call_and_track raises ValueError.
    """

    @patch(
        "agentcore_metering.adapters.django.trackers.llm.litellm"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.get_litellm_params"
    )
    def test_completion_returns_none_raises_value_error(
        self, mock_params, mock_litellm
    ):
        mock_params.return_value = {
            "model": "gpt-4", "api_key": "sk-x", "messages": []
        }
        mock_litellm.completion.return_value = None

        with pytest.raises(ValueError) as exc_info:
            LLMTracker.call_and_track(
                messages=[{"role": "user", "content": "hi"}]
            )
        assert "None" in str(exc_info.value)


@pytest.mark.unit
class TestCallAndTrackEmptyResponse:
    """
    When LiteLLM returns empty response, call_and_track raises ValueError.
    """

    @patch(
        "agentcore_metering.adapters.django.trackers.llm.litellm"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.get_litellm_params"
    )
    def test_empty_response_content_raises_value_error(
        self, mock_params, mock_litellm
    ):
        mock_params.return_value = {"model": "gpt-4", "api_key": "sk-x"}
        msg = MagicMock()
        msg.content = ""
        choice = MagicMock()
        choice.message = msg
        mock_litellm.completion.return_value = MagicMock(
            choices=[choice],
            usage=MagicMock(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            ),
            model="gpt-4",
        )

        with pytest.raises(ValueError) as exc_info:
            LLMTracker.call_and_track(
                messages=[{"role": "user", "content": "hi"}]
            )
        assert "empty" in str(exc_info.value).lower()


@pytest.mark.unit
class TestCallAndTrackUsageExtraction:
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.LLMTracker"
        "._save_usage_to_db"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.litellm"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.get_litellm_params"
    )
    def test_extracts_cached_and_reasoning_tokens_from_nested_usage_details(
        self, mock_params, mock_litellm, mock_save_usage
    ):
        mock_params.return_value = {"model": "gpt-4", "api_key": "sk-x"}
        usage = SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            cached_tokens=0,
            reasoning_tokens=0,
            prompt_tokens_details={"cached_tokens": 3},
            completion_tokens_details={"reasoning_tokens": 2},
        )
        message = SimpleNamespace(content="ok")
        choice = SimpleNamespace(message=message)
        mock_litellm.completion.return_value = SimpleNamespace(
            choices=[choice],
            usage=usage,
            model="gpt-4",
            _hidden_params={},
        )

        content, usage_dict = LLMTracker.call_and_track(
            messages=[{"role": "user", "content": "hi"}]
        )

        assert content == "ok"
        assert usage_dict["cached_tokens"] == 3
        assert usage_dict["reasoning_tokens"] == 2
        save_kwargs = mock_save_usage.call_args.kwargs
        assert save_kwargs["cached_tokens"] == 3
        assert save_kwargs["reasoning_tokens"] == 2

    @patch(
        "agentcore_metering.adapters.django.trackers.llm.LLMTracker"
        "._save_usage_to_db"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.litellm"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.get_litellm_params"
    )
    def test_invalid_hidden_response_cost_does_not_break_call(
        self, mock_params, mock_litellm, mock_save_usage
    ):
        mock_params.return_value = {"model": "gpt-4", "api_key": "sk-x"}
        usage = SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        message = SimpleNamespace(content="ok")
        choice = SimpleNamespace(message=message)
        mock_litellm.completion.return_value = SimpleNamespace(
            choices=[choice],
            usage=usage,
            model="gpt-4",
            _hidden_params={"response_cost": "not-a-number"},
        )

        content, usage_dict = LLMTracker.call_and_track(
            messages=[{"role": "user", "content": "hi"}]
        )

        assert content == "ok"
        assert usage_dict["cost"] is None
        save_kwargs = mock_save_usage.call_args.kwargs
        assert save_kwargs["cost"] is None

    @patch(
        "agentcore_metering.adapters.django.trackers.llm.litellm"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.get_litellm_params"
    )
    def test_whitespace_only_response_raises_value_error(
        self, mock_params, mock_litellm
    ):
        mock_params.return_value = {"model": "gpt-4", "api_key": "sk-x"}
        msg = MagicMock()
        msg.content = "   \n  "
        choice = MagicMock()
        choice.message = msg
        mock_litellm.completion.return_value = MagicMock(
            choices=[choice],
            usage=MagicMock(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            ),
            model="gpt-4",
        )

        with pytest.raises(ValueError) as exc_info:
            LLMTracker.call_and_track(
                messages=[{"role": "user", "content": "hi"}]
            )
        assert "empty" in str(exc_info.value).lower()


@pytest.mark.unit
class TestCallAndTrackTokenFallback:
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.LLMTracker"
        "._save_usage_to_db"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.litellm"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.get_litellm_params"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm_usage.token_counter"
    )
    def test_sync_fallback_uses_token_counter_when_usage_is_zero(
        self, mock_token_counter, mock_params, mock_litellm, mock_save_usage
    ):
        def _side_effect(
            *,
            model,
            custom_tokenizer=None,
            text=None,
            messages=None,
            **_kwargs,
        ):
            if messages is not None:
                return 5
            if text is not None:
                return 7
            return 0

        mock_token_counter.side_effect = _side_effect
        mock_params.return_value = {"model": "gpt-4", "api_key": "sk-x"}
        usage = SimpleNamespace(
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        )
        message = SimpleNamespace(content="hello")
        choice = SimpleNamespace(message=message)
        mock_litellm.completion.return_value = SimpleNamespace(
            choices=[choice],
            usage=usage,
            model="gpt-4",
            _hidden_params={},
        )

        content, usage_dict = LLMTracker.call_and_track(
            messages=[{"role": "user", "content": "hi"}]
        )

        assert content == "hello"
        assert usage_dict["prompt_tokens"] == 5
        assert usage_dict["completion_tokens"] == 7
        assert usage_dict["total_tokens"] == 12
        save_kwargs = mock_save_usage.call_args.kwargs
        assert save_kwargs["prompt_tokens"] == 5
        assert save_kwargs["completion_tokens"] == 7
        assert save_kwargs["total_tokens"] == 12

    @patch(
        "agentcore_metering.adapters.django.trackers.llm.LLMTracker"
        "._save_usage_to_db"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.litellm"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.get_litellm_params"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm_usage.token_counter"
    )
    def test_sync_fallback_guards_min_completion_token_when_token_counter_fails(
        self,
        mock_token_counter,
        mock_params,
        mock_litellm,
        mock_save_usage,
    ):
        def _side_effect(
            *,
            model,
            custom_tokenizer=None,
            text=None,
            messages=None,
            **_kwargs,
        ):
            raise RuntimeError("boom")

        mock_token_counter.side_effect = _side_effect
        mock_params.return_value = {"model": "gpt-4", "api_key": "sk-x"}
        usage = SimpleNamespace(
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        )
        message = SimpleNamespace(content="hello")
        choice = SimpleNamespace(message=message)
        mock_litellm.completion.return_value = SimpleNamespace(
            choices=[choice],
            usage=usage,
            model="gpt-4",
            _hidden_params={},
        )

        _content, usage_dict = LLMTracker.call_and_track(
            messages=[{"role": "user", "content": "hi"}]
        )

        assert usage_dict["completion_tokens"] == 1
        assert usage_dict["total_tokens"] == 1


@pytest.mark.unit
class TestCallAndTrackJsonRepairRetry:
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.time.sleep"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.timezone.now"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.LLMTracker"
        "._save_usage_to_db"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.litellm"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.get_litellm_params"
    )
    def test_json_mode_retries_and_succeeds(
        self,
        mock_params,
        mock_litellm,
        mock_save_usage,
        mock_now,
        mock_sleep,
    ):
        mock_params.return_value = {"model": "gpt-4", "api_key": "sk-x"}
        mock_now.side_effect = [
            datetime(2026, 3, 17, 10, 0, 0),
            datetime(2026, 3, 17, 10, 0, 1),
        ]

        usage = SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        choice_bad = SimpleNamespace(message=SimpleNamespace(content=":"))
        choice_ok = SimpleNamespace(
            message=SimpleNamespace(content='{"cleaned_content":"ok"}')
        )
        response_bad = SimpleNamespace(
            choices=[choice_bad],
            usage=usage,
            model="gpt-4",
            _hidden_params={},
        )
        response_ok = SimpleNamespace(
            choices=[choice_ok],
            usage=usage,
            model="gpt-4",
            _hidden_params={},
        )
        mock_litellm.completion.side_effect = [response_bad, response_ok]

        content, _usage = LLMTracker.call_and_track(
            messages=[{"role": "user", "content": "hi"}],
            json_mode=True,
        )

        assert '"cleaned_content"' in content
        assert mock_litellm.completion.call_count == 2
        assert mock_save_usage.call_count == 2
        mock_sleep.assert_called_once_with(0.5)
        first_started_at = mock_save_usage.call_args_list[0].kwargs[
            "started_at"
        ]
        second_started_at = mock_save_usage.call_args_list[1].kwargs[
            "started_at"
        ]
        assert first_started_at != second_started_at

    @patch(
        "agentcore_metering.adapters.django.trackers.llm.time.sleep"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.LLMTracker"
        "._save_usage_to_db"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.litellm"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.get_litellm_params"
    )
    def test_json_mode_raises_after_retry_exhausted(
        self,
        mock_params,
        mock_litellm,
        mock_save_usage,
        mock_sleep,
    ):
        mock_params.return_value = {"model": "gpt-4", "api_key": "sk-x"}
        usage = SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        choice_bad = SimpleNamespace(message=SimpleNamespace(content=":"))
        response_bad = SimpleNamespace(
            choices=[choice_bad],
            usage=usage,
            model="gpt-4",
            _hidden_params={},
        )
        mock_litellm.completion.side_effect = [
            response_bad,
            response_bad,
            response_bad,
        ]

        with pytest.raises(ValueError) as exc_info:
            LLMTracker.call_and_track(
                messages=[{"role": "user", "content": "hi"}],
                json_mode=True,
            )
        assert "Invalid JSON response after 3 attempts" in str(exc_info.value)
        assert mock_litellm.completion.call_count == 3
        assert mock_save_usage.call_count == 3
        assert mock_sleep.call_count == 2


@pytest.mark.unit
class TestCallAndTrackStreaming:
    """
    call_and_track(stream=True) yields chunks and calls _save_usage_to_db with
    is_streaming=True and first_chunk_at when first non-empty content arrives.
    """

    @patch(
        "agentcore_metering.adapters.django.trackers.llm.LLMTracker"
        "._save_usage_to_db"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.litellm"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.get_litellm_params"
    )
    def test_stream_true_yields_chunks_and_saves_with_is_streaming(
        self, mock_params, mock_litellm, mock_save_usage
    ):
        mock_params.return_value = {"model": "gpt-4", "api_key": "sk-x"}
        delta1 = SimpleNamespace(content="Hello")
        delta2 = SimpleNamespace(content=" world")
        choice1 = SimpleNamespace(delta=delta1)
        choice2 = SimpleNamespace(delta=delta2)
        usage_ns = SimpleNamespace(
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=3,
        )
        chunk1 = SimpleNamespace(choices=[choice1], usage=None, model="gpt-4")
        chunk2 = SimpleNamespace(
            choices=[choice2], usage=usage_ns, model="gpt-4"
        )
        mock_litellm.completion.return_value = iter([chunk1, chunk2])

        gen = LLMTracker.call_and_track(
            messages=[{"role": "user", "content": "hi"}],
            stream=True,
        )
        chunks = []
        try:
            while True:
                chunks.append(next(gen))
        except StopIteration as e:
            usage_return = e.value
        assert chunks == [("content", "Hello"), ("content", "world")]
        assert usage_return is not None
        assert usage_return.get("model") == "gpt-4"
        assert mock_save_usage.called
        save_kwargs = mock_save_usage.call_args.kwargs
        assert save_kwargs["is_streaming"] is True
        assert save_kwargs.get("first_chunk_at") is not None

    @patch(
        "agentcore_metering.adapters.django.trackers.llm.LLMTracker"
        "._save_usage_to_db"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.litellm"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm.get_litellm_params"
    )
    @patch(
        "agentcore_metering.adapters.django.trackers.llm_usage.token_counter"
    )
    def test_stream_fallback_counts_tokens_from_streamed_content(
        self, mock_token_counter, mock_params, mock_litellm, mock_save_usage
    ):
        def _side_effect(
            *,
            model,
            custom_tokenizer=None,
            text=None,
            messages=None,
            **_kwargs,
        ):
            if messages is not None:
                return 3
            if text is not None:
                return 8
            return 0

        mock_token_counter.side_effect = _side_effect
        mock_params.return_value = {"model": "gpt-4", "api_key": "sk-x"}
        delta1 = SimpleNamespace(content="Hello")
        delta2 = SimpleNamespace(content=" world")
        choice1 = SimpleNamespace(delta=delta1)
        choice2 = SimpleNamespace(delta=delta2)
        chunk1 = SimpleNamespace(choices=[choice1], usage=None, model="gpt-4")
        chunk2 = SimpleNamespace(choices=[choice2], usage=None, model="gpt-4")
        mock_litellm.completion.return_value = iter([chunk1, chunk2])

        gen = LLMTracker.call_and_track(
            messages=[{"role": "user", "content": "hi"}],
            stream=True,
        )
        try:
            while True:
                next(gen)
        except StopIteration as e:
            usage_return = e.value

        assert usage_return["prompt_tokens"] == 3
        assert usage_return["completion_tokens"] == 8
        assert usage_return["total_tokens"] == 11
        save_kwargs = mock_save_usage.call_args.kwargs
        assert save_kwargs["prompt_tokens"] == 3
        assert save_kwargs["completion_tokens"] == 8
        assert save_kwargs["total_tokens"] == 11
