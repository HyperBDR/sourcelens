import base64
import io
import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import httpx

from .tls import create_config_ssl_context

MAX_SKILL_PACKAGE_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class RuntimeResources:
    """Materialized per-run resource paths."""

    root: Path
    skill_paths: list[str]
    context_skill_contents: list[str]
    skill_environments: dict[str, dict[str, str]]
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
    skill_environments = {}
    context_skill_contents = []
    general_chat_mode = command.get("task") == "general_chat"
    for skill in command.get("loaded_skills") or []:
        skill_path = _materialize_skill(config, cache_root, skills_root, skill)
        if skill_path is not None:
            skill_paths.append(str(skill_path))
            environment = skill.get("environment") or {}
            if isinstance(environment, dict):
                skill_environments[skill_path.name] = {
                    str(key): str(value)
                    for key, value in environment.items()
                }
        context_content = _context_skill_content(
            skill,
            skill_path=skill_path,
            force=general_chat_mode,
        )
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
                "skill_paths": skill_paths,
                "mcp_count": len(mcp_configs),
                "runtime_root": str(runtime_root),
            },
        )

    return RuntimeResources(
        root=runtime_root,
        skill_paths=skill_paths,
        context_skill_contents=context_skill_contents,
        skill_environments=skill_environments,
        mcp_config_path=mcp_config_path,
    )


def cleanup_runtime_resources(resources):
    """Remove per-run runtime resources but keep shared cache."""

    shutil.rmtree(resources.root, ignore_errors=True)


def _materialize_skill(config, cache_root, skills_root, skill):
    """Write one skill snapshot to cache and link it into the run."""

    skill_uuid = str(skill.get("skill_uuid") or "").strip()
    content_hash = str(skill.get("content_hash") or "").replace(":", "-")
    slug = _safe_name(skill.get("skill_slug") or skill.get("skill_name"))
    if not skill_uuid or not content_hash or not slug:
        return None

    cache_dir = cache_root / "skills" / skill_uuid / content_hash
    complete_file = cache_dir / ".complete"
    if not complete_file.exists():
        _rebuild_skill_cache(config, cache_dir, skill)

    runtime_dir = skills_root / slug
    _copy_dir(cache_dir, runtime_dir)
    return Path("skills") / slug


