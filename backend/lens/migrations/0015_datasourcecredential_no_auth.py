from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0014_datasourcecredential_endpoint_scope"),
    ]

    operations = [
        migrations.AlterField(
            model_name="datasourcecredential",
            name="auth_type",
            field=models.CharField(
                choices=[
                    ("none", "No Authentication"),
                    ("https_token", "HTTPS Token"),
                    ("feishu_app", "Feishu App"),
                ],
                default="https_token",
                max_length=32,
            ),
        ),
    ]
