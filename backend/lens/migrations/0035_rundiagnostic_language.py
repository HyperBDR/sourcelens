"""Add the request-time UI language to RunDiagnostic."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "lens",
            "0034_runexecution_runtime_snapshot_rundiagnosticevidence_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="rundiagnostic",
            name="language",
            field=models.CharField(
                default="en",
                help_text=(
                    "UI language active when the diagnosis was requested."
                ),
                max_length=16,
            ),
        ),
    ]
