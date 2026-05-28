# Initial migration for agentcore_task Django adapter.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TaskExecution",
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
                    "task_id",
                    models.CharField(
                        db_index=True,
                        help_text="Celery task ID",
                        max_length=255,
                        unique=True,
                    ),
                ),
                (
                    "task_name",
                    models.CharField(
                        db_index=True,
                        help_text="Task name (e.g. cloud_billing.tasks.collect_billing_data)",
                        max_length=255,
                    ),
                ),
                (
                    "module",
                    models.CharField(
                        db_index=True,
                        help_text="Module that owns this task (e.g. cloud_billing)",
                        max_length=100,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("STARTED", "Started"),
                            ("SUCCESS", "Success"),
                            ("FAILURE", "Failure"),
                            ("RETRY", "Retry"),
                            ("REVOKED", "Revoked"),
                        ],
                        db_index=True,
                        default="PENDING",
                        help_text="Current task status",
                        max_length=20,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        help_text="When the task was created",
                    ),
                ),
                (
                    "started_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When the task started execution",
                        null=True,
                    ),
                ),
                (
                    "finished_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When the task finished execution",
                        null=True,
                    ),
                ),
                (
                    "task_args",
                    models.JSONField(
                        blank=True,
                        help_text="Task arguments",
                        null=True,
                    ),
                ),
                (
                    "task_kwargs",
                    models.JSONField(
                        blank=True,
                        help_text="Task keyword arguments",
                        null=True,
                    ),
                ),
                (
                    "result",
                    models.JSONField(
                        blank=True,
                        help_text="Task result data",
                        null=True,
                    ),
                ),
                (
                    "error",
                    models.TextField(
                        blank=True,
                        help_text="Error message if task failed",
                        null=True,
                    ),
                ),
                (
                    "traceback",
                    models.TextField(
                        blank=True,
                        help_text="Error traceback if task failed",
                        null=True,
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Additional metadata for the task",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="User who triggered this task",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_tasks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Task Execution",
                "verbose_name_plural": "Task Executions",
                "db_table": "agentcore_task_tracker_execution",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(
                fields=["module", "status"],
                name="agentcore_t_module_7a8b2c_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(
                fields=["task_name", "status"],
                name="agentcore_t_task_na_9c4d1e_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(
                fields=["created_at"],
                name="agentcore_t_created_2f3a5b_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(
                fields=["status", "created_at"],
                name="agentcore_t_status_1b6c9d_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(
                fields=["module", "created_at"],
                name="agentcore_t_module_4e5f6a_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(
                fields=["created_by", "status"],
                name="agentcore_t_created_8d7e0f_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="taskexecution",
            index=models.Index(
                fields=["created_by", "created_at"],
                name="agentcore_t_created_3c2b1a_idx",
            ),
        ),
    ]
