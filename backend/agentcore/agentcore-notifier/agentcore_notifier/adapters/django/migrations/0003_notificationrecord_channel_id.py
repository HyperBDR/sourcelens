# Add channel_id to NotificationRecord for per-channel merge scope.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("agentcore_notifier", "0002_webhookchannel"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationrecord",
            name="channel_link",
            field=models.ForeignKey(
                blank=True,
                db_column="channel_id",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="notification_records",
                to="NotificationChannel",
            ),
        ),
    ]
