import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, parse, request

WORKSPACE_ROOT = "/workspace"
GIT_SHALLOW_DEPTH = "1"
DEFAULT_DATASOURCE_SYNC_WORKERS = 4
FEISHU_EXPORT_PENDING_STATUSES = {1, 2}
FEISHU_EXPORT_SUCCESS_STATUS = 0
FEISHU_EXPORT_POLL_INTERVAL_S = 2
FEISHU_EXPORT_TIMEOUT_S = 600
FEISHU_EXPORT_STATUS_MESSAGES = {
    0: "success",
    1: "initializing",
    2: "processing",
    3: "internal error",
    107: "document too large",
    108: "processing timeout",
    109: "content block permission denied",
    110: "permission denied",
    111: "document deleted",
    122: "export blocked while creating copy",
    123: "document not found",
    6000: "too many images",
}


class DataSourceSyncError(RuntimeError):
    """Raised when LensNode cannot synchronize a datasource."""


def utc_timestamp():
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def normalize_target_path(target_path, workspace_path=WORKSPACE_ROOT):
    """Return a safe target path inside the LensNode workspace."""

    workspace = Path(workspace_path or WORKSPACE_ROOT).resolve()
    raw = str(target_path or "").strip()
    if not raw:
        raise DataSourceSyncError("LENS_SOURCE_TARGET_PATH_REQUIRED")

    target = Path(raw)
    if not target.is_absolute():
        target = workspace / raw
    target = target.resolve()
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise DataSourceSyncError("LENS_SOURCE_TARGET_PATH_INVALID") from exc
    if target == workspace:
        raise DataSourceSyncError("LENS_SOURCE_TARGET_PATH_REQUIRED")
    return target


def inspect_datasource_path(command, workspace_path=WORKSPACE_ROOT):
    """Inspect a datasource target path without mutating local files."""

    target = normalize_target_path(command.get("target_path"), workspace_path)
    config = command.get("config") or {}
    source_type = command.get("source_type") or "git"
    result = {
        "path": str(target),
        "exists": target.exists(),
        "is_directory": target.is_dir(),
        "is_empty": False,
        "is_git_repo": False,
        "source_compatible": True,
        "will_create": False,
        "status": "available",
        "message_code": "available",
        "message": "Target path is available.",
    }

    if not target.exists():
        result["will_create"] = True
        result["message_code"] = "will_create"
        result["message"] = "Directory will be created during first sync."
        return result

    if not target.is_dir():
        result.update(
            {
                "source_compatible": False,
                "status": "blocked",
                "message_code": "not_directory",
                "message": "Target path exists but is not a directory.",
            }
        )
        return result

    children = list(target.iterdir())
    result["is_empty"] = len(children) == 0
    result["is_git_repo"] = (target / ".git").is_dir()
    if result["is_empty"]:
        result["message_code"] = "empty"
        result["message"] = "Directory is empty and can be used."
        return result

    if source_type == "git":
        return _inspect_git_path(target, config, result)

    result["message_code"] = "merge"
    result["message"] = "Directory exists; files may be merged by sync."
    return result


def _inspect_git_path(target, config, result):
    """Inspect Git repository compatibility for a target path."""

    if not result["is_git_repo"]:
        result.update(
            {
                "source_compatible": False,
                "status": "blocked",
                "message_code": "not_git_repo",
                "message": "Directory is not empty and is not a Git repo.",
            }
        )
        return result

    repo_url = config.get("repo_url") or ""
    remote_url = _git_output(["remote", "get-url", "origin"], cwd=target)
    result["remote_url"] = remote_url
    if repo_url and _normalize_repo_url(repo_url) != _normalize_repo_url(remote_url):
        result.update(
            {
                "source_compatible": False,
                "status": "blocked",
                "message_code": "remote_mismatch",
                "message": "Existing Git remote does not match repo URL.",
            }
        )
        return result

    result["message_code"] = "git_update"
    result["message"] = "Existing Git repository can be updated."
    return result


def sync_datasource(command, workspace_path=WORKSPACE_ROOT, emit=None):
    """Synchronize one datasource command and return metrics."""

    source_type = command.get("source_type")
    if source_type == "git":
        return _sync_git(command, workspace_path, emit)
    if source_type == "feishu":
        return _sync_feishu(command, workspace_path, emit)
    raise DataSourceSyncError("LENS_SOURCE_TYPE_UNSUPPORTED")


