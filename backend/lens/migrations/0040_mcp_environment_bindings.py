import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0039_runexecution_admission_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="mcpserver",
            name="environment",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="assistantmcp",
            name="environment_variable_set",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="mcp_bindings",
                to="lens.environmentvariableset",
            ),
        ),
    ]
