# Rename execution table to agentcore_task_execution.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("agentcore_task_tracker", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelTable(
            name="taskexecution",
            table="agentcore_task_execution",
        ),
    ]
