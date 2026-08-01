from django.db import migrations, models


def canonicalize_answer_languages(apps, schema_editor):
    """Normalize legacy values to supported AI answer languages."""

    del schema_editor
    profile_model = apps.get_model("accounts", "Profile")
    for profile in profile_model.objects.only("id", "language").iterator():
        normalized = str(profile.language or "").replace("_", "-").lower()
        prefix = normalized.split("-", 1)[0]
        language = {
            "en": "en-US",
            "zh": "zh-CN",
        }.get(prefix, "en-US")
        if profile.language != language:
            profile_model.objects.filter(pk=profile.pk).update(
                language=language
            )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_role_profile_preferred_platform")]

    operations = [
        migrations.RunPython(
            canonicalize_answer_languages,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="profile",
            name="language",
            field=models.CharField(
                choices=[
                    ("en-US", "English"),
                    ("zh-CN", "简体中文"),
                ],
                default="en-US",
                help_text=(
                    "Specifies the language used by AI when generating "
                    "summaries, titles, and metadata. This is a global "
                    "setting shared across all applications."
                ),
                max_length=10,
            ),
        ),
    ]
