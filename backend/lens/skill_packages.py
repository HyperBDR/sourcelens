"""Skill package import, validation, and export helpers."""

import hashlib
import io
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib import error as urlerror
from urllib import parse, request

from django.conf import settings
from django.db import transaction

from .environment_variables import (
    validate_environment_schema,
    validate_skill_api_policy,
)
from .models import Skill

MAX_ZIP_SIZE = 20 * 1024 * 1024
MAX_UNPACKED_SIZE = 50 * 1024 * 1024
MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_SKILL_MD_SIZE = 256 * 1024
MAX_FILE_COUNT = 300
MAX_GITHUB_DOWNLOAD_SIZE = MAX_ZIP_SIZE
GITHUB_TIMEOUT_SECONDS = 30
BLOCKED_PARTS = {".git", ".ssh", "__pycache__", "node_modules", ".venv"}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,179}$")


class SkillPackageError(ValueError):
    """Raised when a skill package is invalid or unsafe."""


def import_skill_zip(
    *,
    file_obj,
    original_name="",
    source_type="upload",
    source_url="",
):
    """Validate and persist a Skill zip package."""

    data = _read_limited(file_obj, MAX_ZIP_SIZE + 1)
    if len(data) > MAX_ZIP_SIZE:
        raise SkillPackageError("Skill package exceeds 20 MB.")
    if original_name and not str(original_name).lower().endswith(".zip"):
        raise SkillPackageError("Skill package must be a .zip file.")
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise SkillPackageError("Skill package must be a valid zip archive.")

    digest = hashlib.sha256(data).hexdigest()
    with tempfile.TemporaryDirectory() as temp_dir:
        extract_root = Path(temp_dir) / "extract"
        extract_root.mkdir()
        _safe_extract_zip(data, extract_root)
        skill_root = _find_skill_root(extract_root)
        skill_md = skill_root / "SKILL.md"
        metadata = _parse_skill_md(skill_md)
        metadata.update(_parse_sourcelens_config(skill_root))
        slug = _slug_from_metadata(metadata)
        manifest = _package_manifest(skill_root)
        package_root = skill_package_root(slug, digest)
        existing = Skill.objects.filter(slug=slug).first()
        if existing and (
            existing.package_hash != digest
            or existing.source_type != source_type
        ):
            raise SkillPackageError(
                f"Skill slug '{slug}' already exists. "
                "Use a different name or update it explicitly."
            )
        staged_root = package_root.with_name(f".{digest}.tmp")
        if staged_root.exists():
            shutil.rmtree(staged_root)
        staged_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill_root, staged_root)
        created_package_root = False
        try:
            if package_root.exists():
                shutil.rmtree(staged_root)
            else:
                staged_root.rename(package_root)
                created_package_root = True
            with transaction.atomic():
                skill, _created = Skill.objects.update_or_create(
                    slug=slug,
                    defaults={
                        "name": metadata["name"],
                        "definition": {
                            "description": metadata["description"],
                            "content": metadata["content"],
                            "skill_md": metadata["skill_md"],
                            "environment": metadata["environment"],
                            "api": metadata["api"],
                        },
                        "version": digest[:12],
                        "enabled": True,
                        "package_path": str(package_root),
                        "package_hash": digest,
                        "package_size": len(data),
                        "package_manifest": manifest,
                        "source_type": source_type,
                        "source_url": source_url,
                    },
                )
        except Exception:
            shutil.rmtree(staged_root, ignore_errors=True)
            if created_package_root:
                shutil.rmtree(package_root, ignore_errors=True)
            raise
    return skill


