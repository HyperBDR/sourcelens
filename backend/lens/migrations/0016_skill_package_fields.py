from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lens", "0015_datasourcecredential_no_auth"),
    ]

    operations = [
        migrations.AddField(
            model_name="skill",
            name="package_hash",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="skill",
            name="package_manifest",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="skill",
            name="package_path",
            field=models.CharField(blank=True, default="", max_length=700),
        ),
        migrations.AddField(
            model_name="skill",
            name="package_size",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="skill",
            name="source_type",
            field=models.CharField(blank=True, default="manual", max_length=32),
        ),
        migrations.AddField(
            model_name="skill",
            name="source_url",
            field=models.CharField(blank=True, default="", max_length=1000),
        ),
    ]
