import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0051_plugin_invocations"),
    ]

    operations = [
        migrations.AddField(
            model_name="mcpserver",
            name="connection",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="mcp_adapters",
                to="lens.connection",
            ),
        ),
        migrations.AddField(
            model_name="mcpserver",
            name="tools",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="mcpserver",
            name="transport",
            field=models.CharField(
                choices=[
                    ("url", "URL"),
                    ("stdio", "STDIO"),
                    ("plugin", "Plugin Adapter"),
                ],
                max_length=16,
            ),
        ),
    ]
