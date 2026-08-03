import base64
import hashlib
import io
import json
import multiprocessing
import os
import queue
import re
import shutil
import stat
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import httpx

from .document_convert import convert_one
from .path_rules import SIDECAR_SUFFIX, safe_filename
from .tls import create_config_ssl_context

MAX_SKILL_PACKAGE_BYTES = 25 * 1024 * 1024
MAX_RUN_ATTACHMENT_BYTES = 25 * 1024 * 1024
MAX_RUN_ATTACHMENTS = 4
MAX_HISTORY_ARTIFACT_BYTES = 50 * 1024 * 1024
MAX_HISTORY_ARTIFACTS = 3
RUN_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx"}
MAX_FILENAME_COMPONENT_BYTES = 255
STALE_RUNTIME_MAX_AGE_S = 24 * 60 * 60
RUNTIME_ACTIVITY_INTERVAL_S = 15
RUNTIME_CONVERSION_POLL_S = 0.25
RUN_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MCP_ENVIRONMENT_REFERENCE_PATTERN = re.compile(
    r"\$\{([A-Z_][A-Z0-9_]*)\}"
)


@dataclass(frozen=True)
class RuntimeResources:
    """Materialized per-run resource paths."""

    root: Path
    skill_paths: list[str]
    context_skill_contents: list[str]
    skill_environments: dict[str, dict[str, str]]
    mcp_config_path: Path
    skill_api_policies: dict[str, dict] = field(default_factory=dict)
    skill_artifacts: dict[str, dict] = field(default_factory=dict)
    skill_transforms: dict[str, dict] = field(default_factory=dict)
    mcp_configs: list[dict] = field(default_factory=list)


def prepare_runtime_resources(
    config,
    command,
    emit_event=None,
    cancel_event=None,
    on_activity=None,
):
    """Materialize Skill/MCP snapshots into cache and run directories."""

    workspace = Path(config.workspace_path)
    base = workspace / ".sourcelens"
    cache_root = base / "cache"
    runtime_root = _run_runtime_path(workspace, command["run_uuid"])
    skills_root = runtime_root / "skills"
    mcp_root = runtime_root / "mcp"

    skills_root.mkdir(parents=True, exist_ok=True)
    mcp_root.mkdir(parents=True, exist_ok=True)

    skill_paths = []
    skill_environments = {}
    skill_api_policies = {}
    skill_artifacts = {}
    skill_transforms = {}
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
            definition = skill.get("definition") or {}
            api_policy = (
                definition.get("api")
                if isinstance(definition, dict)
                else None
            )
            skill_api_policies[skill_path.name] = (
                api_policy if isinstance(api_policy, dict) else {}
            )
            artifacts = (
                definition.get("artifacts")
                if isinstance(definition, dict)
                else None
            )
            skill_artifacts[skill_path.name] = (
                artifacts if isinstance(artifacts, dict) else {}
            )
            transforms = (
                definition.get("transforms")
                if isinstance(definition, dict)
                else None
            )
            skill_transforms[skill_path.name] = (
                transforms if isinstance(transforms, dict) else {}
            )
        context_content = _context_skill_content(
            skill,
            skill_path=skill_path,
            force=general_chat_mode,
        )
        if context_content:
            context_skill_contents.append(context_content)

    mcp_configs = []
    for mcp in command.get("loaded_mcps") or []:
        mcp_config = _materialize_mcp(mcp_root, mcp)
        if mcp_config is not None:
            mcp_configs.append(mcp_config)

    mcp_config_path = mcp_root / "mcp.json"
    _write_private_json(
        mcp_config_path,
        {
            "servers": [
                _mcp_disk_metadata(config)
                for config in mcp_configs
            ]
        },
    )

    try:
        artifact_paths = _materialize_history_artifacts(
            config,
            command,
            runtime_root,
            cancel_event=cancel_event,
            on_activity=on_activity,
        )
        subject_dir = _materialize_subject_documents(
            config,
            command,
            runtime_root,
            cancel_event=cancel_event,
            on_activity=on_activity,
        )
    except Exception:
        shutil.rmtree(runtime_root, ignore_errors=True)
        raise
    if artifact_paths:
        command["history_artifact_paths"] = artifact_paths
    if subject_dir is not None:
        command["subject_dirs"] = [str(subject_dir)]
        command.setdefault("target_dirs", []).append(
            {"path": str(subject_dir), "material_role": "subject"}
        )

    if emit_event is not None:
        emit_event(
            "resources.materialized",
            {
                "skill_count": len(skill_paths),
                "skill_paths": skill_paths,
                "mcp_count": len(mcp_configs),
                "transform_count": sum(
                    len(items) for items in skill_transforms.values()
                ),
                "runtime_root": str(runtime_root),
            },
        )

    return RuntimeResources(
        root=runtime_root,
        skill_paths=skill_paths,
        context_skill_contents=context_skill_contents,
        skill_environments=skill_environments,
        mcp_config_path=mcp_config_path,
        skill_api_policies=skill_api_policies,
        skill_artifacts=skill_artifacts,
        skill_transforms=skill_transforms,
        mcp_configs=mcp_configs,
    )


