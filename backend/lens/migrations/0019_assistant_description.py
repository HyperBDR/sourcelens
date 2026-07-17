from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lens", "0018_runoutputfile"),
    ]

    operations = [
        migrations.AddField(
            model_name="assistant",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
    ]
