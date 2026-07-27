from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0024_assistant_runexecution_token_budget"),
    ]

    operations = [
        migrations.AddField(
            model_name="run",
            name="outcome",
            field=models.CharField(
                blank=True,
                choices=[
                    ("completed", "Completed"),
                    ("partial", "Partial"),
                    ("blocked", "Blocked"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="run",
            name="termination_detail",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
