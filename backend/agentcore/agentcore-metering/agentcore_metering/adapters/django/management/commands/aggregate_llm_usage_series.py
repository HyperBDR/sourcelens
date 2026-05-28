"""
Management command to aggregate LLMUsage into LLMUsageSeries for charts.

Usage:
  python manage.py aggregate_llm_usage_series --granularity=hour
      --start=... --end=...
  python manage.py aggregate_llm_usage_series --granularity=day
      --start=2025-02-01 --end=2025-02-28
  python manage.py aggregate_llm_usage_series --granularity=month
      --start=2025-01-01 --end=2025-12-31

Suitable for cron: run hourly for granularity=hour (e.g. last 2 hours),
daily for granularity=day (e.g. yesterday), monthly for granularity=month.
"""
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from agentcore_metering.adapters.django.services.usage_chart_series import (
    aggregate_usage_to_series,
)
from agentcore_metering.adapters.django.tasks.aggregate import _default_range
from agentcore_metering.adapters.django.services.usage_aggregation import (
    _parse_date,
    _parse_end_date,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Aggregate LLMUsage into LLMUsageSeries. "
        "Options: --granularity=hour|day|month, --start, --end (YYYY-MM-DD)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--granularity",
            type=str,
            default="hour",
            choices=["hour", "day", "month"],
            help="Bucket granularity (hour/day/month).",
        )
        parser.add_argument(
            "--start",
            type=str,
            default=None,
            help=(
                "Start date (YYYY-MM-DD or ISO). "
                "Default: yesterday for day/month; last 2h for hour."
            ),
        )
        parser.add_argument(
            "--end",
            type=str,
            default=None,
            help=(
                "End date (YYYY-MM-DD or ISO). "
                "Default: yesterday for day/month; now for hour."
            ),
        )

    def handle(self, *args, **options):
        granularity = (options.get("granularity") or "hour").strip().lower()
        start_str = options.get("start")
        end_str = options.get("end")

        if start_str and end_str:
            start_date = _parse_date(start_str)
            end_date = _parse_end_date(end_str)
            if not start_date or not end_date:
                self.stderr.write(
                    self.style.ERROR(
                    "Invalid --start or --end; use YYYY-MM-DD or ISO."
                )
                )
                return
        else:
            start_date, end_date = _default_range(granularity)

        try:
            n = aggregate_usage_to_series(
                granularity=granularity,
                start_date=start_date,
                end_date=end_date,
            )
            msg = (
                f"Aggregated {n} (bucket, model) rows for "
                f"granularity={granularity}."
            )
            self.stdout.write(self.style.SUCCESS(msg))
        except Exception as e:
            logger.exception("aggregate_llm_usage_series failed")
            self.stderr.write(self.style.ERROR(str(e)))
            raise
