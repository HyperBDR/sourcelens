"""Transactional guards for creating work against an assistant."""

from django.core.cache import cache
from django.db import transaction

from .models import Assistant, Session


class AssistantNotRunnableError(RuntimeError):
    """Raised when an assistant cannot accept new work."""


def _has_document_attachments(session):
    """Return whether cached document uploads still belong to a session."""

    key = f"lens:session_document_attachments:{session.uuid}"
    return bool(cache.get(key) or [])


def _find_reusable_empty_session(assistant, user):
    """Return the oldest active empty session for an assistant and user."""

    candidates = Session.objects.filter(
        assistant=assistant,
        user=user,
        status=Session.Status.ACTIVE,
        title="",
        title_manually_edited=False,
    ).order_by("created_at", "pk")
    for session in candidates:
        if session.message_set.exists():
            continue
        if session.run_set.exists():
            continue
        if session.attachments.exists():
            continue
        if _has_document_attachments(session):
            continue
        return session
    return None


def lock_assistant_for_new_work(assistant, user=None):
    """Lock and return an assistant after checking its current state."""

    locked = Assistant.objects.select_for_update().get(pk=assistant.pk)
    if user is None:
        is_runnable = locked.status == Assistant.Status.ACTIVE
    else:
        is_runnable = locked.is_runnable_by(user)
    if not is_runnable:
        raise AssistantNotRunnableError
    return locked


@transaction.atomic
def create_assistant_session(assistant_uuid, user, title=""):
    """Create a session while serializing against assistant archival."""

    assistant = Assistant.objects.get(uuid=assistant_uuid)
    assistant = lock_assistant_for_new_work(assistant, user)
    normalized_title = " ".join(str(title or "").split())
    if not normalized_title:
        existing = _find_reusable_empty_session(assistant, user)
        if existing is not None:
            return existing
    return Session.objects.create(
        assistant=assistant,
        user=user,
        title=normalized_title,
        title_manually_edited=bool(normalized_title),
        title_generation_status=(
            Session.TitleGenerationStatus.SKIPPED
            if normalized_title
            else Session.TitleGenerationStatus.PENDING
        ),
    )