def datasource_sync_workers(command):
    """Return configured datasource sync worker count."""

    try:
        value = int(command.get("max_workers") or 0)
    except (TypeError, ValueError):
        value = 0
    return value if value > 0 else DEFAULT_DATASOURCE_SYNC_WORKERS


def test_datasource_connection(command):
    """Test datasource connectivity without mutating local files."""

    source_type = command.get("source_type")
    config = command.get("config") or {}
    if source_type == "git":
        return _test_git_connection(config)
    if source_type == "feishu":
        return _test_feishu_connection(config)
    raise DataSourceSyncError("LENS_SOURCE_TYPE_UNSUPPORTED")


def _test_git_connection(config):
    """Test that a Git repository and branch are reachable."""

    repo_url = config.get("repo_url")
    if not repo_url:
        raise DataSourceSyncError("LENS_SOURCE_CONFIG_INVALID")

    branch = str(config.get("branch") or "").strip()
    auth_url = _git_auth_url(repo_url, config)
    try:
        result = _run_git(
            ["ls-remote", "--heads", auth_url],
            timeout=60,
            detail_prefix="LENS_SOURCE_GIT_LS_REMOTE_FAILED",
        )
    except DataSourceSyncError:
        return {
            "status": "failed",
            "message_code": "git_unreachable",
            "message": "Git repository is not reachable.",
        }

    branches = _git_remote_branches(result.stdout)
    selected_branch = branch or _default_git_branch(branches)
    if branch and branch not in branches:
        return {
            "status": "failed",
            "message_code": "git_branch_missing",
            "message": "Git branch does not exist or is not accessible.",
            "details": {"branch": branch, "branches": branches},
        }
    if not selected_branch:
        return {
            "status": "failed",
            "message_code": "git_branch_missing",
            "message": "Git branch does not exist or is not accessible.",
            "details": {"branch": branch, "branches": branches},
        }
    return {
        "status": "success",
        "message_code": "git_branch_available",
        "message": "Git repository is reachable and branch exists.",
        "details": {"branch": selected_branch, "branches": branches},
    }


def _test_feishu_connection(config):
    """Test that Feishu document identifiers are available."""

    sync_mode = config.get("sync_mode") or "document_list"
    credentials = _load_credentials(config)
    token = _feishu_tenant_token(credentials)
    if sync_mode == "drive_folder":
        folder_token = _feishu_folder_token(config)
        if not folder_token:
            return {
                "status": "failed",
                "message_code": "feishu_folder_missing",
                "message": "Feishu Drive folder URL or token is required.",
            }
        if not token:
            return {
                "status": "failed",
                "message_code": "LENS_SOURCE_CREDENTIAL_INVALID",
                "message": "Feishu app credential is required.",
            }
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        try:
            children = _list_feishu_folder_children(folder_token, headers)
        except DataSourceSyncError as exc:
            return {
                "status": "failed",
                "message_code": "feishu_folder_unreachable",
                "message": "Feishu Drive folder is not reachable.",
                "details": {
                    "folder_token": folder_token,
                    "error": str(exc),
                },
            }
        return {
            "status": "success",
            "message_code": "feishu_folder_available",
            "message": "Feishu Drive folder is reachable.",
            "details": {
                "folder_token": folder_token,
                "children": len(children),
            },
        }

    doc_ids = _feishu_doc_ids(config)
    if not doc_ids:
        return {
            "status": "failed",
            "message_code": "feishu_document_missing",
            "message": "Feishu document ID or URL is required.",
        }

    if not token:
        return {
            "status": "failed",
            "message_code": "LENS_SOURCE_CREDENTIAL_INVALID",
            "message": "Feishu app credential is required.",
        }

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        document = _export_feishu_document(doc_ids[0], "docx", headers)
    except DataSourceSyncError as exc:
        return {
            "status": "failed",
            "message_code": "feishu_unreachable",
            "message": "Feishu document is not reachable.",
            "details": {
                "doc_id": doc_ids[0],
                "error": str(exc),
            },
        }
    return {
        "status": "success",
        "message_code": "feishu_document_available",
        "message": "Feishu document is reachable.",
        "details": {
            "doc_id": doc_ids[0],
            "title": document.get("file_name") or "",
        },
    }


