import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, parse, request

from . import datasource_manifest as manifest_store
from .datasource_adapters import DataSourceAdapterRegistry
from .datasource_adapters import FunctionDataSourceAdapter
from .datasource_archives import is_file_target_owned, sync_file_archive
from .document_convert import is_convertible, post_process_documents
from .path_rules import is_excluded_path
from .path_rules import normalize_excluded_roots
from .path_rules import relative_path
from .path_rules import safe_filename
from .path_rules import source_sha256
from .path_rules import stable_suffix
from .path_rules import unique_child_path

WORKSPACE_ROOT = "/workspace"
GIT_SHALLOW_DEPTH = "1"
DETAIL_ITEMS_LIMIT = 200
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
        if source_type == "managed_workspace":
            result.update(
                {
                    "source_compatible": False,
                    "status": "blocked",
                    "message_code": "managed_workspace_missing",
                    "message": (
                        "Managed workspace directory does not exist."
                    ),
                }
            )
            return result
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
    if source_type == "managed_workspace":
        result["message_code"] = "managed_workspace_available"
        result["message"] = "Managed workspace directory is available."
        return result
    if result["is_empty"]:
        result["message_code"] = "empty"
        result["message"] = "Directory is empty and can be used."
        return result

    if source_type == "file":
        if not is_file_target_owned(
            target,
            command.get("datasource_uuid"),
        ):
            result.update(
                {
                    "source_compatible": False,
                    "status": "blocked",
                    "message_code": "file_target_not_owned",
                    "message": (
                        "Directory is not owned by this file datasource."
                    ),
                }
            )
            return result
        result["message_code"] = "file_replace"
        result["message"] = "Existing file datasource will be replaced."
        return result

    if source_type == "git" and config.get("git_organization_parent"):
        result["message_code"] = "merge"
        result["message"] = "Directory exists; repositories will be stored in child directories."
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
    adapter = datasource_adapter_registry().get(source_type)
    if adapter is None:
        raise DataSourceSyncError("LENS_SOURCE_TYPE_UNSUPPORTED")
    result = adapter.sync(command, workspace_path, emit)

    target = Path(result.get("target_path") or "").resolve()
    if not target:
        return result
    target_transaction = result.pop("_target_transaction", None)
    try:
        if target_transaction:
            target_transaction.check_cancelled()
        context = _sync_context(command, target)
        manifest_store.write_datasource_marker(target, context)
        if target_transaction:
            target_transaction.check_cancelled()
        sync_items = result.pop("_sync_items", [])
        changed_paths = result.pop("_changed_paths", [])
        deleted_paths = result.pop("_deleted_paths", [])
        sync_result = manifest_store.SyncResult(
            items=sync_items,
            changed_paths=changed_paths,
            deleted_paths=deleted_paths,
            stats=_sync_summary_from_result(result),
        )
        sync_details = _sync_details_by_metric(
            sync_items,
            changed_paths,
            deleted_paths,
        )
        if sync_details["details"]:
            result["details"] = sync_details["details"]
            result["details_truncated"] = sync_details[
                "details_truncated"
            ]
        changed_details = sync_details["details"].get("changed") or []
        if changed_details:
            result["changed_items"] = changed_details
            result["changed_items_truncated"] = sync_details[
                "details_truncated"
            ].get("changed", 0)
        if sync_items:
            manifest_payload = manifest_store.build_manifest(
                context,
                sync_result,
            )
            manifest_payload["synced_at"] = utc_timestamp()
            manifest_store.write_manifest(target, manifest_payload)
        if target_transaction:
            target_transaction.check_cancelled()

        deleted_sidecars = manifest_store.cleanup_deleted_sidecars(
            target,
            deleted_paths,
            context["excluded_datasource_roots"],
        )
        if target_transaction:
            target_transaction.check_cancelled()
        conversion_summary = post_process_documents(
            context,
            sync_result,
            emit,
        )
        conversion_summary["deleted_sidecars"] = deleted_sidecars
        result["conversion_summary"] = conversion_summary
        if target_transaction:
            target_transaction.commit()
    except BaseException:
        if target_transaction:
            target_transaction.rollback()
        raise
    return result


def convert_managed_workspace(
    command,
    workspace_path=WORKSPACE_ROOT,
    emit=None,
):
    """Convert files in a managed workspace without synchronizing it."""

    if command.get("source_type") != "managed_workspace":
        raise DataSourceSyncError("DATASOURCE_CONVERSION_NOT_SUPPORTED")
    target = normalize_target_path(
        command.get("target_path"),
        workspace_path,
    )
    if not target.is_dir():
        raise DataSourceSyncError("MANAGED_WORKSPACE_DIRECTORY_REQUIRED")

    context = _sync_context(command, target)
    items = _managed_workspace_conversion_items(
        target,
        context["excluded_datasource_roots"],
    )
    supported = [
        item
        for item in items
        if is_convertible(target / item.local_path, context["conversion"])
    ]
    unsupported = [
        item
        for item in items
        if not is_convertible(
            target / item.local_path,
            context["conversion"],
        )
    ]

    def emit_progress(event):
        if emit is None:
            return
        payload = dict(event)
        current = int(payload.get("progress_current") or 0)
        payload["summary"] = _managed_conversion_summary(
            payload.get("summary") or {},
            unsupported,
            len(supported),
            current,
        )
        payload["progress_total"] = len(items)
        payload["progress_current"] = len(unsupported) + current
        payload["progress_percent"] = _conversion_percent(
            payload["progress_current"],
            len(items),
        )
        emit(payload)

    summary = post_process_documents(
        context,
        manifest_store.SyncResult(items=supported),
        emit_progress,
    )
    summary = _managed_conversion_summary(
        summary,
        unsupported,
        len(supported),
        len(supported),
    )
    if summary["failed"]:
        summary["warnings"] = list(
            dict.fromkeys(
                [
                    *(summary.get("warnings") or []),
                    "CONVERSION_PARTIAL_FAILED",
                ]
            )
        )
    _emit(
        emit,
        "conversion_complete",
        "done",
        "Managed workspace conversion completed.",
        category="conversion",
        progress_total=len(items),
        progress_current=len(items),
        progress_percent=100,
        summary=summary,
        conversion_summary=summary,
    )
    return {
        "status": "success",
        "target_path": str(target),
        "conversion_summary": summary,
        "warnings": summary.get("warnings") or [],
    }


def _managed_workspace_conversion_items(target, excluded_roots):
    """Return files found under a managed workspace conversion root."""

    items = []
    for path in sorted(target.rglob("*")):
        if not path.is_file() or _is_generated_datasource_path(target, path):
            continue
        if is_excluded_path(path, excluded_roots):
            continue
        try:
            local_path = relative_path(target, path)
        except ValueError:
            continue
        items.append(
            manifest_store.SyncItem(
                source_id=f"managed_workspace:{local_path}",
                source_type="managed_workspace",
                source_path=local_path,
                local_path=local_path,
                name=path.name,
                kind="file",
                extension=path.suffix.lower().lstrip("."),
                status="cataloged",
                metadata={"size": str(path.stat().st_size)},
            )
        )
    return items


