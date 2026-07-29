"""Django test discovery configuration."""

from pathlib import Path

from django.test.runner import DiscoverRunner


class ProjectDiscoverRunner(DiscoverRunner):
    """Discover tests from the backend source root."""

    def __init__(self, *args, **kwargs):
        """Keep application imports relative to the backend source root."""
        if kwargs.get("top_level") is None:
            kwargs["top_level"] = str(Path(__file__).resolve().parents[1])
        super().__init__(*args, **kwargs)
