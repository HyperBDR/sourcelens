from django.db import migrations, models


def normalize_datasource_status(apps, schema_editor):
    """Move historical sync failures out of the enabled-state field."""

    DataSource = apps.get_model("lens", "DataSource")
    DataSource.objects.filter(status="error").update(status="active")


class Migration(migrations.Migration):

    dependencies = [
        ("lens", "0008_datasource_last_error"),
    ]

    operations = [
        migrations.RunPython(
            normalize_datasource_status,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="datasource",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("disabled", "Disabled"),
                ],
                default="active",
                max_length=16,
            ),
        ),
    ]
