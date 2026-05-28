import uuid

from django.db import migrations, models


def fill_llmconfig_uuid(apps, schema_editor):
    LLMConfig = apps.get_model("agentcore_metering", "LLMConfig")
    rows = list(LLMConfig.objects.filter(uuid__isnull=True).only("id", "uuid"))
    for row in rows:
        row.uuid = uuid.uuid4()
    if rows:
        LLMConfig.objects.bulk_update(rows, ["uuid"], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ("agentcore_metering", "0007_remove_modelstrategy"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmconfig",
            name="uuid",
            field=models.UUIDField(
                db_index=True,
                null=True,
                editable=False,
                help_text="Public identifier for API operations.",
            ),
        ),
        migrations.RunPython(
            fill_llmconfig_uuid,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="llmconfig",
            name="uuid",
            field=models.UUIDField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                help_text="Public identifier for API operations.",
                unique=True,
            ),
        ),
    ]
