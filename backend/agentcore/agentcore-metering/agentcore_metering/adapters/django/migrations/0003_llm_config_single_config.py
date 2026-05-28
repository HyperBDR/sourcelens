# Replace per-provider fields with single config JSONField

from django.db import migrations, models


def _migrate_to_single_config(apps, schema_editor):
    LLMConfig = apps.get_model("agentcore_metering", "LLMConfig")
    for row in LLMConfig.objects.all():
        provider = (row.provider or "openai").strip().lower()
        if provider == "azure_openai":
            row.config = row.azure_openai_config or {}
        elif provider == "gemini":
            row.config = row.gemini_config or {}
        else:
            row.config = row.openai_config or {}
        row.save(update_fields=["config"])


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("agentcore_metering", "0002_add_llm_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmconfig",
            name="config",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Provider-specific config (api_key, model, etc.).",
            ),
        ),
        migrations.RunPython(_migrate_to_single_config, _noop_reverse),
        migrations.RemoveField(model_name="llmconfig", name="openai_config"),
        migrations.RemoveField(
            model_name="llmconfig", name="azure_openai_config"
        ),
        migrations.RemoveField(model_name="llmconfig", name="gemini_config"),
        migrations.AlterField(
            model_name="llmconfig",
            name="provider",
            field=models.CharField(
                db_index=True,
                default="openai",
                help_text="Provider key, e.g. openai, azure_openai, gemini.",
                max_length=50,
            ),
        ),
    ]
