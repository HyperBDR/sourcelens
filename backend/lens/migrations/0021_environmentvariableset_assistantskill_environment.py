import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0020_assistant_description"),
    ]

    operations = [
        migrations.CreateModel(
            name="EnvironmentVariableSet",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160, unique=True)),
                ("description", models.TextField(blank=True, default="")),
                ("encrypted_values", models.TextField(blank=True, default="")),
                ("enabled", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddField(
            model_name="assistantskill",
            name="environment_variable_set",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="skill_bindings",
                to="lens.environmentvariableset",
            ),
        ),
    ]
