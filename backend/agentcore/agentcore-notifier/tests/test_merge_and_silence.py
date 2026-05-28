"""Tests for merge_and_silence service."""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from agentcore_notifier.adapters.django.models import NotificationChannel
from agentcore_notifier.adapters.django.models import NotificationRecord
from agentcore_notifier.adapters.django.models import NotifierConfig
from agentcore_notifier.adapters.django.services import merge_and_silence
from agentcore_notifier.constants import Channel, Provider, Status


@pytest.mark.django_db
class TestFilterActiveSilenceRules:
    """Test _filter_active_silence_rules and rule matching."""

    def test_rules_not_list_returns_empty(self):
        assert merge_and_silence._filter_active_silence_rules(None) == []
        assert merge_and_silence._filter_active_silence_rules({}) == []

    def test_non_dict_rule_skipped(self):
        rules = [{"enabled": True, "source_app": "a"}, "not-a-dict", None]
        out = merge_and_silence._filter_active_silence_rules(rules)
        assert len(out) == 1
        assert out[0]["source_app"] == "a"

    def test_disabled_rule_excluded(self):
        rules = [
            {"enabled": True, "source_app": "a"},
            {"enabled": False, "source_app": "b"},
        ]
        out = merge_and_silence._filter_active_silence_rules(rules)
        assert len(out) == 1
        assert out[0]["source_app"] == "a"

    def test_silence_until_passed_excluded(self):
        past = (timezone.now() - timedelta(hours=1)).isoformat()
        rules = [
            {"enabled": True, "silence_until": past},
            {"enabled": True, "source_app": "a"},
        ]
        out = merge_and_silence._filter_active_silence_rules(rules)
        assert len(out) == 1
        assert out[0]["source_app"] == "a"

    def test_should_silence_from_rules_match(self):
        rules = [
            {
                "enabled": True,
                "source_app": "cb",
                "source_type": "alert",
                "source_id": "1",
            }
        ]
        assert merge_and_silence.should_silence_from_rules(
            rules, "cb", "alert", "1", None
        ) is True
        assert merge_and_silence.should_silence_from_rules(
            rules, "other", "alert", "1", None
        ) is False

    def test_should_silence_from_rules_user_id_match(self):
        rules = [{"enabled": True, "user_id": 42}]
        assert merge_and_silence.should_silence_from_rules(
            rules, "a", "b", "c", 42
        ) is True
        assert merge_and_silence.should_silence_from_rules(
            rules, "a", "b", "c", 99
        ) is False


@pytest.mark.django_db
class TestMergeAndSilence:
    """Test should_silence and should_skip_due_to_merge."""

    def test_merge_key(self):
        assert merge_and_silence.merge_key("a", "b", "c") == "global:a:b:c"
        assert merge_and_silence.merge_key("a", "b", "") == "global:a:b:"
        assert merge_and_silence.merge_key("a", "b", "c", 10) == "10:a:b:c"

    def test_should_silence_no_rules(self):
        assert merge_and_silence.should_silence(
            "feishu", "cloud_billing", "alert", "1", None
        ) is False

    def test_should_silence_matching_rule(self):
        NotifierConfig.objects.create(
            scope=NotifierConfig.SCOPE_GLOBAL,
            user=None,
            key="silence_rules",
            value=[
                {
                    "provider_type": "feishu",
                    "source_app": "cloud_billing",
                    "source_type": "alert",
                    "source_id": "1",
                    "user_id": None,
                    "enabled": True,
                }
            ],
        )
        assert merge_and_silence.should_silence(
            "feishu", "cloud_billing", "alert", "1", None
        ) is True
        assert merge_and_silence.should_silence(
            "wechat", "cloud_billing", "alert", "1", None
        ) is False

    def test_should_skip_due_to_merge_no_recent_record(self):
        assert merge_and_silence.should_skip_due_to_merge(
            "feishu", "app", "alert", "1", 15
        ) is False

    def test_should_skip_due_to_merge_has_recent_record(self):
        since = timezone.now() - timedelta(minutes=5)
        NotificationRecord.objects.create(
            source_app="app",
            source_type="alert",
            source_id="1",
            provider_type="feishu",
            channel="webhook",
            payload={},
            status=Status.SUCCESS,
            created_at=since,
        )
        assert merge_and_silence.should_skip_due_to_merge(
            "feishu", "app", "alert", "1", 15
        ) is True

    def test_merge_per_user_dimension(self):
        """Different users must not merge; same user merges within window."""
        since = timezone.now() - timedelta(minutes=5)
        User = get_user_model()
        u1 = User.objects.create_user(username="u1", password="x")
        u2 = User.objects.create_user(username="u2", password="x")
        NotificationRecord.objects.create(
            source_app="app",
            source_type="alert",
            source_id="1",
            provider_type="feishu",
            channel="webhook",
            payload={},
            status=Status.SUCCESS,
            created_at=since,
            user_id=u1.pk,
        )
        assert merge_and_silence.should_skip_due_to_merge(
            "feishu", "app", "alert", "1", 15, user_id=u1.pk
        ) is True
        assert merge_and_silence.should_skip_due_to_merge(
            "feishu", "app", "alert", "1", 15, user_id=u2.pk
        ) is False

    def test_should_skip_due_to_merge_window_zero_returns_false(self):
        assert merge_and_silence.should_skip_due_to_merge(
            "feishu", "app", "alert", "1", 0
        ) is False

    def test_should_skip_due_to_merge_global_user_null(self):
        """When user_id is None, only records with user__isnull=True merge."""
        channel = NotificationChannel.objects.create(
            name="w",
            channel_type=Channel.WEBHOOK,
            config={"url": "https://x.com", "provider_type": "feishu"},
        )
        since = timezone.now() - timedelta(minutes=5)
        NotificationRecord.objects.create(
            source_app="app",
            source_type="alert",
            source_id="1",
            provider_type="feishu",
            channel=Channel.WEBHOOK,
            channel_link=channel,
            payload={},
            status=Status.SUCCESS,
            created_at=since,
            user_id=None,
        )
        assert merge_and_silence.should_skip_due_to_merge(
            "feishu", "app", "alert", "1", 15, user_id=None
        ) is True

    def test_should_skip_due_to_merge_filter_by_channel_id(self):
        channel = NotificationChannel.objects.create(
            name="w",
            channel_type=Channel.WEBHOOK,
            config={"url": "https://x.com", "provider_type": "feishu"},
        )
        since = timezone.now() - timedelta(minutes=5)
        NotificationRecord.objects.create(
            source_app="app",
            source_type="alert",
            source_id="1",
            provider_type="feishu",
            channel=Channel.WEBHOOK,
            channel_link=channel,
            payload={},
            status=Status.SUCCESS,
            created_at=since,
        )
        assert merge_and_silence.should_skip_due_to_merge(
            "feishu", "app", "alert", "1", 15, channel_id=channel.pk
        ) is True
        assert merge_and_silence.should_skip_due_to_merge(
            "feishu", "app", "alert", "1", 15, channel_id=channel.pk + 9999
        ) is False
