"""Transient document attachments stored as cache metadata and media files."""

import hashlib
import logging
import zipfile
import zlib
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path, PurePosixPath
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .assistant_lifecycle import lock_assistant_for_new_work
from .session_lifecycle import lock_active_session

logger = logging.getLogger(__name__)

DOCUMENT_ATTACHMENT_MAX_BYTES = 25 * 1024 * 1024
DOCUMENT_ATTACHMENT_MAX_PER_USER = 8
DOCUMENT_ARCHIVE_MAX_MEMBERS = 10_000
DOCUMENT_ARCHIVE_MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
DOCUMENT_ARCHIVE_MAX_MEMBER_BYTES = 100 * 1024 * 1024
DOCUMENT_ARCHIVE_MAX_COMPRESSION_RATIO = 100
DOCUMENT_ARCHIVE_RATIO_MIN_BYTES = 1024 * 1024
DOCUMENT_PDF_MAX_OBJECTS = 10_000
DOCUMENT_PDF_MAX_PAGES = 500
DOCUMENT_ATTACHMENT_STORAGE_PREFIX = "lens/document-attachments"
_DOCUMENT_FORMATS = {
    ".pdf": ("application/pdf", None),
    ".docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document",
        "word/document.xml",
    ),
    ".pptx": (
        "application/vnd.openxmlformats-officedocument."
        "presentationml.presentation",
        "ppt/presentation.xml",
    ),
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument." "spreadsheetml.sheet",
        "xl/workbook.xml",
    ),
}


class DocumentAttachmentError(ValueError):
    """Raised when a transient document attachment is invalid."""


def is_document_upload(uploaded_file):
    """Return whether the filename declares a supported document type."""

    name = getattr(uploaded_file, "name", "") or ""
    return _safe_original_name(name).suffix.lower() in _DOCUMENT_FORMATS


def store_document_attachment(session, user, uploaded_file):
    """Validate a document, store its bytes, and cache temporary metadata."""

    original_path = _safe_original_name(
        getattr(uploaded_file, "name", "") or "document"
    )
    extension = original_path.suffix.lower()
    if extension not in _DOCUMENT_FORMATS:
        raise DocumentAttachmentError("ATTACHMENT_UNSUPPORTED_TYPE")
    mime_type, package_part = _DOCUMENT_FORMATS[extension]
    declared_size = getattr(uploaded_file, "size", 0) or 0
    if declared_size > DOCUMENT_ATTACHMENT_MAX_BYTES:
        raise DocumentAttachmentError("ATTACHMENT_TOO_LARGE")

    data = uploaded_file.read(DOCUMENT_ATTACHMENT_MAX_BYTES + 1)
    if len(data) > DOCUMENT_ATTACHMENT_MAX_BYTES:
        raise DocumentAttachmentError("ATTACHMENT_TOO_LARGE")
    if not _valid_document_bytes(data, extension, package_part):
        raise DocumentAttachmentError("ATTACHMENT_UNSUPPORTED_TYPE")

    with transaction.atomic():
        lock_assistant_for_new_work(session.assistant, user)
        lock_active_session(session)
        attachment_uuid = str(uuid4())
        created_at = timezone.now()
        expires_at = created_at + timedelta(
            seconds=_attachment_ttl_seconds()
        )
        quota_slot = _reserve_user_quota(user.id, attachment_uuid)
        if quota_slot is None:
            raise DocumentAttachmentError("ATTACHMENT_TOO_MANY")
        storage = document_attachment_storage()
        storage_name = None
        try:
            storage_name = storage.save(
                (
                    f"{DOCUMENT_ATTACHMENT_STORAGE_PREFIX}/"
                    f"{created_at:%Y/%m/%d}/{attachment_uuid}{extension}"
                ),
                ContentFile(data),
            )
            metadata = {
                "uuid": attachment_uuid,
                "kind": "document",
                "session_uuid": str(session.uuid),
                "uploaded_by_id": user.id,
                "run_uuid": "",
                "lensnode_uuid": "",
                "storage_name": storage_name,
                "original_name": str(original_path)[:255],
                "mime_type": mime_type,
                "byte_size": len(data),
                "content_hash": hashlib.sha256(data).hexdigest(),
                "order": 0,
                "quota_slot": quota_slot,
                "created_at": created_at.isoformat(),
                "expires_at": expires_at.isoformat(),
            }
            cache.set(
                _attachment_key(attachment_uuid),
                metadata,
                timeout=_remaining_seconds(metadata),
            )
            _append_index(
                _session_index_key(session.uuid),
                attachment_uuid,
                metadata,
            )
        except Exception:
            if storage_name is not None:
                storage.delete(storage_name)
            cache.delete(_attachment_key(attachment_uuid))
            _release_user_quota(user.id, quota_slot)
            raise
    return metadata


