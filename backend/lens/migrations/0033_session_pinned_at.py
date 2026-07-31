from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lens", "0032_session_semantic_title_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="session",
            name="pinned_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
            ),
        ),
    ]
