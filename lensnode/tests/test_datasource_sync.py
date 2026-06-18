import json
from concurrent.futures import ThreadPoolExecutor as RealThreadPoolExecutor

import pytest

from lensnode.datasource_sync import (
    DataSourceSyncError,
    datasource_sync_workers,
    _default_git_branch,
    _export_feishu_document,
    _export_filename,
    _feishu_folder_token,
    _feishu_export_extension,
    _git_remote_branches,
    _git_auth_url,
    _http_json,
    _poll_feishu_export_task,
    _raise_feishu_business_error,
    _sync_git,
    _sync_git_submodules,
    _sync_feishu_folder,
)


def test_datasource_sync_workers_defaults_to_four():
    """Datasource sync workers default to four and accept command override."""

    assert datasource_sync_workers({}) == 4
    assert datasource_sync_workers({"max_workers": "8"}) == 8
    assert datasource_sync_workers({"max_workers": "invalid"}) == 4


def test_git_auth_url_uses_inline_access_token():
    """HTTPS token auth can use the datasource config access token."""

    url = _git_auth_url(
        "https://github.com/example/repo.git",
        {
            "auth_scheme": "token",
            "access_token": "ghp_example",
        },
    )

    assert url == "https://oauth2:ghp_example@github.com/example/repo.git"


def test_git_remote_branches_parses_heads():
    """Remote branch discovery returns branch names."""

    output = (
        "abc\trefs/heads/main\n"
        "def\trefs/heads/feature/demo\n"
        "ghi\trefs/tags/v1.0.0\n"
    )

    assert _git_remote_branches(output) == ["main", "feature/demo"]


def test_default_git_branch_prefers_main():
    """Git connection tests can choose a branch when input is empty."""

    assert _default_git_branch(["dev", "main"]) == "main"
    assert _default_git_branch(["dev", "master"]) == "master"
    assert _default_git_branch(["release"]) == "release"


def test_sync_git_uses_shallow_clone(tmp_path, monkeypatch):
    """Git clone uses depth=1 for datasource cache sync."""

    calls = []

    def run_git(args, cwd=None, timeout=600, detail_prefix=""):
        del timeout
        calls.append((args, cwd, detail_prefix))
        target = tmp_path / "repo"
        target.mkdir(exist_ok=True)
        return None

    monkeypatch.setattr("lensnode.datasource_sync._run_git", run_git)
    monkeypatch.setattr(
        "lensnode.datasource_sync._count_files",
        lambda path: 1,
    )

    result = _sync_git(
        {
            "config": {
                "repo_url": "https://github.com/example/repo.git",
                "branch": "main",
            },
            "target_path": str(tmp_path / "repo"),
        },
        str(tmp_path),
        None,
    )

    assert result["synced"] == 1
    assert calls[0][0][:3] == ["clone", "--depth", "1"]
    assert calls[0][2] == "LENS_SOURCE_GIT_CLONE_FAILED"


def test_sync_git_update_uses_shallow_fetch(tmp_path, monkeypatch):
    """Existing Git datasource updates use shallow fetch and hard reset."""

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    calls = []

    def run_git(args, cwd=None, timeout=600, detail_prefix=""):
        del timeout
        calls.append((args, cwd, detail_prefix))
        return None

    monkeypatch.setattr("lensnode.datasource_sync._run_git", run_git)
    monkeypatch.setattr(
        "lensnode.datasource_sync._count_files",
        lambda path: 1,
    )

    _sync_git(
        {
            "config": {
                "repo_url": "https://github.com/example/repo.git",
                "branch": "main",
            },
            "target_path": str(repo),
        },
        str(tmp_path),
        None,
    )

    assert calls[0][0] == [
        "fetch",
        "--depth",
        "1",
        "origin",
        "main",
        "--prune",
    ]
    assert calls[1][0] == ["checkout", "main"]
    assert calls[2][0] == ["reset", "--hard", "origin/main"]


def test_sync_git_submodules_runs_when_declared(tmp_path, monkeypatch):
    """Repositories declaring submodules synchronize them recursively."""

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitmodules").write_text("", encoding="utf-8")
    calls = []

    def run_git(args, cwd=None, timeout=600, detail_prefix=""):
        del timeout
        calls.append((args, cwd, detail_prefix))
        return None

    monkeypatch.setattr("lensnode.datasource_sync._run_git", run_git)

    _sync_git_submodules(repo)

    assert calls[0][0] == ["submodule", "sync", "--recursive"]
    assert calls[1][0] == [
        "submodule",
        "update",
        "--init",
        "--recursive",
        "--depth",
        "1",
    ]
    assert calls[1][2] == "LENS_SOURCE_GIT_SUBMODULE_UPDATE_FAILED"


