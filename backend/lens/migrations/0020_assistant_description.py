from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lens", "0019_lensnode_disconnected_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="assistant",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
    ]
