"""
Pytest fixtures for agentcore_metering tests.
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_user(django_user_model):
    return django_user_model.objects.create_user(
        username="adminuser",
        email="admin@example.com",
        password="adminpass123",
        is_staff=True,
    )


@pytest.fixture
def normal_user(django_user_model):
    return django_user_model.objects.create_user(
        username="normaluser",
        email="user@example.com",
        password="userpass123",
        is_staff=False,
    )


@pytest.fixture
def admin_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def authenticated_client(api_client, normal_user):
    api_client.force_authenticate(user=normal_user)
    return api_client