def test_feishu_folder_token_from_drive_url():
    """Feishu folder URLs can be normalized to folder tokens."""

    token = _feishu_folder_token(
        {"folder_url": "https://example.feishu.cn/drive/folder/fldabc123"}
    )

    assert token == "fldabc123"


def test_sync_feishu_folder_preserves_tree(tmp_path, monkeypatch):
    """Drive folder sync writes nested documents to local directories."""

    def list_children(folder_token, headers):
        del headers
        if folder_token == "root":
            return [
                {
                    "token": "child",
                    "name": "Child Folder",
                    "type": "folder",
                },
                {
                    "token": "doc1",
                    "name": "Root Doc",
                    "type": "docx",
                },
            ]
        if folder_token == "child":
            return [
                {
                    "token": "doc2",
                    "name": "Nested Doc",
                    "type": "docx",
                }
            ]
        return []

    def export_document(doc_id, item_type, headers):
        del item_type
        del headers
        return {
            "file_name": doc_id,
            "file_extension": "docx",
            "type": "docx",
            "content": f"content {doc_id}".encode("utf-8"),
        }

    monkeypatch.setattr(
        "lensnode.datasource_sync._list_feishu_folder_children",
        list_children,
    )
    monkeypatch.setattr(
        "lensnode.datasource_sync._export_feishu_document",
        export_document,
    )

    result = _sync_feishu_folder(
        {
            "folder_token": "root",
            "recursive": True,
            "max_depth": 5,
        },
        tmp_path,
        {},
        None,
    )

    assert result["synced"] == 2
    assert (tmp_path / "doc1.docx").exists()
    assert (tmp_path / "Child-Folder" / "doc2.docx").exists()


def test_sync_feishu_folder_uses_configured_workers(tmp_path, monkeypatch):
    """Drive folder sync creates a worker pool with configured size."""

    max_workers = []

    def list_children(folder_token, headers):
        del folder_token, headers
        return []

    def thread_pool_executor(*args, **kwargs):
        max_workers.append(kwargs.get("max_workers"))
        return RealThreadPoolExecutor(*args, **kwargs)

    monkeypatch.setattr(
        "lensnode.datasource_sync._list_feishu_folder_children",
        list_children,
    )
    monkeypatch.setattr(
        "lensnode.datasource_sync.ThreadPoolExecutor",
        thread_pool_executor,
    )

    _sync_feishu_folder(
        {
            "folder_token": "root",
            "recursive": True,
            "max_depth": 5,
        },
        tmp_path,
        {},
        None,
        max_workers=4,
    )

    assert max_workers == [4]


def test_sync_feishu_folder_skips_unchanged_item(tmp_path, monkeypatch):
    """Drive folder sync skips unchanged items from previous manifest."""

    exports = []

    def list_children(folder_token, headers):
        del folder_token, headers
        return [
            {
                "token": "doc1",
                "name": "Root Doc",
                "type": "docx",
                "modified_time": "100",
            }
        ]

    def export_document(doc_id, item_type, headers):
        del item_type, headers
        exports.append(doc_id)
        return {
            "file_name": "Root Doc",
            "file_extension": "docx",
            "type": "docx",
            "content": b"content",
        }

    monkeypatch.setattr(
        "lensnode.datasource_sync._list_feishu_folder_children",
        list_children,
    )
    monkeypatch.setattr(
        "lensnode.datasource_sync._export_feishu_document",
        export_document,
    )

    first = _sync_feishu_folder(
        {"folder_token": "root", "recursive": True, "max_depth": 5},
        tmp_path,
        {},
        None,
        max_workers=1,
    )
    second = _sync_feishu_folder(
        {"folder_token": "root", "recursive": True, "max_depth": 5},
        tmp_path,
        {},
        None,
        max_workers=1,
    )
    manifest = json.loads((tmp_path / "manifest.json").read_text())

    assert exports == ["doc1"]
    assert first["synced"] == 1
    assert second["synced"] == 0
    assert second["skipped"] == 1
    assert manifest["items"][0]["status"] == "skipped"


def test_feishu_export_filename_uses_original_extension():
    exported = {
        "file_name": "Example Doc",
        "file_extension": "docx",
    }

    assert _export_filename(exported, "fallback", "docx") == "Example-Doc.docx"
    assert _feishu_export_extension("bitable") == "xlsx"


