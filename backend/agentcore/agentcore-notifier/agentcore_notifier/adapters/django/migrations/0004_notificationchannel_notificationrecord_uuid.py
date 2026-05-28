# Add uuid to NotificationChannel and NotificationRecord for external API.
# Add nullable first, backfill per row, then set unique and non-null.

import uuid

from django.db import migrations, models


def backfill_channel_uuids(apps, schema_editor):
    """Assign unique uuid to each existing NotificationChannel."""
    NotificationChannel = apps.get_model("agentcore_notifier", "NotificationChannel")
    for ch in NotificationChannel.objects.all():
        ch.uuid = uuid.uuid4()
        ch.save(update_fields=["uuid"])


def backfill_record_uuids(apps, schema_editor):
    """Assign unique uuid to each existing NotificationRecord."""
    NotificationRecord = apps.get_model("agentcore_notifier", "NotificationRecord")
    for rec in NotificationRecord.objects.all():
        rec.uuid = uuid.uuid4()
        rec.save(update_fields=["uuid"])


class Migration(migrations.Migration):

    dependencies = [
        ("agentcore_notifier", "0003_notificationrecord_channel_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationchannel",
            name="uuid",
            field=models.UUIDField(
                db_index=True,
                editable=False,
                null=True,
            ),
        ),
        migrations.RunPython(backfill_channel_uuids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="notificationchannel",
            name="uuid",
            field=models.UUIDField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="notificationrecord",
            name="uuid",
            field=models.UUIDField(
                db_index=True,
                editable=False,
                null=True,
            ),
        ),
        migrations.RunPython(backfill_record_uuids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="notificationrecord",
            name="uuid",
            field=models.UUIDField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                unique=True,
            ),
        ),
    ]
