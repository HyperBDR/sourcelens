from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0053_legacy_integration_migrations"),
    ]

    operations = [
        migrations.AlterField(
            model_name="datasource",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("git", "Git"),
                    ("feishu", "Feishu"),
                    ("jira", "Jira"),
                    ("managed_workspace", "Managed Workspace"),
                ],
                max_length=32,
            ),
        ),
    ]
