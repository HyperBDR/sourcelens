"""Pytest configuration for core integration tests."""

import os

import django

os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.admin_bulk_settings")


def pytest_configure():
    """Initialize the isolated Django registry before test collection."""

    django.setup()
