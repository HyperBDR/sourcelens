import hashlib
import io
import stat
import tarfile
import threading
import zipfile
from pathlib import Path

import httpx
import pytest

from lensnode import datasource_archives
from lensnode import datasource_manifest as manifest_store
from lensnode.datasource_archives import DataSourceArchiveError
from lensnode.datasource_sync import sync_datasource


def _zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def _tar_bytes(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(path)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _zip_symlink_bytes():
    """Return a ZIP containing a Unix symbolic-link entry."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("linked.txt")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "outside.txt")
    return buffer.getvalue()


def _tar_symlink_bytes():
    """Return a TAR.GZ containing a symbolic-link entry."""

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo("linked.txt")
        info.type = tarfile.SYMTYPE
        info.linkname = "outside.txt"
        archive.addfile(info)
    return buffer.getvalue()


def _zip_many_members(member_count):
    """Return a ZIP containing many empty entries."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for index in range(member_count):
            archive.writestr(f"entry-{index}.txt", b"")
    return buffer.getvalue()


def _tar_many_members(member_count):
    """Return a TAR.GZ containing many empty entries."""

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for index in range(member_count):
            archive.addfile(tarfile.TarInfo(f"entry-{index}.txt"))
    return buffer.getvalue()


def _command(data, archive_type, target_path):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            content=data,
            headers={"Content-Length": str(len(data))},
            request=request,
        )
    )
    return {
        "datasource_uuid": "11111111-1111-1111-1111-111111111111",
        "source_type": "file",
        "name": "Uploaded Documents",
        "target_path": str(target_path),
        "archive": {
            "task_id": "archive-task",
            "archive_type": archive_type,
            "byte_size": len(data),
            "content_hash": hashlib.sha256(data).hexdigest(),
        },
        "ai_gateway_url": "http://control/api/lens/lensnode/ai-gateway/",
        "lensnode_token": "token",
        "gateway_http_client": httpx.Client(transport=transport),
        "sync_policy": {},
    }


def test_zip_upload_replaces_previous_contents(tmp_path):
    target = tmp_path / "documents"
    first = _zip_bytes({"docs/old.txt": "old"})
    first_result = sync_datasource(
        _command(first, "zip", target),
        workspace_path=tmp_path,
    )
    assert first_result["files"] == 1
    assert (target / "docs" / "old.txt").read_text() == "old"

    second = _zip_bytes({"new.txt": "new"})
    second_result = sync_datasource(
        _command(second, "zip", target),
        workspace_path=tmp_path,
    )

    assert not (target / "docs" / "old.txt").exists()
    assert (target / "new.txt").read_text() == "new"
    assert second_result["deleted"] == 1


def test_tar_gz_upload_preserves_unicode_paths(tmp_path):
    target = tmp_path / "documents"
    data = _tar_bytes({"资料/说明.txt": "内容"})

    result = sync_datasource(
        _command(data, "tar.gz", target),
        workspace_path=tmp_path,
    )

    assert result["files"] == 1
    assert (target / "资料" / "说明.txt").read_text() == "内容"


def test_unsafe_archive_keeps_previous_target(tmp_path):
    target = tmp_path / "documents"
    valid = _zip_bytes({"old.txt": "old"})
    sync_datasource(
        _command(valid, "zip", target),
        workspace_path=tmp_path,
    )
    unsafe = _zip_bytes({"../escape.txt": "unsafe"})

    with pytest.raises(
        DataSourceArchiveError,
        match="DATASOURCE_ARCHIVE_PATH_INVALID",
    ):
        sync_datasource(
            _command(unsafe, "zip", target),
            workspace_path=tmp_path,
        )

    assert (target / "old.txt").read_text() == "old"
    assert not (tmp_path / "escape.txt").exists()


def test_archive_cannot_replace_unowned_nonempty_directory(tmp_path):
    target = tmp_path / "documents"
    target.mkdir()
    (target / "keep.txt").write_text("keep")
    data = _zip_bytes({"new.txt": "new"})

    with pytest.raises(
        DataSourceArchiveError,
        match="DATASOURCE_ARCHIVE_TARGET_NOT_OWNED",
    ):
        sync_datasource(
            _command(data, "zip", target),
            workspace_path=tmp_path,
        )

    assert (target / "keep.txt").read_text() == "keep"
    assert not (target / "new.txt").exists()


