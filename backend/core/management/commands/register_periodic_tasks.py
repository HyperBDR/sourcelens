"""
Discover all installed apps' periodic_tasks and register to Celery Beat.

Run at startup (e.g. in entrypoint after migrate) so that each app's
register_periodic_tasks() is called and tasks are written to
django_celery_beat. No Django signals; keeps the flow explicit and portable.
"""
import importlib
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from core.periodic_registry import (
    TASK_REGISTRY,
    apply_registry,
)

logger = logging.getLogger(__name__)


def discover_and_register():
    """
    Clear registry, discover each app's periodic_tasks, call
    register_periodic_tasks, then apply registry to django_celery_beat.
    """
    TASK_REGISTRY.clear()

    for app in settings.INSTALLED_APPS:
        try:
            module = importlib.import_module(f"{app}.periodic_tasks")
        except ModuleNotFoundError:
            continue

        if hasattr(module, "register_periodic_tasks"):
            try:
                module.register_periodic_tasks()
            except Exception as e:
                logger.exception(
                    f"register_periodic_tasks failed for app {app}: {e}"
                )

    apply_registry()


class Command(BaseCommand):
    help = (
        "Discover all apps' periodic_tasks.register_periodic_tasks() and "
        "register entries to django_celery_beat without updating existing "
        "rows."
    )

    def handle(self, *args, **options):
        discover_and_register()
        count = len(TASK_REGISTRY)
        self.stdout.write(
            self.style.SUCCESS(
                f"Registered {count} periodic task(s) to django_celery_beat; "
            )
        )