def test_poll_feishu_export_task_waits_while_processing(monkeypatch):
    """Feishu job_status=2 means processing, not failed."""

    responses = [
        {"data": {"result": {"job_status": 2}}},
        {
            "data": {
                "result": {
                    "job_status": 0,
                    "file_token": "exported",
                }
            }
        },
    ]

    def http_json(*args, **kwargs):
        del args, kwargs
        return responses.pop(0)

    monkeypatch.setattr("lensnode.datasource_sync._http_json", http_json)
    monkeypatch.setattr("time.sleep", lambda *args, **kwargs: None)

    result = _poll_feishu_export_task("ticket", "doc", "docx", {})

    assert result["job_status"] == 0
    assert result["file_token"] == "exported"
    assert responses == []


def test_poll_feishu_export_task_accepts_string_processing_status(monkeypatch):
    """Feishu job_status may be returned as a string by API clients."""

    responses = [
        {"data": {"result": {"job_status": "2"}}},
        {
            "data": {
                "result": {
                    "job_status": "0",
                    "file_token": "exported",
                }
            }
        },
    ]

    def http_json(*args, **kwargs):
        del args, kwargs
        return responses.pop(0)

    monkeypatch.setattr("lensnode.datasource_sync._http_json", http_json)
    monkeypatch.setattr("time.sleep", lambda *args, **kwargs: None)

    result = _poll_feishu_export_task("ticket", "doc", "docx", {})

    assert result["job_status"] == "0"
    assert result["file_token"] == "exported"
    assert responses == []


def test_feishu_business_error_is_preserved():
    with pytest.raises(DataSourceSyncError) as exc:
        _raise_feishu_business_error(
            {"code": 99991663, "msg": "permission denied"}
        )

    assert "99991663" in str(exc.value)
    assert "permission denied" in str(exc.value)


def test_export_feishu_document_preserves_failed_result(monkeypatch):
    """Export failures keep Feishu result details for diagnosis."""

    monkeypatch.setattr(
        "lensnode.datasource_sync._create_feishu_export_task",
        lambda *args, **kwargs: "ticket1",
    )
    monkeypatch.setattr(
        "lensnode.datasource_sync._poll_feishu_export_task",
        lambda *args, **kwargs: {
            "job_status": 2,
            "job_error_msg": "permission denied",
            "file_extension": "docx",
        },
    )

    with pytest.raises(DataSourceSyncError) as exc:
        _export_feishu_document("doc1", "docx", {})

    message = str(exc.value)
    assert "LENS_SOURCE_EXPORT_FAILED" in message
    assert "doc1" in message
    assert "ticket1" in message
    assert "job_status=2" in message
    assert "processing" in message
    assert "permission denied" in message


def test_export_feishu_document_shows_official_status_reason(monkeypatch):
    """Export failures include Feishu job status and reason."""

    monkeypatch.setattr(
        "lensnode.datasource_sync._create_feishu_export_task",
        lambda *args, **kwargs: "ticket1",
    )
    monkeypatch.setattr(
        "lensnode.datasource_sync._poll_feishu_export_task",
        lambda *args, **kwargs: {
            "job_status": 107,
            "job_error_msg": "file exceeds limit",
        },
    )

    with pytest.raises(DataSourceSyncError) as exc:
        _export_feishu_document("doc1", "docx", {})

    message = str(exc.value)
    assert "job_status=107" in message
    assert "document too large" in message
    assert "file exceeds limit" in message


def test_sync_feishu_folder_fails_when_every_item_fails(tmp_path, monkeypatch):
    """A folder sync with only failed items should not be marked successful."""

    monkeypatch.setattr(
        "lensnode.datasource_sync._list_feishu_folder_children",
        lambda *args, **kwargs: [
            {
                "token": "doc1",
                "name": "Broken Doc",
                "type": "docx",
            }
        ],
    )

    def export_document(*args, **kwargs):
        del args, kwargs
        raise DataSourceSyncError("export failed")

    monkeypatch.setattr(
        "lensnode.datasource_sync._export_feishu_document",
        export_document,
    )

    with pytest.raises(DataSourceSyncError) as exc:
        _sync_feishu_folder(
            {
                "folder_token": "root",
                "recursive": True,
                "max_depth": 5,
            },
            tmp_path,
            {},
            None,
        )

    assert "all Feishu Drive items failed" in str(exc.value)
    assert (tmp_path / "manifest.json").exists()


def test_http_json_preserves_network_error(monkeypatch):
    def raise_timeout(*args, **kwargs):
        del args, kwargs
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", raise_timeout)

    with pytest.raises(DataSourceSyncError) as exc:
        _http_json("https://example.invalid")

    assert "TimeoutError" in str(exc.value)
