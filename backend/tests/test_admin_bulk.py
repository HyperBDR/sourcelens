"""Atomic admin batch API tests."""

import pytest
from agentcore_metering.adapters.django.models import LLMConfig
from agentcore_notifier.adapters.django.models import NotificationChannel
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.fixture
def admin_client(db):
    user = get_user_model().objects.create_user(
        username="batch-admin",
        is_staff=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def webhook_config():
    return {"url": "https://example.com/webhook"}


@pytest.mark.django_db
class TestNotificationChannelBulkDelete:
    def test_deletes_every_selected_channel(
        self,
        admin_client,
        webhook_config,
    ):
        channels = [
            NotificationChannel.objects.create(
                channel_type=NotificationChannel.TYPE_WEBHOOK,
                name=f"Batch {index}",
                config=webhook_config,
            )
            for index in range(2)
        ]

        response = admin_client.post(
            "/api/v1/admin/notifications/channels/bulk-delete/",
            {"channel_ids": [str(channel.uuid) for channel in channels]},
            format="json",
        )

        assert response.status_code == 200
        assert response.json() == {"count": 2}
        assert not NotificationChannel.objects.filter(
            pk__in=[channel.pk for channel in channels]
        ).exists()

    def test_missing_channel_deletes_none(
        self,
        admin_client,
        webhook_config,
    ):
        channel = NotificationChannel.objects.create(
            channel_type=NotificationChannel.TYPE_WEBHOOK,
            name="Existing",
            config=webhook_config,
        )

        response = admin_client.post(
            "/api/v1/admin/notifications/channels/bulk-delete/",
            {
                "channel_ids": [
                    str(channel.uuid),
                    "00000000-0000-0000-0000-000000000000",
                ]
            },
            format="json",
        )

        assert response.status_code == 400
        assert NotificationChannel.objects.filter(pk=channel.pk).exists()


@pytest.mark.django_db
class TestLLMConfigBulk:
    def test_disables_every_selected_config(self, admin_client):
        configs = [
            LLMConfig.objects.create(
                scope=LLMConfig.Scope.GLOBAL,
                provider="openai",
                config={"model": f"model-{index}"},
                is_active=True,
            )
            for index in range(2)
        ]

        response = admin_client.post(
            "/api/v1/admin/llm-config/bulk/",
            {
                "config_ids": [str(config.uuid) for config in configs],
                "action": "disable",
            },
            format="json",
        )

        assert response.status_code == 200
        assert response.json() == {"count": 2}
        assert not LLMConfig.objects.filter(
            pk__in=[config.pk for config in configs],
            is_active=True,
        ).exists()

    def test_missing_config_changes_none(self, admin_client):
        config = LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            provider="openai",
            config={"model": "existing"},
            is_active=True,
        )

        response = admin_client.post(
            "/api/v1/admin/llm-config/bulk/",
            {
                "config_ids": [
                    str(config.uuid),
                    "00000000-0000-0000-0000-000000000000",
                ],
                "action": "disable",
            },
            format="json",
        )

        assert response.status_code == 400
        config.refresh_from_db()
        assert config.is_active is True

    def test_deletes_every_selected_config(self, admin_client):
        configs = [
            LLMConfig.objects.create(
                scope=LLMConfig.Scope.GLOBAL,
                provider="openai",
                config={"model": f"delete-{index}"},
            )
            for index in range(2)
        ]

        response = admin_client.post(
            "/api/v1/admin/llm-config/bulk/",
            {
                "config_ids": [str(config.uuid) for config in configs],
                "action": "delete",
            },
            format="json",
        )

        assert response.status_code == 200
        assert response.json() == {"count": 2}
        assert not LLMConfig.objects.filter(
            pk__in=[config.pk for config in configs]
        ).exists()
