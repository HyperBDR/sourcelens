"""
Django signals for automatic user setup.

Automatically creates a Profile when a new user is created,
regardless of how the user was created (Django admin, API,
management commands, etc.).
"""

import logging

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import Profile

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_user_resources(sender, instance, created, **kwargs):
    if not created:
        return

    try:
        with transaction.atomic():
            create_profile(instance)
    except Exception as e:
        logger.warning(
            f"Failed to create profile for user "
            f"{instance.username}: {e}",
            exc_info=True,
        )


def create_profile(user):
    try:
        profile, created = Profile.objects.get_or_create(
            user=user,
            defaults={
                "registration_completed": False,
                "language": "en",
                "timezone": "Asia/Shanghai",
            },
        )
        if created:
            logger.info(f"Created profile for user {user.username}")
        return profile
    except Exception as e:
        logger.warning(
            f"Failed to create profile for user {user.username}: {e}"
        )
        return None
