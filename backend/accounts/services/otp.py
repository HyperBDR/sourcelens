"""
Email verification code (OTP) service.

Stores transient login codes and rate-limit counters in the Django
cache (Redis in production), so no database fields or migrations are
required. Only an HMAC of each code is persisted.
"""

import hashlib
import hmac
import logging
import secrets

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

LOGIN_PURPOSE = 'login'

_ALLOWED_PURPOSES = frozenset({LOGIN_PURPOSE})
_CODE_KEY = 'otp:{purpose}:code:{email}'
_COOLDOWN_KEY = 'otp:login:cooldown:{email}'
_DAILY_KEY = 'otp:login:daily:{email}'
_IP_KEY = 'otp:login:ip:{ip}'

_DAILY_TTL_SECONDS = 86400
_IP_TTL_SECONDS = 3600


def _normalize_email(email):
    """Return a normalized email used as a cache key component."""
    return (email or '').strip().lower()


def _get_code_key(email, purpose):
    """Return a purpose-bound cache key for a verification code."""
    if purpose not in _ALLOWED_PURPOSES:
        raise ValueError('Unsupported OTP purpose')
    return _CODE_KEY.format(
        purpose=purpose,
        email=_normalize_email(email),
    )


def _hash_code(code):
    """Return an HMAC of the code keyed by the project secret."""
    return hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        code.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def generate_code():
    """Return a fresh 6-digit numeric verification code."""
    return f"{secrets.randbelow(10 ** 6):06d}"


def _incr_with_ttl(key, ttl):
    """Increment a counter, initializing it with a TTL when absent."""
    if cache.add(key, 1, ttl):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, ttl)
        return 1


def can_send(email, ip=None):
    """
    Check send rate limits for the email and client IP.

    Returns:
        tuple: (allowed, reason) where reason is '' when allowed.
    """
    email = _normalize_email(email)
    cooldown_key = _COOLDOWN_KEY.format(email=email)
    if cache.get(cooldown_key):
        return False, 'cooldown'

    daily_key = _DAILY_KEY.format(email=email)
    daily_count = _incr_with_ttl(daily_key, _DAILY_TTL_SECONDS)
    if daily_count > settings.OTP_SEND_MAX_PER_DAY:
        return False, 'daily_limit'

    if ip:
        ip_key = _IP_KEY.format(ip=ip)
        ip_count = _incr_with_ttl(ip_key, _IP_TTL_SECONDS)
        if ip_count > settings.OTP_SEND_MAX_PER_IP_HOUR:
            return False, 'ip_limit'

    cache.set(cooldown_key, 1, settings.OTP_SEND_COOLDOWN_SECONDS)
    return True, ''


def store_code(email, code, purpose=LOGIN_PURPOSE):
    """Persist the HMAC of a freshly issued code with attempt counter."""
    cache.set(
        _get_code_key(email, purpose),
        {'code_hash': _hash_code(code), 'attempts': 0},
        settings.OTP_CODE_TTL_SECONDS,
    )


def delete_code(email, purpose=LOGIN_PURPOSE):
    """Delete an issued code after delivery failure or cancellation."""
    cache.delete(_get_code_key(email, purpose))


def verify_code(email, code, purpose=LOGIN_PURPOSE):
    """
    Verify a submitted code against the stored record.

    Returns:
        tuple: (ok, reason) where reason is '' on success and one of
        'expired' | 'too_many_attempts' | 'invalid' on failure.
    """
    key = _get_code_key(email, purpose)
    record = cache.get(key)
    if not record:
        return False, 'expired'

    if record.get('attempts', 0) >= settings.OTP_MAX_ATTEMPTS:
        cache.delete(key)
        return False, 'too_many_attempts'

    expected = record.get('code_hash', '')
    if hmac.compare_digest(expected, _hash_code(code or '')):
        cache.delete(key)
        return True, ''

    record['attempts'] = record.get('attempts', 0) + 1
    if record['attempts'] >= settings.OTP_MAX_ATTEMPTS:
        cache.delete(key)
        return False, 'too_many_attempts'
    cache.set(key, record, settings.OTP_CODE_TTL_SECONDS)
    return False, 'invalid'
