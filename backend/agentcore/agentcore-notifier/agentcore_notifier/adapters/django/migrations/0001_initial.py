# Initial migration for agentcore_notifier Django adapter.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationRecord",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("source_app", models.CharField(max_length=100)),
                ("source_type", models.CharField(blank=True, max_length=100)),
                ("source_id", models.CharField(blank=True, max_length=100)),
                (
                    "source_metadata",
                    models.JSONField(blank=True, default=dict),
                ),
                (
                    "channel",
                    models.CharField(default="webhook", max_length=50),
                ),
                (
                    "provider_type",
                    models.CharField(
                        choices=[
                            ("feishu", "Feishu"),
                            ("wecom", "WeCom"),
                            ("wechat", "WeChat Work"),
                            ("email", "Email"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                (
                    "target",
                    models.JSONField(blank=True, default=dict),
                ),
                ("payload", models.JSONField()),
                (
                    "template_key",
                    models.CharField(blank=True, max_length=100),
                ),
                (
                    "locale",
                    models.CharField(blank=True, max_length=20),
                ),
                (
                    "content_metadata",
                    models.JSONField(blank=True, default=dict),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("success", "Success"),
                            ("failed", "Failed"),
                            ("merged", "Merged"),
                            ("silenced", "Silenced"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("response", models.JSONField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                (
                    "provider_message_id",
                    models.CharField(blank=True, max_length=255),
                ),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "notifier_notification_record",
                "ordering": ["-created_at"],
                "verbose_name": "Notification Record",
                "verbose_name_plural": "Notification Records",
            },
        ),
        migrations.CreateModel(
            name="NotifierConfig",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "scope",
                    models.CharField(
                        choices=[("global", "Global"), ("user", "User")],
                        db_index=True,
                        default="global",
                        max_length=20,
                    ),
                ),
                (
                    "key",
                    models.CharField(db_index=True, max_length=128),
                ),
                (
                    "value",
                    models.JSONField(
                        default=dict,
                        help_text="Config payload (JSON).",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        help_text="Null for global scope; set for user-level override.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "agentcore_notifier_config",
                "verbose_name": "Notifier Config",
                "verbose_name_plural": "Notifier Configs",
            },
        ),
        migrations.AddIndex(
            model_name="notificationrecord",
            index=models.Index(
                fields=[
                    "provider_type",
                    "source_app",
                    "source_type",
                    "source_id",
                ],
                name="notifier_no_provider_source_4a7c80_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="notificationrecord",
            index=models.Index(
                fields=["status", "created_at"],
                name="notifier_no_status_created_2b0f3a_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="notificationrecord",
            index=models.Index(
                fields=["created_at"],
                name="notifier_no_created_at_1f8d9e_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="notifierconfig",
            constraint=models.UniqueConstraint(
                fields=("scope", "user", "key"),
                name="agentcore_notifier_config_scope_user_key_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="notifierconfig",
            index=models.Index(
                fields=["scope", "key"],
                name="agentcore_notifier_config_scope_key_idx",
            ),
        ),
    ]
