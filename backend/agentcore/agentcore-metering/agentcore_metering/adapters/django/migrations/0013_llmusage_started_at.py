from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "agentcore_metering",
            "0012_alter_llmconfig_options_alter_llmconfig_is_default",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="llmusage",
            name="started_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="When the LLM request started (t_start).",
                null=True,
            ),
        ),
    ]
