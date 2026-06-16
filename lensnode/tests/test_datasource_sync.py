import pytest

from lensnode.datasource_sync import (
    DataSourceSyncError,
    _export_feishu_document,
    _export_filename,
    _feishu_folder_token,
    _feishu_export_extension,
    _git_auth_url,
    _http_json,
    _poll_feishu_export_task,
    _raise_feishu_business_error,
    _sync_feishu_folder,
)


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
