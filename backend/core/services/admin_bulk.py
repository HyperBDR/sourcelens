"""Atomic bulk mutations for admin resources provided by agentcore apps."""

from uuid import UUID

from agentcore_metering.adapters.django.models import LLMConfig
from agentcore_notifier.adapters.django.models import NotificationChannel
from django.db import transaction

MAX_BULK_ITEMS = 100
LLM_CONFIG_ACTIONS = {"enable", "disable", "delete"}


class AdminBulkMutationError(ValueError):
    """Reject an admin batch before any selected resource is changed."""


def _normalize_uuids(raw_uuids, field_name):
    """Validate a bounded, unique list of UUID identifiers."""

    if not isinstance(raw_uuids, list) or not raw_uuids:
        raise AdminBulkMutationError(f"{field_name} must be a non-empty list.")
    if len(raw_uuids) > MAX_BULK_ITEMS:
        raise AdminBulkMutationError(
            f"{field_name} cannot contain more than {MAX_BULK_ITEMS} items."
        )
    try:
        normalized = [UUID(str(value)) for value in raw_uuids]
    except (TypeError, ValueError, AttributeError) as exc:
        raise AdminBulkMutationError(
            f"{field_name} contains an invalid UUID."
        ) from exc
    if len(set(normalized)) != len(normalized):
        raise AdminBulkMutationError(f"{field_name} contains duplicate UUIDs.")
    return normalized


def _locked_selection(model, resource_uuids, label):
    resources = list(
        model.objects.select_for_update()
        .filter(uuid__in=resource_uuids)
        .order_by("uuid")
    )
    if len(resources) != len(resource_uuids):
        raise AdminBulkMutationError(f"One or more {label} no longer exist.")
    return resources


@transaction.atomic
def delete_notification_channels(raw_uuids):
    """Delete every selected channel or preserve the complete selection."""

    channel_uuids = _normalize_uuids(raw_uuids, "channel_ids")
    channels = _locked_selection(
        NotificationChannel,
        channel_uuids,
        "channels",
    )
    NotificationChannel.objects.filter(
        pk__in=[channel.pk for channel in channels]
    ).delete()
    return len(channels)


@transaction.atomic
def mutate_llm_configs(raw_uuids, action):
    """Apply one action to every selected config or change none of them."""

    if action not in LLM_CONFIG_ACTIONS:
        raise AdminBulkMutationError(
            "action must be enable, disable, or delete."
        )
    config_uuids = _normalize_uuids(raw_uuids, "config_ids")
    configs = _locked_selection(LLMConfig, config_uuids, "LLM configs")
    queryset = LLMConfig.objects.filter(
        pk__in=[config.pk for config in configs]
    )
    if action == "delete":
        queryset.delete()
    else:
        queryset.update(is_active=action == "enable")
    return len(configs)
