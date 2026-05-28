# Add optional user FK to NotificationChannel for scope (global vs user).

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("agentcore_notifier", "0004_notificationchannel_notificationrecord_uuid"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationchannel",
            name="user",
            field=models.ForeignKey(
                blank=True,
                help_text="Null for global channel; set for user-specific channel.",
                null=True,
                on_delete=models.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
