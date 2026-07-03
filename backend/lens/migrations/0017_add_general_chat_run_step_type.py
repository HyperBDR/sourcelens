from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lens", "0016_skill_package_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="runstep",
            name="step_type",
            field=models.CharField(
                choices=[
                    ("query_rewrite", "Query Rewrite"),
                    ("multimodal", "Multimodal"),
                    ("retrieval", "Retrieval"),
                    ("general_chat", "General Chat"),
                    ("answer", "Answer"),
                    ("stream", "Stream"),
                ],
                max_length=32,
            ),
        ),
    ]
