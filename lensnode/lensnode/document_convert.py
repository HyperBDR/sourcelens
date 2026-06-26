import json
import mimetypes
import time
from pathlib import Path

from .conversion_queue import ConversionJob
from .conversion_queue import conversion_queue_from_context
from .datasource_manifest import manifest_local_path
from .datasource_manifest import should_skip_dir
from .path_rules import is_excluded_path
from .path_rules import is_sidecar_dir
from .path_rules import safe_filename
from .path_rules import sidecar_path
from .path_rules import source_sha256

DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
PROMPT_VERSION = "image-search-v1"
DEFAULT_MAX_IMAGES = 100
DEFAULT_MAX_FILE_SIZE_MB = 100
DEFAULT_MAX_PAGES = 500
DEFAULT_TOKEN_CHARS = 4
DETAIL_ITEMS_LIMIT = 200


class ConversionOutput:
    """One converter output."""

    def __init__(self, text="", stats=None, cost=None):
        self.text = text
        self.stats = stats or {}
        self.cost = cost or {}


class BaseConverter:
    """Base file converter."""

    name = "base"
    extensions = set()

    def convert(self, path, context):
        """Convert one file into searchable text."""

        raise NotImplementedError

    def version(self):
        """Return converter version metadata."""

        return {"name": self.name, "version": ""}


class MarkItDownDocumentConverter(BaseConverter):
    """Document converter backed by MarkItDown."""

    name = "markitdown"
    extensions = DOCUMENT_EXTENSIONS

    def convert(self, path, context):
        """Convert a document file into Markdown text."""

        try:
            from markitdown import MarkItDown
        except Exception as exc:
            raise RuntimeError("MARKITDOWN_NOT_AVAILABLE") from exc

        result = MarkItDown().convert(str(path))
        text = getattr(result, "text_content", "") or str(result)
        stats = document_stats(path)
        return ConversionOutput(text=text, stats=stats)

    def version(self):
        """Return MarkItDown version metadata."""

        try:
            import markitdown

            return {"name": self.name, "version": markitdown.__version__}
        except Exception:
            return {"name": self.name, "version": "unknown"}


class GatewayImageConverter(BaseConverter):
    """Image converter backed by the LensNode AI gateway."""

    name = "gateway_vision"
    extensions = IMAGE_EXTENSIONS

    def convert(self, path, context):
        """Convert an image file into a searchable description."""

        content, usage = describe_image_file(path, context)
        return ConversionOutput(
            text=content,
            stats={
                "images_total": 1,
                "images_recognized": 1 if content else 0,
            },
            cost=model_cost_stats(usage, content),
        )

    def version(self):
        """Return gateway converter version metadata."""

        return {"name": self.name, "version": PROMPT_VERSION}


class ConverterRegistry:
    """Registry for pluggable converters."""

    def __init__(self):
        self._converters = []

    def register(self, converter):
        """Register one converter."""

        self._converters.append(converter)

    def converter_for(self, path):
        """Return a converter for a file path."""

        suffix = Path(path).suffix.lower()
        for converter in self._converters:
            if suffix in converter.extensions:
                return converter
        return None


CONVERTERS = ConverterRegistry()
CONVERTERS.register(MarkItDownDocumentConverter())
CONVERTERS.register(GatewayImageConverter())


