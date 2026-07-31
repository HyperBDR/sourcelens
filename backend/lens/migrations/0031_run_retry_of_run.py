import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0030_alter_token_budget_profile_choices"),
    ]

    operations = [
        migrations.AddField(
            model_name="run",
            name="retry_of_run",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="retry_runs",
                to="lens.run",
            ),
        ),
    ]