def get_document_attachment(attachment_uuid):
    """Return cached internal metadata for one document, if still valid."""

    metadata = cache.get(_attachment_key(attachment_uuid))
    if not isinstance(metadata, dict):
        return None
    if _remaining_seconds(metadata) <= 0:
        cache.delete(_attachment_key(attachment_uuid))
        return None
    return metadata


def document_attachment_response(metadata):
    """Return client-safe metadata matching the attachment API shape."""

    return {
        "uuid": metadata["uuid"],
        "url": reverse(
            "lens-attachment",
            kwargs={"uuid": metadata["uuid"]},
        ),
        "kind": "document",
        "mime_type": metadata["mime_type"],
        "width": None,
        "height": None,
        "byte_size": metadata["byte_size"],
        "original_name": metadata["original_name"],
        "order": metadata.get("order", 0),
        "expires_at": metadata["expires_at"],
    }


def document_attachment_storage():
    """Return the private storage used for temporary document bytes."""

    return storages["document_attachments"]


def bind_document_attachments_to_run(
    session,
    run,
    attachment_uuids,
    order_by_uuid=None,
):
    """Bind unclaimed cached documents from a session to one Run."""

    candidates = []
    order_by_uuid = order_by_uuid or {}
    for order, attachment_uuid in enumerate(attachment_uuids or []):
        metadata = get_document_attachment(attachment_uuid)
        if metadata is None:
            return []
        if metadata["session_uuid"] != str(session.uuid):
            return []
        if metadata.get("run_uuid") not in {"", str(run.uuid)}:
            return []
        candidates.append(
            {
                **metadata,
                "run_uuid": str(run.uuid),
                "lensnode_uuid": str(run.lensnode.uuid),
                "order": order_by_uuid.get(str(attachment_uuid), order),
            }
        )

    if not candidates:
        return []
    timeout = max(_remaining_seconds(item) for item in candidates)
    if timeout <= 0:
        return []
    values = {_attachment_key(item["uuid"]): item for item in candidates}
    values[_run_index_key(run.uuid)] = [item["uuid"] for item in candidates]
    cache.set_many(values, timeout=timeout)
    return candidates


def set_run_document_expectation(run_uuid, document_count):
    """Cache the expected transient document count for Run retries."""

    document_count = max(int(document_count), 0)
    try:
        cache.set(
            _run_expectation_key(run_uuid),
            document_count,
            timeout=_attachment_ttl_seconds() * 2,
        )
    except Exception:
        if document_count:
            raise
        logger.debug(
            "Unable to cache zero-document expectation for Run %s.",
            run_uuid,
            exc_info=True,
        )


def get_run_document_expectation(run_uuid):
    """Return a Run's expected document count, or None if state was lost."""

    value = cache.get(_run_expectation_key(run_uuid))
    if value is None:
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def get_run_document_attachments(run_uuid, *, fail_silently=False):
    """Return valid documents bound to one Run in upload order."""

    return get_runs_document_attachments(
        [run_uuid],
        fail_silently=fail_silently,
    ).get(str(run_uuid), [])


