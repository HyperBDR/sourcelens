from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0040_mcp_environment_bindings"),
    ]

    operations = [
        migrations.AddField(
            model_name="run",
            name="citations",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="run",
            name="planned_evidence",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
