from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0026_archive_assistants"),
    ]

    operations = [
        migrations.AddField(
            model_name="run",
            name="feedback",
            field=models.CharField(
                blank=True,
                choices=[
                    ("positive", "Positive"),
                    ("negative", "Negative"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="run",
            name="feedback_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