def _materialize_history_artifacts(
    config,
    command,
    runtime_root,
    cancel_event=None,
    on_activity=None,
):
    """Download trusted prior deliverables into this Run's sandbox."""

    artifacts = command.get("history_artifacts") or []
    if not artifacts:
        return []
    if len(artifacts) > MAX_HISTORY_ARTIFACTS:
        raise ValueError("History artifact count exceeds limit")

    artifact_dir = runtime_root / "conversation-artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    run_uuid = str(command.get("run_uuid") or "").strip()
    paths = []
    total_bytes = 0
    for artifact in artifacts:
        _check_cancelled(cancel_event)
        artifact_uuid = str(artifact.get("uuid") or "").strip()
        expected_size = int(artifact.get("byte_size") or 0)
        expected_hash = str(artifact.get("content_hash") or "")
        if (
            not artifact_uuid
            or len(artifact_uuid) > 36
            or expected_size < 0
            or expected_size > MAX_HISTORY_ARTIFACT_BYTES
            or total_bytes + expected_size > MAX_HISTORY_ARTIFACT_BYTES
            or len(expected_hash) != 64
            or any(
                character not in "0123456789abcdef"
                for character in expected_hash
            )
        ):
            raise ValueError("Invalid history artifact metadata")
        original_name = Path(
            str(artifact.get("filename") or "artifact")
        ).name
        filename = safe_filename(
            original_name,
            max_bytes=(
                MAX_FILENAME_COMPONENT_BYTES
                - len(artifact_uuid.encode("utf-8"))
                - 1
            ),
        )
        data = _download_history_artifact(
            config,
            run_uuid,
            artifact,
            cancel_event=cancel_event,
            on_activity=on_activity,
        )
        if len(data) != expected_size:
            raise ValueError("History artifact size mismatch")
        if hashlib.sha256(data).hexdigest() != expected_hash:
            raise ValueError("History artifact hash mismatch")
        stored_name = f"{artifact_uuid}-{filename}"
        (artifact_dir / stored_name).write_bytes(data)
        total_bytes += len(data)
        paths.append(
            {
                "path": f"/conversation-artifacts/{stored_name}",
                "filename": original_name,
                "source_run_uuid": str(
                    artifact.get("source_run_uuid") or ""
                ),
            }
        )
    return paths


def _materialize_subject_documents(
    config,
    command,
    runtime_root,
    cancel_event=None,
    on_activity=None,
):
    """Download and convert transient documents for one Run."""

    documents = command.get("subject_documents") or []
    if not documents:
        return None
    if len(documents) > MAX_RUN_ATTACHMENTS:
        raise ValueError("Run attachment count exceeds limit")

    subject_dir = runtime_root / "subject-documents"
    subject_dir.mkdir(parents=True, exist_ok=True)
    run_uuid = str(command.get("run_uuid") or "").strip()
    conversion_deadline = time.monotonic() + max(
        1,
        int(command.get("run_timeout_s") or config.request_timeout_s),
    )
    for document in documents:
        _check_cancelled(cancel_event)
        attachment_uuid = str(document.get("uuid") or "").strip()
        original_name = Path(
            str(document.get("original_name") or "document")
        ).name
        attachment_name = safe_filename(
            attachment_uuid,
            fallback="attachment",
        )
        prefix = f"{attachment_name}-"
        filename = safe_filename(
            original_name,
            max_bytes=(
                MAX_FILENAME_COMPONENT_BYTES
                - len(SIDECAR_SUFFIX.encode("utf-8"))
                - len(prefix.encode("utf-8"))
            ),
        )
        extension = Path(filename).suffix.lower()
        if not attachment_uuid or extension not in RUN_DOCUMENT_EXTENSIONS:
            raise ValueError("Unsupported Run attachment metadata")
        data = _download_run_attachment(
            config,
            run_uuid,
            document,
            cancel_event=cancel_event,
            on_activity=on_activity,
        )
        _check_cancelled(cancel_event)
        if len(data) != int(document.get("byte_size") or 0):
            raise ValueError("Run attachment size mismatch")
        digest = hashlib.sha256(data).hexdigest()
        if digest != str(document.get("content_hash") or ""):
            raise ValueError("Run attachment hash mismatch")

        source_path = subject_dir / f"{prefix}{filename}"
        source_path.write_bytes(data)
        context = {
            "source_type": "run_attachment",
            "target_path": str(subject_dir),
            "conversion": {
                "document": True,
                "embedded_image": True,
                "vision_model_ref": command.get("vision_model_ref") or "",
            },
            "ai_gateway_url": config.ai_gateway_url,
            "lensnode_token": config.token,
            "tls_skip_verify": bool(getattr(config, "tls_skip_verify", False)),
            "tls_ca_file": getattr(config, "tls_ca_file", None),
            "vision_model_ref": command.get("vision_model_ref") or "",
        }
        _run_document_conversion(
            subject_dir,
            source_path,
            document,
            context,
            cancel_event=cancel_event,
            on_activity=on_activity,
            deadline_at=conversion_deadline,
        )
    return subject_dir


