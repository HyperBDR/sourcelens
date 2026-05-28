# NotificationChannel model: single table for webhook/email/sms channels.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agentcore_notifier", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationChannel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "channel_type",
                    models.CharField(
                        choices=[("webhook", "Webhook"), ("email", "Email"), ("sms", "SMS")],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("name", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "is_default",
                    models.BooleanField(
                        default=False,
                        help_text="If True, this channel is used for sending when no channel is specified.",
                    ),
                ),
                ("ordering", models.PositiveIntegerField(default=0)),
                (
                    "config",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Type-specific config, e.g. webhook: provider_type, url; email: smtp_host, port; sms: provider, api_key.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "notifier_channel",
                "ordering": ["ordering", "created_at"],
                "verbose_name": "Notification Channel",
                "verbose_name_plural": "Notification Channels",
            },
        ),
    ]
