# Remove ModelStrategy; config resolution uses first active by order only.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("agentcore_metering", "0006_llm_config_list_and_strategy"),
    ]

    operations = [
        migrations.DeleteModel(name="ModelStrategy"),
    ]