def post_process_documents(context, sync_result, emit=None):
    """Convert changed datasource files into searchable sidecars."""

    conversion = context.get("conversion") or {}
    if not conversion_enabled(conversion):
        return {
            "candidates": 0,
            "converted": 0,
            "success": 0,
            "skipped": 0,
            "failed": 0,
            "markdown": 0,
            "deleted_sidecars": 0,
            "chars": 0,
            "estimated_tokens": 0,
            "images_recognized": 0,
            "xlsx_files": 0,
            "sheets": 0,
            "rows": 0,
            "truncated_files": 0,
            "cost": empty_cost_stats(),
            "warnings": [],
            "items": [],
            "items_truncated": 0,
        }

    target = Path(context["target_path"]).resolve()
    excluded_roots = context.get("excluded_datasource_roots") or []
    warnings = []
    candidates = conversion_candidates(
        target,
        sync_result.items,
        context.get("datasource_uuid") or "",
        excluded_roots,
        conversion,
    )
    total = len(candidates)
    summary = {
        "candidates": total,
        "converted": 0,
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "markdown": 0,
        "deleted_sidecars": 0,
        "chars": 0,
        "estimated_tokens": 0,
        "images_recognized": 0,
        "xlsx_files": 0,
        "sheets": 0,
        "rows": 0,
        "truncated_files": 0,
        "cost": empty_cost_stats(),
        "warnings": warnings,
        "items": [],
        "items_truncated": 0,
    }
    emit_conversion(
        emit,
        "conversion_plan",
        "running",
        f"Prepared {total} files for conversion.",
        summary,
        total=total,
        current=0,
    )

    max_images = int(conversion.get("max_images") or DEFAULT_MAX_IMAGES)
    image_count = 0
    jobs = []
    for index, item in enumerate(candidates, start=1):
        path = target / manifest_local_path(item)
        if is_image_path(path):
            image_count += 1
            if image_count > max_images:
                summary["skipped"] += 1
                warnings.append("CONVERSION_MAX_IMAGES_EXCEEDED")
                append_conversion_detail(
                    summary,
                    item,
                    "skipped",
                    "CONVERSION_MAX_IMAGES_EXCEEDED",
                )
                emit_conversion(
                    emit,
                    "conversion_progress",
                    "running",
                    f"Converted {index}/{total} datasource files.",
                    summary,
                    total=total,
                    current=index,
                    current_file=manifest_local_path(item),
                )
                continue
        jobs.append(
            ConversionJob(
                index=index,
                total=total,
                item=item,
                path=path,
            )
        )
    queue = conversion_queue_from_context(context)

    def handle_job(job):
        return convert_job(job, target, context)

    for job, output in queue.run(jobs, handle_job):
        path = job.path
        item = job.item
        index = job.index
        try:
            if isinstance(output, Exception):
                raise output
            result = output
            if result.get("skipped"):
                summary["skipped"] += 1
                if result.get("warning"):
                    warnings.append(result["warning"])
                append_conversion_detail(
                    summary,
                    item,
                    "skipped",
                    result.get("reason") or result.get("warning") or "",
                )
            else:
                summary["converted"] += 1
                summary["success"] += 1
                summary["markdown"] += 1
                append_conversion_detail(summary, item, "converted")
                summary["chars"] += int(result.get("chars") or 0)
                summary["estimated_tokens"] += int(
                    result.get("estimated_tokens") or 0
                )
                summary["images_recognized"] += int(
                    result.get("images_recognized") or 0
                )
                merge_summary_stats(summary, result.get("stats") or {})
                merge_cost_stats(summary["cost"], result.get("cost") or {})
        except Exception as exc:
            summary["failed"] += 1
            warnings.append("CONVERSION_FILE_FAILED")
            write_failed_meta(target, path, item, context, str(exc))
            append_conversion_detail(summary, item, "failed", str(exc))
        emit_conversion(
            emit,
            "conversion_progress",
            "running",
            f"Converted {index}/{total} datasource files.",
            summary,
            total=total,
            current=index,
            current_file=manifest_local_path(item),
        )

    summary["warnings"] = list(dict.fromkeys(warnings))
    emit_conversion(
        emit,
        "conversion_manifest",
        "done",
        "Datasource conversion completed.",
        summary,
        total=total,
        current=total,
    )
    return summary


def append_conversion_detail(summary, item, status, reason=""):
    """Append a compact conversion item detail."""

    if len(summary["items"]) >= DETAIL_ITEMS_LIMIT:
        summary["items_truncated"] += 1
        return
    local_path = manifest_local_path(item)
    summary["items"].append(
        {
            "status": status,
            "path": local_path,
            "name": item.get("name") or Path(local_path).name,
            "extension": Path(local_path).suffix.lower().lstrip("."),
            "reason": reason,
        }
    )


def conversion_enabled(conversion):
    """Return whether any conversion option is enabled."""

    return bool(
        conversion.get("document")
        or conversion.get("image")
        or conversion.get("embedded_image")
    )