def _sync_git(command, workspace_path, emit):
    """Clone or update a Git repository into the target path."""

    config = command.get("config") or {}
    repo_url = config.get("repo_url")
    if not repo_url:
        raise DataSourceSyncError("LENS_SOURCE_CONFIG_INVALID")

    target = normalize_target_path(command.get("target_path"), workspace_path)
    branch = config.get("branch") or "main"
    auth_url = _git_auth_url(repo_url, config)
    _emit(emit, "check_path", "running", "Checking target directory.")
    inspection = inspect_datasource_path(command, workspace_path)
    if not inspection.get("source_compatible"):
        raise DataSourceSyncError(inspection.get("message") or "PATH_BLOCKED")

    target.parent.mkdir(parents=True, exist_ok=True)
    _emit(emit, "sync_content", "running", "Synchronizing Git repository.")
    if not target.exists():
        _run_git(
            [
                "clone",
                "--depth",
                GIT_SHALLOW_DEPTH,
                "--branch",
                branch,
                "--single-branch",
                auth_url,
                str(target),
            ],
            detail_prefix="LENS_SOURCE_GIT_CLONE_FAILED",
        )
    else:
        _run_git(
            [
                "fetch",
                "--depth",
                GIT_SHALLOW_DEPTH,
                "origin",
                branch,
                "--prune",
            ],
            cwd=target,
            detail_prefix="LENS_SOURCE_GIT_FETCH_FAILED",
        )
        _run_git(
            ["checkout", branch],
            cwd=target,
            detail_prefix="LENS_SOURCE_GIT_CHECKOUT_FAILED",
        )
        _run_git(
            ["reset", "--hard", f"origin/{branch}"],
            cwd=target,
            detail_prefix="LENS_SOURCE_GIT_RESET_FAILED",
        )

    _sync_git_submodules(target)

    files = _count_files(target)
    _write_manifest(
        target,
        {
            "source_type": "git",
            "repo_url": repo_url,
            "branch": branch,
            "synced_at": utc_timestamp(),
            "files": files,
        },
    )
    _emit(emit, "manifest", "done", f"Git sync completed with {files} files.")
    return {"synced": 1, "files": files, "target_path": str(target)}


def _sync_git_submodules(target):
    """Synchronize Git submodules when the repository declares them."""

    if not (target / ".gitmodules").exists():
        return
    _run_git(
        ["submodule", "sync", "--recursive"],
        cwd=target,
        detail_prefix="LENS_SOURCE_GIT_SUBMODULE_SYNC_FAILED",
    )
    _run_git(
        [
            "submodule",
            "update",
            "--init",
            "--recursive",
            "--depth",
            GIT_SHALLOW_DEPTH,
        ],
        cwd=target,
        detail_prefix="LENS_SOURCE_GIT_SUBMODULE_UPDATE_FAILED",
    )


def _sync_feishu(command, workspace_path, emit):
    """Export Feishu content into local files."""

    config = command.get("config") or {}
    credentials = _load_credentials(config)
    target = normalize_target_path(command.get("target_path"), workspace_path)
    target.mkdir(parents=True, exist_ok=True)
    max_workers = datasource_sync_workers(command)
    _emit(
        emit,
        "sync_config",
        "running",
        f"Feishu sync uses {max_workers} workers.",
        category="config",
        max_workers=max_workers,
    )
    token = _feishu_tenant_token(credentials)
    if not token:
        raise DataSourceSyncError("LENS_SOURCE_CREDENTIAL_INVALID")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    if (config.get("sync_mode") or "document_list") == "drive_folder":
        return _sync_feishu_folder(config, target, headers, emit, max_workers)
    return _sync_feishu_documents(config, target, headers, emit, max_workers)


def _sync_feishu_documents(config, target, headers, emit, max_workers=1):
    """Export configured Feishu documents into their original file format."""

    docs_dir = target / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    doc_ids = _feishu_doc_ids(config)
    if not doc_ids:
        raise DataSourceSyncError("LENS_SOURCE_CONFIG_INVALID")

    synced = 0
    documents = []
    max_workers = max(1, int(max_workers or 1))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _sync_feishu_document_item,
                doc_id,
                docs_dir,
                headers,
                emit,
            ): doc_id
            for doc_id in doc_ids
        }
        for future in as_completed(futures):
            documents.append(future.result())
            synced += 1

    _write_manifest(
        target,
        {
            "source_type": "feishu",
            "synced_at": utc_timestamp(),
            "documents": documents,
        },
    )
    _emit(
        emit,
        "manifest",
        "done",
        f"Feishu sync completed with {synced} documents.",
        category="summary",
        summary={
            "documents": synced,
            "files": synced,
            "failed": 0,
        },
    )
    return {"synced": synced, "files": synced, "target_path": str(target)}


