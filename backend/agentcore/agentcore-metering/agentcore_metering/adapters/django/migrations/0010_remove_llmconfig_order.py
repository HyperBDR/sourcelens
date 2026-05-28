from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("agentcore_metering", "0009_rename_llm_track_user_created_idx_llm_tracker_user_id_5800dd_idx_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="llmconfig",
            name="order",
        ),
    ]

