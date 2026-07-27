from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0023_sharedqafile"),
    ]

    operations = [
        migrations.AddField(
            model_name="assistant",
            name="token_budget_profile",
            field=models.CharField(
                choices=[("standard", "Standard"), ("deep", "Deep")],
                default="standard",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="runexecution",
            name="token_budget_final_reserve_tokens",
            field=models.PositiveIntegerField(default=40000),
        ),
        migrations.AddField(
            model_name="runexecution",
            name="token_budget_max_tokens",
            field=models.PositiveIntegerField(default=200000),
        ),
        migrations.AddField(
            model_name="runexecution",
            name="token_budget_profile",
            field=models.CharField(
                choices=[("standard", "Standard"), ("deep", "Deep")],
                default="standard",
                max_length=16,
            ),
        ),
    ]
