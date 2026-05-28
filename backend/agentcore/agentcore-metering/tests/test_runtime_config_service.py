import logging
from types import SimpleNamespace

import pytest
from django.test import override_settings

from agentcore_metering.adapters.django.models import LLMConfig, LLMUsage
from agentcore_metering.adapters.django.services import runtime_config as rc


def _mock_completion_response(
    content="ok",
    model="openai/gpt-4o-mini",
    prompt_tokens=11,
    completion_tokens=7,
    total_tokens=18,
    cached_tokens=2,
    reasoning_tokens=1,
):
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
    )
    return SimpleNamespace(choices=[choice], usage=usage, model=model)


@pytest.mark.unit
@pytest.mark.django_db
class TestRuntimeConfigService:
    def test_get_litellm_params_prefers_user_scope_over_global_and_settings(
        self, django_user_model
    ):
        user = django_user_model.objects.create_user(
            username="u1",
            email="u1@example.com",
            password="pass",
        )
        LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            user=None,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"api_key": "global-key", "model": "gpt-4o-mini"},
            is_active=True,
        )
        LLMConfig.objects.create(
            scope=LLMConfig.Scope.USER,
            user=user,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"api_key": "user-key", "model": "gpt-4o-mini"},
            is_active=True,
        )

        with override_settings(
            LLM_PROVIDER="openai",
            OPENAI_CONFIG={"api_key": "settings-key", "model": "gpt-4o-mini"},
        ):
            params = rc.get_litellm_params(user_id=user.id)

        assert params["api_key"] == "user-key"
        assert params["model"] == "openai/gpt-4o-mini"

    def test_get_litellm_params_uses_global_when_user_scope_missing(self):
        LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            user=None,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"api_key": "global-key", "model": "gpt-4o-mini"},
            is_active=True,
        )

        params = rc.get_litellm_params(user_id=99999)

        assert params["api_key"] == "global-key"
        assert params["model"] == "openai/gpt-4o-mini"

    def test_get_litellm_params_without_user_id_ignores_user_configs(
        self, django_user_model
    ):
        user = django_user_model.objects.create_user(
            username="u_missing",
            email="u_missing@example.com",
            password="pass",
        )
        LLMConfig.objects.create(
            scope=LLMConfig.Scope.USER,
            user=user,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"api_key": "user-key", "model": "gpt-4o-mini"},
            is_active=True,
        )
        LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            user=None,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"api_key": "global-key", "model": "gpt-4o-mini"},
            is_active=True,
        )

        params = rc.get_litellm_params()

        assert params["api_key"] == "global-key"
        assert params["model"] == "openai/gpt-4o-mini"

    def test_get_litellm_params_with_model_uuid_uses_that_config(
        self, django_user_model
    ):
        user = django_user_model.objects.create_user(
            username="u_uuid",
            email="u_uuid@example.com",
            password="pass",
        )
        cfg_global = LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            user=None,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"api_key": "global-key", "model": "gpt-4o-mini"},
            is_active=True,
        )
        cfg_user = LLMConfig.objects.create(
            scope=LLMConfig.Scope.USER,
            user=user,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"api_key": "user-key", "model": "gpt-4o-mini"},
            is_active=True,
        )

        params_by_uuid = rc.get_litellm_params(
            user_id=user.id, model_uuid=str(cfg_global.uuid)
        )
        assert params_by_uuid["api_key"] == "global-key"

        params_user_uuid = rc.get_litellm_params(
            user_id=user.id, model_uuid=str(cfg_user.uuid)
        )
        assert params_user_uuid["api_key"] == "user-key"

    def test_get_litellm_params_invalid_model_uuid_raises_no_fallback(self):
        with pytest.raises(ValueError) as exc_info:
            rc.get_litellm_params(
                model_uuid="00000000-0000-0000-0000-000000000000",
            )
        msg = str(exc_info.value)
        assert "model_uuid" in msg or "not found" in msg.lower()

    def test_get_litellm_params_no_db_config_raises(self):
        with pytest.raises(ValueError) as exc_info:
            rc.get_litellm_params()
        msg = str(exc_info.value)
        assert "No LLM config" in msg or "admin" in msg.lower()

    def test_build_litellm_params_preserves_explicit_zero_values(self):
        params = rc.build_litellm_params_from_config(
            "openai",
            {
                "api_key": "k",
                "model": "gpt-4o-mini",
                "temperature": 0,
                "top_p": 0,
                "max_tokens": 0,
            },
        )

        assert params["temperature"] == 0
        assert params["top_p"] == 0
        assert params["max_tokens"] == 0

    def test_build_litellm_params_moonshot_uses_raw_model_id(self):
        params = rc.build_litellm_params_from_config(
            "moonshot",
            {
                "api_key": "k",
                "model": "kimi-k2.5",
            },
        )

        assert params["model"] == "moonshot/kimi-k2.5"

    def test_build_litellm_params_moonshot_strips_legacy_prefix(self):
        params = rc.build_litellm_params_from_config(
            "moonshot",
            {
                "api_key": "k",
                "model": "moonshot/kimi-k2.5",
            },
        )

        assert params["model"] == "moonshot/kimi-k2.5"

    def test_build_litellm_params_moonshot_uses_yaml_temperature_default(
        self,
    ):
        params = rc.build_litellm_params_from_config(
            "moonshot",
            {
                "api_key": "k",
                "model": "kimi-k2.5",
            },
        )

        assert params["temperature"] == 1

    def test_build_litellm_params_moonshot_uses_yaml_top_p_default(self):
        params = rc.build_litellm_params_from_config(
            "moonshot",
            {
                "api_key": "k",
                "model": "kimi-k2.5",
            },
        )

        assert params["top_p"] == 0.95

    def test_build_litellm_params_openai_prefixes_plain_model(self):
        params = rc.build_litellm_params_from_config(
            "openai",
            {
                "api_key": "k",
                "model": "133357084870905856",
            },
        )

        assert params["model"] == "openai/133357084870905856"

    def test_build_litellm_params_openai_keeps_prefixed_model(self):
        params = rc.build_litellm_params_from_config(
            "openai",
            {
                "api_key": "k",
                "model": "openai/gpt-4o-mini",
            },
        )

        assert params["model"] == "openai/gpt-4o-mini"

    def test_build_litellm_params_openai_compatible_keeps_raw_model(self):
        params = rc.build_litellm_params_from_config(
            "openai_compatible",
            {
                "api_key": "k",
                "api_base": "https://example.com/v1",
                "model": "133356111406325760",
            },
        )

        assert params["model"] == "133356111406325760"
        assert params["api_base"] == "https://example.com/v1"
        assert params["custom_llm_provider"] == "openai"

    def test_build_litellm_params_openai_compatible_requires_api_base(self):
        with pytest.raises(ValueError) as exc_info:
            rc.build_litellm_params_from_config(
                "openai_compatible",
                {
                    "api_key": "k",
                    "model": "133356111406325760",
                },
            )

        assert "api_base" in str(exc_info.value)

    def test_validate_llm_config_success_records_usage(
        self, django_user_model, monkeypatch
    ):
        user = django_user_model.objects.create_user(
            username="u2",
            email="u2@example.com",
            password="pass",
        )
        response = _mock_completion_response()
        monkeypatch.setattr(
            rc.litellm, "completion", lambda **kwargs: response
        )
        monkeypatch.setattr(
            rc,
            "completion_cost",
            lambda completion_response: 0.123,
        )

        ok, detail = rc.validate_llm_config(
            provider="openai",
            config={"api_key": "k", "model": "gpt-4o-mini"},
            user=user,
        )

        assert ok is True
        assert detail == ""
        usage = LLMUsage.objects.get(user=user)
        assert usage.model == "openai/gpt-4o-mini"
        assert usage.total_tokens == 18
        assert float(usage.cost) == 0.123

    def test_validate_llm_config_maps_exception_to_user_friendly_key(
        self, monkeypatch
    ):
        def _raise_auth_error(**kwargs):
            raise Exception("401 invalid_api_key")

        monkeypatch.setattr(rc.litellm, "completion", _raise_auth_error)

        ok, detail = rc.validate_llm_config(
            provider="openai",
            config={"api_key": "k", "model": "gpt-4o-mini"},
        )

        assert ok is False
        assert detail == "invalid_api_key"

    def test_run_test_call_returns_error_for_empty_prompt(
        self, django_user_model
    ):
        user = django_user_model.objects.create_user(
            username="u3",
            email="u3@example.com",
            password="pass",
        )

        ok, detail, usage = rc.run_test_call(
            config_uuid=None,
            config_id=1,
            prompt="  ",
            user=user,
        )

        assert ok is False
        assert detail == "Prompt cannot be empty"
        assert usage is None

    def test_run_test_call_success_returns_usage_and_saves_record(
        self, django_user_model, monkeypatch
    ):
        user = django_user_model.objects.create_user(
            username="u4",
            email="u4@example.com",
            password="pass",
        )
        cfg = LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            user=None,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"api_key": "k", "model": "gpt-4o-mini"},
            is_active=True,
        )
        response = _mock_completion_response(content="hello")
        monkeypatch.setattr(
            rc.litellm, "completion", lambda **kwargs: response
        )
        monkeypatch.setattr(
            "agentcore_metering.adapters.django.trackers.llm_usage."
            "completion_cost",
            lambda completion_response: 0.5,
        )

        ok, content, usage = rc.run_test_call(
            config_uuid=str(cfg.uuid),
            config_id=None,
            prompt="hello",
            user=user,
            max_tokens=10,
        )

        assert ok is True
        assert content == "hello"
        assert usage["total_tokens"] == 18
        assert usage["cost"] == 0.5
        assert LLMUsage.objects.filter(
            user=user,
            metadata__node_name="admin_test_call",
        ).exists()

    def test_run_test_call_extracts_nested_cached_and_reasoning_tokens(
        self, django_user_model, monkeypatch
    ):
        user = django_user_model.objects.create_user(
            username="u4b",
            email="u4b@example.com",
            password="pass",
        )
        cfg = LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            user=None,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"api_key": "k", "model": "gpt-4o-mini"},
            is_active=True,
        )
        message = SimpleNamespace(content="hello")
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(
            prompt_tokens=11,
            completion_tokens=7,
            total_tokens=18,
            cached_tokens=0,
            reasoning_tokens=0,
            prompt_tokens_details={"cached_tokens": 4},
            completion_tokens_details={"reasoning_tokens": 3},
        )
        response = SimpleNamespace(
            choices=[choice], usage=usage, model="openai/gpt-4o-mini"
        )
        monkeypatch.setattr(
            rc.litellm, "completion", lambda **kwargs: response
        )
        monkeypatch.setattr(
            "agentcore_metering.adapters.django.trackers.llm_usage."
            "completion_cost",
            lambda completion_response: 0.5,
        )

        ok, content, usage_dict = rc.run_test_call(
            config_uuid=str(cfg.uuid),
            config_id=None,
            prompt="hello",
            user=user,
            max_tokens=10,
        )

        assert ok is True
        assert content == "hello"
        assert usage_dict["cached_tokens"] == 4
        assert usage_dict["reasoning_tokens"] == 3
        record = LLMUsage.objects.get(
            user=user, metadata__node_name="admin_test_call"
        )
        assert record.cached_tokens == 4
        assert record.reasoning_tokens == 3

    def test_run_test_call_logs_request_and_response(
        self, django_user_model, monkeypatch, caplog
    ):
        user = django_user_model.objects.create_user(
            username="u5",
            email="u5@example.com",
            password="pass",
        )
        cfg = LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            user=None,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"api_key": "k", "model": "gpt-4o-mini"},
            is_active=True,
        )
        response = _mock_completion_response(content="hello")
        monkeypatch.setattr(
            rc.litellm, "completion", lambda **kwargs: response
        )
        monkeypatch.setattr(
            "agentcore_metering.adapters.django.trackers.llm_usage."
            "completion_cost",
            lambda completion_response: 0.5,
        )
        caplog.set_level(logging.INFO, logger=rc.logger.name)

        ok, content, _usage = rc.run_test_call(
            config_uuid=str(cfg.uuid),
            config_id=None,
            prompt="hello",
            user=user,
            max_tokens=10,
        )

        assert ok is True
        assert content == "hello"
        assert "Starting run_test_call" in caplog.text
        assert "Finished run_test_call" in caplog.text

    def test_run_test_call_returns_error_for_empty_content(
        self, django_user_model, monkeypatch
    ):
        user = django_user_model.objects.create_user(
            username="u6",
            email="u6@example.com",
            password="pass",
        )
        cfg = LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            user=None,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"api_key": "k", "model": "gpt-4o-mini"},
            is_active=True,
        )
        response = _mock_completion_response(content="")
        monkeypatch.setattr(
            rc.litellm, "completion", lambda **kwargs: response
        )

        ok, detail, usage = rc.run_test_call(
            config_uuid=str(cfg.uuid),
            config_id=None,
            prompt="hello",
            user=user,
            max_tokens=10,
        )

        assert ok is False
        assert detail == "LLM returned empty response"
        assert usage is None

    def test_run_test_call_logs_response_snapshot_for_empty_content(
        self, django_user_model, monkeypatch, caplog
    ):
        user = django_user_model.objects.create_user(
            username="u7",
            email="u7@example.com",
            password="pass",
        )
        cfg = LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            user=None,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"api_key": "k", "model": "gpt-4o-mini"},
            is_active=True,
        )
        message = SimpleNamespace(
            role="assistant",
            content="",
            tool_calls=[{"id": "call_1"}],
        )
        choice = SimpleNamespace(
            message=message,
            finish_reason="length",
        )
        usage = SimpleNamespace(
            prompt_tokens=9,
            completion_tokens=512,
            total_tokens=521,
            cached_tokens=0,
            reasoning_tokens=0,
        )
        response = SimpleNamespace(
            id="resp_test_001",
            choices=[choice],
            usage=usage,
            model="gpt-5-nano-2025-08-07",
        )
        monkeypatch.setattr(
            rc.litellm, "completion", lambda **kwargs: response
        )
        caplog.set_level(logging.WARNING, logger=rc.logger.name)

        ok, detail, call_usage = rc.run_test_call(
            config_uuid=str(cfg.uuid),
            config_id=None,
            prompt="hello",
            user=user,
            max_tokens=512,
        )

        assert ok is False
        assert detail == "LLM returned empty response"
        assert call_usage is None
