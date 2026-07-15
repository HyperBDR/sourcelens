from django.apps import AppConfig


class LensConfig(AppConfig):
    """Lens application configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "lens"

    def ready(self):
        """Register model signal handlers."""

        from . import signals  # noqa: F401
