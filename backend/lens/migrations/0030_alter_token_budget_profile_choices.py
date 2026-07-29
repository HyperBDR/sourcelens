from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0029_datasource_managed_workspace"),
    ]

    operations = [
        migrations.AlterField(
            model_name="assistant",
            name="token_budget_profile",
            field=models.CharField(
                choices=[
                    ("standard", "Standard"),
                    ("deep", "Deep"),
                    ("unlimited", "Unlimited"),
                ],
                default="standard",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="runexecution",
            name="token_budget_profile",
            field=models.CharField(
                choices=[
                    ("standard", "Standard"),
                    ("deep", "Deep"),
                    ("unlimited", "Unlimited"),
                ],
                default="standard",
                max_length=16,
            ),
        ),
    ]