def conversion_candidates(target, items, datasource_uuid, excluded_roots, conversion):
    """Return manifest items eligible for conversion."""

    candidates = []
    for item in items or []:
        if item.get("status") == "deleted":
            continue
        local_path = manifest_local_path(item)
        if not local_path:
            continue
        path = (target / local_path).resolve()
        if not path.is_file() or is_excluded_path(path, excluded_roots):
            continue
        if not is_convertible(path, conversion):
            continue
        if has_foreign_marker(path.parent, target, datasource_uuid, excluded_roots):
            continue
        candidates.append(item)
    return candidates


def has_foreign_marker(parent, target, datasource_uuid, excluded_roots):
    """Return whether path is under a foreign datasource root."""

    for directory in [parent, *parent.parents]:
        if not is_under_target(directory, target):
            break
        if should_skip_dir(directory, datasource_uuid, excluded_roots):
            return True
    return False


def is_under_target(path, target):
    """Return whether path is within the current datasource target."""

    try:
        Path(path).resolve().relative_to(Path(target).resolve())
        return True
    except ValueError:
        return False


def is_convertible(path, conversion):
    """Return whether path is enabled for conversion."""

    suffix = Path(path).suffix.lower()
    if conversion.get("document") and suffix in DOCUMENT_EXTENSIONS:
        return True
    if conversion.get("image") and suffix in IMAGE_EXTENSIONS:
        return True
    return False


def convert_job(job, target, context):
    """Convert one queued job."""

    return convert_one(target, job.path, job.item, context)


def convert_one(target, path, item, context):
    """Convert one file if fingerprint requires it."""

    limits = conversion_limits(context.get("conversion") or {})
    size = path.stat().st_size
    if size > limits["max_file_size"]:
        write_skipped_meta(target, path, item, context, "FILE_TOO_LARGE")
        return {"skipped": True, "reason": "FILE_TOO_LARGE"}

    digest = source_sha256(path)
    fingerprint = conversion_fingerprint(path, digest, context)
    meta_path = sidecar_path(path) / "meta.json"
    content_path = sidecar_path(path) / "content.md"
    meta = read_json(meta_path)
    if (
        meta.get("conversion", {}).get("fingerprint") == fingerprint
        and meta.get("conversion", {}).get("status") == "success"
        and content_path.is_file()
    ):
        return {"skipped": True, "reason": "UNCHANGED"}

    converter = CONVERTERS.converter_for(path)
    if converter is None:
        write_skipped_meta(target, path, item, context, "UNSUPPORTED_TYPE")
        return {"skipped": True, "reason": "UNSUPPORTED_TYPE"}

    if is_image_path(path):
        if not vision_configured(context):
            write_skipped_meta(target, path, item, context, "VISION_NOT_CONFIGURED")
            return {
                "skipped": True,
                "reason": "VISION_NOT_CONFIGURED",
                "warning": "VISION_NOT_CONFIGURED",
            }

    output = converter.convert(path, context)
    text = output.text
    stats = output.stats
    cost = output.cost
    images_recognized = int(stats.get("images_recognized") or 0)

    sidecar_path(path).mkdir(parents=True, exist_ok=True)
    content = content_markdown(target, path, context, text)
    content_path.write_text(content, encoding="utf-8")
    write_success_meta(
        target,
        path,
        item,
        context,
        digest,
        fingerprint,
        len(text),
        images_recognized,
        stats,
    )
    return {
        "chars": len(text),
        "estimated_tokens": estimate_tokens(text),
        "images_recognized": images_recognized,
        "stats": stats,
        "cost": cost,
    }


def conversion_limits(conversion):
    """Return conversion limits in bytes/counts."""

    size_mb = int(conversion.get("max_file_size_mb") or DEFAULT_MAX_FILE_SIZE_MB)
    return {
        "max_file_size": size_mb * 1024 * 1024,
        "max_pages": int(conversion.get("max_pages") or DEFAULT_MAX_PAGES),
    }


def document_stats(path):
    """Return document-specific conversion stats."""

    suffix = Path(path).suffix.lower()
    if suffix == ".xlsx":
        return xlsx_stats(path)
    return {"pages": 0}


