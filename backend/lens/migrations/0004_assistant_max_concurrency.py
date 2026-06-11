from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lens", "0003_assistant_agent_rounds"),
    ]

    operations = [
        migrations.AddField(
            model_name="assistant",
            name="max_concurrency",
            field=models.PositiveSmallIntegerField(default=5),
        ),
    ]
