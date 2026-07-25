from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0020_assistant_description"),
    ]

    operations = [
        migrations.AlterField(
            model_name="datasourcecredential",
            name="auth_type",
            field=models.CharField(
                choices=[
                    ("none", "Public Access"),
                    ("https_token", "HTTPS Token"),
                    ("feishu_app", "Feishu App"),
                ],
                default="https_token",
                max_length=32,
            ),
        ),
    ]
