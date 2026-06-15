import base64
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib import parse, request

WORKSPACE_ROOT = "/workspace"


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

    branch = config.get("branch") or "main"
    auth_url = _git_auth_url(repo_url, config)
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", auth_url, branch],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as exc:
        del exc
        return {
            "status": "failed",
            "message_code": "git_unreachable",
            "message": "Git repository is not reachable.",
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "message_code": "connection_timeout",
            "message": "Connection test timed out.",
        }

    if not result.stdout.strip():
        return {
            "status": "failed",
            "message_code": "git_branch_missing",
            "message": "Git branch does not exist or is not accessible.",
            "details": {"branch": branch},
        }
    return {
        "status": "success",
        "message_code": "git_branch_available",
        "message": "Git repository is reachable and branch exists.",
        "details": {"branch": branch},
    }


def _test_feishu_connection(config):
    """Test that Feishu document identifiers are available."""

    doc_ids = _feishu_doc_ids(config)
    if not doc_ids:
        return {
            "status": "failed",
            "message_code": "feishu_document_missing",
            "message": "Feishu document ID or URL is required.",
        }

    credentials = _load_credentials(config)
    token = _feishu_tenant_token(credentials)
    if not token:
        return {
            "status": "success",
            "message_code": "feishu_config_available",
            "message": "Feishu document configuration is available.",
            "details": {"doc_id": doc_ids[0]},
        }

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        document = _fetch_feishu_document(doc_ids[0], headers)
    except DataSourceSyncError:
        return {
            "status": "failed",
            "message_code": "feishu_unreachable",
            "message": "Feishu document is not reachable.",
            "details": {"doc_id": doc_ids[0]},
        }
    return {
        "status": "success",
        "message_code": "feishu_document_available",
        "message": "Feishu document is reachable.",
        "details": {
            "doc_id": doc_ids[0],
            "title": document.get("title") or "",
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
                "--branch",
                branch,
                "--single-branch",
                auth_url,
                str(target),
            ]
        )
    else:
        _run_git(["fetch", "origin", branch, "--prune"], cwd=target)
        _run_git(["checkout", branch], cwd=target)
        _run_git(["reset", "--hard", f"origin/{branch}"], cwd=target)

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


def _sync_feishu(command, workspace_path, emit):
    """Export Feishu document content into Markdown files."""

    config = command.get("config") or {}
    credentials = _load_credentials(config)
    target = normalize_target_path(command.get("target_path"), workspace_path)
    target.mkdir(parents=True, exist_ok=True)
    docs_dir = target / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    doc_ids = _feishu_doc_ids(config)
    if not doc_ids:
        raise DataSourceSyncError("LENS_SOURCE_CONFIG_INVALID")

    token = _feishu_tenant_token(credentials)
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    synced = 0
    documents = []
    for doc_id in doc_ids:
        _emit(emit, "sync_content", "running", f"Exporting Feishu {doc_id}.")
        document = _fetch_feishu_document(doc_id, headers)
        title = document.get("title") or doc_id
        content = document.get("content") or ""
        markdown = _document_to_markdown(title, content, document)
        filename = f"{_safe_filename(title)}.md"
        (docs_dir / filename).write_text(markdown, encoding="utf-8")
        documents.append(
            {
                "doc_id": doc_id,
                "title": title,
                "file": f"docs/{filename}",
                "source_url": document.get("url") or "",
            }
        )
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
    )
    return {"synced": synced, "files": synced, "target_path": str(target)}


def _run_git(args, cwd=None):
    """Run a Git command and raise a datasource error on failure."""

    try:
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.CalledProcessError as exc:
        raise DataSourceSyncError("LENS_SOURCE_SYNC_FAILED") from exc
    except subprocess.TimeoutExpired as exc:
        raise DataSourceSyncError("LENS_SOURCE_SYNC_TIMEOUT") from exc


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


def _fetch_feishu_document(doc_id, headers):
    """Fetch Feishu document content with a conservative API fallback."""

    urls = [
        f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/raw_content",
        f"https://open.feishu.cn/open-apis/drive/v1/files/{doc_id}",
    ]
    last_error = None
    for url in urls:
        try:
            payload = _http_json(url, headers=headers)
        except DataSourceSyncError as exc:
            last_error = exc
            continue
        data = payload.get("data") or payload
        title = data.get("title") or data.get("name") or doc_id
        content = (
            data.get("content")
            or data.get("raw_content")
            or data.get("text")
            or ""
        )
        return {
            "title": title,
            "content": content,
            "url": data.get("url") or data.get("shortcut_url") or "",
            "raw": data,
        }
    raise last_error or DataSourceSyncError("LENS_SOURCE_SYNC_FAILED")


def _http_json(url, method="GET", data=None, headers=None):
    """Request a JSON endpoint and return the decoded object."""

    req = request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except Exception as exc:
        raise DataSourceSyncError("LENS_SOURCE_SYNC_FAILED") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DataSourceSyncError("LENS_SOURCE_RESPONSE_INVALID") from exc


def _document_to_markdown(title, content, document):
    """Return Markdown content for a Feishu document export."""

    lines = [f"# {title}", ""]
    if content:
        lines.extend([str(content).strip(), ""])
    else:
        encoded = base64.b64encode(
            json.dumps(
                document.get("raw") or {},
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8")
        ).decode("ascii")
        lines.extend(
            [
                "> Feishu did not return text content for this document.",
                "",
                f"<!-- raw_json_base64: {encoded} -->",
                "",
            ]
        )
    return "\n".join(lines)


def _safe_filename(value):
    """Return a filesystem-safe Markdown filename stem."""

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip())
    return cleaned.strip("-") or "document"


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


def _emit(emit, step, status, message):
    """Emit a datasource sync progress event."""

    if emit is not None:
        emit(
            {
                "step": step,
                "status": status,
                "message": message,
                "timestamp": utc_timestamp(),
            }
        )
