"""Add the backward-compatible run resume deadline."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lens", "0037_datasource_conversion_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="run",
            name="resume_by",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
