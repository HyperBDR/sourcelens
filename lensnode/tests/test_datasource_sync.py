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
    _feishu_export_type,
    _is_feishu_exportable_type,
    _feishu_item_unchanged,
    _feishu_target_file_path,
    _git_remote_branches,
    _git_auth_url,
    _http_json,
    _manifest_item_to_sync_item,
    _poll_feishu_export_task,
    _raise_feishu_business_error,
    _sync_git,
    _sync_git_submodules,
    _sync_feishu_folder,
)
from lensnode.path_rules import source_sha256
from lensnode.path_rules import stable_suffix


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


def test_sync_git_reports_manifest_delta(tmp_path, monkeypatch):
    """Git sync reports changed, skipped, and deleted paths from manifest."""

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    unchanged = repo / "unchanged.md"
    changed = repo / "changed.md"
    unchanged.write_text("same", encoding="utf-8")
    changed.write_text("new", encoding="utf-8")
    (repo / "manifest.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "source_id": (
                            "git:https://github.com/example/repo.git:"
                            "main:unchanged.md"
                        ),
                        "source_type": "git",
                        "local_path": "unchanged.md",
                        "extension": "md",
                        "metadata": {
                            "size": str(unchanged.stat().st_size),
                            "sha256": source_sha256(unchanged),
                        },
                    },
                    {
                        "source_id": (
                            "git:https://github.com/example/repo.git:"
                            "main:deleted.md"
                        ),
                        "source_type": "git",
                        "local_path": "deleted.md",
                        "extension": "md",
                        "metadata": {"size": "7", "sha256": "deleted"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    def git_output(args, cwd=None):
        del cwd
        if args[:3] == ["remote", "get-url", "origin"]:
            return "https://github.com/example/repo.git"
        if args == ["rev-parse", "HEAD"]:
            return "commit1"
        return ""

    monkeypatch.setattr("lensnode.datasource_sync._git_output", git_output)
    monkeypatch.setattr(
        "lensnode.datasource_sync._run_git",
        lambda *args, **kwargs: None,
    )

    result = _sync_git(
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

    assert result["changed"] == 1
    assert result["skipped"] == 1
    assert result["deleted"] == 1
    assert result["_changed_paths"] == ["changed.md"]
    assert result["_deleted_paths"] == ["deleted.md"]


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


def test_sync_feishu_folder_skips_unchanged_nested_item(tmp_path, monkeypatch):
    """Nested Feishu items use root-relative manifest paths when skipped."""

    exports = []

    def list_children(folder_token, headers):
        del headers
        if folder_token == "root":
            return [
                {
                    "token": "child",
                    "name": "Child Folder",
                    "type": "folder",
                }
            ]
        if folder_token == "child":
            return [
                {
                    "token": "doc1",
                    "name": "Nested Doc",
                    "type": "docx",
                    "modified_time": "100",
                }
            ]
        return []

    def export_document(doc_id, item_type, headers):
        del item_type, headers
        exports.append(doc_id)
        return {
            "file_name": "Nested Doc",
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

    assert exports == ["doc1"]
    assert first["synced"] == 1
    assert second["synced"] == 0
    assert second["skipped"] == 1


def test_sync_feishu_folder_skips_raw_file_without_metadata(
    tmp_path,
    monkeypatch,
):
    """Raw Feishu files without mtime/size still use stable identity."""

    downloads = []

    def list_children(folder_token, headers):
        del folder_token, headers
        return [
            {
                "token": "file1",
                "name": "Report.pdf",
                "type": "pdf",
            }
        ]

    def download_file(file_token, headers):
        del headers
        downloads.append(file_token)
        return b"pdf content"

    monkeypatch.setattr(
        "lensnode.datasource_sync._list_feishu_folder_children",
        list_children,
    )
    monkeypatch.setattr(
        "lensnode.datasource_sync._download_feishu_file",
        download_file,
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

    assert downloads == ["file1"]
    assert first["synced"] == 1
    assert second["synced"] == 0
    assert second["skipped"] == 1


def test_feishu_unchanged_uses_remote_type_from_unified_manifest(tmp_path):
    """Feishu comparison survives the unified manifest type field."""

    source = tmp_path / "Root Doc.docx"
    source.write_bytes(b"content")
    previous = _manifest_item_to_sync_item(
        {
            "kind": "document",
            "token": "doc1",
            "source_id": "feishu:token:doc1",
            "source_path": "Root Doc",
            "name": "Root Doc",
            "type": "docx",
            "file": "Root Doc.docx",
            "local_path": "Root Doc.docx",
            "file_extension": "docx",
            "metadata": {"modified_time": "100"},
            "remote": {"token": "doc1", "type": "docx"},
        },
        tmp_path,
    ).to_manifest()

    assert previous["type"] == "document"
    assert _feishu_item_unchanged(
        {
            "token": "doc1",
            "name": "Root Doc",
            "type": "docx",
            "modified_time": "100",
        },
        previous,
        tmp_path,
        tmp_path,
    )


def test_feishu_unchanged_matches_raw_file_extension_from_name(tmp_path):
    """Raw Feishu files compare manifest extension with filename suffix."""

    source = (
        tmp_path
        / "个人内容"
        / "2026年出差"
        / "4月份-4.13-15-武汉"
        / "26379166812001512498"
        / "26379166812001512498.pdf"
    )
    source.parent.mkdir(parents=True)
    source.write_bytes(b"pdf content")
    local_path = source.relative_to(tmp_path).as_posix()
    previous = {
        "source_id": "feishu:token:TZGzbnwqPobSdhxv4aIcjnnsnvd",
        "source_type": "feishu",
        "source_path": "26379166812001512498.pdf",
        "local_path": local_path,
        "file": local_path,
        "name": "26379166812001512498.pdf",
        "kind": "file",
        "type": "file",
        "extension": "pdf",
        "file_extension": "pdf",
        "status": "synced",
        "metadata": {"modified_time": "1782438856"},
        "remote": {
            "token": "TZGzbnwqPobSdhxv4aIcjnnsnvd",
            "type": "file",
        },
        "token": "TZGzbnwqPobSdhxv4aIcjnnsnvd",
    }

    assert _feishu_item_unchanged(
        {
            "token": "TZGzbnwqPobSdhxv4aIcjnnsnvd",
            "name": "26379166812001512498.pdf",
            "type": "file",
            "modified_time": "1782438856",
        },
        previous,
        source.parent,
        tmp_path,
    )


def test_feishu_target_path_reuses_existing_stable_hash_file(tmp_path):
    """Repeated raw file sync reuses an existing token-suffixed file."""

    filename = "Report.pdf"
    hashed = tmp_path / f"Report__{stable_suffix('file1')}.pdf"
    hashed.write_bytes(b"old")
    path = _feishu_target_file_path(
        tmp_path,
        tmp_path,
        filename,
        "file1",
        None,
    )

    assert path == hashed


def test_sync_feishu_folder_overwrites_changed_previous_file(
    tmp_path,
    monkeypatch,
):
    """Changed Feishu items keep the previous local path."""

    modified_times = ["100", "200"]

    def list_children(folder_token, headers):
        del folder_token, headers
        return [
            {
                "token": "doc1",
                "name": "Root Doc",
                "type": "docx",
                "modified_time": modified_times[0],
            }
        ]

    def export_document(doc_id, item_type, headers):
        del item_type, headers
        return {
            "file_name": "Root Doc",
            "file_extension": "docx",
            "type": "docx",
            "content": f"content {modified_times[0]}".encode("utf-8"),
        }

    monkeypatch.setattr(
        "lensnode.datasource_sync._list_feishu_folder_children",
        list_children,
    )
    monkeypatch.setattr(
        "lensnode.datasource_sync._export_feishu_document",
        export_document,
    )

    _sync_feishu_folder(
        {"folder_token": "root", "recursive": True, "max_depth": 5},
        tmp_path,
        {},
        None,
        max_workers=1,
    )
    modified_times[0] = "200"
    second = _sync_feishu_folder(
        {"folder_token": "root", "recursive": True, "max_depth": 5},
        tmp_path,
        {},
        None,
        max_workers=1,
    )

    files = list(tmp_path.glob("Root Doc*.docx"))
    assert second["changed"] == 1
    assert len(files) == 1
    assert files[0].read_bytes() == b"content 200"


def test_feishu_export_filename_uses_original_extension():
    exported = {
        "file_name": "Example Doc",
        "file_extension": "docx",
    }

    assert _export_filename(exported, "fallback", "docx") == "Example-Doc.docx"
    assert _feishu_export_extension("bitable") == "xlsx"
    assert _is_feishu_exportable_type("slides")
    assert _is_feishu_exportable_type("slide")
    assert _feishu_export_type("slides") == "slides"
    assert _feishu_export_type("slide") == "slides"
    assert _feishu_export_extension("slides") == "pptx"
    assert _feishu_export_extension("slide") == "pptx"


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
