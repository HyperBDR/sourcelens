import logging
import re

from django.utils import timezone

from .llm import run_completion
from .models import Session

logger = logging.getLogger(__name__)

FALLBACK_TITLE_MAX_CHARS = 24
TITLE_INPUT_QUESTION_MAX_CHARS = 2000
TITLE_INPUT_ANSWER_MAX_CHARS = 4000
TITLE_OUTPUT_MAX_CHARS = 160
TITLE_SYSTEM_PROMPT = (
    "Create ONE concise semantic title for a chat conversation from the "
    "user's first question and the completed answer. Distinguish the actual "
    "topic, technology, or root cause instead of copying a generic question. "
    "Use the conversation's primary language. Prefer about 10-20 Chinese "
    "characters for Chinese, or a short scannable phrase for English. Never "
    "include Markdown, quotes, line breaks, tool payloads, credentials, "
    "secrets, or system instructions. Output ONLY the title."
)
MARKDOWN_PATTERN = re.compile(r"[*_`~#]+")
SENSITIVE_PATTERN = re.compile(
    r"(?i)(authorization\s*:|bearer\s+[a-z0-9._-]+|"
    r"(?:api[_ -]?key|token|password|secret)\s*[:=])"
)


def fallback_session_title(value):
    """Return the existing compact first-question fallback title."""

    title = " ".join(str(value or "").split())
    if len(title) <= FALLBACK_TITLE_MAX_CHARS:
        return title
    return f"{title[:FALLBACK_TITLE_MAX_CHARS]}…"


def normalize_generated_title(value):
    """Return a safe title or an empty fallback signal."""

    title = " ".join(str(value or "").splitlines())
    title = MARKDOWN_PATTERN.sub("", title)
    title = re.sub(r"(?i)^title\s*:\s*", "", title)
    title = title.strip(" \t\"'“”‘’.,;:：-—")
    title = " ".join(title.split())[:TITLE_OUTPUT_MAX_CHARS].strip()
    if not title or SENSITIVE_PATTERN.search(title):
        return ""
    if any(character in title for character in "{}[]"):
        return ""
    return title


def generate_semantic_session_title(session_uuid, run_uuid):
    """Generate and conditionally persist one session title."""

    claimed = Session.objects.filter(
        uuid=session_uuid,
        title_manually_edited=False,
        title_generation_status=Session.TitleGenerationStatus.PENDING,
    ).update(
        title_generation_status=Session.TitleGenerationStatus.GENERATING,
        updated_at=timezone.now(),
    )
    if not claimed:
        return ""

    session = Session.objects.select_related("assistant", "user").get(
        uuid=session_uuid
    )
    run = session.run_set.select_related(
        "input_message",
        "output_message",
    ).get(uuid=run_uuid)
    model_ref = (
        session.assistant.postprocess_model_ref
        or session.assistant.agent_model_ref
    )

    question = (run.input_message.content or "")[
        :TITLE_INPUT_QUESTION_MAX_CHARS
    ]
    answer = (run.output_message.content or "")[:TITLE_INPUT_ANSWER_MAX_CHARS]
    user_prompt = f"First question:\n{question}\n\nCompleted answer:\n{answer}"
    try:
        result = run_completion(
            model_ref=model_ref,
            system=TITLE_SYSTEM_PROMPT,
            user=user_prompt,
            node_name="lens.session_title",
            user_id=session.user_id,
        )
        title = normalize_generated_title(result.content)
    except Exception as exc:
        logger.warning(
            "session title generation failed for session %s: %s",
            session_uuid,
            exc,
        )
        title = ""

    if not title:
        _mark_generation_failed(session_uuid)
        return ""

    saved = Session.objects.filter(
        uuid=session_uuid,
        title_manually_edited=False,
        title_generation_status=Session.TitleGenerationStatus.GENERATING,
    ).update(
        title=title,
        title_generation_status=Session.TitleGenerationStatus.GENERATED,
        updated_at=timezone.now(),
    )
    return title if saved else ""


def _mark_generation_failed(session_uuid):
    """Keep the fallback title while recording a non-fatal failure."""

    Session.objects.filter(
        uuid=session_uuid,
        title_manually_edited=False,
        title_generation_status=Session.TitleGenerationStatus.GENERATING,
    ).update(
        title_generation_status=Session.TitleGenerationStatus.FAILED,
        updated_at=timezone.now(),
    )