def _managed_conversion_summary(
    summary,
    unsupported,
    supported_total,
    supported_current,
):
    """Add standalone conversion lifecycle counters and outcomes."""

    result = dict(summary or {})
    unsupported_items = [
        {
            "status": "unsupported",
            "path": item.local_path,
            "name": item.name,
            "extension": item.extension,
            "reason": "UNSUPPORTED_TYPE",
            "stats": {},
        }
        for item in unsupported
    ]
    items = list(result.get("items") or [])
    existing_paths = {item.get("path") for item in items}
    available = max(DETAIL_ITEMS_LIMIT - len(items), 0)
    new_items = [
        item
        for item in unsupported_items
        if item["path"] not in existing_paths
    ]
    items.extend(new_items[:available])
    completed = min(max(supported_current, 0), supported_total)
    remaining = max(supported_total - completed, 0)
    active = 1 if remaining else 0
    result.update(
        {
            "total": supported_total + len(unsupported),
            "waiting": max(remaining - active, 0),
            "active": active,
            "succeeded": int(result.get("success") or 0),
            "unsupported": len(unsupported),
            "items": items,
            "items_truncated": int(result.get("items_truncated") or 0)
            + max(len(new_items) - available, 0),
        }
    )
    details = dict(result.get("details") or {})
    if unsupported_items:
        details["unsupported"] = unsupported_items[:DETAIL_ITEMS_LIMIT]
    result["details"] = details
    return result


def _conversion_percent(current, total):
    """Return a bounded integer conversion progress percentage."""

    if total <= 0:
        return 100
    return min(100, int((current / total) * 100))


def datasource_adapter_registry():
    """Return the datasource adapter registry."""

    registry = DataSourceAdapterRegistry()
    registry.register(FunctionDataSourceAdapter("git", _sync_git))
    registry.register(FunctionDataSourceAdapter("feishu", _sync_feishu))
    registry.register(FunctionDataSourceAdapter("file", sync_file_archive))
    return registry


def _sync_context(command, target):
    """Return the common datasource sync context."""

    conversion = (command.get("sync_policy") or {}).get("conversion")
    conversion = command.get("conversion") or conversion or {}
    return {
        "datasource_uuid": str(command.get("datasource_uuid") or ""),
        "name": command.get("name") or "",
        "source_type": command.get("source_type") or "",
        "target_path": str(target),
        "config": command.get("config") or {},
        "conversion": conversion,
        "trigger": command.get("trigger") or "",
        "max_workers": command.get("max_workers") or 0,
        "excluded_datasource_roots": normalize_excluded_roots(
            command.get("excluded_datasource_roots") or [],
            target,
        ),
        "ai_gateway_url": command.get("ai_gateway_url") or "",
        "lensnode_token": command.get("lensnode_token") or "",
        "gateway_http_client": command.get("gateway_http_client"),
        "tls_skip_verify": bool(command.get("tls_skip_verify", False)),
        "tls_ca_file": command.get("tls_ca_file") or None,
        "vision_model_ref": conversion.get("vision_model_ref") or "",
        "force": bool(command.get("force", False)),
        "cancel_event": command.get("cancel_event"),
        "on_activity": command.get("on_activity"),
    }


def _sync_summary_from_result(result):
    """Return sync summary fields from a datasource result."""

    keys = [
        "synced",
        "files",
        "folders",
        "failed",
        "scanned",
        "changed",
        "skipped",
        "deleted",
        "documents",
        "by_extension",
        "by_type",
    ]
    return {key: result.get(key) for key in keys if key in result}


def _sync_details_by_metric(items, changed_paths, deleted_paths):
    """Return compact sync details grouped by summary metric."""

    changed = set(changed_paths or [])
    deleted = set(deleted_paths or [])
    details = {
        "scanned": [],
        "changed": [],
        "skipped": [],
        "success": [],
        "failed": [],
        "deleted": [],
        "documents": [],
        "files": [],
    }
    truncated = {key: 0 for key in details}
    for item in items or []:
        local_path = manifest_store.manifest_local_path(item)
        status = item.get("status") or "synced"
        detail = _sync_detail_item(item, local_path)
        if status != "deleted":
            _append_limited_detail(details, truncated, "scanned", detail)
        if local_path not in changed:
            if status == "skipped":
                _append_limited_detail(details, truncated, "skipped", detail)
            elif status == "deleted":
                _append_limited_detail(details, truncated, "deleted", detail)
            elif status == "failed" or item.get("error"):
                _append_limited_detail(details, truncated, "failed", detail)
        else:
            _append_limited_detail(details, truncated, "changed", detail)
            if status == "failed" or item.get("error"):
                _append_limited_detail(details, truncated, "failed", detail)
            else:
                _append_limited_detail(details, truncated, "success", detail)
        kind = item.get("kind") or item.get("type") or ""
        if kind == "document":
            _append_limited_detail(details, truncated, "documents", detail)
        elif kind == "file":
            _append_limited_detail(details, truncated, "files", detail)

    for path in deleted:
        if any(item.get("path") == path for item in details["deleted"]):
            continue
        detail = {
            "status": "deleted",
            "path": path,
            "name": Path(path).name,
            "extension": Path(path).suffix.lower().lstrip("."),
            "source_type": "",
        }
        _append_limited_detail(details, truncated, "deleted", detail)

    return {
        "details": {key: value for key, value in details.items() if value},
        "details_truncated": {
            key: value for key, value in truncated.items() if value
        },
    }


def _sync_detail_item(item, local_path):
    """Return one compact sync detail item."""

    return {
        "status": item.get("status") or "synced",
        "path": local_path,
        "name": item.get("name") or Path(local_path).name,
        "extension": (
            item.get("extension")
            or item.get("file_extension")
            or Path(local_path).suffix.lower().lstrip(".")
        ),
        "source_type": item.get("source_type") or "",
        "reason": item.get("error") or "",
    }


def _append_limited_detail(details, truncated, key, item):
    """Append a detail item with a per-metric limit."""

    if len(details[key]) >= DETAIL_ITEMS_LIMIT:
        truncated[key] += 1
        return
    details[key].append(item)


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
        organization_result = _discover_git_organization(config)
        if organization_result is not None:
            return organization_result
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


