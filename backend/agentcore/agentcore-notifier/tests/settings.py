"""Minimal Django settings for agentcore_notifier tests."""
SECRET_KEY = "test-secret"
DEBUG = True
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "agentcore_notifier.adapters.django",
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
ROOT_URLCONF = "tests.urls"
CELERY_TASK_ALWAYS_EAGER = True
