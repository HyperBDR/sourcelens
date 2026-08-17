from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0041_run_citations_and_planned_evidence"),
    ]

    operations = [
        migrations.AddField(
            model_name="run",
            name="clarification_answered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="run",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"),
                    ("running", "Running"),
                    ("streaming", "Streaming"),
                    ("awaiting_user_input", "Awaiting user input"),
                    ("done", "Done"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="queued",
                max_length=24,
            ),
        ),
    ]
