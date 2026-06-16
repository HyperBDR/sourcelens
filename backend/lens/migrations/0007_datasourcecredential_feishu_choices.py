from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0006_datasourcecredential_datasource_credential"),
    ]

    operations = [
        migrations.AlterField(
            model_name="datasourcecredential",
            name="auth_type",
            field=models.CharField(
                choices=[
                    ("https_token", "HTTPS Token"),
                    ("feishu_app", "Feishu App"),
                ],
                default="https_token",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="datasourcecredential",
            name="provider",
            field=models.CharField(
                choices=[
                    ("github", "GitHub"),
                    ("gitlab", "GitLab"),
                    ("feishu", "Feishu"),
                    ("generic", "Generic"),
                ],
                default="generic",
                max_length=32,
            ),
        ),
    ]
