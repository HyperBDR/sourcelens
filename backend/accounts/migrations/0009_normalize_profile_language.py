from django.db import migrations


def _normalize_language(value):
    """Map any stored language code to the supported en/zh-hans set."""

    code = (value or "").strip().lower().replace("_", "-")
    if code.startswith("zh"):
        return "zh-hans"
    if code.startswith("en"):
        return "en"
    return "en"


def normalize_profile_languages(apps, schema_editor):
    """Rewrite legacy Profile.language values (zh-CN, en-US, es, ...)."""

    Profile = apps.get_model("accounts", "Profile")
    for profile in Profile.objects.all().iterator():
        normalized = _normalize_language(profile.language)
        if normalized != profile.language:
            profile.language = normalized
            profile.save(update_fields=["language"])


def reverse_normalize_profile_languages(apps, schema_editor):
    """No-op: legacy codes are not restored once rewritten."""


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_alter_profile_language"),
    ]

    operations = [
        migrations.RunPython(
            normalize_profile_languages,
            reverse_normalize_profile_languages,
        ),
    ]
