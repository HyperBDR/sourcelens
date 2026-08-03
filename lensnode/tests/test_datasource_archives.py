import hashlib
import io
import stat
import tarfile
import zipfile

import httpx
import pytest

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