@pytest.mark.parametrize(
    ("data", "archive_type"),
    [
        (_zip_symlink_bytes(), "zip"),
        (_tar_symlink_bytes(), "tar.gz"),
    ],
)
def test_archive_rejects_symbolic_links(tmp_path, data, archive_type):
    target = tmp_path / "documents"

    with pytest.raises(
        DataSourceArchiveError,
        match="DATASOURCE_ARCHIVE_LINK_UNSUPPORTED",
    ):
        sync_datasource(
            _command(data, archive_type, target),
            workspace_path=tmp_path,
        )

    assert not target.exists()


@pytest.mark.parametrize(
    ("data", "archive_type"),
    [
        (_zip_bytes({"large.txt": "0" * (2 * 1024 * 1024)}), "zip"),
        (_tar_bytes({"large.txt": "0" * (2 * 1024 * 1024)}), "tar.gz"),
    ],
)
def test_archive_rejects_excessive_compression_ratio(
    tmp_path,
    data,
    archive_type,
):
    target = tmp_path / "documents"

    with pytest.raises(
        DataSourceArchiveError,
        match="DATASOURCE_ARCHIVE_RATIO_TOO_HIGH",
    ):
        sync_datasource(
            _command(data, archive_type, target),
            workspace_path=tmp_path,
        )

    assert not target.exists()


def test_zip_member_limit_precedes_zipfile_materialization(
    tmp_path,
    monkeypatch,
):
    """ZIP entry count is bounded before ZipFile builds its member list."""

    data = _zip_many_members(10_001)

    def fail_zipfile(*args, **kwargs):
        raise AssertionError("ZipFile must not be constructed")

    monkeypatch.setattr(datasource_archives.zipfile, "ZipFile", fail_zipfile)
    with pytest.raises(
        DataSourceArchiveError,
        match="DATASOURCE_ARCHIVE_TOO_MANY_MEMBERS",
    ):
        sync_datasource(
            _command(data, "zip", tmp_path / "documents"),
            workspace_path=tmp_path,
        )


def test_tar_member_limit_does_not_materialize_members(tmp_path, monkeypatch):
    """TAR validation iterates entries instead of calling getmembers."""

    data = _tar_many_members(10_001)

    def fail_getmembers(*args, **kwargs):
        raise AssertionError("getmembers must not be called")

    monkeypatch.setattr(tarfile.TarFile, "getmembers", fail_getmembers)
    with pytest.raises(
        DataSourceArchiveError,
        match="DATASOURCE_ARCHIVE_TOO_MANY_MEMBERS",
    ):
        sync_datasource(
            _command(data, "tar.gz", tmp_path / "documents"),
            workspace_path=tmp_path,
        )


def test_cancel_before_swap_preserves_previous_target(tmp_path, monkeypatch):
    """A cooperative cancellation cannot commit extracted replacement data."""

    target = tmp_path / "documents"
    first = _zip_bytes({"old.txt": "old"})
    sync_datasource(
        _command(first, "zip", target),
        workspace_path=tmp_path,
    )
    cancel_event = threading.Event()
    original_hash = datasource_archives._source_sha256

    def cancel_after_hash(path, event):
        digest = original_hash(path, event)
        cancel_event.set()
        return digest

    monkeypatch.setattr(
        datasource_archives,
        "_source_sha256",
        cancel_after_hash,
    )
    command = _command(_zip_bytes({"new.txt": "new"}), "zip", target)
    command["cancel_event"] = cancel_event

    with pytest.raises(
        DataSourceArchiveError,
        match="DATASOURCE_SYNC_CANCELLED",
    ):
        sync_datasource(command, workspace_path=tmp_path)

    assert (target / "old.txt").read_text() == "old"
    assert not (target / "new.txt").exists()


