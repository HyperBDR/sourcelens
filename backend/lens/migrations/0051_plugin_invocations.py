import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("lens", "0050_plugin_tool_snapshots"),
    ]

    operations = [
        migrations.CreateModel(
            name="PluginInvocation",
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
                    "kind",
                    models.CharField(
                        choices=[
                            ("datasource_sync", "Datasource Sync"),
                            ("tool_invoke", "Tool Invoke"),
                        ],
                        max_length=32,
                    ),
                ),
                ("plugin_key", models.CharField(max_length=64)),
                ("tool_key", models.CharField(blank=True, default="", max_length=128)),
                ("capability", models.CharField(blank=True, default="", max_length=128)),
                ("resource_summary", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("authorized", "Authorized"),
                            ("materialized", "Materialized"),
                        ],
                        default="authorized",
                        max_length=24,
                    ),
                ),
                ("materialized_at", models.DateTimeField(blank=True, null=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="plugin_invocations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "connection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="plugin_invocations",
                        to="lens.connection",
                    ),
                ),
                (
                    "datasource",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="plugin_invocations",
                        to="lens.datasource",
                    ),
                ),
                (
                    "lensnode",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="plugin_invocations",
                        to="lens.lensnode",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="plugin_invocations",
                        to="lens.run",
                    ),
                ),
                (
                    "snapshot",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="invocation_audit",
                        to="lens.executionsnapshot",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        )
    ]