def xlsx_stats(path):
    """Return XLSX workbook stats when openpyxl is available."""

    try:
        from openpyxl import load_workbook
    except Exception:
        return {
            "xlsx_files": 1,
            "sheets": 0,
            "rows": 0,
            "columns": 0,
            "truncated": False,
            "warning": "OPENPYXL_NOT_AVAILABLE",
        }

    workbook = load_workbook(path, read_only=True, data_only=True)
    sheets = []
    total_rows = 0
    max_columns = 0
    try:
        for sheet in workbook.worksheets:
            rows = int(sheet.max_row or 0)
            columns = int(sheet.max_column or 0)
            total_rows += rows
            max_columns = max(max_columns, columns)
            sheets.append(
                {
                    "name": sheet.title,
                    "rows": rows,
                    "columns": columns,
                }
            )
    finally:
        workbook.close()
    return {
        "xlsx_files": 1,
        "sheets": len(sheets),
        "rows": total_rows,
        "columns": max_columns,
        "sheet_stats": sheets,
        "truncated": False,
    }


def estimate_tokens(text):
    """Return a rough token estimate for conversion cost summaries."""

    return max(0, int(len(text or "") / DEFAULT_TOKEN_CHARS))


def empty_cost_stats():
    """Return empty conversion cost stats."""

    return {
        "estimated_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "model_calls": 0,
    }


def model_cost_stats(usage, text):
    """Return model usage stats for one conversion result."""

    usage = usage or {}
    total_tokens = int(usage.get("total_tokens") or 0)
    if total_tokens <= 0:
        total_tokens = estimate_tokens(text)
    return {
        "estimated_tokens": estimate_tokens(text),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": total_tokens,
        "model_calls": 1,
    }


def merge_cost_stats(target, source):
    """Merge model cost stats into a summary bucket."""

    for key in empty_cost_stats():
        target[key] = int(target.get(key) or 0) + int(source.get(key) or 0)


def merge_summary_stats(summary, stats):
    """Merge converter stats into conversion summary."""

    if not stats:
        return
    summary["xlsx_files"] += int(stats.get("xlsx_files") or 0)
    summary["sheets"] += int(stats.get("sheets") or 0)
    summary["rows"] += int(stats.get("rows") or 0)
    if stats.get("truncated"):
        summary["truncated_files"] += 1