def _conversion_worker(target, path, item, context, result_queue):
    """Convert one document and report a serialization-safe result."""

    try:
        result = convert_one(target, path, item, context)
    except Exception as exc:
        result_queue.put(
            {
                "ok": False,
                "error": str(exc) or type(exc).__name__,
            }
        )
        return
    result_queue.put({"ok": True, "result": result})


def _run_document_conversion(
    target,
    path,
    item,
    context,
    *,
    cancel_event,
    on_activity,
    deadline_at,
):
    """Run conversion in a child process bounded by cancellation and time."""

    _check_cancelled(cancel_event)
    remaining_s = deadline_at - time.monotonic()
    if remaining_s <= 0:
        raise TimeoutError("Run attachment conversion exceeded run timeout")

    process_context = multiprocessing.get_context("spawn")
    result_queue = process_context.Queue(maxsize=1)
    process = process_context.Process(
        target=_conversion_worker,
        args=(target, path, item, context, result_queue),
        name="document-attachment-conversion",
    )
    started = False
    try:
        process.start()
        started = True
        next_activity_at = time.monotonic()
        while process.is_alive():
            _check_cancelled(cancel_event)
            remaining_s = deadline_at - time.monotonic()
            if remaining_s <= 0:
                raise TimeoutError(
                    "Run attachment conversion exceeded run timeout"
                )
            process.join(
                timeout=min(RUNTIME_CONVERSION_POLL_S, remaining_s)
            )
            now = time.monotonic()
            if now >= next_activity_at:
                _touch_activity(on_activity)
                next_activity_at = now + RUNTIME_ACTIVITY_INTERVAL_S

        try:
            payload = result_queue.get(timeout=1)
        except queue.Empty as exc:
            raise RuntimeError(
                "Document conversion process exited without a result"
            ) from exc
        if not payload.get("ok"):
            raise RuntimeError(payload.get("error") or "CONVERSION_FAILED")
        return payload.get("result")
    finally:
        if started and process.is_alive():
            process.terminate()
            process.join(timeout=1)
        if started and process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(timeout=1)
        result_queue.close()
        result_queue.join_thread()


def _download_run_attachment(
    config,
    run_uuid,
    document,
    cancel_event=None,
    on_activity=None,
):
    """Download one Run-bound document with a hard byte ceiling."""

    _check_cancelled(cancel_event)
    _touch_activity(on_activity)
    attachment_uuid = str(document.get("uuid") or "").strip()
    url = _run_attachment_url(
        config.ai_gateway_url,
        run_uuid,
        attachment_uuid,
    )
    chunks = []
    size = 0
    with httpx.Client(
        timeout=config.request_timeout_s,
        verify=create_config_ssl_context(config),
    ) as client:
        with client.stream(
            "GET",
            url,
            headers={"Authorization": f"Bearer {config.token}"},
        ) as response:
            response.raise_for_status()
            content_length = int(response.headers.get("Content-Length") or 0)
            if content_length > MAX_RUN_ATTACHMENT_BYTES:
                raise ValueError("Run attachment download exceeds size limit")
            for chunk in response.iter_bytes():
                _check_cancelled(cancel_event)
                size += len(chunk)
                if size > MAX_RUN_ATTACHMENT_BYTES:
                    raise ValueError(
                        "Run attachment download exceeds size limit"
                    )
                chunks.append(chunk)
                _touch_activity(on_activity)
    _check_cancelled(cancel_event)
    _touch_activity(on_activity)
    return b"".join(chunks)