def test_cancel_during_swap_restores_previous_target(tmp_path, monkeypatch):
    """Cancellation after backup rename restores the previous directory."""

    target = tmp_path / "documents"
    sync_datasource(
        _command(_zip_bytes({"old.txt": "old"}), "zip", target),
        workspace_path=tmp_path,
    )
    cancel_event = threading.Event()
    original_rename = Path.rename

    def cancel_after_backup(path, destination):
        result = original_rename(path, destination)
        if path == target:
            cancel_event.set()
        return result

    monkeypatch.setattr(Path, "rename", cancel_after_backup)
    command = _command(_zip_bytes({"new.txt": "new"}), "zip", target)
    command["cancel_event"] = cancel_event

    with pytest.raises(
        DataSourceArchiveError,
        match="DATASOURCE_SYNC_CANCELLED",
    ):
        sync_datasource(command, workspace_path=tmp_path)

    assert (target / "old.txt").read_text() == "old"
    assert not (target / "new.txt").exists()


@pytest.mark.parametrize(
    "writer_name",
    ["write_datasource_marker", "write_manifest"],
)
def test_pipeline_failure_restores_previous_target(
    tmp_path,
    monkeypatch,
    writer_name,
):
    """Post-swap metadata failures preserve the last valid import."""

    target = tmp_path / "documents"
    sync_datasource(
        _command(_zip_bytes({"old.txt": "old"}), "zip", target),
        workspace_path=tmp_path,
    )

    def fail_write(*args, **kwargs):
        raise RuntimeError("metadata write failed")

    monkeypatch.setattr(manifest_store, writer_name, fail_write)
    with pytest.raises(RuntimeError, match="metadata write failed"):
        sync_datasource(
            _command(_zip_bytes({"new.txt": "new"}), "zip", target),
            workspace_path=tmp_path,
        )

    assert (target / "old.txt").read_text() == "old"
    assert not (target / "new.txt").exists()
    assert not list(tmp_path.glob(".sourcelens-backup-*"))


def test_cancel_after_target_rename_restores_previous_target(
    tmp_path,
    monkeypatch,
):
    """Cancellation after replacement rolls back the complete pipeline."""

    target = tmp_path / "documents"
    sync_datasource(
        _command(_zip_bytes({"old.txt": "old"}), "zip", target),
        workspace_path=tmp_path,
    )
    cancel_event = threading.Event()
    original_write = manifest_store.write_datasource_marker

    def cancel_after_marker(*args, **kwargs):
        original_write(*args, **kwargs)
        cancel_event.set()

    monkeypatch.setattr(
        manifest_store,
        "write_datasource_marker",
        cancel_after_marker,
    )
    command = _command(_zip_bytes({"new.txt": "new"}), "zip", target)
    command["cancel_event"] = cancel_event

    with pytest.raises(
        DataSourceArchiveError,
        match="DATASOURCE_SYNC_CANCELLED",
    ):
        sync_datasource(command, workspace_path=tmp_path)

    assert (target / "old.txt").read_text() == "old"
    assert not (target / "new.txt").exists()
    assert not list(tmp_path.glob(".sourcelens-backup-*"))


def test_failed_first_import_removes_uncommitted_target(
    tmp_path,
    monkeypatch,
):
    """A failed initial metadata write leaves no imported target."""

    target = tmp_path / "documents"

    def fail_marker(*args, **kwargs):
        raise RuntimeError("marker write failed")

    monkeypatch.setattr(
        manifest_store,
        "write_datasource_marker",
        fail_marker,
    )
    with pytest.raises(RuntimeError, match="marker write failed"):
        sync_datasource(
            _command(_zip_bytes({"new.txt": "new"}), "zip", target),
            workspace_path=tmp_path,
        )

    assert not target.exists()
    assert not list(tmp_path.glob(".sourcelens-backup-*"))


def test_successful_reupload_removes_target_backup(tmp_path):
    """A fully committed re-upload removes its rollback backup."""

    target = tmp_path / "documents"
    sync_datasource(
        _command(_zip_bytes({"old.txt": "old"}), "zip", target),
        workspace_path=tmp_path,
    )
    sync_datasource(
        _command(_zip_bytes({"new.txt": "new"}), "zip", target),
        workspace_path=tmp_path,
    )

    assert (target / "new.txt").read_text() == "new"
    assert not list(tmp_path.glob(".sourcelens-backup-*"))
