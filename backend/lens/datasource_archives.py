"""Validation and private storage helpers for datasource archives."""

import hashlib
import stat
import struct
import tarfile
import unicodedata
import uuid
import zipfile
from pathlib import PurePosixPath

from django.conf import settings
from django.core.files.storage import storages
from rest_framework.exceptions import ValidationError

ARCHIVE_EXTENSIONS = (".zip", ".tar.gz", ".tgz")
RESERVED_ROOT_NAMES = {
    ".sourcelens-datasource.json",
    "manifest.json",
}
ZIP_EOCD_SIGNATURE = b"PK\x05\x06"
ZIP_EOCD_MIN_BYTES = 22
ZIP_EOCD_SEARCH_BYTES = ZIP_EOCD_MIN_BYTES + 65_535


def datasource_archive_storage():
    """Return the dedicated non-public datasource archive storage."""

    return storages["datasource_archives"]


def validate_datasource_archive(upload):
    """Validate one uploaded archive and return immutable metadata."""

    name = str(getattr(upload, "name", "") or "")
    archive_type = _archive_type(name)
    size = int(getattr(upload, "size", 0) or 0)
    if not archive_type:
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_TYPE_UNSUPPORTED"})
    if size <= 0:
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_EMPTY"})
    if size > settings.DATASOURCE_ARCHIVE_MAX_BYTES:
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_TOO_LARGE"})

    try:
        upload.seek(0)
        if archive_type == "zip":
            _validate_zip(upload, size)
        else:
            _validate_tar(upload, size)
        upload.seek(0)
    except ValidationError:
        raise
    except (OSError, tarfile.TarError, zipfile.BadZipFile):
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_INVALID"})

    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    return {
        "archive_type": archive_type,
        "byte_size": size,
        "content_hash": digest.hexdigest(),
        "original_name": PurePosixPath(name).name,
    }


def store_datasource_archive(upload, metadata, task_id):
    """Store a validated archive under a non-public random name."""

    extension = ".zip" if metadata["archive_type"] == "zip" else ".tar.gz"
    storage_name = datasource_archive_storage().save(
        f"{task_id}/{uuid.uuid4().hex}{extension}",
        upload,
    )
    return {**metadata, "storage_name": storage_name}


def delete_datasource_archive(metadata):
    """Delete a stored datasource archive if it still exists."""

    storage_name = str((metadata or {}).get("storage_name") or "")
    storage = datasource_archive_storage()
    if storage_name and storage.exists(storage_name):
        storage.delete(storage_name)


def _archive_type(name):
    """Return the supported archive type inferred from its filename."""

    lowered = name.lower()
    if lowered.endswith(".zip"):
        return "zip"
    if lowered.endswith((".tar.gz", ".tgz")):
        return "tar.gz"
    return ""


def _validate_zip(upload, compressed_size):
    """Reject malformed or unsafe ZIP members."""

    _validate_zip_directory_metadata(upload)
    if not zipfile.is_zipfile(upload):
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_INVALID"})
    upload.seek(0)
    with zipfile.ZipFile(upload) as archive:
        seen = set()
        total_size = 0
        member_count = 0
        for member in archive.infolist():
            member_count = _increment_member_count(member_count)
            path = _validate_member_path(member.filename, seen)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValidationError(
                    {"file": "DATASOURCE_ARCHIVE_LINK_UNSUPPORTED"}
                )
            if member.flag_bits & 0x1:
                raise ValidationError({"file": "DATASOURCE_ARCHIVE_ENCRYPTED"})
            if member.compress_type not in {
                zipfile.ZIP_STORED,
                zipfile.ZIP_DEFLATED,
                zipfile.ZIP_BZIP2,
                zipfile.ZIP_LZMA,
            }:
                raise ValidationError(
                    {"file": "DATASOURCE_ARCHIVE_COMPRESSION_UNSUPPORTED"}
                )
            if member.is_dir():
                continue
            total_size = _validate_member_size(
                member.file_size,
                member.compress_size,
                total_size,
            )
            _validate_reserved_path(path)
        _validate_archive_not_empty(member_count)
        _validate_total_compression_ratio(total_size, compressed_size)