def _discover_git_organization(config):
    """Return repositories under a Git organization URL when supported."""

    repo_url = config.get("repo_url")
    parsed = parse.urlsplit(str(repo_url or "").rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    group_path = parsed.path.strip("/")
    if not group_path:
        return None

    projects, attempts = _discover_git_projects(parsed, group_path, config)
    if not projects:
        if not str(parsed.path or "").rstrip("/").endswith(".git"):
            return {
                "status": "failed",
                "message_code": "git_organization_unreachable",
                "message": "Git organization is not reachable.",
                "details": {
                    "scope": "organization",
                    "organization_url": repo_url,
                    "attempts": attempts,
                },
            }
        return None

    repositories = _git_project_repositories(projects, config)
    if not repositories:
        return None
    owner_types = sorted(
        {
            project.get("owner_type")
            for project in projects
            if project.get("owner_type")
        }
    )
    return {
        "status": "success",
        "message_code": "git_organization_available",
        "message": "Git organization is reachable.",
        "details": {
            "scope": "organization",
            "owner_type": owner_types[0] if len(owner_types) == 1 else "",
            "organization_url": repo_url,
            "repositories": repositories,
        },
    }


def _git_project_repositories(projects, config):
    """Return repository entries with branch details."""

    repositories = []
    max_workers = min(12, max(1, len(projects)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_git_project_repository, project, config)
            for project in projects
        ]
        for future in as_completed(futures):
            repository = future.result()
            if repository is not None:
                repositories.append(repository)
    repositories.sort(key=lambda item: item.get("name") or "")
    return repositories


def _git_project_repository(project, config):
    """Return one repository entry with branches."""

    clone_url = project.get("repo_url") or ""
    if not clone_url:
        return None
    branches = _git_project_branches(project, config)
    selected_branch = (
        project.get("default_branch")
        if project.get("default_branch") in branches
        else _default_git_branch(branches)
    )
    return {
        "name": project.get("name") or _repo_name_from_url(clone_url),
        "path": project.get("path") or project.get("name") or "",
        "repo_url": clone_url,
        "default_branch": selected_branch,
        "branches": branches,
    }


def _git_project_branches(project, config):
    """Return branches for a discovered Git project."""

    if project.get("service") == "gitlab" and project.get("api_id") is not None:
        branches = _gitlab_project_branches(project, config)
        if branches:
            return branches
    clone_url = project.get("repo_url") or ""
    return _git_repo_branches(clone_url, config)


def _gitlab_project_branches(project, config):
    """Return GitLab project branches through the GitLab API."""

    api_base_url = project.get("api_base_url") or ""
    api_id = project.get("api_id")
    if not api_base_url or api_id is None:
        return []
    branches = []
    for page in range(1, 11):
        url = (
            f"{api_base_url}/api/v4/projects/{parse.quote(str(api_id), safe='')}"
            f"/repository/branches?per_page=100&page={page}"
        )
        payload, _error_detail = _git_api_json(
            url,
            config,
            auth_style="gitlab",
            timeout=10,
        )
        if not isinstance(payload, list):
            return branches
        if not payload:
            break
        branches.extend(
            item.get("name")
            for item in payload
            if item.get("name")
        )
        if len(payload) < 100:
            break
    return branches


def _discover_git_projects(parsed, group_path, config):
    """Discover projects from supported Git organization APIs."""

    attempts = []
    provider = str(config.get("provider") or "").lower()
    hostname = str(parsed.hostname or "").lower()
    if provider == "github" or hostname == "github.com":
        projects, github_attempts = _discover_github_projects(
            parsed,
            group_path,
            config,
        )
        attempts.extend(github_attempts)
        return projects, attempts
    if provider == "gitlab":
        projects, attempt = _discover_gitlab_projects(
            parsed,
            group_path,
            config,
        )
        attempts.append(attempt)
        return projects, attempts
    projects, attempt = _discover_gitlab_projects(parsed, group_path, config)
    attempts.append(attempt)
    if projects:
        return projects, attempts
    projects, attempt = _discover_gitea_projects(parsed, group_path, config)
    attempts.append(attempt)
    return projects, attempts


def _discover_github_projects(parsed, group_path, config):
    """Discover repositories from a GitHub owner or repository URL."""

    api_base = _github_api_base(parsed, config)
    parts = [part for part in group_path.split("/") if part]
    if not parts:
        return None, []
    if len(parts) >= 2:
        owner, repo = parts[0], parts[1]
        url = (
            f"{api_base}/repos/{parse.quote(owner, safe='')}"
            f"/{parse.quote(repo, safe='')}"
        )
        payload, error_detail = _git_api_json(
            url,
            config,
            auth_style="github",
        )
        if not isinstance(payload, dict):
            return None, [_git_api_attempt("github", url, error_detail)]
        return (
            [_github_project(payload, api_base, "repo")],
            [_git_api_attempt("github", url, error_detail)],
        )

    owner = parts[0]
    projects, attempts = _discover_github_owner_projects(
        api_base,
        owner,
        "org",
        config,
    )
    if projects:
        return projects, attempts
    user_projects, user_attempts = _discover_github_owner_projects(
        api_base,
        owner,
        "user",
        config,
    )
    attempts.extend(user_attempts)
    return user_projects, attempts


def _github_api_base(parsed, config):
    """Return the GitHub API base URL for public or enterprise GitHub."""

    endpoint = str(config.get("endpoint_url") or "").rstrip("/")
    if endpoint:
        endpoint_parsed = parse.urlsplit(endpoint)
        if endpoint_parsed.netloc == "github.com":
            return "https://api.github.com"
        return f"{endpoint}/api/v3"
    if parsed.netloc == "github.com":
        return "https://api.github.com"
    base_url = parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    return f"{base_url}/api/v3"


def _discover_github_owner_projects(api_base, owner, owner_type, config):
    """Discover GitHub repositories for an organization or user owner."""

    projects = []
    attempts = []
    last_error = ""
    owner_path = "orgs" if owner_type == "org" else "users"
    for page in range(1, 11):
        url = (
            f"{api_base}/{owner_path}/{parse.quote(owner, safe='')}/repos"
            f"?per_page=100&page={page}"
        )
        payload, error_detail = _git_api_json(
            url,
            config,
            auth_style="github",
        )
        attempts.append(_git_api_attempt("github", url, error_detail))
        if not isinstance(payload, list):
            last_error = error_detail
            return None if page == 1 else projects, attempts
        if not payload:
            break
        projects.extend(
            _github_project(item, api_base, owner_type)
            for item in payload
        )
        if len(payload) < 100:
            break
    if last_error and not projects:
        return None, attempts
    return projects, attempts


def _github_project(item, api_base, owner_type):
    """Return a normalized GitHub repository project entry."""

    return {
        "service": "github",
        "api_base_url": api_base,
        "owner_type": owner_type,
        "name": item.get("name") or item.get("full_name"),
        "path": item.get("full_name") or item.get("name"),
        "repo_url": item.get("clone_url") or item.get("html_url") or "",
        "default_branch": item.get("default_branch") or "",
    }


def _discover_gitlab_projects(parsed, group_path, config):
    """Discover projects from a GitLab group URL."""

    encoded_group = parse.quote(group_path, safe="")
    base_url = parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    projects = []
    last_error = ""
    for page in range(1, 11):
        url = (
            f"{base_url}/api/v4/groups/{encoded_group}/projects"
            f"?include_subgroups=true&simple=true&per_page=100&page={page}"
        )
        payload, error_detail = _git_api_json(
            url,
            config,
            auth_style="gitlab",
        )
        if not isinstance(payload, list):
            last_error = error_detail
            return (
                None if page == 1 else projects,
                _git_api_attempt("gitlab", url, last_error),
            )
        if not payload:
            break
        projects.extend(
            {
                "service": "gitlab",
                "api_base_url": base_url,
                "api_id": item.get("id"),
                "name": item.get("name") or item.get("path"),
                "path": item.get("path") or item.get("name"),
                "repo_url": (
                    item.get("http_url_to_repo")
                    or item.get("web_url")
                    or ""
                ),
                "default_branch": item.get("default_branch") or "",
            }
            for item in payload
        )
        if len(payload) < 100:
            break
    return projects, _git_api_attempt("gitlab", url, last_error)


def _discover_gitea_projects(parsed, group_path, config):
    """Discover repositories from a Gitea organization URL."""

    org = group_path.split("/", 1)[0]
    base_url = parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    projects = []
    last_error = ""
    for page in range(1, 11):
        url = (
            f"{base_url}/api/v1/orgs/{parse.quote(org)}/repos"
            f"?limit=100&page={page}"
        )
        payload, error_detail = _git_api_json(
            url,
            config,
            auth_style="gitea",
        )
        if not isinstance(payload, list):
            last_error = error_detail
            return (
                None if page == 1 else projects,
                _git_api_attempt("gitea", url, last_error),
            )
        if not payload:
            break
        projects.extend(
            {
                "service": "gitea",
                "name": item.get("name") or item.get("full_name"),
                "path": item.get("name") or item.get("full_name"),
                "repo_url": (
                    item.get("clone_url")
                    or item.get("html_url")
                    or ""
                ),
                "default_branch": item.get("default_branch") or "",
            }
            for item in payload
        )
        if len(payload) < 100:
            break
    return projects, _git_api_attempt("gitea", url, last_error)


def _git_api_attempt(service, url, error_detail):
    """Return a compact Git API discovery attempt detail."""

    return {
        "service": service,
        "url": url,
        "error": error_detail or "",
    }


def _git_api_json(url, config, auth_style, timeout=30):
    """Fetch JSON from a Git service API."""

    headers = {"Accept": "application/json"}
    credentials = _load_credentials(config)
    token = credentials.get("token") or credentials.get("password")
    if token and auth_style == "gitlab":
        headers["PRIVATE-TOKEN"] = token
    elif token and auth_style == "github":
        headers["Authorization"] = f"Bearer {token}"
    elif token and auth_style == "gitea":
        headers["Authorization"] = f"token {token}"
    req = request.Request(url, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), ""
    except error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")[:500]
        except Exception:
            body = ""
        return None, f"HTTP {exc.code}: {body}"
    except error.URLError as exc:
        return None, str(exc.reason)
    except TimeoutError:
        return None, "request timed out"
    except json.JSONDecodeError as exc:
        return None, f"invalid json: {exc}"


def _git_repo_branches(repo_url, config):
    """Return remote branches for one repository URL."""

    try:
        auth_url = _git_auth_url(repo_url, config)
        result = _run_git(
            ["ls-remote", "--heads", auth_url],
            timeout=60,
            detail_prefix="LENS_SOURCE_GIT_LS_REMOTE_FAILED",
        )
    except DataSourceSyncError:
        return []
    return _git_remote_branches(result.stdout)


def _repo_name_from_url(repo_url):
    """Return a displayable repository name from a clone URL."""

    path = parse.urlsplit(repo_url or "").path.rstrip("/")
    name = path.rsplit("/", 1)[-1] if path else ""
    return name[:-4] if name.endswith(".git") else name


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
    if config.get("scope_type") == "organization" or config.get("repositories"):
        return _sync_git_organization(command, workspace_path, emit)

    repo_url = config.get("repo_url")
    if not repo_url:
        raise DataSourceSyncError("LENS_SOURCE_CONFIG_INVALID")

    target = normalize_target_path(command.get("target_path"), workspace_path)
    branch = config.get("branch") or "main"
    auth_url = _git_auth_url(repo_url, config)
    previous_manifest = _read_manifest(target)
    previous_items = manifest_store.manifest_items_by_source_id(
        previous_manifest
    )
    _emit(emit, "check_path", "running", "Checking target directory.")
    inspection = inspect_datasource_path(command, workspace_path)
    if not inspection.get("source_compatible"):
        raise DataSourceSyncError(inspection.get("message") or "PATH_BLOCKED")

    target.parent.mkdir(parents=True, exist_ok=True)
    _emit(emit, "sync_content", "running", "Synchronizing Git repository.")
    if not (target / ".git").exists():
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

    items = _git_manifest_items(target, repo_url, branch)
    changed_paths, deleted_paths, skipped = _git_manifest_delta(
        items,
        previous_items,
    )
    files = len(items)
    summary = {
        "scanned": files,
        "changed": len(changed_paths),
        "skipped": skipped,
        "deleted": len(deleted_paths),
        "failed": 0,
        "files": files,
        "folders": 0,
        "documents": 0,
        "by_extension": _count_file_extensions(target),
        "by_type": {"git": 1},
    }
    _emit(
        emit,
        "manifest",
        "done",
        (
            f"Git sync completed with {files} files, "
            f"{summary['changed']} changed, {skipped} skipped."
        ),
        category="summary",
        progress_total=1,
        progress_current=1,
        progress_percent=100,
        summary=summary,
    )
    return {
        "synced": 1,
        "files": files,
        "target_path": str(target),
        "_sync_items": items,
        "_changed_paths": changed_paths,
        "_deleted_paths": deleted_paths,
        **summary,
    }


def _sync_git_organization(command, workspace_path, emit):
    """Synchronize multiple Git repositories under one datasource root."""

    config = command.get("config") or {}
    repositories = [
        item for item in config.get("repositories") or []
        if item.get("enabled", True)
    ]
    if not repositories:
        raise DataSourceSyncError("LENS_SOURCE_CONFIG_INVALID")

    root = normalize_target_path(command.get("target_path"), workspace_path)
    root.mkdir(parents=True, exist_ok=True)
    totals = {
        "synced": 0,
        "files": 0,
        "folders": 0,
        "documents": 0,
        "scanned": 0,
        "changed": 0,
        "skipped": 0,
        "deleted": 0,
        "failed": 0,
        "by_extension": {},
        "by_type": {"git": len(repositories)},
    }
    sync_items = []
    changed_paths = []
    deleted_paths = []
    repository_summaries = []
    failed_repositories = []
    total = len(repositories)
    _emit(
        emit,
        "sync_plan",
        "running",
        f"Prepared {total} Git repositories for synchronization.",
        category="summary",
        progress_total=total,
        progress_current=0,
        progress_percent=0,
        summary=totals,
    )
    for index, repository in enumerate(repositories, start=1):
        name = repo_target_subdir(repository)
        repo_target = root / name
        repo_command = {
            **command,
            "target_path": str(repo_target),
            "config": {
                **config,
                "repo_url": repository.get("repo_url") or "",
                "branch": repository.get("branch") or config.get("branch") or "main",
            },
        }
        repo_command["config"].pop("repositories", None)
        repo_command["config"]["scope_type"] = "repository"
        _emit(
            emit,
            "repository_started",
            "running",
            f"Synchronizing Git repository {name}.",
            category="repository",
            progress_total=total,
            progress_current=index - 1,
            progress_percent=int(((index - 1) / total) * 100),
            current_file=name,
        )
        repository_event_status = "done"
        repository_event_message = f"Finished Git repository {name}."
        repository_event_error = ""
        try:
            result = _sync_git(repo_command, workspace_path, emit)
            repo_items = result.pop("_sync_items", [])
            repo_changed = result.pop("_changed_paths", [])
            repo_deleted = result.pop("_deleted_paths", [])
            _write_git_repository_manifest(
                repo_command,
                repo_target,
                result,
                repo_items,
                repo_changed,
                repo_deleted,
            )
            prefixed_items = _prefix_sync_items(repo_items, name)
            sync_items.extend(prefixed_items)
            changed_paths.extend(_prefix_paths(repo_changed, name))
            deleted_paths.extend(_prefix_paths(repo_deleted, name))
            _merge_git_summary(totals, result)
            totals["synced"] += 1
            repository_summaries.append(
                _repository_summary(name, repository, "success", result)
            )
        except Exception as exc:
            totals["failed"] += 1
            repository_event_status = "failed"
            repository_event_error = str(exc)
            repository_event_message = (
                f"Failed Git repository {name}: {repository_event_error}"
            )
            failure = _repository_summary(
                name,
                repository,
                "failed",
                {"error": str(exc)},
            )
            failed_repositories.append(failure)
            repository_summaries.append(failure)
        _emit(
            emit,
            "repository_done",
            repository_event_status,
            repository_event_message,
            category="repository",
            progress_total=total,
            progress_current=index,
            progress_percent=int((index / total) * 100),
            summary=totals,
            current_file=name,
            error=repository_event_error,
        )

    return {
        **totals,
        "status": (
            "failed" if failed_repositories and not totals["synced"] else "success"
        ),
        "target_path": str(root),
        "repository_summaries": repository_summaries,
        "failed_repositories": failed_repositories,
        "partial_success": bool(failed_repositories and totals["synced"]),
        "_sync_items": sync_items,
        "_changed_paths": changed_paths,
        "_deleted_paths": deleted_paths,
    }


def repo_target_subdir(repository):
    """Return a stable target subdirectory for a repository item."""

    raw = (
        repository.get("target_subdir")
        or repository.get("name")
        or repository.get("path")
        or _repo_name_from_url(repository.get("repo_url") or "")
        or "repository"
    )
    return safe_filename(str(raw).strip()) or "repository"


def _write_git_repository_manifest(
    command,
    target,
    result,
    items,
    changed_paths,
    deleted_paths,
):
    context = _sync_context(command, target)
    sync_result = manifest_store.SyncResult(
        items=items,
        changed_paths=changed_paths,
        deleted_paths=deleted_paths,
        stats=_sync_summary_from_result(result),
    )
    payload = manifest_store.build_manifest(context, sync_result)
    payload["synced_at"] = utc_timestamp()
    manifest_store.write_datasource_marker(target, context)
    manifest_store.write_manifest(target, payload)


def _prefix_sync_items(items, prefix):
    result = []
    for item in items or []:
        local_path = f"{prefix}/{item.local_path}"
        source_path = f"{prefix}/{item.source_path}"
        result.append(
            manifest_store.SyncItem(
                source_id=item.source_id,
                source_type=item.source_type,
                source_path=source_path,
                local_path=local_path,
                name=item.name,
                kind=item.kind,
                extension=item.extension,
                status=item.status,
                metadata=item.metadata,
                remote=item.remote,
            )
        )
    return result


def _prefix_paths(paths, prefix):
    return [f"{prefix}/{path}" for path in paths or []]


def _merge_git_summary(target, source):
    for key in [
        "files",
        "folders",
        "documents",
        "scanned",
        "changed",
        "skipped",
        "deleted",
    ]:
        target[key] += int(source.get(key) or 0)
    for extension, count in (source.get("by_extension") or {}).items():
        for _ in range(int(count or 0)):
            _increment_counter(target["by_extension"], extension)


def _repository_summary(name, repository, status, result):
    return {
        "name": name,
        "repo_url": repository.get("repo_url") or "",
        "branch": repository.get("branch") or "",
        "status": status,
        "files": result.get("files") or 0,
        "changed": result.get("changed") or 0,
        "skipped": result.get("skipped") or 0,
        "deleted": result.get("deleted") or 0,
        "error": result.get("error") or "",
    }


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


def _git_manifest_items(target, repo_url, branch):
    """Return unified manifest items for a Git datasource."""

    items = []
    commit = _git_output(["rev-parse", "HEAD"], cwd=target)
    for path in sorted(target.rglob("*")):
        if not path.is_file():
            continue
        if _is_generated_datasource_path(target, path):
            continue
        local_path = relative_path(target, path)
        extension = path.suffix.lower().lstrip(".")
        source_id = f"git:{repo_url}:{branch}:{local_path}"
        items.append(
            manifest_store.SyncItem(
                source_id=source_id,
                source_type="git",
                source_path=local_path,
                local_path=local_path,
                name=path.name,
                kind="file",
                extension=extension,
                status="synced",
                metadata={
                    "commit": commit,
                    "size": str(path.stat().st_size),
                    "sha256": source_sha256(path),
                },
                remote={
                    "repo_url": repo_url,
                    "branch": branch,
                    "path": local_path,
                },
            )
        )
    return items


def _git_manifest_delta(items, previous_items):
    """Return changed and deleted Git paths compared with previous manifest."""

    current_ids = set()
    changed_paths = []
    skipped = 0
    for item in items:
        source_id = manifest_store.manifest_source_id(item)
        current_ids.add(source_id)
        previous_item = previous_items.get(source_id)
        if previous_item and _git_item_signature(
            item.to_manifest()
        ) == _git_item_signature(previous_item):
            skipped += 1
            item.status = "skipped"
            continue
        changed_paths.append(item.local_path)

    deleted_paths = []
    for source_id, previous_item in previous_items.items():
        if source_id in current_ids:
            continue
        local_path = _manifest_local_path(previous_item)
        if local_path:
            deleted_paths.append(local_path)
    return changed_paths, deleted_paths, skipped


def _git_item_signature(item):
    """Return comparable Git file metadata."""

    metadata = item.get("metadata") or {}
    return {
        "source_type": item.get("source_type") or "git",
        "local_path": _manifest_local_path(item),
        "extension": item.get("extension") or item.get("file_extension") or "",
        "size": str(metadata.get("size") or ""),
        "sha256": str(metadata.get("sha256") or ""),
    }


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
    sync_items = []
    max_workers = max(1, int(max_workers or 1))
    stats = {
        "scanned": len(doc_ids),
        "changed": len(doc_ids),
        "skipped": 0,
        "deleted": 0,
        "failed": 0,
        "folders": 0,
        "documents": 0,
        "files": 0,
        "by_extension": {},
        "by_type": {"docx": len(doc_ids)},
    }
    _emit(
        emit,
        "sync_plan",
        "running",
        f"Prepared {len(doc_ids)} Feishu documents for export.",
        category="summary",
        progress_total=len(doc_ids),
        progress_current=0,
        progress_percent=100 if not doc_ids else 0,
        summary=stats,
    )
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
            try:
                item = future.result()
                documents.append(item)
                sync_items.append(_manifest_item_to_sync_item(item, target))
                synced += 1
                stats["documents"] += 1
                stats["files"] += 1
                _increment_counter(
                    stats["by_extension"],
                    _manifest_item_extension(item),
                )
            except DataSourceSyncError:
                stats["failed"] += 1
                raise
            _emit(
                emit,
                "sync_progress",
                "running",
                f"Exported {synced}/{len(doc_ids)} Feishu documents.",
                category="summary",
                progress_total=len(doc_ids),
                progress_current=synced,
                progress_percent=_progress_percent(synced, len(doc_ids)),
                summary=stats,
            )

    _write_manifest(
        target,
        {
            "source_type": "feishu",
            "synced_at": utc_timestamp(),
            "stats": stats,
            "documents": documents,
        },
    )
    _emit(
        emit,
        "manifest",
        "done",
        f"Feishu sync completed with {synced} documents.",
        category="summary",
        progress_total=len(doc_ids),
        progress_current=synced,
        progress_percent=100,
        summary=stats,
    )
    return {
        "synced": synced,
        "files": synced,
        "target_path": str(target),
        "_sync_items": sync_items,
        "_changed_paths": [item.local_path for item in sync_items],
        "_deleted_paths": [],
        **stats,
    }


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

    previous_manifest = _read_manifest(target)
    previous_items = _manifest_items_by_token(previous_manifest)
    incremental = config.get(
        "feishu_incremental",
        config.get("incremental", True),
    ) is not False
    delete_missing = config.get(
        "feishu_delete_missing",
        config.get("delete_missing", False),
    ) is True
    seen_tokens = set()
    manifest_items = []
    deleted_paths = []
    pending_items = []
    stats = {
        "folders": 0,
        "documents": 0,
        "files": 0,
        "scanned": 0,
        "changed": 0,
        "skipped": 0,
        "deleted": 0,
        "failed": 0,
        "by_extension": {},
        "by_type": {},
    }

    def emit_scan_progress(force=False):
        if not force and stats["scanned"] % 25 != 0:
            return
        _emit(
            emit,
            "scan_progress",
            "running",
            (
                f"Scanned {stats['scanned']} Feishu Drive items in "
                f"{stats['folders']} folders."
            ),
            category="summary",
            progress_current=stats["scanned"],
            summary=stats,
        )

    def scan(current_token, current_dir, depth):
        stats["folders"] += 1
        _emit(
            emit,
            "scan_folder",
            "running",
            f"Scanning Feishu folder {current_token}.",
            category="summary",
            progress_current=stats["scanned"],
            summary=stats,
        )
        children = _list_feishu_folder_children(current_token, headers)
        item_futures = {}
        for child in children:
            name = _feishu_item_name(child)
            item_type = _feishu_item_type(child)
            token = _feishu_item_token(child)
            if not token:
                continue
            seen_tokens.add(token)
            stats["scanned"] += 1
            _increment_counter(stats["by_type"], item_type or "unknown")
            emit_scan_progress()
            if item_type == "folder":
                if not recursive or depth >= max_depth:
                    continue
                next_dir = current_dir / _safe_filename(name)
                next_dir.mkdir(parents=True, exist_ok=True)
                scan(token, next_dir, depth + 1)
                continue
            previous_item = previous_items.get(token)
            if incremental and _feishu_item_unchanged(
                child,
                previous_item,
                current_dir,
                root_dir,
            ):
                item = _feishu_manifest_item_from_previous(
                    child,
                    previous_item,
                    current_dir,
                    root_dir,
                )
                manifest_items.append(item)
                stats["skipped"] += 1
                _increment_counter(
                    stats["by_extension"],
                    _manifest_item_extension(item),
                )
                _emit(
                    emit,
                    "item_skipped",
                    "done",
                    f"Skipped unchanged Feishu {name}.",
                    category="document",
                    token=token,
                    item_type=item_type,
                    item_name=name,
                    file=item.get("file"),
                )
                continue
            pending_items.append((child, current_dir, previous_item))

    scan(folder_token, root_dir, 1)
    emit_scan_progress(force=True)
    stats["changed"] = len(pending_items)
    _emit(
        emit,
        "sync_plan",
        "running",
        (
            f"Scanned {stats['scanned']} items; "
            f"{stats['changed']} need sync, {stats['skipped']} skipped."
        ),
        category="summary",
        progress_total=stats["changed"],
        progress_current=0,
        progress_percent=100 if stats["changed"] == 0 else 0,
        summary=stats,
    )

    completed = 0
    max_workers = max(1, int(max_workers or 1))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        item_futures = {
            executor.submit(
                _sync_feishu_drive_item,
                child,
                current_dir,
                root_dir,
                previous_item,
                headers,
                emit,
            ): child
            for child, current_dir, previous_item in pending_items
        }
        for future in as_completed(item_futures):
            child = item_futures[future]
            name = _feishu_item_name(child)
            item_type = _feishu_item_type(child)
            token = _feishu_item_token(child)
            completed += 1
            try:
                item = future.result()
                manifest_items.append(item)
                if item.get("kind") == "document":
                    stats["documents"] += 1
                else:
                    stats["files"] += 1
                _increment_counter(
                    stats["by_extension"],
                    _manifest_item_extension(item),
                )
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
            _emit(
                emit,
                "sync_progress",
                "running",
                (
                    f"Synced {completed}/{stats['changed']} changed items."
                ),
                category="summary",
                progress_total=stats["changed"],
                progress_current=completed,
                progress_percent=_progress_percent(
                    completed,
                    stats["changed"],
                ),
                summary=stats,
            )

    for token, item in previous_items.items():
        if token in seen_tokens:
            continue
        deleted_item = {**item, "status": "deleted"}
        manifest_items.append(deleted_item)
        stats["deleted"] += 1
        local_path = _manifest_local_path(item)
        if local_path:
            deleted_paths.append(local_path)
        if delete_missing and local_path:
            _delete_manifest_file(target, local_path)
    _write_manifest(
        target,
        {
            "source_type": "feishu",
            "sync_mode": "drive_folder",
            "folder_token": folder_token,
            "incremental": incremental,
            "delete_missing": delete_missing,
            "synced_at": utc_timestamp(),
            "stats": stats,
            "items": manifest_items,
        },
    )
    total = stats["documents"] + stats["files"]
    total_success = total + stats["skipped"]
    if total_success == 0 and stats["failed"] > 0:
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
        (
            f"Feishu folder sync completed with {total} files, "
            f"{stats['skipped']} skipped."
        ),
        category="summary",
        summary=stats,
    )
    return {
        "synced": total,
        "files": total,
        "target_path": str(target),
        "folders": stats["folders"],
        "scanned": stats["scanned"],
        "changed": stats["changed"],
        "skipped": stats["skipped"],
        "deleted": stats["deleted"],
        "failed": stats["failed"],
        "documents": stats["documents"],
        "by_extension": stats["by_extension"],
        "by_type": stats["by_type"],
        "_sync_items": [
            _manifest_item_to_sync_item(item, target)
            for item in manifest_items
        ],
        "_changed_paths": [
            _manifest_local_path(item)
            for item in manifest_items
            if item.get("status") not in {"deleted", "skipped"}
        ],
        "_deleted_paths": deleted_paths,
    }


