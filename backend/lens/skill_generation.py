from pathlib import Path

from django.utils.text import slugify

from .models import AssistantSkill, Skill

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent / "skills"
WORKSPACE_GUIDE_SUFFIX = "workspace-guide"
WORKSPACE_GUIDE_LOAD_CONFIG = {
    "mode": "context",
    "inject": True,
}


def read_builtin_skill(skill_name):
    """Return the bundled SKILL.md content for a built-in skill."""

    path = BUILTIN_SKILLS_DIR / skill_name / "SKILL.md"
    return path.read_text(encoding="utf-8")


def workspace_guide_slug(assistant):
    """Return the deterministic Workspace Guide skill slug."""

    return f"{assistant.slug}-{WORKSPACE_GUIDE_SUFFIX}"


def sync_workspace_guide_skill(assistant, workspace_guide):
    """Create, update, or disable an assistant Workspace Guide skill."""

    if workspace_guide is None:
        return None

    enabled = bool(workspace_guide.get("enabled"))
    content = str(workspace_guide.get("content") or "").strip()
    slug = workspace_guide_slug(assistant)

    if not enabled or not content:
        _disable_workspace_guide_binding(assistant, slug)
        return None

    skill_md = build_workspace_guide_skill_md(
        assistant=assistant,
        content=content,
    )
    skill, _ = Skill.objects.update_or_create(
        slug=slug,
        defaults={
            "name": f"{assistant.name} Workspace Guide",
            "definition": {
                "content": skill_md,
                "description": (
                    "Workspace structure and search guidance for "
                    f"{assistant.name}."
                ),
            },
            "version": "1",
            "enabled": True,
        },
    )
    AssistantSkill.objects.update_or_create(
        assistant=assistant,
        skill=skill,
        defaults={
            "enabled": True,
            "load_config": WORKSPACE_GUIDE_LOAD_CONFIG,
        },
    )
    return skill


def build_workspace_guide_skill_md(*, assistant, content):
    """Build a complete Workspace Guide SKILL.md from user guidance."""

    skill_name = slugify(workspace_guide_slug(assistant))
    description = (
        "Use this skill when answering questions about the "
        f"{assistant.name} workspace structure, repository layout, search "
        "priority, or recent code changes."
    )
    selected_dirs = "\n".join(
        f"- {item.get('path')}"
        for item in assistant.selected_dirs or []
        if item.get("path")
    )
    return (
        "---\n"
        f"name: {skill_name}\n"
        f"description: {description}\n"
        "---\n\n"
        f"# {assistant.name} Workspace Guide\n\n"
        "## Selected Workspace Directories\n\n"
        f"{selected_dirs or '- No selected directories were configured.'}\n\n"
        "## Workspace Structure\n\n"
        f"{content}\n\n"
        "## Required Usage Rules\n\n"
        "- Treat this guide as authoritative for repository layout and "
        "search priority.\n"
        "- Prefer exact repository, product, or module matches before broad "
        "workspace searches.\n"
        "- If the selected workspace is a product-level directory, inspect "
        "direct child repositories before assuming the root is a Git repo.\n"
        "- For recent-change questions, inspect the most relevant repository "
        "first with git_log, then use git_diff only for commit ranges needed "
        "to explain the changes.\n"
        "- Do not repeatedly query the same repository with larger ranges "
        "unless previous evidence was insufficient.\n"
        "- After collecting evidence from the primary repository and one "
        "related repository, summarize before expanding further.\n"
        "- Classify recent changes as new features, bug fixes, "
        "build/deployment/config changes, or unclear from evidence.\n"
        "- If a path is a directory, search within it or choose a specific "
        "file instead of trying to read the directory as a file.\n"
    )


def get_workspace_guide_payload(assistant):
    """Return the persisted Workspace Guide payload for an assistant."""

    slug = workspace_guide_slug(assistant)
    binding = (
        assistant.skill_bindings.select_related("skill")
        .filter(skill__slug=slug)
        .first()
    )
    if binding is None:
        return {
            "enabled": False,
            "content": "",
        }
    return {
        "enabled": binding.enabled,
        "content": _workspace_guide_user_content(binding.skill.definition),
        "skill_uuid": str(binding.skill.uuid),
        "skill_slug": binding.skill.slug,
        "load_config": binding.load_config,
    }


def _disable_workspace_guide_binding(assistant, slug):
    """Disable an existing Workspace Guide binding if one exists."""

    AssistantSkill.objects.filter(
        assistant=assistant,
        skill__slug=slug,
    ).update(enabled=False)


def _workspace_guide_user_content(definition):
    """Extract the user-authored workspace guide section."""

    if isinstance(definition, str):
        text = definition
    else:
        text = (
            definition.get("content")
            or definition.get("markdown")
            or definition.get("skill_md")
            or ""
        )
    marker = "## Workspace Structure"
    rules_marker = "## Required Usage Rules"
    if marker not in text:
        return text.strip()
    section = text.split(marker, 1)[1]
    if rules_marker in section:
        section = section.split(rules_marker, 1)[0]
    return section.strip()
