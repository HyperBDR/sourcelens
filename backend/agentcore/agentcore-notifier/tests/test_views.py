"""Tests for stats and config API views."""
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient



@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="admin",
        email="admin@test.com",
        password="adminpass",
    )


@pytest.fixture
def api_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.mark.django_db
class TestNotificationStatsView:
    """Test GET notification-stats/."""

    def test_get_stats_returns_summary(self, api_client):
        response = api_client.get("/notification-stats/")
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "total" in data["summary"]
        assert "by_source" in data
        assert "by_provider" in data

    def test_unauthorized_returns_403(self, client):
        response = client.get("/notification-stats/")
        assert response.status_code == 403


