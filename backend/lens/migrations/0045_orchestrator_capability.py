from django.db import migrations, models
import django.db.models.deletion


def migrate_assistant_capabilities(apps, schema_editor):
    """Set Assistant capabilities from the legacy execution task."""

    del schema_editor
    Assistant = apps.get_model("lens", "Assistant")
    supported = {"general_chat", "code_analysis", "knowledge_qa"}
    for assistant in Assistant.objects.all():
        capability = assistant.selected_task
        if capability == "qa":
            capability = "knowledge_qa"
        if capability not in supported:
            capability = "general_chat"
        Assistant.objects.filter(pk=assistant.pk).update(capability=capability)


class Migration(migrations.Migration):
    dependencies = [("lens", "0044_skill_metadata_and_workspace_guide")]

    operations = [
        migrations.AlterField(
            model_name="assistant",
            name="lensnode",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assistants",
                to="lens.lensnode",
            ),
        ),
        migrations.AddField(
            model_name="assistant",
            name="capability",
            field=models.CharField(
                choices=[
                    ("general_chat", "General Chat"),
                    ("code_analysis", "Code Analysis"),
                    ("knowledge_qa", "Knowledge Q&A"),
                    ("orchestrator", "Orchestrator"),
                ],
                default="general_chat",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="assistant",
            name="subagent_assistant_uuids",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="run",
            name="parent_run",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="delegated_runs",
                to="lens.run",
            ),
        ),
        migrations.AddIndex(
            model_name="run",
            index=models.Index(fields=["parent_run"], name="lens_run_parent_idx"),
        ),
        migrations.RunPython(migrate_assistant_capabilities),
        migrations.RemoveField(model_name="assistant", name="selected_task"),
        migrations.AddField(
            model_name="assistant",
            name="is_system",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="session",
            name="routing_mode",
            field=models.CharField(
                choices=[("direct", "Direct"), ("smart", "Smart routing")],
                default="direct",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="session",
            name="allowed_assistant_uuids",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
