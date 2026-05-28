"""
API tests for admin token-stats and llm-usage endpoints.

Base path: /api/v1/admin/ (as in tests/urls.py).
"""
import pytest


@pytest.mark.api
@pytest.mark.django_db
class TestAdminTokenStatsAPI:
    """
    GET token-stats/ requires admin; returns summary, by_model, series.
    """

    def test_unauthenticated_returns_401_or_403(self, api_client):
        response = api_client.get("/api/v1/admin/token-stats/")
        assert response.status_code in (401, 403)

    def test_authenticated_non_staff_returns_403(self, authenticated_client):
        response = authenticated_client.get("/api/v1/admin/token-stats/")
        assert response.status_code == 403

    def test_admin_returns_200_with_summary_and_by_model(self, admin_client):
        response = admin_client.get("/api/v1/admin/token-stats/")
        assert response.status_code == 200
        body = response.json()
        assert "summary" in body
        assert "by_model" in body
        assert body["summary"]["total_calls"] == 0
        assert body["summary"]["total_tokens"] == 0
        assert body["by_model"] == []

    def test_admin_returns_400_for_invalid_granularity(self, admin_client):
        response = admin_client.get(
            "/api/v1/admin/token-stats/",
            {"granularity": "invalid"},
        )
        assert response.status_code == 400
        body = response.json()
        assert "detail" in body
        assert "Unsupported granularity" in body["detail"]


@pytest.mark.api
@pytest.mark.django_db
class TestAdminLLMUsageListAPI:
    """
    GET /api/v1/admin/llm-usage/ requires admin and returns paginated list.
    """

    def test_unauthenticated_returns_401_or_403(self, api_client):
        response = api_client.get("/api/v1/admin/llm-usage/")
        assert response.status_code in (401, 403)

    def test_authenticated_non_staff_returns_403(self, authenticated_client):
        response = authenticated_client.get("/api/v1/admin/llm-usage/")
        assert response.status_code == 403

    def test_admin_returns_200_with_results_and_total(self, admin_client):
        response = admin_client.get("/api/v1/admin/llm-usage/")
        assert response.status_code == 200
        body = response.json()
        assert "results" in body
        assert "total" in body
        assert "page" in body
        assert "page_size" in body
        assert body["results"] == []
        assert body["total"] == 0

    def test_admin_accepts_query_params(self, admin_client):
        response = admin_client.get(
            "/api/v1/admin/llm-usage/",
            {"page": "1", "page_size": "10"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["page"] == 1
        assert body["page_size"] == 10

    def test_admin_invalid_page_falls_back_to_default(self, admin_client):
        response = admin_client.get(
            "/api/v1/admin/llm-usage/",
            {"page": "not-a-number"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["page"] == 1
        assert body["page_size"] == 20
