"""Serializers for notification stats and config API."""
from rest_framework import serializers


class NotificationSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    total_sent = serializers.IntegerField()
    total_failed = serializers.IntegerField()
    total_merged = serializers.IntegerField()
    total_silenced = serializers.IntegerField()
    total_pending = serializers.IntegerField()


class NotificationStatsResponseSerializer(serializers.Serializer):
    summary = NotificationSummarySerializer()
    by_source = serializers.ListField(child=serializers.DictField())
    by_provider = serializers.ListField(child=serializers.DictField())
    summary_prev = serializers.DictField(required=False, allow_null=True)
    series = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_null=True,
    )


class NotificationRecordListSerializer(serializers.Serializer):
    uuid = serializers.UUIDField()
    source_app = serializers.CharField()
    source_type = serializers.CharField()
    source_id = serializers.CharField()
    provider_type = serializers.CharField()
    provider_display_name = serializers.CharField(
        required=False,
        allow_blank=True,
    )
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    sent_at = serializers.DateTimeField(allow_null=True)
    user_id = serializers.IntegerField(allow_null=True)


class NotificationRecordListResponseSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = serializers.ListField(child=serializers.DictField())
