import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import RunOutputFile

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=RunOutputFile)
def purge_output_file_bytes(sender, instance, **kwargs):
    """Delete the stored bytes when a RunOutputFile row is removed.

    Django cascades the row on session/run deletion but leaves the
    FileField bytes in the 'deliverables' storage. Removing them here
    keeps deliverable storage bounded to live sessions across every
    deletion path (session purge, run delete, admin delete).
    """

    if not instance.file:
        return
    try:
        instance.file.delete(save=False)
    except Exception:
        logger.warning(
            "Failed to purge deliverable bytes for %s", instance.uuid,
            exc_info=True,
        )
