"""
Tests for get_litellm_params: config validation and ValueError paths.

Config is read from DB only; tests create a global LLMConfig so that
validation (e.g. missing api_key) is exercised.
"""
import pytest

from agentcore_metering.adapters.django.models import LLMConfig
from agentcore_metering.adapters.django.services import get_litellm_params


@pytest.mark.unit
@pytest.mark.django_db
class TestGetLlmServiceOpenAI:
    def test_missing_api_key_raises_value_error(self):
        LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            user=None,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={},
            is_active=True,
        )
        with pytest.raises(ValueError) as exc_info:
            get_litellm_params()
        assert "OpenAI" in str(exc_info.value)
        err = str(exc_info.value).lower()
        assert "incomplete" in err or "api" in err


@pytest.mark.unit
@pytest.mark.django_db
class TestGetLlmServiceAzureOpenAI:
    def test_empty_config_raises_value_error(self):
        LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            user=None,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="azure_openai",
            config={},
            is_active=True,
        )
        with pytest.raises(ValueError) as exc_info:
            get_litellm_params()
        assert "Azure" in str(exc_info.value)

    def test_missing_api_base_raises_value_error(self):
        LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            user=None,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="azure_openai",
            config={"api_key": "key", "api_base": ""},
            is_active=True,
        )
        with pytest.raises(ValueError) as exc_info:
            get_litellm_params()
        assert "Azure" in str(exc_info.value)

    def test_missing_api_key_raises_value_error(self):
        LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            user=None,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="azure_openai",
            config={"api_key": "", "api_base": "https://example.com"},
            is_active=True,
        )
        with pytest.raises(ValueError) as exc_info:
            get_litellm_params()
        assert "Azure" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.django_db
class TestGetLlmServiceGemini:
    def test_missing_api_key_raises_value_error(self):
        LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            user=None,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="gemini",
            config={},
            is_active=True,
        )
        with pytest.raises(ValueError) as exc_info:
            get_litellm_params()
        assert "Gemini" in str(exc_info.value)
        assert "incomplete" in str(exc_info.value).lower()
