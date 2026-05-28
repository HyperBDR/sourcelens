"""
Data models for agentcore_notifier Django adapter.
"""
import uuid

from django.conf import settings
from django.db import models

from agentcore_notifier.constants import Channel, Provider, Status


class NotificationRecord(models.Model):
    """
    Single notification send attempt (source, target, content, result).
    """

    STATUS_CHOICES = [
        (Status.PENDING, "Pending"),
        (Status.SUCCESS, "Success"),
        (Status.FAILED, "Failed"),
        (Status.MERGED, "Merged"),
        (Status.SILENCED, "Silenced"),
    ]

    PROVIDER_TYPE_CHOICES = [
        (Provider.FEISHU, "Feishu"),
        (Provider.WECOM, "WeCom"),
        (Provider.WECHAT, "WeChat Work"),
        (Provider.EMAIL, "Email"),
    ]

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )
    source_app = models.CharField(max_length=100)
    source_type = models.CharField(max_length=100, blank=True)
    source_id = models.CharField(max_length=100, blank=True)
    source_metadata = models.JSONField(default=dict, blank=True)

    channel = models.CharField(max_length=50, default=Channel.WEBHOOK)
    channel_link = models.ForeignKey(
        "NotificationChannel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_records",
        db_column="channel_id",
    )
    provider_type = models.CharField(
        max_length=20, choices=PROVIDER_TYPE_CHOICES, db_index=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    target = models.JSONField(default=dict, blank=True)

    payload = models.JSONField()
    template_key = models.CharField(max_length=100, blank=True)
    locale = models.CharField(max_length=20, blank=True)
    content_metadata = models.JSONField(default=dict, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=Status.PENDING,
        db_index=True,
    )
    response = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True)

    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "notifier_notification_record"
        verbose_name = "Notification Record"
        verbose_name_plural = "Notification Records"
        indexes = [
            models.Index(
                fields=[
                    "provider_type",
                    "source_app",
                    "source_type",
                    "source_id",
                ]
            ),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.provider_type} - {self.source_app} - {self.status} - "
            f"{self.created_at}"
        )


class NotifierConfig(models.Model):
    """
    Config table (global and optional user scope), aligned with TaskConfig.
    """

    SCOPE_GLOBAL = "global"
    SCOPE_USER = "user"
    SCOPE_CHOICES = [(SCOPE_GLOBAL, "Global"), (SCOPE_USER, "User")]

    scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default=SCOPE_GLOBAL,
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Null for global scope; set for user-level override."
        ),
    )
    key = models.CharField(max_length=128, db_index=True)
    value = models.JSONField(default=dict, help_text="Config payload (JSON).")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agentcore_notifier_config"
        verbose_name = "Notifier Config"
        verbose_name_plural = "Notifier Configs"
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "user", "key"],
                name="agentcore_notifier_config_scope_user_key_uniq",
            )
        ]
        indexes = [models.Index(fields=["scope", "key"])]

    def __str__(self):
        u = f"user={self.user_id}" if self.user_id else "global"
        return f"NotifierConfig({self.scope},{u},key={self.key})"


class NotificationChannel(models.Model):
    """
    Single notification channel (webhook or email SMTP).
    Type-specific settings in config (JSON); one channel can be default.
    """

    TYPE_WEBHOOK = Channel.WEBHOOK
    TYPE_EMAIL = Channel.EMAIL
    TYPE_SMS = Channel.SMS
    TYPE_CHOICES = [
        (TYPE_WEBHOOK, "Webhook"),
        (TYPE_EMAIL, "Email"),
        (TYPE_SMS, "SMS"),
    ]

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )
    channel_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        db_index=True,
    )
    name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text=(
            "If True, this channel is used for sending when none specified."
        ),
    )
    ordering = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Send priority: smaller = higher; same value uses created_at."
        ),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Null for global channel; set for user-specific channel.",
    )
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Webhook: provider_type, url, message_prefix, sign_secret, "
            "merge_*, silence_window_minutes; email: smtp_*, from_email, etc."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifier_channel"
        verbose_name = "Notification Channel"
        verbose_name_plural = "Notification Channels"
        ordering = ["ordering", "created_at"]

    def __str__(self):
        name = self.name or self.get_channel_type_display()
        return f"{self.channel_type}: {name}"
