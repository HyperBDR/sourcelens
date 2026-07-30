from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lens", "0030_alter_token_budget_profile_choices"),
    ]

    operations = [
        migrations.AddField(
            model_name="session",
            name="title_generation_status",
            field=models.CharField(
                choices=[
                    ("skipped", "Skipped"),
                    ("pending", "Pending"),
                    ("generating", "Generating"),
                    ("generated", "Generated"),
                    ("failed", "Failed"),
                ],
                default="skipped",
                db_default="skipped",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="session",
            name="title_manually_edited",
            field=models.BooleanField(db_default=False, default=False),
        ),
    ]
