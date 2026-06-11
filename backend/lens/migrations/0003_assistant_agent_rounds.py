from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lens", "0002_assistant_postprocess_model_ref_mcpserver_version_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="assistant",
            name="agent_rounds",
            field=models.CharField(
                choices=[
                    ("flash", "极速"),
                    ("fast", "快速"),
                    ("balanced", "均衡"),
                    ("deep", "深度"),
                    ("max", "极限"),
                ],
                default="balanced",
                max_length=16,
            ),
        ),
    ]
