"""Transactional guards for creating work against an assistant."""

from django.db import transaction

from .models import Assistant, Session


class AssistantNotRunnableError(RuntimeError):
    """Raised when an assistant cannot accept new work."""


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
    return Session.objects.create(
        assistant=assistant,
        user=user,
        title=title,
    )
