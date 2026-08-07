from django.core.management.base import BaseCommand

from lens.models import Message, Run, Session
from lens.session_titles import fallback_session_title
from lens.tasks import (
    SESSION_TITLE_TASK_EXPIRY_SECONDS,
    generate_session_title,
)


class Command(BaseCommand):
    """Backfill readable titles for historical sessions with messages."""

    help = "Backfill missing titles for sessions that contain messages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Report candidates without changing sessions or "
                "enqueueing tasks."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limit the number of sessions to inspect; zero means all.",
        )

    def handle(self, *args, **options):
        sessions = Session.objects.filter(
            title="",
            title_manually_edited=False,
        ).order_by("created_at", "pk")
        limit = options["limit"]
        if limit > 0:
            sessions = sessions[:limit]

        counts = {"fallback": 0, "queued": 0, "skipped": 0, "failed": 0}
        for session in sessions:
            user_message = session.message_set.filter(
                role=Message.Role.USER,
            ).order_by("sequence", "uuid").first()
            if user_message is None:
                counts["skipped"] += 1
                continue

            title = fallback_session_title(user_message.content)
            if not title:
                counts["skipped"] += 1
                continue

            runs = session.run_set.filter(
                status=Run.Status.DONE,
                output_message__isnull=False,
            ).exclude(
                outcome=Run.Outcome.BLOCKED,
            ).select_related("input_message").order_by(
                "created_at",
                "pk",
            )
            run = next(
                (
                    candidate
                    for candidate in runs
                    if (candidate.output_message.content or "").strip()
                ),
                None,
            )
            status = (
                Session.TitleGenerationStatus.PENDING
                if run is not None
                else Session.TitleGenerationStatus.FAILED
            )
            if options["dry_run"]:
                counts["fallback"] += 1
                counts["queued"] += int(run is not None)
                continue

            updated = Session.objects.filter(
                pk=session.pk,
                title="",
                title_manually_edited=False,
            ).update(
                title=title,
                title_generation_status=status,
            )
            if not updated:
                continue

            counts["fallback"] += 1
            if run is None:
                counts["failed"] += 1
                continue

            try:
                generate_session_title.apply_async(
                    args=[str(session.uuid), str(run.uuid)],
                    expires=SESSION_TITLE_TASK_EXPIRY_SECONDS,
                )
                counts["queued"] += 1
            except Exception:
                Session.objects.filter(
                    pk=session.pk,
                    title_generation_status=(
                        Session.TitleGenerationStatus.PENDING
                    ),
                ).update(
                    title_generation_status=(
                        Session.TitleGenerationStatus.FAILED
                    ),
                )
                counts["failed"] += 1

        self.stdout.write(
            "Backfilled {fallback} fallback title(s); queued {queued}; "
            "marked {failed} failed; skipped {skipped}.".format(**counts)
        )
