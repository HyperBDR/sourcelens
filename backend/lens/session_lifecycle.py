"""Transactional lifecycle helpers for chat sessions."""

from django.db import transaction
from django.utils import timezone

from .models import Session


class SessionStateError(RuntimeError):
    """Raised when an operation is invalid for the session state."""


def lock_active_session(session):
    """Lock and return a session after confirming that it is active."""

    locked = Session.objects.select_for_update().get(pk=session.pk)
    if locked.status != Session.Status.ACTIVE:
        raise SessionStateError
    return locked


@transaction.atomic
def pin_session(session):
    """Pin an active session using a stable persisted timestamp."""

    session = lock_active_session(session)
    if session.pinned_at is None:
        session.pinned_at = timezone.now()
        session.save(update_fields=["pinned_at", "updated_at"])
    return session


@transaction.atomic
def unpin_session(session):
    """Remove an active session from the pinned group."""

    session = lock_active_session(session)
    if session.pinned_at is not None:
        session.pinned_at = None
        session.save(update_fields=["pinned_at", "updated_at"])
    return session


@transaction.atomic
def archive_session(session):
    """Archive a session and remove it from the pinned group."""

    session = lock_active_session(session)
    session.status = Session.Status.ARCHIVED
    session.pinned_at = None
    session.save(update_fields=["status", "pinned_at", "updated_at"])
    return session


@transaction.atomic
def restore_session(session):
    """Restore an archived session without implicitly pinning it."""

    session = Session.objects.select_for_update().get(pk=session.pk)
    if session.status != Session.Status.ARCHIVED:
        raise SessionStateError
    session.status = Session.Status.ACTIVE
    session.save(update_fields=["status", "updated_at"])
    return session
