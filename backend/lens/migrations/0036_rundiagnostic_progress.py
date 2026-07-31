"""Add execution progress tracking to RunDiagnostic."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lens", "0035_rundiagnostic_language"),
    ]

    operations = [
        migrations.AddField(
            model_name="rundiagnostic",
            name="progress",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Execution stage and detail while the diagnosis is pending.",
            ),
        ),
    ]