def update_skill_zip(
    skill,
    *,
    file_obj,
    original_name="",
    source_type="upload",
    source_url="",
):
    """Validate a Skill zip package and replace an existing Skill snapshot."""

    if skill.source_type != source_type:
        raise SkillPackageError(
            "Skill source type cannot be changed during update."
        )
    data = _read_limited(file_obj, MAX_ZIP_SIZE + 1)
    if len(data) > MAX_ZIP_SIZE:
        raise SkillPackageError("Skill package exceeds 20 MB.")
    if original_name and not str(original_name).lower().endswith(".zip"):
        raise SkillPackageError("Skill package must be a .zip file.")
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise SkillPackageError("Skill package must be a valid zip archive.")

    digest = hashlib.sha256(data).hexdigest()
    with tempfile.TemporaryDirectory() as temp_dir:
        extract_root = Path(temp_dir) / "extract"
        extract_root.mkdir()
        _safe_extract_zip(data, extract_root)
        skill_root = _find_skill_root(extract_root)
        metadata = _parse_skill_md(skill_root / "SKILL.md")
        metadata.update(_parse_sourcelens_config(skill_root))
        slug = _slug_from_metadata(metadata)
        if slug != skill.slug:
            raise SkillPackageError(
                "Updated package Skill name must match the existing Skill."
            )
        manifest = _package_manifest(skill_root)
        package_root = skill_package_root(slug, digest)
        staged_root = package_root.with_name(f".{digest}.tmp")
        if staged_root.exists():
            shutil.rmtree(staged_root)
        staged_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill_root, staged_root)
        old_package_path = skill.package_path
        created_package_root = False
        try:
            if package_root.exists():
                shutil.rmtree(staged_root)
            else:
                staged_root.rename(package_root)
                created_package_root = True
            with transaction.atomic():
                skill.name = metadata["name"]
                skill.definition = {
                    "description": metadata["description"],
                    "content": metadata["content"],
                    "skill_md": metadata["skill_md"],
                    "environment": metadata["environment"],
                    "api": metadata["api"],
                }
                skill.version = digest[:12]
                skill.enabled = True
                skill.package_path = str(package_root)
                skill.package_hash = digest
                skill.package_size = len(data)
                skill.package_manifest = manifest
                skill.source_url = source_url
                skill.save(
                    update_fields=[
                        "name",
                        "definition",
                        "version",
                        "enabled",
                        "package_path",
                        "package_hash",
                        "package_size",
                        "package_manifest",
                        "source_url",
                        "updated_at",
                    ]
                )
                transaction.on_commit(
                    lambda: _remove_old_package_path(
                        old_package_path,
                        str(package_root),
                    )
                )
        except Exception:
            shutil.rmtree(staged_root, ignore_errors=True)
            if created_package_root:
                shutil.rmtree(package_root, ignore_errors=True)
            raise
    return skill


def import_skill_from_github(url):
    """Download a public GitHub Skill zip and import it."""

    return _github_skill_zip(url, import_skill_zip)


def update_skill_from_github(skill, url):
    """Download a public GitHub Skill zip and update an existing Skill."""

    return _github_skill_zip(
        url,
        lambda **kwargs: update_skill_zip(skill, **kwargs),
    )


def _github_skill_zip(url, importer):
    """Download a public GitHub Skill zip and pass it to an importer."""

    zip_url = _github_zip_url(url)
    opener = request.build_opener(_GitHubRedirectHandler)
    req = request.Request(
        zip_url,
        headers={
            "Accept": "application/zip",
            "User-Agent": "SourceLens Skill Importer",
        },
    )
    try:
        with opener.open(req, timeout=GITHUB_TIMEOUT_SECONDS) as response:
            data = response.read(MAX_GITHUB_DOWNLOAD_SIZE + 1)
    except urlerror.HTTPError as exc:
        raise SkillPackageError(f"GitHub download failed: HTTP {exc.code}")
    except urlerror.URLError as exc:
        raise SkillPackageError(f"GitHub download failed: {exc.reason}")
    if len(data) > MAX_GITHUB_DOWNLOAD_SIZE:
        raise SkillPackageError("GitHub skill package exceeds 20 MB.")
    return importer(
        file_obj=io.BytesIO(data),
        original_name="github-skill.zip",
        source_type="github",
        source_url=url,
    )


