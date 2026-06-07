import json
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeResources:
    """Materialized per-run resource paths."""

    root: Path
    skill_paths: list[str]
    context_skill_contents: list[str]
    mcp_config_path: Path


def prepare_runtime_resources(config, command, emit_event=None):
    """Materialize Skill/MCP snapshots into cache and run directories."""

    workspace = Path(config.workspace_path)
    base = workspace / ".sourcelens"
    cache_root = base / "cache"
    runtime_root = base / "runtime" / "runs" / command["run_uuid"]
    skills_root = runtime_root / "skills"
    mcp_root = runtime_root / "mcp"

    skills_root.mkdir(parents=True, exist_ok=True)
    mcp_root.mkdir(parents=True, exist_ok=True)

    skill_paths = []
    context_skill_contents = []
    for skill in command.get("loaded_skills") or []:
        skill_path = _materialize_skill(cache_root, skills_root, skill)
        if skill_path is not None:
            skill_paths.append(str(skill_path))
        context_content = _context_skill_content(skill)
        if context_content:
            context_skill_contents.append(context_content)

    mcp_configs = []
    for mcp in command.get("loaded_mcps") or []:
        mcp_config = _materialize_mcp(cache_root, mcp_root, mcp)
        if mcp_config is not None:
            mcp_configs.append(mcp_config)

    mcp_config_path = mcp_root / "mcp.json"
    _write_json(mcp_config_path, {"servers": mcp_configs})

    if emit_event is not None:
        emit_event(
            "resources.materialized",
            {
                "skill_count": len(skill_paths),
                "mcp_count": len(mcp_configs),
                "runtime_root": str(runtime_root),
            },
        )

    return RuntimeResources(
        root=runtime_root,
        skill_paths=skill_paths,
        context_skill_contents=context_skill_contents,
        mcp_config_path=mcp_config_path,
    )


def cleanup_runtime_resources(resources):
    """Remove per-run runtime resources but keep shared cache."""

    shutil.rmtree(resources.root, ignore_errors=True)


def _materialize_skill(cache_root, skills_root, skill):
    """Write one skill snapshot to cache and link it into the run."""

    skill_uuid = str(skill.get("skill_uuid") or "").strip()
    content_hash = str(skill.get("content_hash") or "").replace(":", "-")
    slug = _safe_name(skill.get("skill_slug") or skill.get("skill_name"))
    if not skill_uuid or not content_hash or not slug:
        return None

    cache_dir = cache_root / "skills" / skill_uuid / content_hash
    skill_file = cache_dir / "SKILL.md"
    if not skill_file.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(_skill_markdown(skill), encoding="utf-8")
        _write_json(cache_dir / "metadata.json", _skill_metadata(skill))

    runtime_dir = skills_root / slug
    _copy_dir(cache_dir, runtime_dir)
    return Path("skills") / slug


def _materialize_mcp(cache_root, mcp_root, mcp):
    """Write one MCP snapshot to cache and link it into the run."""

    mcp_uuid = str(mcp.get("mcp_uuid") or "").strip()
    content_hash = str(mcp.get("content_hash") or "").replace(":", "-")
    name = _safe_name(mcp.get("mcp_name"))
    if not mcp_uuid or not content_hash or not name:
        return None

    cache_dir = cache_root / "mcp" / mcp_uuid / content_hash
    config_file = cache_dir / "mcp.json"
    if not config_file.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        _write_json(config_file, _mcp_payload(mcp))
        _write_json(cache_dir / "metadata.json", _mcp_metadata(mcp))

    runtime_dir = mcp_root / name
    _link_or_copy(cache_dir, runtime_dir)
    return {
        "name": mcp.get("mcp_name"),
        "transport": mcp.get("transport"),
        "endpoint": mcp.get("endpoint"),
        "config_path": str(runtime_dir / "mcp.json"),
        "load_config": mcp.get("load_config") or {},
    }


def _skill_markdown(skill):
    """Build SKILL.md content from the control-plane snapshot."""

    definition = skill.get("definition") or {}
    body = _skill_body(definition)
    if body.lstrip().startswith("---"):
        return f"{body.strip()}\n"
    description = ""
    if isinstance(definition, dict):
        description = (
            definition.get("description")
            or definition.get("summary")
            or ""
        )
    if not body:
        body = (
            f"# {skill.get('skill_name')}\n\n"
            "Use this skill when the current task matches its description."
        )
    return (
        "---\n"
        f"name: {skill.get('skill_slug') or skill.get('skill_name')}\n"
        f"description: {description or skill.get('skill_name')}\n"
        "---\n\n"
        f"{body.strip()}\n"
    )


def _skill_body(definition):
    """Return the canonical body text from a skill definition."""

    if isinstance(definition, str):
        return definition
    return (
        definition.get("content")
        or definition.get("markdown")
        or definition.get("skill_md")
        or definition.get("summary")
        or ""
    )


def _context_skill_content(skill):
    """Return prompt-injected content for context skills."""

    load_config = skill.get("load_config") or {}
    if not load_config.get("inject"):
        return ""
    body = _skill_body(skill.get("definition") or {}).strip()
    if not body:
        return ""
    name = skill.get("skill_name") or skill.get("skill_slug") or "Skill"
    return f"## {name}\n\n{body[:4000]}"


def _skill_metadata(skill):
    """Return serializable skill cache metadata."""

    return {
        "uuid": skill.get("skill_uuid"),
        "slug": skill.get("skill_slug"),
        "name": skill.get("skill_name"),
        "version": skill.get("version"),
        "content_hash": skill.get("content_hash"),
        "load_config": skill.get("load_config") or {},
    }


def _mcp_payload(mcp):
    """Return one MCP server config payload."""

    return {
        "name": mcp.get("mcp_name"),
        "transport": mcp.get("transport"),
        "endpoint": mcp.get("endpoint"),
        "config": mcp.get("config") or {},
        "load_config": mcp.get("load_config") or {},
    }


def _mcp_metadata(mcp):
    """Return serializable MCP cache metadata."""

    return {
        "uuid": mcp.get("mcp_uuid"),
        "name": mcp.get("mcp_name"),
        "version": mcp.get("version"),
        "content_hash": mcp.get("content_hash"),
    }


def _write_json(path, payload):
    """Write JSON payload to a path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _link_or_copy(source, target):
    """Link a cache directory into runtime, falling back to copy."""

    if target.exists() or target.is_symlink():
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)
    try:
        target.symlink_to(source, target_is_directory=True)
    except OSError:
        shutil.copytree(source, target)


def _copy_dir(source, target):
    """Copy a cache directory into runtime."""

    if target.exists() or target.is_symlink():
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)
    shutil.copytree(source, target)


def _safe_name(value):
    """Return a filesystem-safe resource name."""

    text = str(value or "").strip().lower()
    output = []
    for char in text:
        if char.isalnum() or char in {"-", "_"}:
            output.append(char)
        elif char.isspace():
            output.append("-")
    return "".join(output).strip("-_")