def get_runs_document_attachments(run_uuids, *, fail_silently=False):
    """Return valid documents for several Runs using batched cache reads."""

    try:
        normalized_run_uuids = list(
            dict.fromkeys(str(value) for value in run_uuids or [])
        )
        documents_by_run = {run_uuid: [] for run_uuid in normalized_run_uuids}
        if not normalized_run_uuids:
            return documents_by_run

        run_keys = {
            run_uuid: _run_index_key(run_uuid)
            for run_uuid in normalized_run_uuids
        }
        run_indexes = cache.get_many(run_keys.values())
        attachment_uuids = list(
            dict.fromkeys(
                attachment_uuid
                for key in run_keys.values()
                for attachment_uuid in (run_indexes.get(key) or [])
            )
        )
        attachment_keys = {
            attachment_uuid: _attachment_key(attachment_uuid)
            for attachment_uuid in attachment_uuids
        }
        cached_attachments = cache.get_many(attachment_keys.values())
        expired_keys = []
        for run_uuid, run_key in run_keys.items():
            for attachment_uuid in run_indexes.get(run_key) or []:
                attachment_key = attachment_keys[attachment_uuid]
                metadata = cached_attachments.get(attachment_key)
                if not isinstance(metadata, dict):
                    continue
                if _remaining_seconds(metadata) <= 0:
                    expired_keys.append(attachment_key)
                    continue
                if metadata.get("run_uuid") != run_uuid:
                    continue
                documents_by_run[run_uuid].append(metadata)
            documents_by_run[run_uuid].sort(
                key=lambda item: item.get("order", 0)
            )
        if expired_keys:
            cache.delete_many(expired_keys)
        return documents_by_run
    except Exception:
        if fail_silently:
            logger.debug(
                "Unable to read temporary documents for Runs %s.",
                run_uuids,
                exc_info=True,
            )
            return {str(run_uuid): [] for run_uuid in run_uuids or []}
        raise


def delete_document_attachment(
    attachment_uuid,
    *,
    session_uuid=None,
    user_id=None,
):
    """Delete one document's cached metadata and original file."""

    metadata = get_document_attachment(attachment_uuid)
    if metadata is None:
        return False
    if session_uuid is not None:
        if metadata["session_uuid"] != str(session_uuid):
            return False
    if user_id is not None and metadata["uploaded_by_id"] != user_id:
        return False
    document_attachment_storage().delete(metadata["storage_name"])
    cache.delete(_attachment_key(attachment_uuid))
    _release_user_quota(
        metadata["uploaded_by_id"],
        metadata.get("quota_slot"),
    )
    return True


def delete_session_document_attachments(session_uuid, user_id=None):
    """Delete all still-cached documents uploaded for one Session."""

    key = _session_index_key(session_uuid)
    attachment_uuids = cache.get(key) or []
    deleted = 0
    for attachment_uuid in attachment_uuids:
        deleted += int(
            delete_document_attachment(
                attachment_uuid,
                session_uuid=session_uuid,
                user_id=user_id,
            )
        )
    cache.delete(key)
    return deleted


def cleanup_expired_document_files(now=None):
    """Delete source files older than the fixed document attachment TTL."""

    cutoff = (now or timezone.now()) - timedelta(
        seconds=_attachment_ttl_seconds()
    )
    storage = document_attachment_storage()
    deleted = 0
    for storage_name in _iter_storage_files(
        storage,
        DOCUMENT_ATTACHMENT_STORAGE_PREFIX,
    ):
        try:
            modified_at = storage.get_modified_time(storage_name)
        except (NotImplementedError, OSError):
            continue
        if modified_at > cutoff:
            continue
        storage.delete(storage_name)
        deleted += 1
    return deleted


def _attachment_ttl_seconds():
    """Return the configured fixed retention window in seconds."""

    value = int(getattr(settings, "DOCUMENT_ATTACHMENT_TTL_SECONDS", 86400))
    return max(value, 60)


def _attachment_key(attachment_uuid):
    return f"lens:document_attachment:{attachment_uuid}"


def _session_index_key(session_uuid):
    return f"lens:session_document_attachments:{session_uuid}"


def _run_index_key(run_uuid):
    return f"lens:run_document_attachments:{run_uuid}"


def _run_expectation_key(run_uuid):
    return f"lens:run_document_attachment_expectation:{run_uuid}"