def conversion_fingerprint(path, digest, context):
    """Return conversion fingerprint for one source file."""

    conversion = context.get("conversion") or {}
    payload = {
        "source_sha256": digest,
        "options": {
            "document": bool(conversion.get("document")),
            "image": bool(conversion.get("image")),
            "embedded_image": bool(conversion.get("embedded_image")),
            "document_model_ref": conversion.get("document_model_ref") or "",
        },
        "tool": converter_version(path),
        "model_ref": conversion.get("vision_model_ref") or "",
        "prompt_version": PROMPT_VERSION,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    import hashlib

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def converter_version(path):
    """Return converter version metadata."""

    converter = CONVERTERS.converter_for(path)
    if converter is not None:
        return converter.version()
    return {"name": "none", "version": ""}


def describe_image_file(path, context):
    """Describe an image file through the LensNode gateway."""

    conversion = context.get("conversion") or {}
    model_ref = conversion.get("vision_model_ref") or context.get(
        "vision_model_ref"
    )
    gateway_url = context.get("ai_gateway_url")
    token = context.get("lensnode_token")
    if not model_ref or not gateway_url or not token:
        raise RuntimeError("VISION_MODEL_NOT_CONFIGURED")
    from .gateway_model import describe_image_result

    mime_type = mimetypes.guess_type(str(path))[0] or "image/png"
    prompt = image_prompt()
    result = describe_image_result(
        path.read_bytes(),
        prompt,
        mime_type,
        model_ref=model_ref,
        ai_gateway_url=gateway_url,
        token=token,
    )
    return result.get("content") or "", result.get("usage") or {}


def vision_configured(context):
    """Return whether image recognition has enough gateway settings."""

    conversion = context.get("conversion") or {}
    return bool(
        (conversion.get("vision_model_ref") or context.get("vision_model_ref"))
        and context.get("ai_gateway_url")
        and context.get("lensnode_token")
    )


def image_prompt():
    """Return the image description prompt."""

    return (
        "请为知识库检索生成图片描述。包含图片中的文字、图表数据、"
        "关键对象、场景和业务含义。避免泛泛描述。"
    )


def content_markdown(target, path, context, text):
    """Return searchable markdown with a compact frontmatter."""

    source_path = path.resolve().relative_to(Path(target).resolve()).as_posix()
    source_name = path.name
    return (
        "---\n"
        f"datasource_uuid: {context.get('datasource_uuid') or ''}\n"
        f"source_type: {context.get('source_type') or ''}\n"
        f"source_path: {source_path}\n"
        f"source_name: {source_name}\n"
        f"converter: {converter_version(path).get('name')}\n"
        "---\n\n"
        f"# {source_name}\n\n"
        f"{text.strip()}\n"
    )


def write_success_meta(
    target,
    path,
    item,
    context,
    digest,
    fingerprint,
    chars,
    images_recognized,
    stats=None,
):
    """Write successful conversion metadata."""

    stats = dict(stats or {})
    stats["chars"] = chars
    stats.setdefault("images_total", images_recognized)
    stats.setdefault("images_recognized", images_recognized)
    write_meta(
        target,
        path,
        item,
        context,
        {
            "status": "success",
            "error": "",
            "fingerprint": fingerprint,
            "stats": stats,
            "source_sha256": digest,
        },
    )


def write_failed_meta(target, path, item, context, error):
    """Write failed conversion metadata."""

    write_meta(
        target,
        path,
        item,
        context,
        {
            "status": "failed",
            "error": error,
            "fingerprint": "",
            "stats": {},
            "source_sha256": "",
        },
    )


def write_skipped_meta(target, path, item, context, reason):
    """Write skipped conversion metadata."""

    write_meta(
        target,
        path,
        item,
        context,
        {
            "status": "skipped",
            "error": reason,
            "fingerprint": "",
            "stats": {},
            "source_sha256": "",
        },
    )


def write_meta(target, path, item, context, conversion):
    """Write sidecar meta.json."""

    sidecar_path(path).mkdir(parents=True, exist_ok=True)
    source_path = path.resolve().relative_to(Path(target).resolve()).as_posix()
    payload = {
        "schema_version": 1,
        "datasource": {
            "uuid": context.get("datasource_uuid") or "",
            "name": context.get("name") or "",
            "source_type": context.get("source_type") or "",
        },
        "source": {
            "path": source_path,
            "name": path.name,
            "extension": path.suffix.lstrip(".").lower(),
            "size": path.stat().st_size if path.exists() else 0,
            "sha256": conversion.pop("source_sha256", ""),
            "mtime": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(path.stat().st_mtime if path.exists() else 0),
            ),
            "remote": item.get("remote") or {},
        },
        "conversion": {
            "status": conversion.get("status"),
            "error": conversion.get("error", ""),
            "fingerprint": conversion.get("fingerprint", ""),
            "generated_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(),
            ),
            "options": context.get("conversion") or {},
            "tool": converter_version(path),
            "model": {
                "ref": (context.get("conversion") or {}).get(
                    "vision_model_ref",
                    "",
                ),
                "prompt_version": PROMPT_VERSION,
            },
            "stats": conversion.get("stats") or {},
        },
        "retrieval": {
            "content_path": (
                sidecar_path(path)
                / "content.md"
            ).resolve().relative_to(Path(target).resolve()).as_posix(),
            "source_path": source_path,
            "title": safe_filename(path.name),
            "mime_type": mimetypes.guess_type(str(path))[0] or "",
        },
    }
    (sidecar_path(path) / "meta.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_json(path):
    """Read a JSON file or return empty dict."""

    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def is_document_path(path):
    """Return whether a path is a supported document."""

    return Path(path).suffix.lower() in DOCUMENT_EXTENSIONS


def is_image_path(path):
    """Return whether a path is a supported image."""

    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def emit_conversion(
    emit,
    step,
    status,
    message,
    summary,
    total=0,
    current=0,
    current_file="",
):
    """Emit one conversion progress event."""

    if emit is None:
        return
    percent = 100 if total <= 0 else int(current * 100 / total)
    event_summary = dict(summary or {})
    if step != "conversion_manifest":
        event_summary.pop("items", None)
        event_summary.pop("items_truncated", None)
    emit(
        {
            "step": step,
            "status": status,
            "message": message,
            "category": "conversion",
            "summary": event_summary,
            "progress_total": total,
            "progress_current": current,
            "progress_percent": max(0, min(100, percent)),
            "current_file": current_file,
        }
    )
