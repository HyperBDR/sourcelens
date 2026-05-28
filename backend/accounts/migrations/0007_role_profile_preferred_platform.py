from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_alter_profile_timezone'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Role',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'name',
                    models.CharField(
                        help_text='Human-readable role name.',
                        max_length=120,
                        unique=True,
                    ),
                ),
                (
                    'visible_features',
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text=(
                            'Feature keys visible to users who hold this role.'
                        ),
                    ),
                ),
                (
                    'preferred_platform',
                    models.CharField(
                        blank=True,
                        default='',
                        help_text='Default platform to open after login.',
                        max_length=50,
                    ),
                ),
                (
                    'is_active',
                    models.BooleanField(
                        default=True,
                        help_text=(
                            'Whether this role participates in access '
                            'calculation.'
                        ),
                    ),
                ),
                (
                    'groups',
                    models.ManyToManyField(
                        blank=True,
                        help_text='Groups whose members inherit this role.',
                        related_name='platform_roles',
                        to='auth.group',
                    ),
                ),
                (
                    'users',
                    models.ManyToManyField(
                        blank=True,
                        help_text='Users directly bound to this role.',
                        related_name='platform_roles',
                        to='auth.user',
                    ),
                ),
            ],
            options={
                'ordering': ['name', 'id'],
            },
        ),
        migrations.AddField(
            model_name='profile',
            name='preferred_platform',
            field=models.CharField(
                blank=True,
                default='',
                help_text=(
                    'Optional user-level preferred platform. If empty, '
                    'the effective role preference is used.'
                ),
                max_length=50,
            ),
        ),
    ]
