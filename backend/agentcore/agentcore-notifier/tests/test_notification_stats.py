"""Tests for notification_stats service."""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from agentcore_notifier.adapters.django.models import NotificationChannel
from agentcore_notifier.adapters.django.models import NotificationRecord
from agentcore_notifier.adapters.django.services import notification_stats
from agentcore_notifier.constants import Channel, Provider, Status


@pytest.mark.django_db
class TestGetNotificationStatsFromQuery:
    """Test get_notification_stats_from_query."""

    def test_empty_db_returns_zero_summary(self):
        out = notification_stats.get_notification_stats_from_query({})
        assert out["summary"]["total"] == 0
        assert out["summary"]["total_sent"] == 0
        assert out["by_source"] == []
        assert out["by_provider"] == []

    def test_summary_counts_by_status(self):
        channel = NotificationChannel.objects.create(
            name="w",
            channel_type=Channel.WEBHOOK,
            config={"url": "https://x.com", "provider_type": "feishu"},
        )
        NotificationRecord.objects.create(
            source_app="a",
            source_type="t",
            source_id="1",
            provider_type=Provider.FEISHU,
            channel=Channel.WEBHOOK,
            channel_link=channel,
            payload={},
            status=Status.SUCCESS,
        )
        NotificationRecord.objects.create(
            source_app="a",
            source_type="t",
            source_id="2",
            provider_type=Provider.FEISHU,
            channel=Channel.WEBHOOK,
            channel_link=channel,
            payload={},
            status=Status.FAILED,
        )
        out = notification_stats.get_notification_stats_from_query({})
        assert out["summary"]["total"] == 2
        assert out["summary"]["total_sent"] == 1
        assert out["summary"]["total_failed"] == 1
        assert len(out["by_source"]) == 1
        assert out["by_source"][0]["source_app"] == "a"
        assert out["by_source"][0]["count"] == 2
        assert len(out["by_provider"]) == 1
        assert out["by_provider"][0]["provider_type"] == Provider.FEISHU

    def test_filter_by_user_id(self):
        User = get_user_model()
        u1 = User.objects.create_user(username="u1", password="x")
        u2 = User.objects.create_user(username="u2", password="x")
        channel = NotificationChannel.objects.create(
            name="w",
            channel_type=Channel.WEBHOOK,
            config={"url": "https://x.com", "provider_type": "feishu"},
        )
        for u in (u1, u1, u2):
            NotificationRecord.objects.create(
                source_app="a",
                source_type="t",
                source_id="1",
                provider_type=Provider.FEISHU,
                channel=Channel.WEBHOOK,
                channel_link=channel,
                payload={},
                status=Status.SUCCESS,
                user=u,
            )
        out = notification_stats.get_notification_stats_from_query(
            {"user_id": u1.pk}
        )
        assert out["summary"]["total"] == 2
        out_all = notification_stats.get_notification_stats_from_query({})
        assert out_all["summary"]["total"] == 3

    def test_invalid_user_id_is_ignored(self):
        out = notification_stats.get_notification_stats_from_query(
            {"user_id": "not-an-int"}
        )
        assert "summary" in out
        assert "total" in out["summary"]

    def test_filter_by_start_date_and_end_date(self):
        channel = NotificationChannel.objects.create(
            name="w",
            channel_type=Channel.WEBHOOK,
            config={"url": "https://x.com", "provider_type": "feishu"},
        )
        now = timezone.now()
        base = now.replace(hour=12, minute=0, second=0, microsecond=0)
        in_range = base - timedelta(days=1)
        NotificationRecord.objects.create(
            source_app="a",
            source_type="t",
            source_id="1",
            provider_type=Provider.FEISHU,
            channel=Channel.WEBHOOK,
            channel_link=channel,
            payload={},
            status=Status.SUCCESS,
            created_at=in_range,
        )
        start = (base - timedelta(days=2)).strftime("%Y-%m-%d")
        end = base.strftime("%Y-%m-%d")
        out = notification_stats.get_notification_stats_from_query(
            {"start_date": start, "end_date": end}
        )
        assert out["summary"]["total"] == 1

    def test_series_day_returns_24_buckets(self):
        out = notification_stats.get_notification_stats_from_query(
            {
                "granularity": "day",
                "start_date": "2025-02-01",
                "end_date": "2025-02-01",
            }
        )
        assert "series" in out
        assert len(out["series"]) == 24
        assert out["series"][0]["bucket"] == "00:00"
        assert out["series"][23]["bucket"] == "23:00"

    def test_series_month_returns_one_bucket_per_day(self):
        out = notification_stats.get_notification_stats_from_query(
            {
                "granularity": "month",
                "start_date": "2025-02-01",
                "end_date": "2025-02-28",
            }
        )
        assert "series" in out
        assert len(out["series"]) == 28

    def test_series_year_returns_12_buckets(self):
        out = notification_stats.get_notification_stats_from_query(
            {"granularity": "year", "end_date": "2025-06-15"}
        )
        assert "series" in out
        assert len(out["series"]) == 12
        assert out["series"][0]["bucket"] == "2025-01"
        assert out["series"][11]["bucket"] == "2025-12"

    def test_series_invalid_granularity_omitted(self):
        out = notification_stats.get_notification_stats_from_query(
            {"granularity": "hour"}
        )
        assert "series" not in out


@pytest.mark.django_db
class TestGetNotificationRecordListFromQuery:
    """Test get_notification_record_list_from_query."""

    def test_paginated_list_empty(self):
        out = notification_stats.get_notification_record_list_from_query({})
        assert out["total"] == 0
        assert out["page"] == 1
        assert out["page_size"] >= 1
        assert out["results"] == []

    def test_invalid_pagination_params_fallback_to_defaults(self):
        out = notification_stats.get_notification_record_list_from_query(
            {"page": "oops", "page_size": "oops"}
        )
        assert out["page"] == 1
        assert out["page_size"] == 20

    def test_paginated_list_with_filters(self):
        channel = NotificationChannel.objects.create(
            name="w",
            channel_type=Channel.WEBHOOK,
            config={"url": "https://x.com", "provider_type": "feishu"},
        )
        NotificationRecord.objects.create(
            source_app="myapp",
            source_type="alert",
            source_id="1",
            provider_type=Provider.FEISHU,
            channel=Channel.WEBHOOK,
            channel_link=channel,
            payload={},
            status=Status.SUCCESS,
        )
        out = notification_stats.get_notification_record_list_from_query(
            {"page": 1, "page_size": 10}
        )
        assert out["total"] == 1
        assert len(out["results"]) == 1
        assert out["results"][0].source_app == "myapp"

    def test_filter_by_source_app_and_status(self):
        channel = NotificationChannel.objects.create(
            name="w",
            channel_type=Channel.WEBHOOK,
            config={"url": "https://x.com", "provider_type": "feishu"},
        )
        NotificationRecord.objects.create(
            source_app="app1",
            source_type="alert",
            source_id="1",
            provider_type=Provider.FEISHU,
            channel=Channel.WEBHOOK,
            channel_link=channel,
            payload={},
            status=Status.SUCCESS,
        )
        NotificationRecord.objects.create(
            source_app="app2",
            source_type="alert",
            source_id="1",
            provider_type=Provider.FEISHU,
            channel=Channel.WEBHOOK,
            channel_link=channel,
            payload={},
            status=Status.FAILED,
        )
        out = notification_stats.get_notification_record_list_from_query(
            {"source_app": "app1", "status": Status.SUCCESS}
        )
        assert out["total"] == 1
        assert out["results"][0].source_app == "app1"
