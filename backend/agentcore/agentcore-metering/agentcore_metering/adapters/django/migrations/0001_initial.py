# Generated for agentcore_metering adapter (table llm_tracker_usage)

import uuid

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
            name="LLMUsage",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "model",
                    models.CharField(
                        db_index=True,
                        help_text="LLM model name used for this call",
                        max_length=200,
                    ),
                ),
                (
                    "prompt_tokens",
                    models.IntegerField(
                        default=0,
                        help_text="Number of input/prompt tokens used",
                    ),
                ),
                (
                    "completion_tokens",
                    models.IntegerField(
                        default=0,
                        help_text=(
                            "Number of output/completion tokens generated"
                        ),
                    ),
                ),
                (
                    "total_tokens",
                    models.IntegerField(
                        db_index=True,
                        default=0,
                        help_text="Total tokens used (prompt + completion)",
                    ),
                ),
                (
                    "cached_tokens",
                    models.IntegerField(
                        default=0,
                        help_text="Number of cached tokens (if applicable)",
                    ),
                ),
                (
                    "reasoning_tokens",
                    models.IntegerField(
                        default=0,
                        help_text="Number of reasoning tokens (for o1 models)",
                    ),
                ),
                (
                    "success",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        help_text="Whether the LLM call succeeded",
                    ),
                ),
                (
                    "error",
                    models.TextField(
                        blank=True,
                        help_text="Error message if the call failed",
                        null=True,
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text=(
                            "Context information (e.g. node_name, "
                            "workflow_type)"
                        ),
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        help_text="Timestamp when this LLM call was made",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        help_text="User who triggered this LLM call",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="llm_usages",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "LLM Usage",
                "verbose_name_plural": "LLM Usages",
                "db_table": "llm_tracker_usage",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="llmusage",
            index=models.Index(
                fields=["user", "-created_at"],
                name="llm_track_user_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="llmusage",
            index=models.Index(
                fields=["model", "-created_at"],
                name="llm_track_model_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="llmusage",
            index=models.Index(
                fields=["total_tokens", "-created_at"],
                name="llm_track_tokens_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="llmusage",
            index=models.Index(
                fields=["success", "-created_at"],
                name="llm_track_success_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="llmusage",
            index=models.Index(
                fields=["created_at"],
                name="llm_track_created_at_idx",
            ),
        ),
    ]