def _download_history_artifact(
    config,
    run_uuid,
    artifact,
    cancel_event=None,
    on_activity=None,
):
    """Download one conversation artifact with a hard byte ceiling."""

    _check_cancelled(cancel_event)
    _touch_activity(on_activity)
    artifact_uuid = str(artifact.get("uuid") or "").strip()
    url = _history_artifact_url(
        config.ai_gateway_url,
        run_uuid,
        artifact_uuid,
    )
    chunks = []
    size = 0
    with httpx.Client(
        timeout=config.request_timeout_s,
        verify=create_config_ssl_context(config),
    ) as client:
        with client.stream(
            "GET",
            url,
            headers={"Authorization": f"Bearer {config.token}"},
        ) as response:
            response.raise_for_status()
            content_length = int(response.headers.get("Content-Length") or 0)
            if content_length > MAX_HISTORY_ARTIFACT_BYTES:
                raise ValueError(
                    "History artifact download exceeds size limit"
                )
            for chunk in response.iter_bytes():
                _check_cancelled(cancel_event)
                size += len(chunk)
                if size > MAX_HISTORY_ARTIFACT_BYTES:
                    raise ValueError(
                        "History artifact download exceeds size limit"
                    )
                chunks.append(chunk)
                _touch_activity(on_activity)
    _check_cancelled(cancel_event)
    _touch_activity(on_activity)
    return b"".join(chunks)


def _run_attachment_url(
    ai_gateway_url,
    run_uuid,
    attachment_uuid,
):
    """Derive the Run attachment endpoint from the AI gateway URL."""

    base = str(ai_gateway_url).rstrip("/")
    suffix = "/ai-gateway"
    if base.endswith(suffix):
        base = base[: -len(suffix)]
    return f"{base}/runs/{run_uuid}/attachments/{attachment_uuid}/"


def _history_artifact_url(
    ai_gateway_url,
    run_uuid,
    artifact_uuid,
):
    """Derive the history artifact endpoint from the AI gateway URL."""

    base = str(ai_gateway_url).rstrip("/")
    suffix = "/ai-gateway"
    if base.endswith(suffix):
        base = base[: -len(suffix)]
    return f"{base}/runs/{run_uuid}/history-artifacts/{artifact_uuid}/"


def cleanup_runtime_resources(resources):
    """Remove per-run runtime resources but keep shared cache."""

    shutil.rmtree(resources.root, ignore_errors=True)


def cleanup_run_runtime_resources(workspace_path, run_uuid):
    """Remove one Run's deterministic runtime directory."""

    if not workspace_path or not run_uuid:
        return False
    try:
        runtime_root = _run_runtime_path(workspace_path, run_uuid)
    except (OSError, ValueError):
        return False
    shutil.rmtree(runtime_root, ignore_errors=True)
    return not runtime_root.exists()


def _run_runtime_path(workspace_path, run_uuid):
    """Return a contained runtime path for one validated Run identifier."""

    identifier = str(run_uuid).strip()
    if not RUN_IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError("Invalid Run identifier")

    workspace_root = Path(workspace_path).resolve()
    runs_root = workspace_root / ".sourcelens" / "runtime" / "runs"
    resolved_runs_root = runs_root.resolve()
    try:
        resolved_runs_root.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError("Runtime root escapes workspace") from exc

    runtime_root = runs_root / identifier
    if runtime_root.is_symlink():
        raise ValueError("Run runtime path cannot be a symlink")
    resolved_runtime_root = runtime_root.resolve()
    try:
        resolved_runtime_root.relative_to(resolved_runs_root)
    except ValueError as exc:
        raise ValueError("Run runtime path escapes runtime root") from exc
    return resolved_runtime_root


def cleanup_stale_runtime_resources(
    workspace_path,
    max_age_s=STALE_RUNTIME_MAX_AGE_S,
    now=None,
):
    """Remove abandoned per-Run directories older than the safety window."""

    runs_root = Path(workspace_path) / ".sourcelens" / "runtime" / "runs"
    cutoff = float(time.time() if now is None else now) - max(
        0,
        int(max_age_s),
    )
    try:
        candidates = list(runs_root.iterdir())
    except (FileNotFoundError, OSError):
        return 0

    removed = 0
    for path in candidates:
        try:
            if path.is_symlink() or not path.is_dir():
                continue
            if path.stat().st_mtime > cutoff:
                continue
        except (FileNotFoundError, OSError):
            continue
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            removed += 1
    return removed


