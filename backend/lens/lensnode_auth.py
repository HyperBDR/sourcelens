import hashlib
import hmac
import secrets

from django.utils import timezone


def issue_lensnode_token(lensnode):
    """Issue a plaintext token once and persist only its hash."""

    token = secrets.token_urlsafe(48)
    lensnode.auth_token_hash = hash_lensnode_token(token)
    lensnode.token_issued_at = timezone.now()
    lensnode.token_revoked = False
    lensnode.save(
        update_fields=[
            "auth_token_hash",
            "token_issued_at",
            "token_revoked",
            "updated_at",
        ]
    )
    return token


def hash_lensnode_token(token):
    """Return the stable hash used for LensNode token lookup."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(lensnode, token):
    """Return whether a plaintext token matches a LensNode hash."""

    if not token or not lensnode.auth_token_hash:
        return False
    return hmac.compare_digest(
        lensnode.auth_token_hash,
        hash_lensnode_token(token),
    )
