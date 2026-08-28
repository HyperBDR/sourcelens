from django.db import migrations, models
import django.db.models.deletion


def migrate_assistant_capabilities(apps, schema_editor):
    """Set Assistant capabilities and initial smart-routing descriptions."""

    del schema_editor
    Assistant = apps.get_model("lens", "Assistant")
    AssistantMCP = apps.get_model("lens", "AssistantMCP")
    AssistantSkill = apps.get_model("lens", "AssistantSkill")
    supported = {"general_chat", "code_analysis", "knowledge_qa"}
    capability_descriptions = {
        "general_chat": "general chat and requests related to connected tools",
        "code_analysis": "code analysis, implementation review, and engineering troubleshooting",
        "knowledge_qa": "questions about configured workspaces or knowledge bases",
    }
    capability_names = {
        "general_chat": "General Chat",
        "code_analysis": "Code Analysis",
        "knowledge_qa": "Knowledge Q&A",
    }
    skills_by_assistant = {}
    for binding in AssistantSkill.objects.filter(
        enabled=True,
        skill__enabled=True,
    ).select_related("skill"):
        names = skills_by_assistant.setdefault(binding.assistant_id, [])
        if binding.skill.name and len(names) < 8:
            names.append(" ".join(binding.skill.name.split())[:80])
    mcps_by_assistant = {}
    for binding in AssistantMCP.objects.filter(
        enabled=True,
        mcp__enabled=True,
    ).select_related("mcp"):
        names = mcps_by_assistant.setdefault(binding.assistant_id, [])
        if binding.mcp.name and len(names) < 8:
            names.append(" ".join(binding.mcp.name.split())[:80])
    for assistant in Assistant.objects.all():
        capability = assistant.selected_task
        if capability == "qa":
            capability = "knowledge_qa"
        if capability not in supported:
            capability = "general_chat"
        parts = [
            f"Capability: {capability_names[capability]}.",
            f"Best suited for: {capability_descriptions[capability]}.",
        ]
        description = " ".join((assistant.description or "").split())[:320]
        if description:
            parts.append(f"Assistant overview: {description}.")
        skills = skills_by_assistant.get(assistant.pk, [])
        if skills:
            parts.append(f"Available Skills: {', '.join(skills)}.")
        mcps = mcps_by_assistant.get(assistant.pk, [])
        if mcps:
            parts.append(f"Available MCPs: {', '.join(mcps)}.")
        if assistant.selected_dirs:
            parts.append(
                "The workspace scope is limited to configured directories."
            )
        Assistant.objects.filter(pk=assistant.pk).update(
            capability=capability,
            routing_description="".join(parts)[:1000],
        )


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
                ],
                default="general_chat",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="assistant",
            name="routing_description",
            field=models.TextField(blank=True, default=""),
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
                choices=[("direct", "Direct"), ("smart", "Smart Collaboration")],
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
