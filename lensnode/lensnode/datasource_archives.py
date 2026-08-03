"""Download and safely materialize file-upload datasource archives."""

import hashlib
import json
import shutil
import stat
import struct
import tarfile
import tempfile
import unicodedata
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from . import datasource_manifest as manifest_store

MAX_ARCHIVE_BYTES = 90 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000
MAX_ARCHIVE_MEMBER_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 100
ARCHIVE_RATIO_MIN_BYTES = 1024 * 1024
MAX_ARCHIVE_DIRECTORY_BYTES = 16 * 1024 * 1024
ZIP_EOCD_SIGNATURE = b"PK\x05\x06"
ZIP_EOCD_MIN_BYTES = 22
ZIP_EOCD_SEARCH_BYTES = ZIP_EOCD_MIN_BYTES + 65_535
RESERVED_ROOT_NAMES = {
    ".sourcelens-datasource.json",
    "manifest.json",
}


class DataSourceArchiveError(RuntimeError):
    """Raised when an uploaded datasource archive is unsafe or invalid."""


def sync_file_archive(command, workspace_path, emit=None):
    """Download, extract, and fully replace one file datasource directory."""

    from .datasource_sync import normalize_target_path

    cancel_event = command.get("cancel_event")
    _check_cancelled(cancel_event)
    target = normalize_target_path(command.get("target_path"), workspace_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _validate_existing_target(target, command.get("datasource_uuid"))
    archive = command.get("archive") or {}
    temp_root = Path(
        tempfile.mkdtemp(
            prefix=".sourcelens-upload-",
            dir=target.parent,
        )
    )
    archive_path = temp_root / "archive"
    contents = temp_root / "contents"
    contents.mkdir()
    try:
        _emit(emit, "download", "running", "Downloading datasource archive.")
        _download_archive(command, archive, archive_path, cancel_event)
        _emit(emit, "extract", "running", "Extracting datasource archive.")
        if archive.get("archive_type") == "zip":
            _extract_zip(archive_path, contents, cancel_event)
        elif archive.get("archive_type") == "tar.gz":
            _extract_tar(archive_path, contents, cancel_event)
        else:
            raise DataSourceArchiveError("DATASOURCE_ARCHIVE_TYPE_UNSUPPORTED")
        files = _archive_files(contents, cancel_event)
        if not files:
            raise DataSourceArchiveError("DATASOURCE_ARCHIVE_EMPTY")
        items, changed_paths, by_extension = _archive_items(
            contents,
            files,
            cancel_event,
        )
        previous_paths = _previous_paths(target)
        folders = _archive_folder_count(contents, cancel_event)
        _replace_target(target, contents, cancel_event)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    deleted_paths = sorted(previous_paths - set(changed_paths))
    return {
        "status": "success",
        "target_path": str(target),
        "synced": len(items),
        "files": len(items),
        "folders": folders,
        "failed": 0,
        "scanned": len(items),
        "changed": len(items),
        "skipped": 0,
        "deleted": len(deleted_paths),
        "by_extension": by_extension,
        "by_type": {"file": len(items)},
        "_sync_items": items,
        "_changed_paths": changed_paths,
        "_deleted_paths": deleted_paths,
    }


def _download_archive(command, metadata, destination, cancel_event):
    """Stream one authenticated archive and verify its size and digest."""

    expected_size = int(metadata.get("byte_size") or 0)
    expected_hash = str(metadata.get("content_hash") or "")
    if (
        not expected_size
        or expected_size > MAX_ARCHIVE_BYTES
        or not expected_hash
    ):
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_METADATA_INVALID")
    url = _archive_url(
        command.get("ai_gateway_url"),
        command.get("datasource_uuid"),
        metadata.get("task_id"),
    )
    client = command.get("gateway_http_client")
    if client is None:
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_CLIENT_UNAVAILABLE")
    digest = hashlib.sha256()
    size = 0
    try:
        with client.stream(
            "GET",
            url,
            headers={
                "Authorization": (
                    f"Bearer {command.get('lensnode_token') or ''}"
                )
            },
        ) as response:
            response.raise_for_status()
            content_length = int(response.headers.get("Content-Length") or 0)
            if content_length and content_length != expected_size:
                raise DataSourceArchiveError(
                    "DATASOURCE_ARCHIVE_SIZE_MISMATCH"
                )
            with destination.open("wb") as output:
                for chunk in response.iter_bytes():
                    _check_cancelled(cancel_event)
                    size += len(chunk)
                    if size > expected_size or size > MAX_ARCHIVE_BYTES:
                        raise DataSourceArchiveError(
                            "DATASOURCE_ARCHIVE_TOO_LARGE"
                        )
                    digest.update(chunk)
                    output.write(chunk)
    except DataSourceArchiveError:
        raise
    except Exception as exc:
        raise DataSourceArchiveError(
            "DATASOURCE_ARCHIVE_DOWNLOAD_FAILED"
        ) from exc
    if size != expected_size:
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_SIZE_MISMATCH")
    if digest.hexdigest() != expected_hash:
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_HASH_MISMATCH")


def _archive_url(ai_gateway_url, datasource_uuid, task_id):
    """Derive the archive endpoint from the configured AI gateway URL."""

    base = str(ai_gateway_url or "").rstrip("/")
    suffix = "/ai-gateway"
    if base.endswith(suffix):
        base = base[: -len(suffix)]
    return f"{base}/datasources/{datasource_uuid}/archives/{task_id}/"


def _extract_zip(archive_path, destination, cancel_event=None):
    """Extract validated ZIP members without following archive links."""

    try:
        _validate_zip_directory_metadata(archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            seen = set()
            total = 0
            member_count = 0
            for member in archive.infolist():
                _check_cancelled(cancel_event)
                member_count = _increment_member_count(member_count)
                relative = _safe_member_path(member.filename, seen)
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise DataSourceArchiveError(
                        "DATASOURCE_ARCHIVE_LINK_UNSUPPORTED"
                    )
                if member.flag_bits & 0x1:
                    raise DataSourceArchiveError(
                        "DATASOURCE_ARCHIVE_ENCRYPTED"
                    )
                total = _validate_size(
                    member.file_size,
                    member.compress_size,
                    total,
                )
                target = destination / relative
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                _validate_reserved_path(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                with (
                    archive.open(member) as source,
                    target.open("xb") as output,
                ):
                    _copy_with_cancel(source, output, cancel_event)
                target.chmod(0o644)
            _validate_archive_not_empty(member_count)
            _validate_total_compression_ratio(
                total,
                archive_path.stat().st_size,
            )
    except DataSourceArchiveError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_INVALID") from exc


def _extract_tar(archive_path, destination, cancel_event=None):
    """Extract validated TAR.GZ regular files and directories."""

    try:
        with tarfile.open(archive_path, mode="r|gz") as archive:
            seen = set()
            total = 0
            member_count = 0
            for member in archive:
                _check_cancelled(cancel_event)
                member_count = _increment_member_count(member_count)
                relative = _safe_member_path(member.name, seen)
                if not member.isdir() and not member.isfile():
                    raise DataSourceArchiveError(
                        "DATASOURCE_ARCHIVE_LINK_UNSUPPORTED"
                    )
                target = destination / relative
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                total = _validate_size(member.size, None, total)
                _validate_reserved_path(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise DataSourceArchiveError("DATASOURCE_ARCHIVE_INVALID")
                with source, target.open("xb") as output:
                    _copy_with_cancel(source, output, cancel_event)
                target.chmod(0o644)
            _validate_archive_not_empty(member_count)
            _validate_total_compression_ratio(
                total,
                archive_path.stat().st_size,
            )
    except DataSourceArchiveError:
        raise
    except (OSError, tarfile.TarError) as exc:
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_INVALID") from exc


def _safe_member_path(name, seen):
    """Return a normalized member path confined to the extraction root."""

    if not name or "\x00" in name or "\\" in name:
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_PATH_INVALID")
    normalized = unicodedata.normalize("NFC", name.rstrip("/"))
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or (path.parts and ":" in path.parts[0])
        or any(len(part.encode("utf-8")) > 255 for part in path.parts)
    ):
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_PATH_INVALID")
    key = str(path)
    if key in seen:
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_PATH_DUPLICATE")
    seen.add(key)
    return path


def _validate_zip_directory_metadata(archive_path):
    """Reject oversized ZIP directories before ZipFile materializes them."""

    size = archive_path.stat().st_size
    read_size = min(size, ZIP_EOCD_SEARCH_BYTES)
    with archive_path.open("rb") as handle:
        handle.seek(size - read_size)
        tail = handle.read(read_size)
    offset = tail.rfind(ZIP_EOCD_SIGNATURE)
    if offset < 0 or len(tail) - offset < ZIP_EOCD_MIN_BYTES:
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_INVALID")
    fields = struct.unpack_from("<4s4H2LH", tail, offset)
    disk_number, directory_disk = fields[1], fields[2]
    disk_members, total_members = fields[3], fields[4]
    directory_size = fields[5]
    comment_size = fields[7]
    if (
        disk_number != 0
        or directory_disk != 0
        or disk_members != total_members
        or comment_size != len(tail) - offset - ZIP_EOCD_MIN_BYTES
    ):
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_INVALID")
    if total_members > MAX_ARCHIVE_MEMBERS:
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_TOO_MANY_MEMBERS")
    if directory_size > MAX_ARCHIVE_DIRECTORY_BYTES:
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_DIRECTORY_TOO_LARGE")


def _increment_member_count(member_count):
    """Increment and enforce the archive entry ceiling."""

    member_count += 1
    if member_count > MAX_ARCHIVE_MEMBERS:
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_TOO_MANY_MEMBERS")
    return member_count


def _validate_archive_not_empty(member_count):
    """Reject archives without entries."""

    if member_count == 0:
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_EMPTY")


def _validate_size(size, compressed_size, total):
    """Enforce archive expansion ceilings."""

    size = int(size or 0)
    if size > MAX_ARCHIVE_MEMBER_BYTES:
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_MEMBER_TOO_LARGE")
    total += size
    if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_EXPANDS_TOO_LARGE")
    if (
        compressed_size is not None
        and size >= ARCHIVE_RATIO_MIN_BYTES
        and size
        > max(int(compressed_size or 0), 1)
        * MAX_ARCHIVE_COMPRESSION_RATIO
    ):
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_RATIO_TOO_HIGH")
    return total


def _validate_total_compression_ratio(total, compressed_size):
    """Reject archives whose aggregate expansion ratio is excessive."""

    if (
        total >= ARCHIVE_RATIO_MIN_BYTES
        and total
        > max(int(compressed_size or 0), 1)
        * MAX_ARCHIVE_COMPRESSION_RATIO
    ):
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_RATIO_TOO_HIGH")


def _validate_reserved_path(path):
    """Protect metadata written by the datasource manifest pipeline."""

    if len(path.parts) == 1 and path.name in RESERVED_ROOT_NAMES:
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_PATH_RESERVED")


def _validate_existing_target(target, datasource_uuid):
    """Refuse to replace a non-empty directory owned by another source."""

    if not target.exists():
        return
    if not target.is_dir():
        raise DataSourceArchiveError("LENS_SOURCE_TARGET_PATH_INVALID")
    if not any(target.iterdir()):
        return
    if not is_file_target_owned(target, datasource_uuid):
        raise DataSourceArchiveError("DATASOURCE_ARCHIVE_TARGET_NOT_OWNED")


def is_file_target_owned(target, datasource_uuid):
    """Return whether a non-empty target belongs to this datasource."""

    if not datasource_uuid:
        return False
    marker = Path(target) / manifest_store.MARKER_FILE
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return str(payload.get("datasource_uuid") or "") == str(
        datasource_uuid or ""
    )


def _replace_target(target, contents, cancel_event=None):
    """Replace the target directory and restore it if the swap fails."""

    _check_cancelled(cancel_event)
    backup = target.parent / f".sourcelens-backup-{uuid.uuid4().hex}"
    moved_old = False
    try:
        if target.exists():
            target.rename(backup)
            moved_old = True
        _check_cancelled(cancel_event)
        contents.rename(target)
    except Exception:
        if moved_old and not target.exists() and backup.exists():
            backup.rename(target)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _previous_paths(target):
    """Return paths from the previous datasource manifest."""

    return {
        manifest_store.manifest_local_path(item)
        for item in manifest_store.manifest_items(
            manifest_store.read_manifest(target)
        )
        if manifest_store.manifest_local_path(item)
    }


def _archive_files(root, cancel_event=None):
    """Return regular files under one extracted datasource root."""

    files = []
    for path in root.rglob("*"):
        _check_cancelled(cancel_event)
        if path.is_file() and not path.is_symlink():
            files.append(path)
    return sorted(files)


def _archive_items(root, files, cancel_event):
    """Build manifest items before committing the directory replacement."""

    items = []
    changed_paths = []
    by_extension = {}
    for path in files:
        _check_cancelled(cancel_event)
        relative = path.relative_to(root).as_posix()
        extension = path.suffix.lower().lstrip(".")
        changed_paths.append(relative)
        key = extension or "none"
        by_extension[key] = by_extension.get(key, 0) + 1
        items.append(
            manifest_store.SyncItem(
                source_id=f"file:{_source_sha256(path, cancel_event)}",
                source_type="file",
                source_path=relative,
                local_path=relative,
                name=path.name,
                kind="file",
                extension=extension,
                status="synced",
                metadata={"byte_size": path.stat().st_size},
            )
        )
    return items, changed_paths, by_extension


def _source_sha256(path, cancel_event):
    """Hash one extracted file while honoring cooperative cancellation."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            _check_cancelled(cancel_event)
            chunk = handle.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def _archive_folder_count(root, cancel_event):
    """Count extracted directories while honoring cancellation."""

    count = 0
    for path in root.rglob("*"):
        _check_cancelled(cancel_event)
        if path.is_dir():
            count += 1
    return count


def _copy_with_cancel(source, output, cancel_event):
    """Copy an archive member in bounded cancellable chunks."""

    while True:
        _check_cancelled(cancel_event)
        chunk = source.read(1024 * 1024)
        if not chunk:
            return
        output.write(chunk)


def _check_cancelled(cancel_event):
    """Raise when the datasource task has been cancelled."""

    if cancel_event is not None and cancel_event.is_set():
        raise DataSourceArchiveError("DATASOURCE_SYNC_CANCELLED")


def _emit(emit, step, status, message):
    """Emit one optional datasource task progress event."""

    if emit:
        emit({"step": step, "status": status, "message": message})
