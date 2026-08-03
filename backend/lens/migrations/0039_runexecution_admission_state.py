from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0038_run_awaiting_resume"),
    ]

    operations = [
        migrations.AddField(
            model_name="runexecution",
            name="dispatch_id",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="runexecution",
            name="admitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="runexecution",
            name="checkpoint_ready_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
