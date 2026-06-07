import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib import parse, request

from .models import DataSource


class SourceSyncError(ValueError):
    """Raised when datasource synchronization cannot proceed."""


def _run_git(args, cwd=None):
    """Run a git command and return the completed process."""

    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.CalledProcessError as exc:
        raise SourceSyncError("LENS_SOURCE_SYNC_FAILED") from exc
    except subprocess.TimeoutExpired as exc:
        raise SourceSyncError("LENS_SOURCE_SYNC_TIMEOUT") from exc


def _validate_no_inline_credentials(config):
    """Reject datasource configs that store secret values inline."""

    forbidden_keys = {
        "password",
        "token",
        "access_token",
        "secret",
        "private_key",
    }
    if forbidden_keys.intersection(config):
        raise SourceSyncError("LENS_SOURCE_INLINE_CREDENTIAL_FORBIDDEN")


def _credential_env_name(credentials_ref):
    """Return environment variable name for a credential reference."""

    normalized = "".join(
        char if char.isalnum() else "_" for char in str(credentials_ref).upper()
    )
    return f"LENS_CREDENTIAL_{normalized}"


def _load_credentials(config):
    """Load credentials from environment by config.credentials_ref."""

    credentials_ref = config.get("credentials_ref")
    if not credentials_ref:
        return {}
    raw = os.getenv(_credential_env_name(credentials_ref), "")
    if not raw:
        raise SourceSyncError("LENS_SOURCE_CREDENTIAL_NOT_FOUND")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SourceSyncError("LENS_SOURCE_CREDENTIAL_INVALID") from exc
    if not isinstance(value, dict):
        raise SourceSyncError("LENS_SOURCE_CREDENTIAL_INVALID")
    return value


def _http_get_json(url, headers=None, params=None):
    """GET a JSON document with urllib."""

    if params:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{parse.urlencode(params, doseq=True)}"
    req = request.Request(url, headers=headers or {}, method="GET")
    try:
        with request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except Exception as exc:
        raise SourceSyncError("LENS_SOURCE_SYNC_FAILED") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SourceSyncError("LENS_SOURCE_RESPONSE_INVALID") from exc


def _write_json(path, payload):
    """Write formatted JSON payload to a path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _target_cache_path(datasource, namespace):
    """Return the cache path for a non-git datasource namespace."""

    if not datasource.target_path:
        raise SourceSyncError("LENS_SOURCE_TARGET_PATH_REQUIRED")
    target = Path(datasource.target_path)
    return target / namespace


def _target_git_path(datasource):
    """Return the cache path for a git datasource."""

    if not datasource.target_path:
        raise SourceSyncError("LENS_SOURCE_TARGET_PATH_REQUIRED")
    return Path(datasource.target_path)


def _sync_git(datasource):
    """Clone or update a git datasource into local cache."""

    config = datasource.config
    _validate_no_inline_credentials(config)
    repo_url = config.get("repo_url")
    if not repo_url:
        raise SourceSyncError("LENS_SOURCE_CONFIG_INVALID")

    branch = config.get("branch") or "main"
    target = _target_git_path(datasource)
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() and not (target / ".git").exists():
        raise SourceSyncError("LENS_SOURCE_CACHE_NOT_GIT_REPO")

    if not target.exists():
        _run_git(
            [
                "clone",
                "--branch",
                branch,
                "--single-branch",
                repo_url,
                str(target),
            ]
        )
    else:
        _run_git(["fetch", "origin", branch, "--prune"], cwd=target)
        _run_git(["checkout", branch], cwd=target)
        _run_git(["reset", "--hard", f"origin/{branch}"], cwd=target)

    datasource.target_path = str(target)
    return 1


def _sync_jira(datasource):
    """Synchronize Jira search results into local cache."""

    config = datasource.config
    _validate_no_inline_credentials(config)
    base_url = config.get("base_url")
    if not base_url:
        raise SourceSyncError("LENS_SOURCE_CONFIG_INVALID")
    credentials = _load_credentials(config)
    auth_scheme = config.get("auth_scheme", "bearer")
    headers = {"Accept": "application/json"}
    if credentials:
        if auth_scheme == "bearer":
            bearer = credentials.get("bearer_token") or credentials.get("token")
            if not bearer:
                raise SourceSyncError("LENS_SOURCE_CREDENTIAL_INVALID")
            headers["Authorization"] = f"Bearer {bearer}"
        elif auth_scheme == "basic":
            import base64

            username = credentials.get("username")
            api_token = credentials.get("api_token")
            if not username or not api_token:
                raise SourceSyncError("LENS_SOURCE_CREDENTIAL_INVALID")
            raw = f"{username}:{api_token}".encode("utf-8")
            headers["Authorization"] = f'Basic {base64.b64encode(raw).decode("ascii")}'

    query_rules = config.get("query_rules") or {}
    field_mapping = config.get("field_mapping") or {}
    fields = list(field_mapping.values()) or [
        "summary",
        "description",
        "status",
        "updated",
    ]
    params = {
        "jql": query_rules.get("jql", "ORDER BY updated DESC"),
        "fields": ",".join(fields),
        "maxResults": int(query_rules.get("max_results", 50)),
    }
    url = f'{base_url.rstrip("/")}/rest/api/2/search'
    payload = _http_get_json(url, headers=headers, params=params)
    issues = payload.get("issues", [])
    target = _target_cache_path(datasource, "jira")
    _write_json(target / "issues.json", payload)
    return len(issues)


def _sync_feishu(datasource):
    """Synchronize Feishu document metadata into local cache."""

    config = datasource.config
    _validate_no_inline_credentials(config)
    app_token = config.get("app_token")
    doc_ids = config.get("doc_ids") or []
    if not app_token or not isinstance(doc_ids, list):
        raise SourceSyncError("LENS_SOURCE_CONFIG_INVALID")
    credentials = _load_credentials(config)
    tenant_token = credentials.get("tenant_access_token")
    if credentials and not tenant_token:
        raise SourceSyncError("LENS_SOURCE_CREDENTIAL_INVALID")

    headers = {"Accept": "application/json"}
    if tenant_token:
        headers["Authorization"] = f"Bearer {tenant_token}"

    documents = []
    for doc_id in doc_ids:
        url = (
            "https://open.feishu.cn/open-apis/drive/v1/files/"
            f"{parse.quote(str(doc_id))}"
        )
        documents.append(_http_get_json(url, headers=headers))

    payload = {
        "app_token": app_token,
        "documents": documents,
    }
    target = _target_cache_path(datasource, "feishu")
    _write_json(target / "documents.json", payload)
    return len(documents)


def sync_datasource(datasource):
    """Synchronize one datasource by type."""

    if datasource.source_type == DataSource.SourceType.GIT:
        return _sync_git(datasource)

    if datasource.source_type == DataSource.SourceType.JIRA:
        return _sync_jira(datasource)

    if datasource.source_type == DataSource.SourceType.FEISHU:
        return _sync_feishu(datasource)

    raise SourceSyncError("LENS_SOURCE_TYPE_UNSUPPORTED")


def reset_cache_path(path):
    """Remove a datasource cache path for tests or manual cleanup."""

    if path and Path(path).exists():
        shutil.rmtree(path)