class _GitHubRedirectHandler(request.HTTPRedirectHandler):
    """Validate each GitHub package redirect target before following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_github_download_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def skill_package_root(slug, package_hash):
    """Return persistent storage path for one Skill package snapshot."""

    return (
        Path(settings.STORAGE_ROOT)
        / "lens"
        / "skills"
        / slug
        / package_hash
    )


def package_zip_bytes(skill):
    """Return a downloadable zip archive for a Skill."""

    buffer = io.BytesIO()
    package_path = Path(skill.package_path) if skill.package_path else None
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if (
            package_path is not None
            and package_path.exists()
            and package_path.is_dir()
        ):
            for path in sorted(package_path.rglob("*")):
                if path.is_file():
                    archive.write(
                        path,
                        str(
                            PurePosixPath(skill.slug)
                            / path.relative_to(package_path)
                        ),
                    )
        else:
            archive.writestr(
                f"{skill.slug}/SKILL.md",
                _skill_md_from_definition(skill),
            )
            definition = skill.definition or {}
            environment = definition.get("environment") or []
            api = definition.get("api") or {}
            if environment or api:
                config = {"environment": environment}
                if api:
                    config["api"] = api
                archive.writestr(
                    f"{skill.slug}/sourcelens.json",
                    json.dumps(
                        config,
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                )
    buffer.seek(0)
    return buffer


def _read_limited(file_obj, limit):
    """Read at most limit bytes from an upload or stream."""

    if hasattr(file_obj, "chunks"):
        chunks = []
        total = 0
        for chunk in file_obj.chunks():
            total += len(chunk)
            if total > limit:
                chunks.append(chunk[: max(0, limit - (total - len(chunk)))])
                break
            chunks.append(chunk)
        return b"".join(chunks)
    return file_obj.read(limit)


def _safe_extract_zip(data, destination):
    """Extract a zip after checking file count, size, and paths."""

    total_size = 0
    files = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            files += 1
            if files > MAX_FILE_COUNT:
                raise SkillPackageError(
                    "Skill package contains too many files."
                )
            if info.file_size > MAX_FILE_SIZE:
                raise SkillPackageError(
                    "Skill package contains an oversized file."
                )
            total_size += info.file_size
            if total_size > MAX_UNPACKED_SIZE:
                raise SkillPackageError("Skill package unpacks over 50 MB.")
            _validate_zip_member(info)
        archive.extractall(destination)


def _validate_zip_member(info):
    """Reject unsafe zip member names or unsupported entries."""

    name = info.filename.replace("\\", "/")
    path = PurePosixPath(name)
    if name.startswith("/") or not name.strip() or ".." in path.parts:
        raise SkillPackageError("Skill package contains unsafe paths.")
    if any(part in BLOCKED_PARTS for part in path.parts):
        raise SkillPackageError("Skill package contains blocked directories.")
    mode = (info.external_attr >> 16) & 0o170000
    if mode in {0o120000, 0o020000, 0o060000}:
        raise SkillPackageError(
            "Skill package contains unsupported file types."
        )


def _find_skill_root(extract_root):
    """Return the directory containing SKILL.md."""

    if (extract_root / "SKILL.md").is_file():
        return extract_root
    candidates = [
        path
        for path in extract_root.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    ]
    if len(candidates) != 1:
        raise SkillPackageError(
            "Skill package must contain one SKILL.md root."
        )
    return candidates[0]


def _parse_skill_md(path):
    """Parse required frontmatter and body from SKILL.md."""

    data = path.read_bytes()
    if len(data) > MAX_SKILL_MD_SIZE:
        raise SkillPackageError("SKILL.md exceeds 256 KB.")
    text = data.decode("utf-8")
    if not text.startswith("---\n"):
        raise SkillPackageError("SKILL.md must start with YAML frontmatter.")
    end = text.find("\n---", 4)
    if end < 0:
        raise SkillPackageError("SKILL.md frontmatter is not closed.")
    frontmatter = text[4:end].strip()
    body = text[text.find("\n", end + 4) + 1 :].strip()
    fields = _parse_simple_frontmatter(frontmatter)
    name = str(fields.get("name") or "").strip()
    description = str(fields.get("description") or "").strip()
    if not name or not description:
        raise SkillPackageError("SKILL.md requires name and description.")
    return {
        "name": name,
        "description": description,
        "content": body,
        "skill_md": text.strip() + "\n",
    }


def _parse_sourcelens_config(skill_root):
    """Read and validate optional SourceLens Skill package configuration."""

    path = skill_root / "sourcelens.json"
    if not path.exists():
        return {"environment": [], "api": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SkillPackageError(
            "sourcelens.json must contain valid JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise SkillPackageError(
            "sourcelens.json must contain a JSON object."
        )
    try:
        environment = validate_environment_schema(payload.get("environment"))
        api = validate_skill_api_policy(payload.get("api"), environment)
        return {"environment": environment, "api": api}
    except Exception as exc:
        raise SkillPackageError(str(exc)) from exc


def _parse_simple_frontmatter(frontmatter):
    """Parse simple key-value YAML frontmatter."""

    fields = {}
    for line in frontmatter.splitlines():
        if ":" not in line or line.startswith((" ", "\t", "-")):
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip("'\"")
    return fields


def _slug_from_metadata(metadata):
    """Return validated slug from Skill metadata name."""

    slug = str(metadata["name"]).strip()
    if not SLUG_RE.match(slug):
        raise SkillPackageError(
            "Skill name must use lowercase letters, numbers, '-' or '_'."
        )
    return slug


def _package_manifest(skill_root):
    """Return compact package metadata for persisted Skill files."""

    files = []
    total_size = 0
    for path in sorted(skill_root.rglob("*")):
        if not path.is_file():
            continue
        size = path.stat().st_size
        total_size += size
        files.append(
            {
                "path": str(PurePosixPath(path.relative_to(skill_root))),
                "size": size,
            }
        )
    return {
        "files": files,
        "file_count": len(files),
        "total_size": total_size,
    }


def _github_zip_url(value):
    """Return a codeload GitHub zip URL from supported GitHub inputs."""

    parsed = parse.urlsplit(str(value or "").strip())
    github_hosts = {"github.com", "www.github.com", "codeload.github.com"}
    if parsed.netloc not in github_hosts:
        raise SkillPackageError("Only public GitHub URLs are supported.")
    if parsed.netloc == "codeload.github.com":
        return parse.urlunsplit(parsed)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise SkillPackageError(
            "GitHub URL must include owner and repository."
        )
    owner, repo = parts[0], parts[1]
    ref = "main"
    if len(parts) >= 4 and parts[2] in {"tree", "blob"}:
        ref = parts[3]
    elif len(parts) >= 4 and parts[2] == "archive":
        return parse.urlunsplit(parsed)
    return f"https://codeload.github.com/{owner}/{repo}/zip/{ref}"


def _validate_github_download_url(value):
    """Reject redirects away from GitHub download hosts."""

    parsed = parse.urlsplit(str(value or ""))
    if parsed.netloc not in {"github.com", "codeload.github.com"}:
        raise SkillPackageError(
            "GitHub download redirected to an unsafe host."
        )


def _remove_old_package_path(old_path, new_path):
    """Remove the previous package snapshot after a successful update."""

    if not old_path or old_path == new_path:
        return
    shutil.rmtree(old_path, ignore_errors=True)


def _skill_md_from_definition(skill):
    """Build a basic SKILL.md for legacy database-only skills."""

    definition = skill.definition or {}
    content = (
        definition.get("skill_md")
        or definition.get("content")
        or definition.get("markdown")
        or definition.get("summary")
        or ""
    )
    if str(content).lstrip().startswith("---"):
        return str(content).strip() + "\n"
    description = (
        definition.get("description")
        or definition.get("summary")
        or skill.name
    )
    return (
        "---\n"
        f"name: {skill.slug}\n"
        f"description: {description}\n"
        "---\n\n"
        f"{str(content).strip()}\n"
    )