def _sync_feishu_document_item(doc_id, docs_dir, headers, emit):
    """Export one Feishu document and return manifest metadata."""

    _emit(
        emit,
        "item_started",
        "running",
        f"Exporting Feishu {doc_id}.",
        category="document",
        kind="document",
        token=doc_id,
        item_type="docx",
        item_name=doc_id,
    )
    try:
        exported = _export_feishu_document(doc_id, "docx", headers)
    except DataSourceSyncError as exc:
        _emit(
            emit,
            "item_failed",
            "failed",
            f"Failed to export Feishu {doc_id}.",
            category="document",
            kind="document",
            token=doc_id,
            item_type="docx",
            item_name=doc_id,
            error=str(exc),
        )
        raise
    filename = _export_filename(exported, doc_id, "docx")
    (docs_dir / filename).write_bytes(exported["content"])
    _emit(
        emit,
        "item_done",
        "done",
        f"Exported Feishu {doc_id} to docs/{filename}.",
        category="document",
        kind="document",
        token=doc_id,
        item_type=exported.get("type") or "docx",
        item_name=exported.get("file_name") or doc_id,
        file=f"docs/{filename}",
        file_extension=exported.get("file_extension") or "docx",
    )
    return {
        "doc_id": doc_id,
        "title": exported.get("file_name") or doc_id,
        "file": f"docs/{filename}",
        "type": exported.get("type") or "docx",
        "file_extension": exported.get("file_extension") or "docx",
    }


def _sync_feishu_folder(config, target, headers, emit, max_workers=1):
    """Recursively synchronize a Feishu Drive folder."""

    folder_token = _feishu_folder_token(config)
    if not folder_token:
        raise DataSourceSyncError("LENS_SOURCE_CONFIG_INVALID")
    recursive = config.get("recursive", True) is not False
    max_depth = int(config.get("max_depth") or 10)
    root_dir = target

    manifest_items = []
    stats = {
        "folders": 0,
        "documents": 0,
        "files": 0,
        "failed": 0,
    }

    def walk(current_token, current_dir, depth, executor):
        stats["folders"] += 1
        _emit(
            emit,
            "scan_folder",
            "running",
            f"Scanning Feishu folder {current_token}.",
        )
        children = _list_feishu_folder_children(current_token, headers)
        item_futures = {}
        for child in children:
            name = _feishu_item_name(child)
            item_type = _feishu_item_type(child)
            token = _feishu_item_token(child)
            if not token:
                continue
            if item_type == "folder":
                if not recursive or depth >= max_depth:
                    continue
                next_dir = current_dir / _safe_filename(name)
                next_dir.mkdir(parents=True, exist_ok=True)
                walk(token, next_dir, depth + 1, executor)
                continue
            item_futures[
                executor.submit(
                    _sync_feishu_drive_item,
                    child,
                    current_dir,
                    headers,
                    emit,
                )
            ] = child
        for future in as_completed(item_futures):
            child = item_futures[future]
            name = _feishu_item_name(child)
            item_type = _feishu_item_type(child)
            token = _feishu_item_token(child)
            try:
                item = future.result()
                manifest_items.append(item)
                if item.get("kind") == "document":
                    stats["documents"] += 1
                else:
                    stats["files"] += 1
            except DataSourceSyncError as exc:
                stats["failed"] += 1
                _emit(
                    emit,
                    "item_failed",
                    "failed",
                    f"Failed to sync Feishu {name}.",
                    category="document",
                    token=token,
                    item_type=item_type,
                    item_name=name,
                    error=str(exc),
                )
                manifest_items.append(
                    {
                        "token": token,
                        "name": name,
                        "type": item_type,
                        "error": str(exc),
                    }
                )

    max_workers = max(1, int(max_workers or 1))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        walk(folder_token, root_dir, 1, executor)
    _write_manifest(
        target,
        {
            "source_type": "feishu",
            "sync_mode": "drive_folder",
            "folder_token": folder_token,
            "synced_at": utc_timestamp(),
            "stats": stats,
            "items": manifest_items,
        },
    )
    total = stats["documents"] + stats["files"]
    if total == 0 and stats["failed"] > 0:
        message = (
            "LENS_SOURCE_SYNC_FAILED: all Feishu Drive items failed; "
            "see manifest.json for item errors"
        )
        _emit(emit, "manifest", "failed", message)
        raise DataSourceSyncError(message)
    _emit(
        emit,
        "manifest",
        "done",
        f"Feishu folder sync completed with {total} files.",
        category="summary",
        summary=stats,
    )
    return {
        "synced": total,
        "files": total,
        "target_path": str(target),
        "folders": stats["folders"],
        "failed": stats["failed"],
    }


