from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agentcore_metering", "0010_remove_llmconfig_order"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmconfig",
            name="is_default",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text=(
                    "If true, this global config is used when model_uuid is "
                    "not set. Only one global LLM config should be default."
                ),
            ),
        ),
    ]
