"""
API tests for LLM config: global and per-user GET/PUT/DELETE.
"""
import pytest

from agentcore_metering.adapters.django.models import LLMConfig


@pytest.mark.api
@pytest.mark.django_db
class TestAdminLLMConfigGlobal:
    """
    GET list / POST create for /api/v1/admin/llm-config/ (global configs).
    """

    def test_global_config_requires_admin(self, api_client):
        response = api_client.get("/api/v1/admin/llm-config/")
        assert response.status_code in (401, 403)
        response = api_client.post(
            "/api/v1/admin/llm-config/",
            {"provider": "openai", "config": {}},
            format="json",
        )
        assert response.status_code in (401, 403)

    def test_get_global_returns_empty_list_when_no_configs(self, admin_client):
        response = admin_client.get("/api/v1/admin/llm-config/")
        assert response.status_code == 200
        assert response.json() == []

    def test_post_global_creates_config(self, admin_client):
        response = admin_client.post(
            "/api/v1/admin/llm-config/",
            {
                "provider": "openai",
                "config": {"api_key": "sk-test", "model": "gpt-4"},
            },
            format="json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["scope"] == "global"
        assert body["provider"] == "openai"
        assert body["user"] is None
        assert "config" in body
        assert body["config"].get("model") == "gpt-4"
        assert "api_key" in body["config"]
        assert "***" in body["config"]["api_key"]

    def test_get_global_after_post_returns_list_with_config(
        self, admin_client
    ):
        admin_client.post(
            "/api/v1/admin/llm-config/",
            {
                "provider": "openai",
                "config": {"api_key": "sk-x", "model": "gpt-4"},
            },
            format="json",
        )
        response = admin_client.get("/api/v1/admin/llm-config/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["provider"] == "openai"

    def test_put_global_updates_existing(self, admin_client):
        create_resp = admin_client.post(
            "/api/v1/admin/llm-config/",
            {
                "provider": "openai",
                "config": {"api_key": "sk-a", "model": "gpt-4"},
            },
            format="json",
        )
        assert create_resp.status_code == 201
        config_uuid = create_resp.json()["uuid"]
        response = admin_client.put(
            f"/api/v1/admin/llm-config/{config_uuid}/",
            {
                "provider": "openai",
                "config": {"api_key": "sk-b", "model": "gpt-3.5"},
            },
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["config"]["model"] == "gpt-3.5"
        assert (
            LLMConfig.objects.filter(
                scope=LLMConfig.Scope.GLOBAL
            ).count() == 1
        )


    def test_put_global_preserves_masked_api_key_when_setting_default(
        self, admin_client
    ):
        create_resp = admin_client.post(
            "/api/v1/admin/llm-config/",
            {
                "provider": "openai",
                "config": {
                    "api_key": "sk-test-secret-1234",
                    "model": "gpt-4o-mini",
                },
            },
            format="json",
        )
        assert create_resp.status_code == 201
        config_uuid = create_resp.json()["uuid"]

        detail_resp = admin_client.get(
            f"/api/v1/admin/llm-config/{config_uuid}/"
        )
        assert detail_resp.status_code == 200
        detail_body = detail_resp.json()
        assert detail_body["config"]["api_key"] != "sk-test-secret-1234"

        update_resp = admin_client.put(
            f"/api/v1/admin/llm-config/{config_uuid}/",
            {
                "provider": detail_body["provider"],
                "config": detail_body["config"],
                "is_active": detail_body["is_active"],
                "is_default": True,
            },
            format="json",
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["is_default"] is True

        cfg = LLMConfig.objects.get(uuid=config_uuid)
        assert cfg.is_default is True
        assert cfg.config["api_key"] == "sk-test-secret-1234"
        assert cfg.config["model"] == "gpt-4o-mini"


@pytest.mark.api
@pytest.mark.django_db
class TestAdminLLMConfigUser:
    """
    GET list, GET/PUT/DELETE /api/v1/admin/llm-config/users/<user_id>/.
    """

    def test_get_user_config_returns_404_when_empty(
        self, admin_client, normal_user
    ):
        response = admin_client.get(
            f"/api/v1/admin/llm-config/users/{normal_user.pk}/"
        )
        assert response.status_code == 404

    def test_put_user_creates_config(self, admin_client, normal_user):
        response = admin_client.put(
            f"/api/v1/admin/llm-config/users/{normal_user.pk}/",
            {
                "provider": "openai",
                "config": {"api_key": "sk-user", "model": "gpt-4"},
            },
            format="json",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["scope"] == "user"
        assert body["user_id"] == normal_user.pk
        assert body["provider"] == "openai"

    def test_duplicate_user_configs_return_conflict(
        self, admin_client, normal_user
    ):
        LLMConfig.objects.create(
            scope=LLMConfig.Scope.USER,
            user=normal_user,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"api_key": "sk-one", "model": "gpt-4"},
            is_active=True,
        )
        LLMConfig.objects.create(
            scope=LLMConfig.Scope.USER,
            user=normal_user,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider="openai",
            config={"api_key": "sk-two", "model": "gpt-4"},
            is_active=True,
        )

        get_response = admin_client.get(
            f"/api/v1/admin/llm-config/users/{normal_user.pk}/"
        )
        assert get_response.status_code == 409

        put_response = admin_client.put(
            f"/api/v1/admin/llm-config/users/{normal_user.pk}/",
            {
                "provider": "openai",
                "config": {"api_key": "sk-new", "model": "gpt-4"},
            },
            format="json",
        )
        assert put_response.status_code == 409

    def test_get_user_config_after_put(self, admin_client, normal_user):
        admin_client.put(
            f"/api/v1/admin/llm-config/users/{normal_user.pk}/",
            {
                "provider": "openai",
                "config": {"api_key": "sk-x", "model": "gpt-4"},
            },
            format="json",
        )
        response = admin_client.get(
            f"/api/v1/admin/llm-config/users/{normal_user.pk}/"
        )
        assert response.status_code == 200
        assert response.json()["user_id"] == normal_user.pk

    def test_delete_user_config_returns_204(self, admin_client, normal_user):
        admin_client.put(
            f"/api/v1/admin/llm-config/users/{normal_user.pk}/",
            {"provider": "openai", "config": {"api_key": "sk-x"}},
            format="json",
        )
        response = admin_client.delete(
            f"/api/v1/admin/llm-config/users/{normal_user.pk}/"
        )
        assert response.status_code == 204
        response2 = admin_client.get(
            f"/api/v1/admin/llm-config/users/{normal_user.pk}/"
        )
        assert response2.status_code == 404

    def test_get_user_config_404_for_unknown_user(self, admin_client):
        response = admin_client.get("/api/v1/admin/llm-config/users/999999/")
        assert response.status_code == 404

    def test_list_user_configs_empty(self, admin_client):
        response = admin_client.get("/api/v1/admin/llm-config/users/")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_user_configs_returns_created(
        self, admin_client, normal_user
    ):
        admin_client.put(
            f"/api/v1/admin/llm-config/users/{normal_user.pk}/",
            {"provider": "openai", "config": {"api_key": "sk-x"}},
            format="json",
        )
        response = admin_client.get("/api/v1/admin/llm-config/users/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["user_id"] == normal_user.pk
