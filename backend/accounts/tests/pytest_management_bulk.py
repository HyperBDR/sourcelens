"""Pytest-only atomic management bulk action API tests."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from accounts.models import Role

User = get_user_model()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="bulk-admin",
        password="x",
        is_staff=True,
    )


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.mark.django_db
class TestManagementUserBulk:
    def test_updates_every_selected_user(self, admin_client):
        users = [
            User.objects.create_user(username=f"bulk-user-{index}")
            for index in range(2)
        ]

        response = admin_client.post(
            "/api/v1/management/users/bulk-status/",
            {
                "user_ids": [user.pk for user in users],
                "is_active": False,
            },
            format="json",
        )

        assert response.status_code == 200
        assert response.json() == {"count": 2}
        assert not User.objects.filter(
            pk__in=[user.pk for user in users],
            is_active=True,
        ).exists()

    def test_missing_user_changes_none(self, admin_client):
        user = User.objects.create_user(username="bulk-existing-user")

        response = admin_client.post(
            "/api/v1/management/users/bulk-status/",
            {"user_ids": [user.pk, 999999], "is_active": False},
            format="json",
        )

        assert response.status_code == 400
        user.refresh_from_db()
        assert user.is_active is True

    def test_cannot_disable_acting_admin(self, admin_client, admin_user):
        response = admin_client.post(
            "/api/v1/management/users/bulk-status/",
            {"user_ids": [admin_user.pk], "is_active": False},
            format="json",
        )

        assert response.status_code == 400
        admin_user.refresh_from_db()
        assert admin_user.is_active is True


@pytest.mark.django_db
class TestManagementRoleBulk:
    def test_updates_every_selected_role(self, admin_client):
        roles = [
            Role.objects.create(name=f"bulk-role-{index}", is_active=True)
            for index in range(2)
        ]

        response = admin_client.post(
            "/api/v1/management/roles/bulk-status/",
            {
                "role_ids": [role.pk for role in roles],
                "is_active": False,
            },
            format="json",
        )

        assert response.status_code == 200
        assert response.json() == {"count": 2}
        assert not Role.objects.filter(
            pk__in=[role.pk for role in roles],
            is_active=True,
        ).exists()

    def test_missing_role_changes_none(self, admin_client):
        role = Role.objects.create(name="bulk-role", is_active=True)

        response = admin_client.post(
            "/api/v1/management/roles/bulk-status/",
            {"role_ids": [role.pk, 999999], "is_active": False},
            format="json",
        )

        assert response.status_code == 400
        role.refresh_from_db()
        assert role.is_active is True


@pytest.mark.django_db
class TestManagementGroupBulkDelete:
    def test_deletes_every_selected_group(self, admin_client):
        groups = [
            Group.objects.create(name=f"bulk-group-{index}")
            for index in range(2)
        ]

        response = admin_client.post(
            "/api/v1/management/groups/bulk-delete/",
            {"group_ids": [group.pk for group in groups]},
            format="json",
        )

        assert response.status_code == 200
        assert response.json() == {"count": 2}
        assert not Group.objects.filter(
            pk__in=[group.pk for group in groups]
        ).exists()

    def test_missing_group_deletes_none(self, admin_client):
        group = Group.objects.create(name="bulk-existing-group")

        response = admin_client.post(
            "/api/v1/management/groups/bulk-delete/",
            {"group_ids": [group.pk, 999999]},
            format="json",
        )

        assert response.status_code == 400
        assert Group.objects.filter(pk=group.pk).exists()
