"""Pytest bootstrap for accounts tests."""
import os

import django


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "accounts.tests.settings")
django.setup()
