# Add TaskConfig for global (and future user) task config.

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agentcore_task_tracker", "0002_rename_execution_table"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TaskConfig",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "scope",
                    models.CharField(
                        choices=[("global", "Global"), ("user", "User")],
                        db_index=True,
                        default="global",
                        max_length=20,
                    ),
                ),
                (
                    "key",
                    models.CharField(db_index=True, max_length=128),
                ),
                (
                    "value",
                    models.JSONField(
                        default=dict,
                        help_text='Config payload, e.g. {"retention_days": 30}.',
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        help_text="Null for global scope; set for user-level override.",
                        null=True,
                        on_delete=models.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "agentcore_task_config",
                "verbose_name": "Task Config",
                "verbose_name_plural": "Task Configs",
            },
        ),
        migrations.AddConstraint(
            model_name="taskconfig",
            constraint=models.UniqueConstraint(
                fields=("scope", "user", "key"),
                name="agentcore_task_config_scope_user_key_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="taskconfig",
            index=models.Index(
                fields=["scope", "key"],
                name="agentcore_task_config_scope_key_idx",
            ),
        ),
    ]
