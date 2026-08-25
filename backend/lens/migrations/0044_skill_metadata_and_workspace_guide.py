from django.db import migrations, models


def migrate_skill_identity(apps, schema_editor):
    """Preserve package names and classify legacy workspace guides."""

    Skill = apps.get_model("lens", "Skill")
    for skill in Skill.objects.all().iterator():
        skill.package_name = skill.slug or ""
        if (skill.slug or "").endswith("-workspace-guide"):
            skill.kind = "workspace_guide"
        skill.save(update_fields=["package_name", "kind"])


def migrate_workspace_guides(apps, schema_editor):
    """Move legacy Workspace Guide content onto its Assistant."""

    Assistant = apps.get_model("lens", "Assistant")
    AssistantSkill = apps.get_model("lens", "AssistantSkill")

    for binding in AssistantSkill.objects.filter(
        skill__kind="workspace_guide",
        enabled=True,
    ).select_related("assistant", "skill"):
        definition = binding.skill.definition or {}
        content = (
            definition.get("content")
            if isinstance(definition, dict)
            else definition
        )
        content = str(content or "").strip()
        if content and not binding.assistant.workspace_guide:
            Assistant.objects.filter(pk=binding.assistant_id).update(
                workspace_guide=content,
            )
        binding.enabled = False
        binding.save(update_fields=["enabled"])


class Migration(migrations.Migration):

    dependencies = [("lens", "0043_runtraceevent")]

    operations = [
        migrations.AddField(
            model_name="skill",
            name="source_ref",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="skill",
            name="source_path",
            field=models.CharField(
                blank=True,
                default="",
                max_length=500,
            ),
        ),
        migrations.AddField(
            model_name="skill",
            name="latest_source_ref",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="skill",
            name="source_checked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="skill",
            name="package_name",
            field=models.CharField(
                blank=True,
                default="",
                max_length=180,
            ),
        ),
        migrations.AddField(
            model_name="skill",
            name="kind",
            field=models.CharField(
                default="standard",
                max_length=32,
            ),
        ),
        migrations.RunPython(
            migrate_skill_identity,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="skill",
            name="slug",
        ),
        migrations.AddField(
            model_name="assistant",
            name="workspace_guide",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RunPython(
            migrate_workspace_guides,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
