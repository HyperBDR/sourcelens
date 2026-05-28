import os

from .celery import app as celery_app

# __all__ is a list that specifies the public objects of the module
__all__ = ('celery_app',)


def _init_sentry():
    """Initialize Sentry error tracking if configured."""
    from core.settings.sentry import (
        SENTRY_DSN,
        SENTRY_ENABLED,
        SENTRY_ENVIRONMENT,
        SENTRY_PROFILING_SAMPLE_RATE,
        SENTRY_RELEASE,
        SENTRY_SEND_DEFAULT_PII,
        SENTRY_TRACES_SAMPLE_RATE,
    )

    if not SENTRY_ENABLED or not SENTRY_DSN:
        return

    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        release=SENTRY_RELEASE or None,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=SENTRY_PROFILING_SAMPLE_RATE,
        send_default_pii=SENTRY_SEND_DEFAULT_PII,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
    )


_init_sentry()