def _user_quota_slot_key(user_id, slot):
    return f"lens:user_document_attachment_slot:{user_id}:{slot}"


def _reserve_user_quota(user_id, attachment_uuid):
    """Atomically reserve one bounded live-document slot for a user."""

    for slot in range(DOCUMENT_ATTACHMENT_MAX_PER_USER):
        if cache.add(
            _user_quota_slot_key(user_id, slot),
            attachment_uuid,
            timeout=_attachment_ttl_seconds(),
        ):
            return slot
    return None


def _release_user_quota(user_id, slot):
    """Release a live-document slot when its attachment is deleted."""

    if slot is None:
        return
    cache.delete(_user_quota_slot_key(user_id, slot))


def _append_index(key, attachment_uuid, metadata):
    attachment_uuids = list(cache.get(key) or [])
    if attachment_uuid not in attachment_uuids:
        attachment_uuids.append(attachment_uuid)
    cache.set(
        key,
        attachment_uuids,
        timeout=max(_remaining_seconds(metadata), 1),
    )


def _remaining_seconds(metadata):
    expires_at = datetime.fromisoformat(metadata["expires_at"])
    return int((expires_at - timezone.now()).total_seconds())


def _safe_original_name(value):
    name = PurePosixPath(str(value).replace("\\", "/")).name
    return Path(name or "document")


def _valid_document_bytes(data, extension, package_part):
    if extension == ".pdf":
        return _valid_pdf_bytes(data)
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            members = archive.infolist()
            if not _valid_archive_members(members):
                return False
            members_by_name = {member.filename: member for member in members}
            required_members = [
                members_by_name.get("[Content_Types].xml"),
                members_by_name.get(package_part),
            ]
            if any(
                member is None or member.is_dir() or member.file_size <= 0
                for member in required_members
            ):
                return False
            return archive.testzip() is None
    except (
        EOFError,
        NotImplementedError,
        OSError,
        RuntimeError,
        zipfile.BadZipFile,
        zlib.error,
    ):
        return False


def _valid_pdf_bytes(data):
    """Return whether a PDF has bounded structural complexity."""

    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            return False
        object_count = sum(len(entries) for entries in reader.xref.values())
        object_count += len(reader.xref_objStm)
        if object_count > DOCUMENT_PDF_MAX_OBJECTS:
            return False
        if "/Pages" not in reader.root_object:
            return False
        return len(reader.pages) <= DOCUMENT_PDF_MAX_PAGES
    except (
        KeyError,
        PdfReadError,
        OSError,
        TypeError,
        ValueError,
        RecursionError,
    ):
        return False


def _valid_archive_members(members):
    """Reject OOXML archives that can expand beyond safe worker limits."""

    if len(members) > DOCUMENT_ARCHIVE_MAX_MEMBERS:
        return False
    total_size = 0
    for member in members:
        if member.flag_bits & 0x1:
            return False
        if member.compress_type not in {
            zipfile.ZIP_STORED,
            zipfile.ZIP_DEFLATED,
        }:
            return False
        if member.is_dir():
            continue
        size = max(int(member.file_size), 0)
        compressed_size = max(int(member.compress_size), 0)
        total_size += size
        if size > DOCUMENT_ARCHIVE_MAX_MEMBER_BYTES:
            return False
        if total_size > DOCUMENT_ARCHIVE_MAX_UNCOMPRESSED_BYTES:
            return False
        if size and compressed_size == 0:
            return False
        if (
            size > DOCUMENT_ARCHIVE_RATIO_MIN_BYTES
            and size > compressed_size * DOCUMENT_ARCHIVE_MAX_COMPRESSION_RATIO
        ):
            return False
    return True


def _iter_storage_files(storage, path):
    try:
        directories, files = storage.listdir(path)
    except (FileNotFoundError, NotImplementedError, OSError):
        return
    for filename in files:
        yield f"{path.rstrip('/')}/{filename}"
    for directory in directories:
        child = f"{path.rstrip('/')}/{directory}"
        yield from _iter_storage_files(storage, child)
