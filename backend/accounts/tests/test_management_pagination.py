import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient


User = get_user_model()


def _payload(response):
    body = response.json()
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


@pytest.mark.django_db
class TestManagementUsersPagination:
    def test_users_list_filters_by_exact_case_sensitive_username(self):
        admin = User.objects.create_user(
            username="admin_for_exact_username",
            password="x",
            is_staff=True,
        )
        matching_user = User.objects.create_user(
            username="hfl-u-123",
            password="x",
        )
        User.objects.create_user(username="hfl-u-1234", password="x")
        User.objects.create_user(username="HFL-U-123", password="x")

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get(
            "/api/v1/management/users/",
            {"username": "hfl-u-123"},
        )

        assert response.status_code == 200
        data = _payload(response)
        assert data["count"] == 1
        assert [user["id"] for user in data["results"]] == [matching_user.id]

    def test_users_list_returns_empty_page_for_unknown_username(self):
        admin = User.objects.create_user(
            username="admin_for_unknown_username",
            password="x",
            is_staff=True,
        )

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get(
            "/api/v1/management/users/",
            {"username": "missing-user"},
        )

        assert response.status_code == 200
        data = _payload(response)
        assert data["count"] == 0
        assert data["results"] == []

    def test_users_list_filters_by_exact_case_sensitive_email(self):
        admin = User.objects.create_user(
            username="admin_for_exact_email",
            password="x",
            is_staff=True,
        )
        matching_user = User.objects.create_user(
            username="email-match",
            email="user@example.com",
            password="x",
        )
        User.objects.create_user(
            username="email-case-mismatch",
            email="USER@example.com",
            password="x",
        )
        User.objects.create_user(
            username="email-partial-mismatch",
            email="user@example.com.extra",
            password="x",
        )

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get(
            "/api/v1/management/users/",
            {"email": "user@example.com"},
        )

        assert response.status_code == 200
        data = _payload(response)
        assert data["count"] == 1
        assert [user["id"] for user in data["results"]] == [matching_user.id]

    def test_users_list_combines_username_and_email_filters(self):
        admin = User.objects.create_user(
            username="admin_for_combined_filters",
            password="x",
            is_staff=True,
        )
        matching_user = User.objects.create_user(
            username="combined-user",
            email="combined@example.com",
            password="x",
        )
        User.objects.create_user(
            username="other-combined-user",
            email="combined@example.com",
            password="x",
        )

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get(
            "/api/v1/management/users/",
            {
                "username": "combined-user",
                "email": "combined@example.com",
            },
        )

        assert response.status_code == 200
        data = _payload(response)
        assert data["count"] == 1
        assert [user["id"] for user in data["results"]] == [matching_user.id]

    def test_users_list_applies_pagination_after_email_filter(self):
        admin = User.objects.create_user(
            username="admin_for_email_pagination",
            password="x",
            is_staff=True,
        )
        User.objects.create_user(
            username="first-shared-email",
            email="shared@example.com",
            password="x",
        )
        second_user = User.objects.create_user(
            username="second-shared-email",
            email="shared@example.com",
            password="x",
        )

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get(
            "/api/v1/management/users/",
            {"email": "shared@example.com", "page": 2, "page_size": 1},
        )

        assert response.status_code == 200
        data = _payload(response)
        assert data["count"] == 2
        assert data["page"] == 2
        assert data["page_size"] == 1
        assert [user["id"] for user in data["results"]] == [second_user.id]

    def test_users_list_applies_pagination_after_username_filter(self):
        admin = User.objects.create_user(
            username="admin_for_filtered_pagination",
            password="x",
            is_staff=True,
        )
        User.objects.create_user(username="filtered-user", password="x")
        for idx in range(3):
            User.objects.create_user(
                username=f"unrelated_user_{idx}",
                password="x",
            )

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get(
            "/api/v1/management/users/",
            {"username": "filtered-user", "page": 2, "page_size": 1},
        )

        assert response.status_code == 200
        data = _payload(response)
        assert data["count"] == 1
        assert data["page"] == 2
        assert data["page_size"] == 1
        assert data["results"] == []

    def test_users_list_username_filter_keeps_management_permission(self):
        user = User.objects.create_user(
            username="user_without_management_access",
            password="x",
        )

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(
            "/api/v1/management/users/",
            {"username": user.username},
        )

        assert response.status_code == 403

    def test_users_list_supports_page_and_page_size(self):
        admin = User.objects.create_user(
            username="admin_for_users",
            password="x",
            is_staff=True,
        )
        for idx in range(25):
            User.objects.create_user(
                username=f"user_{idx}",
                password="x",
            )

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get(
            "/api/v1/management/users/",
            {"page": 2, "page_size": 10},
        )

        assert response.status_code == 200
        data = _payload(response)
        assert data["count"] >= 26
        assert data["page"] == 2
        assert data["page_size"] == 10
        assert len(data["results"]) == 10

    def test_users_list_invalid_pagination_falls_back_and_caps(self):
        admin = User.objects.create_user(
            username="admin_for_users_invalid",
            password="x",
            is_staff=True,
        )
        for idx in range(3):
            User.objects.create_user(
                username=f"user_invalid_{idx}",
                password="x",
            )

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get(
            "/api/v1/management/users/",
            {"page": "oops", "page_size": 9999},
        )

        assert response.status_code == 200
        data = _payload(response)
        assert data["page"] == 1
        assert data["page_size"] == 100
        assert "results" in data

    def test_users_list_non_positive_page_is_clamped_to_one(self):
        admin = User.objects.create_user(
            username="admin_for_users_min_page",
            password="x",
            is_staff=True,
        )
        for idx in range(5):
            User.objects.create_user(
                username=f"user_min_page_{idx}",
                password="x",
            )

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get(
            "/api/v1/management/users/",
            {"page": 0, "page_size": 2},
        )

        assert response.status_code == 200
        data = _payload(response)
        assert data["count"] >= 6
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["results"]) == 2

    def test_users_list_large_page_returns_empty_results(self):
        admin = User.objects.create_user(
            username="admin_for_users_large_page",
            password="x",
            is_staff=True,
        )
        for idx in range(4):
            User.objects.create_user(
                username=f"user_large_page_{idx}",
                password="x",
            )

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get(
            "/api/v1/management/users/",
            {"page": 999, "page_size": 10},
        )

        assert response.status_code == 200
        data = _payload(response)
        assert data["count"] >= 5
        assert data["page"] == 100
        assert data["page_size"] == 10
        assert data["results"] == []


@pytest.mark.django_db
class TestManagementGroupsPagination:
    def test_groups_list_supports_page_and_page_size(self):
        admin = User.objects.create_user(
            username="admin_for_groups",
            password="x",
            is_staff=True,
        )
        for idx in range(23):
            Group.objects.create(name=f"group_{idx}")

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get(
            "/api/v1/management/groups/",
            {"page": 2, "page_size": 10},
        )

        assert response.status_code == 200
        data = _payload(response)
        assert data["count"] == 23
        assert data["page"] == 2
        assert data["page_size"] == 10
        assert len(data["results"]) == 10

    def test_groups_list_non_positive_page_is_clamped_to_one(self):
        admin = User.objects.create_user(
            username="admin_for_groups_min_page",
            password="x",
            is_staff=True,
        )
        for idx in range(3):
            Group.objects.create(name=f"group_min_{idx}")

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get(
            "/api/v1/management/groups/",
            {"page": -1, "page_size": 2},
        )

        assert response.status_code == 200
        data = _payload(response)
        assert data["count"] == 3
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["results"]) == 2
