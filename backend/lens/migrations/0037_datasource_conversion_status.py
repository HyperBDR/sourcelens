from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0036_rundiagnostic_progress"),
    ]

    operations = [
        migrations.AddField(
            model_name="datasource",
            name="last_conversion_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="datasource",
            name="last_conversion_status",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
    ]
