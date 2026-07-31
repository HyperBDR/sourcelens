import hashlib
import re
import shutil
from pathlib import Path

INVALID_FILENAME_CHARS = re.compile(r'[\\/:\*\?"<>\|\x00-\x1f]+')
SIDECAR_SUFFIX = ".sourcelens"


def safe_filename(value, fallback="document", max_bytes=None):
    """Return a Unicode-preserving filesystem-safe filename."""

    cleaned = INVALID_FILENAME_CHARS.sub("-", str(value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if cleaned in {"", ".", ".."}:
        cleaned = fallback
    if max_bytes is not None:
        cleaned = _truncate_filename(cleaned, max_bytes, fallback)
    return cleaned


def _truncate_filename(value, max_bytes, fallback):
    """Truncate one filename by encoded bytes while preserving its suffix."""

    max_bytes = max(int(max_bytes), 1)
    if len(value.encode("utf-8")) <= max_bytes:
        return value
    path = Path(value)
    suffix = path.suffix
    suffix_size = len(suffix.encode("utf-8"))
    if suffix_size >= max_bytes:
        suffix = ""
        suffix_size = 0
    stem = value[: -len(path.suffix)] if path.suffix else value
    budget = max_bytes - suffix_size
    truncated = stem.encode("utf-8")[:budget].decode("utf-8", "ignore")
    truncated = truncated.rstrip(" .")
    if not truncated:
        truncated = fallback.encode("utf-8")[:budget].decode(
            "utf-8",
            "ignore",
        )
    return f"{truncated}{suffix}"


def stable_suffix(value, length=8):
    """Return a stable short suffix for conflict-safe filenames."""

    raw = str(value or "").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:length]


def unique_child_path(parent, filename, source_id=""):
    """Return a stable available child path under parent."""

    parent = Path(parent)
    candidate = parent / filename
    if not candidate.exists():
        return candidate

    path = Path(filename)
    suffix = stable_suffix(source_id or filename)
    stem = path.stem or "document"
    name = f"{stem}__{suffix}{path.suffix}"
    return parent / name


def relative_path(root, path):
    """Return a POSIX relative path from root to path."""

    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


def is_relative_to(path, root):
    """Return whether path is inside root."""

    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def is_sidecar_dir(path):
    """Return whether a path is a SourceLens sidecar directory."""

    return Path(path).name.endswith(SIDECAR_SUFFIX)


def sidecar_path(source_path):
    """Return the sidecar directory path for a source file."""

    return Path(f"{source_path}{SIDECAR_SUFFIX}")


def remove_sidecar(source_path):
    """Delete a sidecar directory for a source file when present."""

    sidecar = sidecar_path(source_path)
    if sidecar.is_dir():
        shutil.rmtree(sidecar)
        return True
    return False


def source_sha256(path):
    """Return a sha256 digest for a local source file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_excluded_roots(paths, target):
    """Return excluded roots under the target path."""

    target = Path(target).resolve()
    roots = []
    for item in paths or []:
        path = Path(str(item)).resolve()
        if path == target:
            continue
        if is_relative_to(path, target):
            roots.append(path)
    return roots


def is_excluded_path(path, roots):
    """Return whether path is inside any excluded datasource root."""

    return any(is_relative_to(path, root) for root in roots or [])
