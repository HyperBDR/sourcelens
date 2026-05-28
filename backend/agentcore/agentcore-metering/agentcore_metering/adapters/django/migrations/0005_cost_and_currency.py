# Replace cost_usd with cost + cost_currency for flexible multi-currency

from django.db import migrations, models


def _backfill_cost_and_currency(apps, schema_editor):
    LLMUsage = apps.get_model("agentcore_metering", "LLMUsage")
    for row in LLMUsage.objects.all():
        if getattr(row, "cost_usd", None) is not None:
            row.cost = row.cost_usd
            row.cost_currency = "USD"
            row.save(update_fields=["cost", "cost_currency"])


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("agentcore_metering", "0004_add_llm_usage_cost_usd"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmusage",
            name="cost",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                default=None,
                help_text=(
                    "Cost amount (use with cost_currency for multi-currency)"
                ),
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="llmusage",
            name="cost_currency",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="USD",
                help_text="ISO 4217 currency code (e.g. USD, CNY).",
                max_length=10,
            ),
        ),
        migrations.RunPython(_backfill_cost_and_currency, _noop_reverse),
        migrations.RemoveField(
            model_name="llmusage",
            name="cost_usd",
        ),
    ]