def _sync_feishu_drive_item(item, target_dir, headers, emit):
    """Synchronize one Feishu Drive file item."""

    token = _feishu_item_token(item)
    name = _feishu_item_name(item)
    item_type = _feishu_item_type(item)
    if _is_feishu_exportable_type(item_type):
        _emit(
            emit,
            "item_started",
            "running",
            f"Exporting Feishu {name}.",
            category="document",
            kind="document",
            token=token,
            item_type=item_type,
            item_name=name,
        )
        exported = _export_feishu_document(token, item_type, headers)
        filename = _export_filename(exported, name or token, item_type)
        (target_dir / filename).write_bytes(exported["content"])
        _emit(
            emit,
            "item_done",
            "done",
            f"Exported Feishu {name} to {filename}.",
            category="document",
            kind="document",
            token=token,
            item_type=item_type,
            item_name=exported.get("file_name") or name or token,
            file=str((target_dir / filename).name),
            file_extension=exported.get("file_extension") or "",
        )
        return {
            "kind": "document",
            "token": token,
            "name": exported.get("file_name") or name or token,
            "type": item_type,
            "file": str((target_dir / filename).name),
            "file_extension": exported.get("file_extension") or "",
        }

    _emit(
        emit,
        "item_started",
        "running",
        f"Downloading Feishu {name}.",
        category="file",
        kind="file",
        token=token,
        item_type=item_type,
        item_name=name,
    )
    filename = _safe_filename(name or token)
    raw = _download_feishu_file(token, headers)
    (target_dir / filename).write_bytes(raw)
    _emit(
        emit,
        "item_done",
        "done",
        f"Downloaded Feishu {name} to {filename}.",
        category="file",
        kind="file",
        token=token,
        item_type=item_type,
        item_name=name,
        file=str((target_dir / filename).name),
    )
    return {
        "kind": "file",
        "token": token,
        "name": name,
        "type": item_type,
        "file": str((target_dir / filename).name),
    }


def _run_git(
    args,
    cwd=None,
    timeout=600,
    detail_prefix="LENS_SOURCE_SYNC_FAILED",
):
    """Run a Git command and raise a datasource error on failure."""

    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        detail = _git_error_detail(exc)
        raise DataSourceSyncError(f"{detail_prefix}: {detail}") from exc
    except subprocess.TimeoutExpired as exc:
        raise DataSourceSyncError(
            f"{detail_prefix}: git command timed out"
        ) from exc


def _git_error_detail(exc):
    """Return a compact Git error detail for task diagnostics."""

    stderr = (exc.stderr or "").strip()
    stdout = (exc.stdout or "").strip()
    detail = stderr or stdout or str(exc)
    if len(detail) > 1000:
        return f"{detail[:1000]}..."
    return detail


def _git_output(args, cwd=None):
    """Run a Git command and return stdout, or an empty string."""

    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def _git_remote_branches(output):
    """Return branch names from git ls-remote --heads output."""

    branches = []
    for line in str(output or "").splitlines():
        parts = line.strip().split()
        if len(parts) < 2 or not parts[1].startswith("refs/heads/"):
            continue
        branch = parts[1][len("refs/heads/") :]
        if branch:
            branches.append(branch)
    return branches


def _default_git_branch(branches):
    """Return the preferred branch from a remote branch list."""

    for branch in ["main", "master"]:
        if branch in branches:
            return branch
    return branches[0] if branches else ""


def _normalize_repo_url(value):
    """Return a comparable Git remote URL without credentials."""

    parsed = parse.urlsplit(value or "")
    if parsed.scheme in {"http", "https"}:
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        return parse.urlunsplit(
            (parsed.scheme, netloc, parsed.path.rstrip("/"), "", "")
        )
    return str(value or "").rstrip("/")


