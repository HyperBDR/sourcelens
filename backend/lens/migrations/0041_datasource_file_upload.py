from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0040_mcp_environment_bindings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="datasource",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("git", "Git"),
                    ("feishu", "Feishu"),
                    ("file", "File Upload"),
                    ("managed_workspace", "Managed Workspace"),
                ],
                max_length=32,
            ),
        ),
    ]
