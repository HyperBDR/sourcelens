import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0052_mcp_plugin_adapters"),
    ]

    operations = [
        migrations.CreateModel(
            name="LegacyIntegrationMigration",
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
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "source_kind",
                    models.CharField(
                        choices=[
                            ("credential", "Credential"),
                            ("datasource", "Datasource"),
                        ],
                        max_length=16,
                    ),
                ),
                ("source_uuid", models.UUIDField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("migrated", "Migrated"),
                            ("manual_review", "Manual Review"),
                            ("rolled_back", "Rolled Back"),
                        ],
                        max_length=24,
                    ),
                ),
                ("reason", models.CharField(blank=True, default="", max_length=64)),
                ("details", models.JSONField(blank=True, default=dict)),
                (
                    "connection",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="legacy_migration_records",
                        to="lens.connection",
                    ),
                ),
                (
                    "datasource",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="legacy_migration_records",
                        to="lens.datasource",
                    ),
                ),
            ],
            options={"ordering": ["source_kind", "source_uuid"]},
        ),
        migrations.AddConstraint(
            model_name="legacyintegrationmigration",
            constraint=models.UniqueConstraint(
                fields=("source_kind", "source_uuid"),
                name="lens_legacy_migration_source_uniq",
            ),
        ),
    ]