def _git_auth_url(repo_url, config):
    """Inject HTTPS token credentials into a Git URL when configured."""

    if config.get("auth_scheme") != "token":
        return repo_url
    credentials = _load_credentials(config)
    token = credentials.get("token") or credentials.get("password")
    username = credentials.get("username") or "oauth2"
    if not token:
        raise DataSourceSyncError("LENS_SOURCE_CREDENTIAL_INVALID")
    parsed = parse.urlsplit(repo_url)
    if parsed.scheme not in {"http", "https"}:
        raise DataSourceSyncError("LENS_SOURCE_AUTH_SCHEME_UNSUPPORTED")
    netloc = f"{parse.quote(username)}:{parse.quote(token)}@{parsed.netloc}"
    return parse.urlunsplit(
        (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
    )


def _load_credentials(config):
    """Load transient datasource credentials from command config."""

    if config.get("access_token"):
        return {
            "token": config.get("access_token"),
            "username": config.get("username") or "oauth2",
        }
    if config.get("app_id") or config.get("app_secret"):
        return {
            "app_id": config.get("app_id") or "",
            "app_secret": config.get("app_secret") or "",
        }
    return {}


def _feishu_tenant_token(credentials):
    """Return an existing or newly requested Feishu tenant token."""

    if credentials.get("tenant_access_token"):
        return credentials["tenant_access_token"]
    app_id = credentials.get("app_id")
    app_secret = credentials.get("app_secret")
    if not app_id or not app_secret:
        return ""
    payload = json.dumps(
        {"app_id": app_id, "app_secret": app_secret},
        ensure_ascii=False,
    ).encode("utf-8")
    data = _http_json(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        method="POST",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    token = data.get("tenant_access_token")
    if not token:
        raise DataSourceSyncError("LENS_SOURCE_CREDENTIAL_INVALID")
    return token


def _feishu_doc_ids(config):
    """Return Feishu document IDs from explicit IDs or document URLs."""

    doc_ids = list(config.get("doc_ids") or [])
    document_url = config.get("document_url") or ""
    if document_url:
        doc_ids.extend(re.findall(r"/(?:docx|docs)/([A-Za-z0-9]+)", document_url))
    return [item for item in dict.fromkeys(doc_ids) if item]


def _feishu_folder_token(config):
    """Return a Feishu Drive folder token from explicit token or URL."""

    if config.get("folder_token"):
        return str(config["folder_token"]).strip()
    folder_url = config.get("folder_url") or ""
    patterns = [
        r"/drive/folder/([A-Za-z0-9_-]+)",
        r"/folder/([A-Za-z0-9_-]+)",
        r"[?&]folder_token=([A-Za-z0-9_-]+)",
        r"[?&]token=([A-Za-z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, folder_url)
        if match:
            return match.group(1)
    return ""


def _list_feishu_folder_children(folder_token, headers):
    """List immediate children under a Feishu Drive folder."""

    items = []
    page_token = ""
    while True:
        query = {
            "folder_token": folder_token,
            "page_size": "100",
        }
        if page_token:
            query["page_token"] = page_token
        payload = _http_json(
            "https://open.feishu.cn/open-apis/drive/v1/files"
            f"?{parse.urlencode(query)}",
            headers=headers,
        )
        data = payload.get("data") or payload
        batch = (
            data.get("files")
            or data.get("items")
            or data.get("children")
            or []
        )
        items.extend(batch)
        page_token = (
            data.get("next_page_token")
            or data.get("page_token")
            or ""
        )
        if not data.get("has_more") or not page_token:
            break
    return items


def _feishu_item_token(item):
    """Return a Drive item token from common Feishu response fields."""

    return (
        item.get("token")
        or item.get("file_token")
        or item.get("doc_token")
        or item.get("obj_token")
        or item.get("id")
        or ""
    )


def _feishu_item_name(item):
    """Return a Drive item display name."""

    return item.get("name") or item.get("title") or _feishu_item_token(item)


def _feishu_item_type(item):
    """Return a normalized Drive item type."""

    value = str(
        item.get("type")
        or item.get("file_type")
        or item.get("obj_type")
        or ""
    ).lower()
    if value in {"folder", "dir", "directory"}:
        return "folder"
    return value or "file"


def _is_feishu_exportable_type(item_type):
    """Return whether a Drive item should use Feishu export tasks."""

    return item_type in {
        "doc",
        "docx",
        "docs",
        "sheet",
        "bitable",
        "base",
    }


def _feishu_export_type(item_type):
    """Return the Feishu export API type for a Drive item type."""

    if item_type in {"doc", "docx", "docs"}:
        return "docx"
    if item_type == "sheet":
        return "sheet"
    if item_type in {"bitable", "base"}:
        return "bitable"
    return item_type or "docx"


def _feishu_export_extension(item_type):
    """Return the preferred original-format export extension."""

    export_type = _feishu_export_type(item_type)
    mapping = {
        "docx": "docx",
        "sheet": "xlsx",
        "bitable": "xlsx",
    }
    return mapping.get(export_type, "docx")


def _export_feishu_document(file_token, item_type, headers):
    """Export one Feishu document-like item with the official Drive API."""

    export_type = _feishu_export_type(item_type)
    file_extension = _feishu_export_extension(item_type)
    ticket = _create_feishu_export_task(
        file_token,
        export_type,
        file_extension,
        headers,
    )
    result = _poll_feishu_export_task(
        ticket,
        file_token,
        export_type,
        headers,
    )
    status = _feishu_job_status(result)
    if status != FEISHU_EXPORT_SUCCESS_STATUS:
        detail = _feishu_export_status_detail(result)
        raise DataSourceSyncError(
            "LENS_SOURCE_EXPORT_FAILED: "
            f"token={file_token} type={export_type} "
            f"extension={file_extension} ticket={ticket} {detail}"
        )
    export_file_token = result.get("file_token")
    if not export_file_token:
        detail = _compact_json(result)
        raise DataSourceSyncError(
            "LENS_SOURCE_EXPORT_FILE_MISSING: "
            f"token={file_token} type={export_type} "
            f"extension={file_extension} ticket={ticket} result={detail}"
        )
    try:
        content = _download_feishu_export_file(export_file_token, headers)
    except DataSourceSyncError as exc:
        raise DataSourceSyncError(
            "LENS_SOURCE_EXPORT_DOWNLOAD_FAILED: "
            f"token={file_token} export_file_token={export_file_token} "
            f"type={export_type} extension={file_extension} error={exc}"
        ) from exc
    return {
        "content": content,
        "file_name": result.get("file_name") or file_token,
        "file_extension": result.get("file_extension") or file_extension,
        "type": result.get("type") or export_type,
        "file_token": export_file_token,
    }


def _create_feishu_export_task(file_token, file_type, file_extension, headers):
    """Create a Feishu Drive export task and return its ticket."""

    payload = {
        "token": file_token,
        "type": file_type,
        "file_extension": file_extension,
    }
    data = _http_json(
        "https://open.feishu.cn/open-apis/drive/v1/export_tasks",
        method="POST",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
    )
    ticket = (data.get("data") or {}).get("ticket") or data.get("ticket")
    if not ticket:
        detail = _compact_json(data)
        raise DataSourceSyncError(
            "LENS_SOURCE_EXPORT_TICKET_MISSING: "
            f"token={file_token} type={file_type} "
            f"extension={file_extension} response={detail}"
        )
    return ticket


def _poll_feishu_export_task(ticket, file_token, file_type, headers):
    """Poll a Feishu Drive export task until it finishes."""

    query = parse.urlencode({"token": file_token, "type": file_type})
    url = (
        "https://open.feishu.cn/open-apis/drive/v1/export_tasks/"
        f"{ticket}?{query}"
    )
    result = {}
    deadline = time.monotonic() + FEISHU_EXPORT_TIMEOUT_S
    while time.monotonic() < deadline:
        data = _http_json(url, headers=headers)
        data = data.get("data") or data
        result = data.get("result") or data
        status = _feishu_job_status(result)
        if status == FEISHU_EXPORT_SUCCESS_STATUS:
            return result
        if status not in FEISHU_EXPORT_PENDING_STATUSES:
            return result
        time.sleep(FEISHU_EXPORT_POLL_INTERVAL_S)
    detail = _feishu_export_status_detail(result)
    raise DataSourceSyncError(
        "LENS_SOURCE_EXPORT_TIMEOUT: "
        f"token={file_token} type={file_type} ticket={ticket} "
        f"last_result={detail}"
    )


def _feishu_job_status(result):
    """Return Feishu export job status as an integer when possible."""

    value = result.get("job_status")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _feishu_export_status_detail(result):
    """Return a readable Feishu export status detail."""

    status = _feishu_job_status(result)
    message = FEISHU_EXPORT_STATUS_MESSAGES.get(status, "unknown status")
    error_msg = str(result.get("job_error_msg") or "").strip()
    detail = (
        f"job_status={result.get('job_status')} status={message} "
        f"job_error_msg={error_msg or '-'}"
    )
    return f"{detail} result={_compact_json(result)}"


def _download_feishu_export_file(file_token, headers):
    """Download an exported Feishu Drive file."""

    url = (
        "https://open.feishu.cn/open-apis/drive/v1/export_tasks/file/"
        f"{file_token}/download"
    )
    return _http_bytes(url, headers=headers)


def _export_filename(exported, fallback_name, fallback_type):
    """Return a safe filename for an exported Feishu document."""

    file_name = exported.get("file_name") or fallback_name
    extension = exported.get("file_extension")
    extension = extension or _feishu_export_extension(fallback_type)
    stem = _safe_filename(file_name)
    if stem.lower().endswith(f".{extension.lower()}"):
        return stem
    return f"{stem}.{extension}"


def _download_feishu_file(file_token, headers):
    """Download a Feishu Drive file as bytes."""

    urls = [
        (
            "https://open.feishu.cn/open-apis/drive/v1/files/"
            f"{file_token}/download"
        ),
        (
            "https://open.feishu.cn/open-apis/drive/v1/medias/"
            f"{file_token}/download"
        ),
    ]
    last_error = None
    for url in urls:
        try:
            return _http_bytes(url, headers=headers)
        except DataSourceSyncError as exc:
            last_error = exc
            continue
    raise last_error or DataSourceSyncError("LENS_SOURCE_SYNC_FAILED")


def _http_json(url, method="GET", data=None, headers=None):
    """Request a JSON endpoint and return the decoded object."""

    req = request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with _urlopen_with_retries(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = _http_error_detail(exc)
        raise DataSourceSyncError(detail) from exc
    except Exception as exc:
        raise DataSourceSyncError(
            f"LENS_SOURCE_SYNC_FAILED: {type(exc).__name__}: {exc}"
        ) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DataSourceSyncError("LENS_SOURCE_RESPONSE_INVALID") from exc
    _raise_feishu_business_error(payload)
    return payload


def _http_bytes(url, headers=None):
    """Request a binary endpoint and return bytes."""

    req = request.Request(url, headers=headers or {}, method="GET")
    try:
        with _urlopen_with_retries(req, timeout=120) as response:
            return response.read()
    except error.HTTPError as exc:
        detail = _http_error_detail(exc)
        raise DataSourceSyncError(detail) from exc
    except Exception as exc:
        raise DataSourceSyncError(
            f"LENS_SOURCE_SYNC_FAILED: {type(exc).__name__}: {exc}"
        ) from exc


def _urlopen_with_retries(req, timeout, attempts=3):
    """Open a URL with short retries for transient network failures."""

    last_error = None
    for attempt in range(attempts):
        try:
            return request.urlopen(req, timeout=timeout)
        except error.HTTPError:
            raise
        except error.URLError as exc:
            last_error = exc
            if attempt + 1 >= attempts:
                raise
            time.sleep(1)
    raise last_error


def _http_error_detail(exc):
    """Return a compact HTTP error detail, including JSON body if present."""

    try:
        raw = exc.read().decode("utf-8")
    except Exception:
        raw = ""
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        code = payload.get("code") or payload.get("error")
        msg = payload.get("msg") or payload.get("message")
        if code or msg:
            return f"HTTP_{exc.code}: {code or ''} {msg or ''}".strip()
        return f"HTTP_{exc.code}: {raw[:300]}"
    return f"HTTP_{exc.code}: {exc.reason}"


def _raise_feishu_business_error(payload):
    """Raise when Feishu returns a JSON business error with HTTP 200."""

    code = payload.get("code")
    if code in (None, 0):
        return
    msg = payload.get("msg") or payload.get("message") or "Feishu API error"
    raise DataSourceSyncError(f"FEISHU_API_ERROR: {code} {msg}")


def _safe_filename(value):
    """Return a filesystem-safe filename stem."""

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip())
    return cleaned.strip("-") or "document"


def _compact_json(value):
    """Return compact JSON for diagnostics without oversized messages."""

    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        raw = str(value)
    if len(raw) > 1000:
        return f"{raw[:1000]}..."
    return raw


def _write_manifest(target, payload):
    """Write datasource sync manifest."""

    (target / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _count_files(path):
    """Return the number of non-git files under a path."""

    count = 0
    for item in path.rglob("*"):
        if ".git" in item.parts:
            continue
        if item.is_file():
            count += 1
    return count


def _emit(emit, step, status, message, **extra):
    """Emit a datasource sync progress event."""

    if emit is not None:
        payload = {
            "step": step,
            "status": status,
            "message": message,
            "timestamp": utc_timestamp(),
        }
        payload.update(extra)
        emit(payload)