def _validate_tar(upload, compressed_size):
    """Reject malformed or unsafe compressed TAR members."""

    upload.seek(0)
    with tarfile.open(fileobj=upload, mode="r|gz") as archive:
        seen = set()
        total_size = 0
        member_count = 0
        for member in archive:
            member_count = _increment_member_count(member_count)
            path = _validate_member_path(member.name, seen)
            if not member.isdir() and not member.isfile():
                raise ValidationError(
                    {"file": "DATASOURCE_ARCHIVE_LINK_UNSUPPORTED"}
                )
            if member.isfile():
                total_size = _validate_member_size(
                    member.size,
                    None,
                    total_size,
                )
                _validate_reserved_path(path)
        _validate_archive_not_empty(member_count)
        _validate_total_compression_ratio(total_size, compressed_size)


def _validate_zip_directory_metadata(upload):
    """Reject oversized ZIP directories before ZipFile materializes them."""

    upload.seek(0, 2)
    size = upload.tell()
    read_size = min(size, ZIP_EOCD_SEARCH_BYTES)
    upload.seek(size - read_size)
    tail = upload.read(read_size)
    offset = tail.rfind(ZIP_EOCD_SIGNATURE)
    if offset < 0 or len(tail) - offset < ZIP_EOCD_MIN_BYTES:
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_INVALID"})
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
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_INVALID"})
    if total_members > settings.DATASOURCE_ARCHIVE_MAX_MEMBERS:
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_TOO_MANY_MEMBERS"})
    if directory_size > settings.DATASOURCE_ARCHIVE_MAX_DIRECTORY_BYTES:
        raise ValidationError(
            {"file": "DATASOURCE_ARCHIVE_DIRECTORY_TOO_LARGE"}
        )
    upload.seek(0)


def _increment_member_count(member_count):
    """Increment and enforce the archive entry ceiling."""

    member_count += 1
    if member_count > settings.DATASOURCE_ARCHIVE_MAX_MEMBERS:
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_TOO_MANY_MEMBERS"})
    return member_count


def _validate_archive_not_empty(member_count):
    """Reject archives without entries."""

    if member_count == 0:
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_EMPTY"})


def _validate_member_path(name, seen):
    """Return a normalized safe archive member path."""

    if not name or "\x00" in name or "\\" in name:
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_PATH_INVALID"})
    normalized = unicodedata.normalize("NFC", name.rstrip("/"))
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or (path.parts and ":" in path.parts[0])
    ):
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_PATH_INVALID"})
    if any(len(part.encode("utf-8")) > 255 for part in path.parts):
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_PATH_INVALID"})
    key = str(path)
    if key in seen:
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_PATH_DUPLICATE"})
    seen.add(key)
    return path


def _validate_member_size(size, compressed_size, total_size):
    """Enforce per-entry, total-size, and compression-ratio limits."""

    size = int(size or 0)
    if size > settings.DATASOURCE_ARCHIVE_MAX_MEMBER_BYTES:
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_MEMBER_TOO_LARGE"})
    total_size += size
    if total_size > settings.DATASOURCE_ARCHIVE_MAX_UNCOMPRESSED_BYTES:
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_EXPANDS_TOO_LARGE"})
    if (
        compressed_size is not None
        and size >= settings.DATASOURCE_ARCHIVE_RATIO_MIN_BYTES
        and size
        > max(int(compressed_size or 0), 1)
        * settings.DATASOURCE_ARCHIVE_MAX_COMPRESSION_RATIO
    ):
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_RATIO_TOO_HIGH"})
    return total_size


def _validate_total_compression_ratio(total_size, compressed_size):
    """Reject archives whose aggregate expansion ratio is excessive."""

    if (
        total_size >= settings.DATASOURCE_ARCHIVE_RATIO_MIN_BYTES
        and total_size
        > max(int(compressed_size or 0), 1)
        * settings.DATASOURCE_ARCHIVE_MAX_COMPRESSION_RATIO
    ):
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_RATIO_TOO_HIGH"})


def _validate_reserved_path(path):
    """Protect datasource metadata files generated by LensNode."""

    if len(path.parts) == 1 and path.name in RESERVED_ROOT_NAMES:
        raise ValidationError({"file": "DATASOURCE_ARCHIVE_PATH_RESERVED"})
