"""Tests for cleanup_old_notification_records."""
from datetime import timedelta

import pytest
from django.utils import timezone

from agentcore_notifier.adapters.django.cleanup import (
    cleanup_old_notification_records,
)
from agentcore_notifier.adapters.django.models import NotificationRecord
from agentcore_notifier.constants import Channel, Provider, Status


@pytest.mark.django_db
class TestCleanupOldNotificationRecords:
    """Test cleanup logic."""

    def test_cleanup_invalid_retention_returns_skipped(self):
        out = cleanup_old_notification_records(retention_days=0)
        assert out.get("skipped") is True
        assert out["deleted_count"] == 0

    def test_cleanup_deletes_old_records(self):
        old = timezone.now() - timedelta(days=40)
        rec = NotificationRecord.objects.create(
            source_app="app",
            source_type="t",
            source_id="1",
            provider_type=Provider.FEISHU,
            channel=Channel.WEBHOOK,
            payload={},
            status=Status.SUCCESS,
        )
        NotificationRecord.objects.filter(pk=rec.pk).update(created_at=old)
        out = cleanup_old_notification_records(retention_days=30)
        assert out["deleted_count"] == 1
        assert not NotificationRecord.objects.filter(
            created_at__lt=old
        ).exists()

    def test_cleanup_only_completed(self):
        old = timezone.now() - timedelta(days=40)
        rec = NotificationRecord.objects.create(
            source_app="app",
            source_type="t",
            source_id="1",
            provider_type=Provider.FEISHU,
            channel=Channel.WEBHOOK,
            payload={},
            status=Status.PENDING,
        )
        NotificationRecord.objects.filter(pk=rec.pk).update(created_at=old)
        out = cleanup_old_notification_records(
            retention_days=30, only_completed=True
        )
        assert out["deleted_count"] == 0
        out2 = cleanup_old_notification_records(
            retention_days=30, only_completed=False
        )
        assert out2["deleted_count"] == 1
