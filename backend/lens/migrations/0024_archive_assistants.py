from django.db import migrations, models


def archive_disabled_assistants(apps, schema_editor):
    """Map assistants retired by the former delete action to archived."""

    del schema_editor
    assistant = apps.get_model("lens", "Assistant")
    assistant.objects.filter(status="disabled").update(status="archived")


def disable_archived_assistants(apps, schema_editor):
    """Restore the legacy status value when rolling back."""

    del schema_editor
    assistant = apps.get_model("lens", "Assistant")
    assistant.objects.filter(status="archived").update(status="disabled")


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0023_sharedqafile"),
    ]

    operations = [
        migrations.RunPython(
            archive_disabled_assistants,
            disable_archived_assistants,
        ),
        migrations.AlterField(
            model_name="assistant",
            name="status",
            field=models.CharField(
                choices=[("active", "Active"), ("archived", "Archived")],
                default="active",
                max_length=16,
            ),
        ),
    ]
