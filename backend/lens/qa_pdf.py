"""Server-side PDF generation for one Q&A turn."""

import logging
from pathlib import PurePosixPath

import bleach
import markdown
import requests
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)

ALLOWED_MARKDOWN_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
ALLOWED_MARKDOWN_ATTRIBUTES = {"a": ["href", "title"]}


class QAPdfGenerationError(Exception):
    """Raised when the configured PDF service cannot produce a safe PDF."""


def _safe_markdown(value):
    """Render Markdown while removing scripts, images, and unsafe URLs."""

    rendered = markdown.markdown(
        value or "",
        extensions=["extra", "sane_lists"],
        output_format="html",
    )
    return bleach.clean(
        rendered,
        tags=ALLOWED_MARKDOWN_TAGS,
        attributes=ALLOWED_MARKDOWN_ATTRIBUTES,
        protocols={"http", "https", "mailto"},
        strip=True,
    )


def _display_filename(file_object, preferred_name=""):
    """Return a stable display-only filename without exposing storage paths."""

    if preferred_name:
        return preferred_name
    name = getattr(getattr(file_object, "file", None), "name", "")
    return PurePosixPath(name).name


def run_pdf_context(run):
    """Build PDF template data from an owned completed run."""

    input_files = []
    if run.input_message_id:
        input_files = [
            _display_filename(item, item.original_name)
            for item in run.input_message.attachments.all()
        ]
    return {
        "title": (run.input_message.content or "")[:200],
        "question": run.input_message.content or "",
        "answer": run.output_message.content or "",
        "assistant_name": run.session.assistant.name,
        "published_at": run.finished_at or run.created_at,
        "input_files": input_files,
        "output_files": [item.filename for item in run.output_files.all()],
    }


def shared_qa_pdf_context(share):
    """Build PDF template data from an authorized shared-Q&A snapshot."""

    files = list(share.files.all())
    return {
        "title": share.title,
        "question": share.question,
        "answer": share.answer,
        "assistant_name": share.assistant_name,
        "published_at": share.published_at or share.created_at,
        "input_files": [item.filename for item in files if item.kind == "input"],
        "output_files": [item.filename for item in files if item.kind == "output"],
    }


def generate_qa_pdf(context):
    """Render trusted Q&A fields and ask Gotenberg Chromium for a PDF."""

    gotenberg_url = settings.GOTENBERG_URL
    if not gotenberg_url:
        raise QAPdfGenerationError("PDF service is not configured.")

    published_at = context.get("published_at")
    if published_at and timezone.is_aware(published_at):
        published_at = timezone.localtime(published_at)
    template_context = {
        **context,
        "answer_html": _safe_markdown(context.get("answer")),
        "published_at": published_at,
    }
    html = render_to_string("lens/qa_export.html", template_context)
    try:
        response = requests.post(
            f"{gotenberg_url}/forms/chromium/convert/html",
            files={
                "files": (
                    "index.html",
                    html.encode("utf-8"),
                    "text/html; charset=utf-8",
                )
            },
            data={
                "paperWidth": "8.27",
                "paperHeight": "11.7",
                "marginTop": "0.55",
                "marginBottom": "0.55",
                "marginLeft": "0.55",
                "marginRight": "0.55",
                "printBackground": "true",
            },
            timeout=(
                settings.GOTENBERG_CONNECT_TIMEOUT_S,
                settings.GOTENBERG_REQUEST_TIMEOUT_S,
            ),
        )
    except requests.RequestException as exc:
        logger.warning("Gotenberg request failed: %s", exc)
        raise QAPdfGenerationError("PDF service is unavailable.") from exc

    content = response.content
    if (
        response.status_code != 200
        or not content.startswith(b"%PDF-")
        or len(content) > settings.GOTENBERG_MAX_PDF_BYTES
    ):
        logger.warning(
            "Gotenberg returned an invalid PDF response: status=%s bytes=%s",
            response.status_code,
            len(content),
        )
        raise QAPdfGenerationError("PDF service returned an invalid response.")
    return content
