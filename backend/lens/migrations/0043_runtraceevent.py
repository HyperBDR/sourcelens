import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0042_run_clarification_state"),
    ]

    operations = [
        migrations.CreateModel(
            name="RunTraceEvent",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("event_id", models.UUIDField()),
                ("sequence", models.PositiveBigIntegerField()),
                ("attempt", models.PositiveIntegerField(default=1)),
                ("event_type", models.CharField(max_length=128)),
                ("timestamp", models.DateTimeField()),
                (
                    "checkpoint_id",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                ("turn", models.PositiveIntegerField(blank=True, null=True)),
                ("step", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "call_id",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                (
                    "parent_call_id",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="trace_events",
                        to="lens.run",
                    ),
                ),
            ],
            options={
                "ordering": ["sequence"],
                "indexes": [
                    models.Index(
                        fields=["run", "sequence"],
                        name="lens_trace_run_seq_idx",
                    ),
                    models.Index(
                        fields=["run", "call_id"],
                        name="lens_trace_run_call_idx",
                    ),
                    models.Index(
                        fields=["run", "event_type"],
                        name="lens_trace_run_type_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("run", "event_id"),
                        name="lens_trace_run_event_uniq",
                    ),
                    models.UniqueConstraint(
                        fields=("run", "sequence"),
                        name="lens_trace_run_seq_uniq",
                    ),
                ],
            },
        ),
    ]
