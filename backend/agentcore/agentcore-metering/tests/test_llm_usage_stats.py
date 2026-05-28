"""
Tests for usage_aggregation: _parse_date, get_summary_stats, by_model, series.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone as django_tz

from agentcore_metering.adapters.django.services.usage_aggregation import (
    _bucket_key_for_fill,
    _parse_date,
    _parse_end_date,
    get_stats_by_model,
    get_summary_stats,
    get_time_series_stats,
    get_token_stats_from_query,
)
from agentcore_metering.adapters.django.models import LLMUsage


@pytest.mark.unit
class TestParseDate:
    def test_returns_none_for_none(self):
        assert _parse_date(None) is None

    def test_returns_none_for_empty_string(self):
        assert _parse_date("") is None

    def test_parses_iso_datetime_string(self):
        out = _parse_date("2025-02-01T12:00:00+00:00")
        assert out is not None
        assert out.year == 2025
        assert out.month == 2
        assert out.day == 1

    def test_returns_none_for_invalid_string(self):
        assert _parse_date("not-a-date") is None


@pytest.mark.unit
class TestParseEndDate:
    def test_returns_none_for_none(self):
        assert _parse_end_date(None) is None

    def test_date_only_returns_end_of_day(self):
        out = _parse_end_date("2025-02-01")
        assert out is not None
        assert out.hour == 23
        assert out.minute == 59


@pytest.mark.unit
class TestBucketKeyForFill:
    """
    _bucket_key_for_fill normalizes bucket to a string key so DB and expected
    buckets match (naive/aware, date/datetime).
    """

    def test_returns_none_for_none(self):
        assert _bucket_key_for_fill(None, "day") is None
        assert _bucket_key_for_fill(None, "month") is None
        assert _bucket_key_for_fill(None, "year") is None

    def test_day_granularity_normalizes_datetime(self):
        dt = datetime(2026, 2, 21, 3, 0, 0)
        key = _bucket_key_for_fill(dt, "day")
        assert key is not None
        assert "2026-02-21" in key
        assert "03:00:00" in key

    def test_month_granularity_uses_date_iso(self):
        d = date(2026, 2, 21)
        assert _bucket_key_for_fill(d, "month") == "2026-02-21"
        dt = datetime(2026, 2, 21, 15, 30, 0)
        assert _bucket_key_for_fill(dt, "month") == "2026-02-21"

    def test_year_granularity_normalizes_to_first_of_month(self):
        dt = datetime(2026, 3, 7, 10, 0, 0)
        key = _bucket_key_for_fill(dt, "year")
        assert key is not None
        assert "2026-03-01" in key
        assert "00:00:00" in key or "00:00" in key


@pytest.mark.unit
@pytest.mark.django_db
class TestGetSummaryStats:
    def test_returns_zeros_when_no_records(self):
        out = get_summary_stats()
        assert out["total_calls"] == 0
        assert out["total_tokens"] == 0

    def test_aggregates_single_record(self):
        LLMUsage.objects.create(
            model="gpt-4",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            success=True,
        )
        out = get_summary_stats()
        assert out["total_calls"] == 1
        assert out["total_tokens"] == 30


@pytest.mark.unit
@pytest.mark.django_db
class TestGetStatsByModel:
    def test_empty_list_when_no_records(self):
        assert get_stats_by_model() == []

    def test_one_row_per_model_with_totals(self):
        LLMUsage.objects.create(model="gpt-4", total_tokens=15)
        LLMUsage.objects.create(model="gpt-4", total_tokens=3)
        LLMUsage.objects.create(model="claude", total_tokens=6)
        rows = get_stats_by_model()
        assert len(rows) == 2
        by_model = {r["model"]: r for r in rows}
        assert by_model["gpt-4"]["total_calls"] == 2
        assert by_model["gpt-4"]["total_tokens"] == 18


@pytest.mark.unit
@pytest.mark.django_db
class TestGetTimeSeriesStats:
    def test_raises_for_unsupported_granularity(self):
        with pytest.raises(ValueError, match="Unsupported granularity"):
            get_time_series_stats(granularity="invalid")

    def test_day_granularity_returns_buckets(self):
        LLMUsage.objects.create(model="m1", total_tokens=10)
        items = get_time_series_stats(granularity="day")
        assert isinstance(items, list)

    def test_day_granularity_fills_empty_hours(self):
        start = django_tz.make_aware(datetime(2026, 2, 21, 0, 0, 0))
        end = django_tz.make_aware(datetime(2026, 2, 21, 23, 59, 59))
        usage = LLMUsage.objects.create(model="m1", total_tokens=10)
        LLMUsage.objects.filter(id=usage.id).update(
            created_at=django_tz.make_aware(datetime(2026, 2, 21, 3, 15, 0))
        )

        items = get_time_series_stats(
            granularity="day",
            start_date=start,
            end_date=end,
        )

        assert len(items) == 24
        assert sum(i["total_tokens"] for i in items) == 10
        assert sum(1 for i in items if i["total_tokens"] > 0) == 1

    def test_month_granularity_fills_all_days_when_no_data(self):
        start = django_tz.make_aware(datetime(2026, 2, 1, 0, 0, 0))
        end = django_tz.make_aware(datetime(2026, 2, 28, 23, 59, 59))

        items = get_time_series_stats(
            granularity="month",
            start_date=start,
            end_date=end,
        )

        assert len(items) == 28
        assert all(i["total_tokens"] == 0 for i in items)

    def test_year_granularity_fills_all_months(self):
        start = django_tz.make_aware(datetime(2026, 1, 1, 0, 0, 0))
        end = django_tz.make_aware(datetime(2026, 12, 31, 23, 59, 59))
        usage = LLMUsage.objects.create(model="m1", total_tokens=9)
        LLMUsage.objects.filter(id=usage.id).update(
            created_at=django_tz.make_aware(datetime(2026, 3, 7, 10, 0, 0))
        )

        items = get_time_series_stats(
            granularity="year",
            start_date=start,
            end_date=end,
        )

        assert len(items) == 12
        assert sum(i["total_tokens"] for i in items) == 9
        assert sum(1 for i in items if i["total_tokens"] > 0) == 1

    def test_year_granularity_returns_twelve_months_when_end_in_non_utc(self):
        """
        When end_date is last second of year in a timezone ahead of UTC,
        converting to UTC would be next year; we must still return 12 months
        (Jan–Dec of that calendar year).
        """
        start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC"))
        end = datetime(
            2026, 12, 31, 23, 59, 59,
            tzinfo=ZoneInfo("America/Los_Angeles"),
        )

        items = get_time_series_stats(
            granularity="year",
            start_date=start,
            end_date=end,
        )

        assert len(items) == 12
        assert items[0]["bucket"].startswith("2026-01")
        assert items[-1]["bucket"].startswith("2026-12")


@pytest.mark.unit
@pytest.mark.django_db
class TestGetTokenStatsFromQuery:
    def test_returns_summary_and_by_model_without_granularity(self):
        LLMUsage.objects.create(model="m1", total_tokens=10)
        out = get_token_stats_from_query({})
        assert "summary" in out
        assert out["summary"]["total_tokens"] == 10
        assert "by_model" in out
        assert out["series"] is None

    def test_raises_for_unsupported_granularity_in_params(self):
        with pytest.raises(ValueError, match="Unsupported granularity"):
            get_token_stats_from_query({"granularity": "bad"})

    def test_day_query_with_date_only_keeps_existing_hour_data(self):
        usage = LLMUsage.objects.create(model="m1", total_tokens=12)
        LLMUsage.objects.filter(id=usage.id).update(
            created_at=django_tz.make_aware(datetime(2026, 2, 21, 7, 45, 0))
        )

        out = get_token_stats_from_query({
            "granularity": "day",
            "start_date": "2026-02-21",
            "end_date": "2026-02-21",
        })

        series = out["series"]["items"]
        assert len(series) == 24
        assert sum(i["total_tokens"] for i in series) == 12
        assert sum(1 for i in series if i["total_tokens"] > 0) == 1