def _rebuild_skill_cache(config, cache_dir, skill):
    """Rebuild one Skill cache directory atomically."""

    parent = cache_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{cache_dir.name}.",
            suffix=".tmp",
            dir=parent,
        )
    )
    try:
        package_files = skill.get("package_files") or []
        if package_files:
            _write_skill_package(temp_dir, package_files)
        elif skill.get("package_hash"):
            archive = _download_skill_package(config, skill)
            _safe_extract_zip(archive, temp_dir)
        else:
            (temp_dir / "SKILL.md").write_text(
                _skill_markdown(skill),
                encoding="utf-8",
            )
        _write_json(temp_dir / "metadata.json", _skill_metadata(skill))
        (temp_dir / ".complete").write_text("ok\n", encoding="utf-8")
        if (cache_dir / ".complete").exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            return
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)
        os.replace(temp_dir, cache_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _download_skill_package(config, skill):
    """Download a Skill package zip from the control plane."""

    skill_uuid = str(skill.get("skill_uuid") or "").strip()
    package_hash = str(skill.get("package_hash") or "").strip()
    if not skill_uuid:
        raise ValueError("skill_uuid is required to download a Skill package")
    url = _skill_package_url(config.ai_gateway_url, skill_uuid)
    with httpx.Client(
        timeout=config.request_timeout_s,
        verify=create_config_ssl_context(config),
    ) as client:
        response = client.get(
            url,
            headers={"Authorization": f"Bearer {config.token}"},
            params={"hash": package_hash} if package_hash else None,
        )
        response.raise_for_status()
        data = response.content
    if len(data) > MAX_SKILL_PACKAGE_BYTES:
        raise ValueError("Skill package download exceeds size limit")
    return data


def _skill_package_url(ai_gateway_url, skill_uuid):
    """Return the package endpoint URL derived from the AI gateway URL."""

    base = str(ai_gateway_url).rstrip("/")
    suffix = "/ai-gateway"
    if base.endswith(suffix):
        base = base[: -len(suffix)]
    return f"{base}/skills/{skill_uuid}/package/"


def _safe_extract_zip(data, target_dir):
    """Extract a zip archive into target_dir with path safety checks."""

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        prefix = _single_root_prefix(archive.infolist())
        for info in archive.infolist():
            name = _strip_zip_prefix(info.filename, prefix)
            relative_path = _safe_relative_package_path(name)
            if relative_path is None:
                continue
            if info.is_dir():
                (target_dir / relative_path).mkdir(parents=True, exist_ok=True)
                continue
            target = target_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _single_root_prefix(infos):
    """Return a removable single top-level zip directory prefix."""

    roots = set()
    has_root_skill = False
    for info in infos:
        path = PurePosixPath(str(info.filename).replace("\\", "/"))
        parts = [part for part in path.parts if part not in {"", "."}]
        if not parts or ".." in parts:
            continue
        if parts == ["SKILL.md"]:
            has_root_skill = True
        roots.add(parts[0])
    if has_root_skill or len(roots) != 1:
        return ""
    return next(iter(roots))


def _strip_zip_prefix(name, prefix):
    """Strip one top-level zip directory prefix when present."""

    text = str(name or "").replace("\\", "/").strip()
    if not prefix:
        return text
    path = PurePosixPath(text)
    if path.parts and path.parts[0] == prefix:
        return PurePosixPath(*path.parts[1:]).as_posix()
    return text


def _write_skill_package(cache_dir, package_files):
    """Write a packaged Skill snapshot into the cache directory."""

    for item in package_files:
        relative_path = _safe_relative_package_path(item.get("path"))
        if relative_path is None:
            continue
        content = base64.b64decode(str(item.get("content_b64") or ""))
        target = cache_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def _safe_relative_package_path(value):
    """Return a safe package-relative path or None."""

    text = str(value or "").replace("\\", "/").strip()
    path = PurePosixPath(text)
    if not text or text.startswith("/") or ".." in path.parts:
        return None
    return Path(*path.parts)


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


def _context_skill_content(skill, skill_path=None, force=False):
    """Return prompt-injected content for context skills."""

    load_config = skill.get("load_config") or {}
    if not force and not load_config.get("inject"):
        return ""
    body = _skill_body(skill.get("definition") or {}).strip()
    if not body and not force:
        return ""
    name = skill.get("skill_name") or skill.get("skill_slug") or "Skill"
    slug = skill.get("skill_slug") or name
    path_line = f"\nRuntime path: `{skill_path}`\n" if skill_path else ""
    manifest = skill.get("package_manifest") or {}
    manifest_line = ""
    if isinstance(manifest, dict):
        file_count = manifest.get("file_count")
        directories = manifest.get("directories") or []
        if file_count or directories:
            manifest_line = (
                f"\nPackage: {file_count or 0} files"
                f"; directories: {', '.join(directories[:8]) or 'none'}\n"
            )
    if not body:
        body = (
            "This Skill has no instruction body in its SKILL.md snapshot. "
            "Use its bundled scripts and resources when they match the "
            "user's request."
        )
    return f"## {name}\n\nSlug: `{slug}`{path_line}{manifest_line}\n{body[:12000]}"


def _skill_metadata(skill):
    """Return serializable skill cache metadata."""

    return {
        "uuid": skill.get("skill_uuid"),
        "slug": skill.get("skill_slug"),
        "name": skill.get("skill_name"),
        "version": skill.get("version"),
        "content_hash": skill.get("content_hash"),
        "load_config": skill.get("load_config") or {},
        "api": (skill.get("definition") or {}).get("api") or {},
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
