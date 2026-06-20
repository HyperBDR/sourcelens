import os

from .celery import app as celery_app

# __all__ is a list that specifies the public objects of the module
__all__ = ('celery_app',)

# Known-transient infrastructure / restart noise. These fire while containers
# are recreated (deploys) or when a dependency is briefly unreachable, and are
# not application bugs. Matched case-insensitively against the event's
# exception value and log message so they never reach Sentry.
_TRANSIENT_NOISE_PATTERNS = (
    'could not translate host name',
    'connection refused',
    'timeout reading from',
    'cannot connect to redis',
    'error 111 connecting',
    'connection closed by server',
    'timed out waiting for up message',
    'signal 9 (sigkill)',
    # Raised by concurrent.futures only while the interpreter/executor is
    # shutting down (container restart/deploy), never by application code.
    'cannot schedule new futures after',
)


def _drop_transient_infra_events(event, hint):
    """Drop known transient infra/restart events before sending to Sentry."""
    parts = []
    exc_info = hint.get('exc_info') if hint else None
    if exc_info and len(exc_info) >= 2 and exc_info[1] is not None:
        parts.append(str(exc_info[1]))
    log_record = hint.get('log_record') if hint else None
    if log_record is not None:
        parts.append(str(getattr(log_record, 'message', '') or ''))
    logentry = event.get('logentry') or {}
    parts.append(str(logentry.get('message', '') or ''))
    parts.append(str(logentry.get('formatted', '') or ''))
    for value in (event.get('exception', {}) or {}).get('values', []) or []:
        parts.append(str(value.get('value', '') or ''))

    blob = ' '.join(parts).lower()
    if any(pattern in blob for pattern in _TRANSIENT_NOISE_PATTERNS):
        return None
    return event


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
        before_send=_drop_transient_infra_events,
        # Disable auto-discovery to prevent Sentry from eagerly importing
        # langgraph, openai, and huggingface_hub integration shims at startup.
        # Those packages are lazily loaded in application code; auto-enabling
        # overrides that and adds ~2.8 s per process to cold-start time.
        auto_enabling_integrations=False,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
    )


_init_sentry()
