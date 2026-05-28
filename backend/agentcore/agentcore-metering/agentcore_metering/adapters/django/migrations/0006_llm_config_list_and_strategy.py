# Multiple LLM configs per scope + strategy (list + strategy menu)

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("agentcore_metering", "0005_cost_and_currency"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="llmconfig",
            name="model_type",
            field=models.CharField(
                db_index=True,
                default="llm",
                help_text="Model capability: llm (only supported for now).",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="llmconfig",
            name="is_active",
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text="If false, this config is not used when resolving.",
            ),
        ),
        migrations.AddField(
            model_name="llmconfig",
            name="order",
            field=models.PositiveSmallIntegerField(
                db_index=True,
                default=0,
                help_text="Order for strategy (e.g. first or round-robin).",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="llmconfig",
            name="agentcore_metering_llm_config_scope_user_unique",
        ),
        migrations.RemoveConstraint(
            model_name="llmconfig",
            name="agentcore_metering_llm_config_single_global",
        ),
        migrations.AlterModelOptions(
            name="llmconfig",
            options={
                "ordering": ["order", "id"],
                "verbose_name": "LLM Config",
                "verbose_name_plural": "LLM Configs",
            },
        ),
        migrations.CreateModel(
            name="ModelStrategy",
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
                        max_length=20,
                    ),
                ),
                (
                    "model_type",
                    models.CharField(
                        db_index=True, default="llm", max_length=30
                    ),
                ),
                (
                    "strategy",
                    models.CharField(
                        choices=[
                            ("first", "First (by order)"),
                            ("round_robin", "Round-robin"),
                        ],
                        default="first",
                        max_length=20,
                    ),
                ),
                ("state", models.JSONField(
                    blank=True,
                    default=dict,
                    help_text=(
                        "Strategy state, e.g. last_index for round_robin."
                    ),
                )),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="llm_strategies",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Model Strategy",
                "verbose_name_plural": "Model Strategies",
                "db_table": "agentcore_metering_model_strategy",
            },
        ),
        migrations.AddConstraint(
            model_name="modelstrategy",
            constraint=models.UniqueConstraint(
                fields=("scope", "user", "model_type"),
                name="agentcore_metering_strategy_scope_user_type_unique",
            ),
        ),
    ]
