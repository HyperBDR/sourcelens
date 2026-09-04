from django.core.management.base import BaseCommand

from lens.plugins.releases import reconcile_plugin_releases


class Command(BaseCommand):
    """Register installed Plugin versions without promoting new releases."""

    help = "Register installed Plugin release lifecycle state"

    def handle(self, *args, **options):
        """Reconcile filesystem packages with persisted release records."""

        del args, options
        releases = reconcile_plugin_releases()
        self.stdout.write(
            self.style.SUCCESS(
                f"Registered {len(releases)} Plugin release(s)."
            )
        )
