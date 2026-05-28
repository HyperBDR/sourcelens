# Generated migration to update Profile defaults

from django.db import migrations


def update_existing_profiles_timezone(apps, schema_editor):
    """
    Update existing profiles with UTC timezone to Asia/Shanghai
    Only update profiles that still have the old default UTC timezone
    """
    Profile = apps.get_model('accounts', 'Profile')
    Profile.objects.filter(timezone='UTC').update(timezone='Asia/Shanghai')


def reverse_update_timezone(apps, schema_editor):
    """
    Reverse migration: set timezone back to UTC
    """
    Profile = apps.get_model('accounts', 'Profile')
    Profile.objects.filter(timezone='Asia/Shanghai').update(timezone='UTC')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_alter_profile_language'),
    ]

    operations = [
        migrations.RunPython(
            update_existing_profiles_timezone,
            reverse_update_timezone
        ),
    ]
