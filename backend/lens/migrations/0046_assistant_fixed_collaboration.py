from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0045_orchestrator_capability"),
    ]

    operations = [
        migrations.AddField(
            model_name="assistant",
            name="routing_mode",
            field=models.CharField(
                choices=[
                    ("direct", "Direct"),
                    ("smart", "Smart Collaboration"),
                ],
                db_index=True,
                default="direct",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="assistant",
            name="collaboration_members",
            field=models.ManyToManyField(
                blank=True,
                related_name="collaboration_coordinators",
                symmetrical=False,
                to="lens.assistant",
            ),
        ),
    ]