def _sync_feishu_drive_item(
    item,
    target_dir,
    root_dir,
    previous_item,
    headers,
    emit,
):
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
        path = _feishu_target_file_path(
            target_dir,
            root_dir,
            filename,
            token,
            previous_item,
        )
        path.write_bytes(exported["content"])
        local_path = relative_path(root_dir, path)
        _emit(
            emit,
            "item_done",
            "done",
            f"Exported Feishu {name} to {local_path}.",
            category="document",
            kind="document",
            token=token,
            item_type=item_type,
            item_name=exported.get("file_name") or name or token,
            file=local_path,
            file_extension=exported.get("file_extension") or "",
        )
        return {
            "kind": "document",
            "token": token,
            "source_id": f"feishu:token:{token}",
            "source_path": name or token,
            "name": exported.get("file_name") or name or token,
            "type": item_type,
            "file": local_path,
            "local_path": local_path,
            "file_extension": exported.get("file_extension") or "",
            "metadata": _feishu_item_sync_metadata(item),
            "remote": {"token": token, "type": item_type},
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
    path = _feishu_target_file_path(
        target_dir,
        root_dir,
        filename,
        token,
        previous_item,
    )
    path.write_bytes(raw)
    local_path = relative_path(root_dir, path)
    _emit(
        emit,
        "item_done",
        "done",
        f"Downloaded Feishu {name} to {local_path}.",
        category="file",
        kind="file",
        token=token,
        item_type=item_type,
        item_name=name,
        file=local_path,
    )
    return {
        "kind": "file",
        "token": token,
        "source_id": f"feishu:token:{token}",
        "source_path": name or token,
        "name": name,
        "type": item_type,
        "file": local_path,
        "local_path": local_path,
        "file_extension": _feishu_item_file_extension(item),
        "metadata": _feishu_item_sync_metadata(item),
        "remote": {"token": token, "type": item_type},
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
        "slide",
        "slides",
        "bitable",
        "base",
    }


def _feishu_export_type(item_type):
    """Return the Feishu export API type for a Drive item type."""

    if item_type in {"doc", "docx", "docs"}:
        return "docx"
    if item_type == "sheet":
        return "sheet"
    if item_type in {"slide", "slides"}:
        return "slides"
    if item_type in {"bitable", "base"}:
        return "bitable"
    return item_type or "docx"


def _feishu_export_extension(item_type):
    """Return the preferred original-format export extension."""

    export_type = _feishu_export_type(item_type)
    mapping = {
        "docx": "docx",
        "sheet": "xlsx",
        "slides": "pptx",
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


def _feishu_item_sync_metadata(item):
    """Return metadata used to decide whether a Feishu item changed."""

    metadata = {}
    for source, target in [
        ("modified_time", "modified_time"),
        ("updated_time", "modified_time"),
        ("edit_time", "modified_time"),
        ("size", "size"),
        ("checksum", "checksum"),
        ("md5", "checksum"),
    ]:
        value = item.get(source)
        if value not in (None, ""):
            metadata[target] = str(value)
    return metadata


def _feishu_item_signature(item):
    """Return comparable Feishu metadata, or empty when unavailable."""

    metadata = _feishu_item_sync_metadata(item)
    signature = {
        key: metadata[key]
        for key in ["modified_time", "size", "checksum"]
        if metadata.get(key)
    }
    item_type = _feishu_item_type(item)
    if item_type:
        signature["type"] = item_type
    if _is_feishu_exportable_type(item_type):
        signature["file_extension"] = _feishu_export_extension(item_type)
    else:
        file_extension = _feishu_item_file_extension(item)
        if file_extension:
            signature["file_extension"] = file_extension
    if any(key != "type" for key in signature):
        return signature
    token = _feishu_item_token(item)
    name = _feishu_item_name(item)
    if token:
        signature["token"] = token
    if name:
        signature["name"] = name
    return signature if token or name else {}


def _feishu_item_file_extension(item):
    """Return a comparable file extension for a Feishu Drive item."""

    name = _feishu_item_name(item)
    extension = Path(str(name or "")).suffix.lower().lstrip(".")
    return extension or ""


def _feishu_manifest_signature(item):
    """Return comparable metadata from a manifest item."""

    metadata = item.get("metadata") or {}
    remote = item.get("remote") or {}
    signature = {
        key: str(metadata[key])
        for key in ["modified_time", "size", "checksum"]
        if metadata.get(key) not in (None, "")
    }
    item_type = remote.get("type") or item.get("type")
    if item_type:
        signature["type"] = item_type
    if item.get("file_extension"):
        signature["file_extension"] = item.get("file_extension")
    if any(key != "type" for key in signature):
        return signature
    token = item.get("token") or remote.get("token")
    name = item.get("name") or item.get("source_path")
    if token:
        signature["token"] = token
    if name:
        signature["name"] = name
    return signature if token or name else {}


def _feishu_item_unchanged(item, previous_item, target_dir, root_dir=None):
    """Return whether a remote Feishu item can be skipped."""

    if not previous_item or previous_item.get("status") == "deleted":
        return False
    signature = _feishu_item_signature(item)
    previous_signature = _feishu_manifest_signature(previous_item)
    if not signature or signature != previous_signature:
        return False
    previous_file = _manifest_local_path(previous_item)
    if not previous_file:
        return False
    paths = _feishu_previous_file_paths(previous_file, target_dir, root_dir)
    return any(path.exists() for path in paths)


def _feishu_previous_file_paths(previous_file, target_dir, root_dir=None):
    """Return candidate local paths for a previous Feishu manifest item."""

    previous_path = Path(str(previous_file))
    if previous_path.is_absolute():
        return [previous_path]
    paths = []
    if root_dir is not None:
        paths.append(Path(root_dir) / previous_path)
    paths.append(Path(target_dir) / previous_path.name)
    paths.append(Path(target_dir) / previous_path)
    return list(dict.fromkeys(paths))


def _feishu_target_file_path(
    target_dir,
    root_dir,
    filename,
    token,
    previous_item=None,
):
    """Return a stable local path for a Feishu file download."""

    previous_file = _manifest_local_path(previous_item or {})
    if previous_file:
        for path in _feishu_previous_file_paths(
            previous_file,
            target_dir,
            root_dir,
        ):
            try:
                path.resolve().relative_to(Path(root_dir).resolve())
            except ValueError:
                continue
            if path.exists():
                return path
    path = unique_child_path(target_dir, filename, token)
    stable_path = target_dir / _feishu_stable_filename(filename, token)
    if stable_path.exists():
        return stable_path
    return path


def _feishu_stable_filename(filename, token):
    """Return the stable conflict filename for one Feishu item."""

    path = Path(filename)
    suffix = stable_suffix(token or filename)
    stem = path.stem or "document"
    return f"{stem}__{suffix}{path.suffix}"


def _feishu_manifest_item_from_previous(
    item,
    previous_item,
    target_dir,
    root_dir=None,
):
    """Return manifest metadata for an unchanged Feishu item."""

    token = _feishu_item_token(item)
    name = _feishu_item_name(item)
    item_type = _feishu_item_type(item)
    previous_file = _manifest_local_path(previous_item)
    return {
        **previous_item,
        "kind": previous_item.get("kind") or "document",
        "token": token,
        "source_id": f"feishu:token:{token}",
        "source_path": previous_item.get("source_path") or name,
        "name": name,
        "type": item_type,
        "file": previous_file,
        "local_path": previous_file,
        "metadata": _feishu_item_sync_metadata(item),
        "remote": {"token": token, "type": item_type},
        "status": "skipped",
    }


def _manifest_items_by_token(manifest):
    """Return manifest items keyed by token."""

    return manifest_store.manifest_items_by_token(manifest)


def _manifest_local_path(item):
    """Return current or legacy local path for one manifest item."""

    return item.get("local_path") or item.get("file") or ""


def _manifest_item_to_sync_item(item, target):
    """Return a unified sync item from current or legacy manifest data."""

    local_path = _manifest_local_path(item)
    token = item.get("token") or (item.get("remote") or {}).get("token") or ""
    source_id = item.get("source_id") or (
        f"feishu:token:{token}" if token else local_path
    )
    path = Path(local_path)
    extension = item.get("file_extension") or item.get("extension")
    extension = extension or path.suffix.lower().lstrip(".")
    return manifest_store.SyncItem(
        source_id=source_id,
        source_type=item.get("source_type") or "feishu",
        source_path=item.get("source_path") or item.get("name") or local_path,
        local_path=local_path,
        name=item.get("name") or path.name,
        kind=item.get("kind") or item.get("type") or "file",
        extension=extension,
        status=item.get("status") or "synced",
        metadata=item.get("metadata") or {},
        remote=item.get("remote") or {"token": token, "type": item.get("type")},
    )


def _increment_counter(counter, key):
    """Increment a normalized counter key."""

    key = str(key or "unknown").strip().lower() or "unknown"
    counter[key] = int(counter.get(key) or 0) + 1


def _manifest_item_extension(item):
    """Return a normalized file extension for a manifest item."""

    extension = str(
        item.get("file_extension") or item.get("extension") or ""
    ).strip().lower()
    if extension:
        return extension.lstrip(".") or "unknown"
    file_name = str(item.get("file") or item.get("name") or "")
    suffix = Path(file_name).suffix.lower().lstrip(".")
    return suffix or str(item.get("type") or "unknown").lower()


def _progress_percent(current, total):
    """Return bounded integer progress percentage."""

    try:
        current_value = int(current or 0)
        total_value = int(total or 0)
    except (TypeError, ValueError):
        return 0
    if total_value <= 0:
        return 100
    return max(0, min(100, int(current_value * 100 / total_value)))


def _delete_manifest_file(target, file_name):
    """Delete a file listed in manifest if it is under target."""

    try:
        path = (target / str(file_name)).resolve()
        path.relative_to(target.resolve())
    except ValueError:
        return
    if path.is_file():
        path.unlink()


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

    return safe_filename(value)


def _compact_json(value):
    """Return compact JSON for diagnostics without oversized messages."""

    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        raw = str(value)
    if len(raw) > 1000:
        return f"{raw[:1000]}..."
    return raw


def _read_manifest(target):
    """Read datasource sync manifest if it exists."""

    return manifest_store.read_manifest(target)


def _write_manifest(target, payload):
    """Write datasource sync manifest."""

    manifest_store.write_manifest(target, payload)


def _count_files(path):
    """Return the number of non-git files under a path."""

    count = 0
    for item in path.rglob("*"):
        if _is_generated_datasource_path(path, item):
            continue
        if item.is_file():
            count += 1
    return count


def _count_file_extensions(path):
    """Return non-git file counts grouped by extension."""

    counts = {}
    for item in path.rglob("*"):
        if _is_generated_datasource_path(path, item) or not item.is_file():
            continue
        _increment_counter(counts, item.suffix.lower().lstrip("."))
    return counts


def _is_generated_datasource_path(root, path):
    """Return whether a path is generated datasource metadata."""

    try:
        parts = Path(path).relative_to(root).parts
    except ValueError:
        parts = Path(path).parts
    if ".git" in parts:
        return True
    if any(part.endswith(".sourcelens") for part in parts):
        return True
    return Path(path).name in {
        "manifest.json",
        "manifest.json.tmp",
        ".sourcelens-datasource.json",
    }


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
