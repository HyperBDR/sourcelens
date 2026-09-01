from django.core.management.base import BaseCommand, CommandError

from lens.plugins.legacy_migration import (
    migrate_legacy_github_integrations,
    rollback_legacy_github_integrations,
)


class Command(BaseCommand):
    """Migrate or roll back legacy datasource credentials."""

    help = "Migrate legacy GitHub datasource credentials to Plugin Connections."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--rollback", action="store_true")

    def handle(self, *args, **options):
        del args
        if options["apply"] and options["rollback"]:
            raise CommandError("Choose either --apply or --rollback.")
        if options["rollback"]:
            report = rollback_legacy_github_integrations()
        else:
            report = migrate_legacy_github_integrations(dry_run=not options["apply"])
        self.stdout.write(self.style.SUCCESS(str(report)))
