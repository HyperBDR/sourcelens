"""
Cloudflare Turnstile verification service.

Verifies a client-submitted Turnstile token against Cloudflare's
siteverify endpoint using only the standard library, so no extra
dependency is required.
"""

import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

VERIFY_TIMEOUT_SECONDS = 5


def verify_token(token, remote_ip=None):
    """
    Verify a Turnstile token with Cloudflare.

    Args:
        token: The token returned by the Turnstile widget.
        remote_ip: Optional client IP for additional validation.

    Returns:
        tuple: (success, error_codes)
            - (True, []) when verification passes or is bypassed.
            - (False, [..]) with Cloudflare error codes on failure.
    """
    secret = getattr(settings, 'TURNSTILE_SECRET_KEY', '')
    if not secret:
        logger.warning(
            "Turnstile secret key is not configured; bypassing "
            "verification (development mode)."
        )
        return True, []

    if not token:
        return False, ['missing-input-response']

    payload = {'secret': secret, 'response': token}
    if remote_ip:
        payload['remoteip'] = remote_ip

    data = urllib.parse.urlencode(payload).encode('utf-8')
    request = urllib.request.Request(
        settings.TURNSTILE_VERIFY_URL,
        data=data,
        method='POST',
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=VERIFY_TIMEOUT_SECONDS,
        ) as response:
            body = json.loads(response.read().decode('utf-8'))
    except Exception as exc:
        logger.error(
            "Turnstile verification request failed: %s: %s",
            type(exc).__name__,
            exc,
        )
        return False, ['network-error']

    success = bool(body.get('success', False))
    error_codes = body.get('error-codes', []) or []
    if not success:
        logger.warning(
            "Turnstile verification rejected: %s",
            error_codes,
        )
    return success, error_codes
