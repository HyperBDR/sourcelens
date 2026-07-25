import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import RunOutputFile, SharedQAFile

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=SharedQAFile)
@receiver(post_delete, sender=RunOutputFile)
def purge_deliverable_bytes(sender, instance, **kwargs):
    """Delete stored bytes when a deliverable record is removed.

    Django cascades database rows but leaves FileField bytes in storage.
    Removing them here keeps both private and shared deliverables bounded
    to live database records across every deletion path.
    """

    if not instance.file:
        return
    try:
        instance.file.delete(save=False)
    except Exception:
        logger.warning(
            "Failed to purge deliverable bytes for %s",
            instance.uuid,
            exc_info=True,
        )
