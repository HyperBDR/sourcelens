from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "lens",
            "0028_runexecution_agent_rounds_runexecution_run_timeout_s",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="datasource",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("git", "Git"),
                    ("feishu", "Feishu"),
                    ("managed_workspace", "Managed Workspace"),
                ],
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="datasource",
            name="availability_checked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="datasource",
            name="availability_message",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="datasource",
            name="availability_status",
            field=models.CharField(
                choices=[
                    ("unknown", "Unknown"),
                    ("available", "Available"),
                    ("unavailable", "Unavailable"),
                    ("error", "Error"),
                ],
                default="unknown",
                max_length=16,
            ),
        ),
    ]