def _check_cancelled(cancel_event):
    """Abort synchronous materialization after a Run cancellation."""

    if cancel_event is None or not cancel_event.is_set():
        return
    from .gateway_model import RunCancelledError

    raise RunCancelledError(
        "Run was cancelled while materializing document attachments."
    )


def _touch_activity(on_activity):
    """Refresh the executor idle watchdog when work makes progress."""

    if on_activity is not None:
        on_activity()


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
    _enable_skill_scripts(runtime_dir)
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
            source_mode = (info.external_attr >> 16) & 0o777
            target.chmod(0o755 if source_mode & 0o111 else 0o644)
    _enable_skill_scripts(target_dir)


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
        target.chmod(_safe_package_file_mode(item.get("mode")))
    _enable_skill_scripts(cache_dir)


def _safe_relative_package_path(value):
    """Return a safe package-relative path or None."""

    text = str(value or "").replace("\\", "/").strip()
    path = PurePosixPath(text)
    if not text or text.startswith("/") or ".." in path.parts:
        return None
    return Path(*path.parts)


def _materialize_mcp(mcp_root, mcp):
    """Write one MCP snapshot only inside the ephemeral run directory."""

    mcp_uuid = str(mcp.get("mcp_uuid") or "").strip()
    content_hash = str(mcp.get("content_hash") or "").replace(":", "-")
    name = _safe_name(mcp.get("mcp_name"))
    if not mcp_uuid or not content_hash or not name:
        return None

    runtime_dir = mcp_root / name
    runtime_dir.mkdir(parents=True, exist_ok=True)
    environment = mcp.get("environment") or {}
    if not isinstance(environment, dict):
        environment = {}
    payload = {
        "name": mcp.get("mcp_name"),
        "transport": mcp.get("transport"),
        "endpoint": _expand_mcp_environment(
            mcp.get("endpoint"),
            environment,
        ),
        "config": _expand_mcp_environment(
            mcp.get("config") or {},
            environment,
        ),
        "load_config": mcp.get("load_config") or {},
    }
    _write_private_json(
        runtime_dir / "mcp.json",
        _mcp_disk_metadata(payload),
    )
    _write_json(runtime_dir / "metadata.json", _mcp_metadata(mcp))
    return payload


def _expand_mcp_environment(value, environment):
    """Expand declared ${NAME} references in an ephemeral MCP payload."""

    if isinstance(value, dict):
        return {
            key: _expand_mcp_environment(item, environment)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _expand_mcp_environment(item, environment)
            for item in value
        ]
    if not isinstance(value, str):
        return value
    return MCP_ENVIRONMENT_REFERENCE_PATTERN.sub(
        lambda match: str(
            environment.get(match.group(1), match.group(0))
        ),
        value,
    )


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
        "artifacts": (
            (skill.get("definition") or {}).get("artifacts") or {}
        ),
    }


def _mcp_metadata(mcp):
    """Return serializable MCP cache metadata."""

    return {
        "uuid": mcp.get("mcp_uuid"),
        "name": mcp.get("mcp_name"),
        "version": mcp.get("version"),
        "content_hash": mcp.get("content_hash"),
    }


def _mcp_disk_metadata(config):
    """Return non-sensitive MCP metadata safe for the Agent filesystem."""

    return {
        "name": config.get("name"),
        "transport": config.get("transport"),
        "endpoint_configured": bool(config.get("endpoint")),
    }


def _write_json(path, payload):
    """Write JSON payload to a path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_private_json(path, payload):
    """Write a per-run JSON file with owner-only permissions."""

    _write_json(path, payload)
    path.chmod(0o600)


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


def _safe_package_file_mode(value):
    """Return a sanitized regular-file mode from package metadata."""

    try:
        mode = int(value)
    except (TypeError, ValueError):
        mode = 0
    return 0o755 if stat.S_IMODE(mode) & 0o111 else 0o644


def _enable_skill_scripts(skill_root):
    """Grant sanitized execute permission to files under scripts/."""

    scripts_root = skill_root / "scripts"
    if not scripts_root.is_dir() or scripts_root.is_symlink():
        return
    for path in scripts_root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            path.chmod(0o755)
