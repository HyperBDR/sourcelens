import asyncio
import hashlib
import json
import logging
from datetime import timedelta
from time import sleep

from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from accounts.models import normalize_answer_language

from .assistant_lifecycle import lock_assistant_for_new_work
from .attachments import (
    AttachmentError,
    attachment_data_url,
    bind_attachments_to_message,
)
from .document_attachments import (
    bind_document_attachments_to_run,
    get_run_document_attachments,
    get_run_document_expectation,
    set_run_document_expectation,
)
from .llm import run_completion, run_completion_multimodal
from .models import (
    Assistant,
    EnvironmentVariableSet,
    GlobalSetting,
    LensNode,
    Message,
    MessageAttachment,
    Run,
    RunExecution,
    RunStep,
    RunTraceExport,
    Session,
)
from .runtime_events import public_step_detail, sanitize_termination_detail
from .session_lifecycle import lock_active_session
from .session_titles import fallback_session_title
from .trace_context import root_observation_id_for_run, trace_id_for_run

logger = logging.getLogger(__name__)

TERMINAL_RUN_STATUSES = {
    Run.Status.DONE,
    Run.Status.FAILED,
    Run.Status.CANCELLED,
}
STREAM_POLL_INTERVAL_SECONDS = 0.3
STREAM_PING_INTERVAL_SECONDS = 15

BUSY_RETRY_INTERVAL_S = 5
BUSY_RETRY_WINDOW_S = 120
DOCUMENT_ATTACHMENT_CAPABILITY = "run_document_attachments"

HISTORY_MAX_PAIRS = 5
HISTORY_MAX_MESSAGE_CHARS = 2000
HISTORY_MAX_TOTAL_CHARS = 8000

QUERY_REWRITE_HISTORY_TURNS = 3
QUERY_REWRITE_MAX_CHARS = 400
QUERY_REWRITE_SYSTEM = (
    "You rewrite a user's latest question into ONE concise, self-contained "
    "search query for a document and code knowledge base. Resolve pronouns "
    'and references ("it", "that", "the above") using the conversation. '
    "Keep entity, product, feature and command names. Prefer the terminology "
    "the documents likely use, and fix obvious typos or homophones toward the "
    "domain term. If the question is already clear and self-contained, return "
    "it unchanged. Answer in the SAME language as the question. Output ONLY "
    "the rewritten query text — no quotes, no explanation."
)


MULTIMODAL_INTENT_MAX_CHARS = 600
MULTIMODAL_INTENT_SYSTEM = (
    "You analyze a user's troubleshooting question that includes one or "
    "more screenshots/images plus text. Combine both into ONE concise, "
    "self-contained query for a code and document knowledge base. "
    "Transcribe any error messages, stack traces, log lines, identifiers, "
    "component or file names, and visible UI state from the images into "
    "text, and merge them with the user's wording. Resolve references "
    '("it", "this error", "the above") using the conversation. Keep '
    "entity, product, feature and command names. Answer in the SAME "
    "language as the question. Output ONLY the resulting query text — no "
    "quotes, no explanation."
)


class LensNodeDispatchError(RuntimeError):
    """Raised when a run cannot be dispatched to its LensNode."""


def lensnode_group_name(lensnode_uuid):
    """Return the Channels group name for a LensNode."""

    return f"lens.lensnode.{lensnode_uuid}"


LENSNODE_DISCONNECT_GRACE_SECONDS_DEFAULT = 180


def get_lensnode_disconnect_grace_seconds():
    """Return how long a disconnected node keeps its runs before they fail.

    A blue/green API deploy recycles the container a node is connected to, so
    a WebSocket drop is not proof the node's in-flight runs failed — the node
    reconnects on an interval. Only a node still gone after this window has its
    RUNNING/STREAMING runs marked failed (see
    lens.tasks.check_lensnode_disconnect_grace_period). Admin-tunable via the
    GlobalSetting key ``lensnode.disconnect_grace_s``.
    """

    setting = GlobalSetting.objects.filter(
        key="lensnode.disconnect_grace_s"
    ).first()
    try:
        value = int(
            setting.value
            if setting
            else LENSNODE_DISCONNECT_GRACE_SECONDS_DEFAULT
        )
    except (TypeError, ValueError):
        return LENSNODE_DISCONNECT_GRACE_SECONDS_DEFAULT
    return max(1, value)


def schedule_lensnode_disconnect_grace_check(lensnode_uuid, disconnected_at):
    """Schedule the one-shot check that fails a node's runs if it stays gone
    past the grace window.

    Kept here (not in the consumer) so the scheduling policy is a service, not
    transport logic. Uses a Celery countdown task, not an in-process timer: the
    API process itself is what gets recycled on a blue/green switch, so an
    asyncio timer would die with it — the Celery worker is a separate process.
    disconnected_at pins the check to this disconnect episode.

    apply_async talks to the broker; wrap it so a broker hiccup at disconnect
    time can't raise out of the consumer's disconnect() — the periodic idle
    reaper (lens.lensnode_cleanup) remains the backstop for a genuinely dead
    node whose check never got scheduled.
    """

    from .tasks import check_lensnode_disconnect_grace_period

    grace_s = get_lensnode_disconnect_grace_seconds()
    try:
        check_lensnode_disconnect_grace_period.apply_async(
            args=[str(lensnode_uuid), disconnected_at.isoformat()],
            countdown=grace_s,
        )
    except Exception:
        logger.exception(
            "Failed to schedule disconnect grace check for lensnode %s; "
            "its runs will be reaped by the idle sweep instead",
            lensnode_uuid,
        )


def fail_active_runs_for_lensnode(lensnode_uuid):
    """Mark all non-terminal runs for a lensnode as failed.

    Called from the grace-period check once a node is confirmed still gone
    (see lens.tasks.check_lensnode_disconnect_grace_period), NOT directly on
    every disconnect — a brief drop during a blue/green switch must not fail
    runs the node is still executing and will report on reconnect. The
    status=RUNNING/STREAMING filter is itself the guard against a run that
    finished (left those states) while the node was reconnecting.
    """

    now = timezone.now()
    run_ids = list(
        Run.objects.filter(
            lensnode__uuid=lensnode_uuid,
            status__in=[Run.Status.RUNNING, Run.Status.STREAMING],
        ).values_list("id", flat=True)
    )
    if not run_ids:
        return 0
    Run.objects.filter(id__in=run_ids).update(
        status=Run.Status.FAILED,
        error="LENSNODE_DISCONNECTED",
        finished_at=now,
        updated_at=now,
    )
    fail_running_steps_for_runs(run_ids)
    return len(run_ids)


def fail_running_steps_for_runs(run_ids):
    """Finalize in-flight steps for runs failed outside the step context.

    Out-of-band failure paths (lensnode disconnect, orphan reconcile, idle
    sweep) update the Run row directly, so their RUNNING RunStep rows would
    otherwise stay RUNNING forever and disagree with the terminal Run state.
    """

    return RunStep.objects.filter(
        run_id__in=run_ids,
        status=RunStep.Status.RUNNING,
    ).update(status=RunStep.Status.FAILED, updated_at=timezone.now())


RECONCILE_GRACE_SECONDS = 60
RECONCILE_CONFIRM_GRACE_SECONDS_DEFAULT = 20


def get_reconcile_confirm_grace_seconds():
    """Return how long a reconnect-unreported run waits before being failed.

    A node's ``hello`` on reconnect reports its currently in-flight runs, but
    LensNode redelivers ``run_done`` at-least-once through a durable outbox
    (``LensNodeClient._send_loop``) — a run that finished during the drop is
    legitimately absent from that snapshot while its already-computed answer
    is still safely queued for delivery. Failing it immediately discards a
    correct answer that was moments from arriving. This window gives the
    normal completion path a chance to land first (see
    lens.tasks.confirm_reconcile_orphan). Admin-tunable via the GlobalSetting
    key ``lensnode.reconcile_confirm_grace_s``.
    """

    setting = GlobalSetting.objects.filter(
        key="lensnode.reconcile_confirm_grace_s"
    ).first()
    try:
        value = int(
            setting.value
            if setting
            else RECONCILE_CONFIRM_GRACE_SECONDS_DEFAULT
        )
    except (TypeError, ValueError):
        return RECONCILE_CONFIRM_GRACE_SECONDS_DEFAULT
    return max(1, value)


def schedule_reconcile_orphan_confirmation(run_uuid):
    """Schedule the delayed check that fails a run if it's still non-terminal.

    Called from reconcile_lensnode_active_runs for each candidate instead of
    failing it inline, so a run that legitimately finished during the drop
    gets a chance to reach a terminal state through the normal completion
    path (see get_reconcile_confirm_grace_seconds) before being written off.

    apply_async talks to the broker; wrap it so a broker hiccup can't raise
    out of the consumer's hello handler — the periodic idle reaper
    (lens.lensnode_cleanup) remains the backstop if scheduling fails.
    """

    from .tasks import confirm_reconcile_orphan

    grace_s = get_reconcile_confirm_grace_seconds()
    try:
        confirm_reconcile_orphan.apply_async(
            args=[str(run_uuid)],
            countdown=grace_s,
        )
    except Exception:
        logger.exception(
            "Failed to schedule reconcile-orphan confirmation for run %s; "
            "it will be reaped by the idle sweep instead",
            run_uuid,
        )


def reconcile_lensnode_active_runs(lensnode_uuid, active_run_uuids):
    """Schedule an orphan check for this node's runs it is no longer running.

    On (re)connect a LensNode reports the runs it is actively executing. A
    RUNNING/STREAMING run assigned to the node that the node does not claim
    is a candidate orphan (e.g. the control plane restarted mid-answer and
    the terminal frame was delayed on the dropped socket) — but LensNode
    redelivers at-least-once on reconnect, so a run that just finished is
    legitimately unreported while its result is still in flight. Rather than
    failing candidates inline, this schedules a delayed confirmation per
    candidate so the normal completion path gets a chance to resolve it
    first (see schedule_reconcile_orphan_confirmation). A short grace window
    on run age avoids even considering a run that was just dispatched but
    not yet started node-side.
    """

    active = {str(value) for value in (active_run_uuids or [])}
    now = timezone.now()
    candidates = (
        Run.objects.filter(
            lensnode__uuid=lensnode_uuid,
            status__in=[Run.Status.RUNNING, Run.Status.STREAMING],
            started_at__lt=now - timedelta(seconds=RECONCILE_GRACE_SECONDS),
        )
        .exclude(uuid__in=active)
        .values_list("uuid", flat=True)
    )
    count = 0
    for run_uuid in candidates:
        schedule_reconcile_orphan_confirmation(run_uuid)
        count += 1
    return count


def _next_sequence(session):
    """Return next message sequence for a session."""

    last_sequence = session.message_set.aggregate(Max("sequence"))[
        "sequence__max"
    ]
    return (last_sequence or 0) + 1


@transaction.atomic
def create_execution_run(
    session,
    question,
    idempotency_key="",
    retry_of_run=None,
    enqueue=True,
    attachment_uuids=None,
    user=None,
):
    """Create a queued run for LensNode execution."""

    assistant = lock_assistant_for_new_work(session.assistant, user)
    session = lock_active_session(session)
    session.assistant = assistant

    if idempotency_key:
        existing = (
            Run.objects.filter(
                session=session,
                idempotency_key=idempotency_key,
            )
            .select_related("output_message")
            .first()
        )
        if existing:
            return existing

    validate_retry_run(session, retry_of_run)

    if (
        not session.title_manually_edited
        and session.title_generation_status
        == Session.TitleGenerationStatus.PENDING
        and not session.message_set.exists()
    ):
        fallback_title = fallback_session_title(question)
        if fallback_title:
            session.title = fallback_title
            session.save(update_fields=["title", "updated_at"])

    input_message = Message.objects.create(
        session=session,
        role=Message.Role.USER,
        content=question,
        sequence=_next_sequence(session),
    )
    output_message = Message.objects.create(
        session=session,
        role=Message.Role.ASSISTANT,
        content="",
        sequence=input_message.sequence + 1,
    )
    run = Run.objects.create(
        session=session,
        status=Run.Status.QUEUED,
        input_message=input_message,
        output_message=output_message,
        retry_of_run=retry_of_run,
        lensnode=session.assistant.lensnode,
        idempotency_key=idempotency_key,
    )
    input_message.run = run
    input_message.save(update_fields=["run"])
    create_run_execution_snapshot(run)
    requested_attachment_uuids = [
        str(value) for value in (attachment_uuids or [])
    ]
    attachment_order = {
        value: order for order, value in enumerate(requested_attachment_uuids)
    }
    image_uuids = bind_attachments_to_message(
        session,
        input_message,
        requested_attachment_uuids,
        order_by_uuid=attachment_order,
    )
    document_uuids = [
        value
        for value in requested_attachment_uuids
        if str(value) not in image_uuids
    ]
    if document_uuids and run.execution.task == "general_chat":
        raise AttachmentError("ATTACHMENT_UNSUPPORTED_TYPE")
    if document_uuids and not supports_document_attachments(run.lensnode):
        raise AttachmentError("DOCUMENT_ATTACHMENTS_UNSUPPORTED_BY_LENSNODE")
    documents = bind_document_attachments_to_run(
        session,
        run,
        document_uuids,
        order_by_uuid=attachment_order,
    )
    if len(image_uuids) + len(documents) != len(requested_attachment_uuids):
        raise AttachmentError("ATTACHMENT_NOT_FOUND")

    document_count = len(documents)
    set_run_document_expectation(run.uuid, document_count)
    if enqueue:
        transaction.on_commit(
            lambda: _enqueue_answer_run(run.uuid, document_count)
        )

    return run


def validate_retry_run(session, retry_of_run):
    """Reject Retry links outside the Session or with an existing cycle."""

    if retry_of_run is None:
        return
    seen = set()
    current = retry_of_run
    while current is not None:
        if current.session_id != session.pk:
            raise ValueError("Retry Run must belong to the same Session.")
        if current.pk in seen:
            raise ValueError("Retry Run chain contains a cycle.")
        seen.add(current.pk)
        if current.retry_of_run_id is None:
            return
        current = Run.objects.only(
            "pk",
            "session_id",
            "retry_of_run_id",
        ).get(pk=current.retry_of_run_id)


def _enqueue_answer_run(run_uuid, expected_document_count=0):
    """Enqueue a run after transaction commit."""

    from .tasks import enqueue_answer_run_task

    enqueue_answer_run_task(run_uuid, expected_document_count)


def supports_document_attachments(lensnode):
    """Return whether a LensNode advertised transient document support."""

    labels = lensnode.labels if lensnode else {}
    return bool(
        isinstance(labels, dict)
        and labels.get(DOCUMENT_ATTACHMENT_CAPABILITY) is True
    )


def _enqueue_session_title_generation(session_uuid, run_uuid):
    """Enqueue semantic title generation after the answer is committed."""

    from .tasks import generate_session_title

    generate_session_title.delay(str(session_uuid), str(run_uuid))


def analyze_multimodal_intent(run):
    """Fold a run's image attachments and text into one search query.

    Calls the assistant's multimodal model with the question, recent
    history and the attached images, returning a consolidated textual
    query that drives retrieval and the node answer. Falls back to the
    original question when no multimodal model is set, no images decode,
    or the call fails, so dispatch never blocks on this step.
    """

    assistant = run.session.assistant
    original = run.input_message.content
    attachments = list(
        run.input_message.attachments.filter(kind=MessageAttachment.Kind.IMAGE)
    )
    if not attachments or not assistant.multimodal_model_ref:
        return {"question": original, "rewritten": False, "image_count": 0}

    image_data_urls = []
    for attachment in attachments:
        data_url = attachment_data_url(attachment)
        if data_url:
            image_data_urls.append(data_url)
    if not image_data_urls:
        return {"question": original, "rewritten": False, "image_count": 0}

    context = _recent_history_context(run)
    user_text = (
        (f"Conversation so far:\n{context}\n\n" if context else "")
        + f"User question: {original or '(no text, analyze the image)'}\n\n"
        + "Combined search query:"
    )
    try:
        result = run_completion_multimodal(
            model_ref=assistant.multimodal_model_ref,
            system=MULTIMODAL_INTENT_SYSTEM,
            user_text=user_text,
            image_data_urls=image_data_urls,
            node_name="lens.multimodal_intent",
            user_id=run.session.user_id,
        )
    except Exception as exc:
        logger.warning(
            "multimodal intent failed for run %s: %s", run.uuid, exc
        )
        return {
            "question": original,
            "rewritten": False,
            "image_count": len(image_data_urls),
            "error": str(exc),
        }

    text = " ".join((result.content or "").split())[
        :MULTIMODAL_INTENT_MAX_CHARS
    ]
    if not text:
        return {
            "question": original,
            "rewritten": False,
            "image_count": len(image_data_urls),
            "usage": result.usage,
        }
    return {
        "question": text,
        "rewritten": text != (original or "").strip(),
        "original": original,
        "image_count": len(image_data_urls),
        "usage": result.usage,
    }


def build_loaded_skills(assistant):
    """Snapshot active skill bindings for LensNode dispatch."""

    loaded = []
    for binding in assistant.skill_bindings.select_related(
        "skill", "environment_variable_set"
    ).filter(
        enabled=True,
        skill__enabled=True,
    ):
        skill = binding.skill
        content_hash = skill.package_hash or _content_hash(skill.definition)
        loaded.append(
            {
                "skill_uuid": str(skill.uuid),
                "skill_slug": skill.slug,
                "skill_name": skill.name,
                "version": skill.version,
                "content_hash": content_hash,
                "definition": skill.definition,
                "package_hash": skill.package_hash,
                "package_size": skill.package_size,
                "package_manifest": skill.package_manifest,
                "load_config": binding.load_config,
                "environment_variable_set_uuid": (
                    str(binding.environment_variable_set.uuid)
                    if binding.environment_variable_set
                    else None
                ),
            }
        )
    return loaded


def build_loaded_mcps(assistant):
    """Snapshot active MCP bindings for LensNode dispatch."""

    loaded = []
    for binding in assistant.mcp_bindings.select_related("mcp").filter(
        enabled=True
    ):
        loaded.append(
            {
                "mcp_uuid": str(binding.mcp.uuid),
                "mcp_name": binding.mcp.name,
                "version": binding.mcp.version,
                "content_hash": _content_hash(
                    {
                        "transport": binding.mcp.transport,
                        "endpoint": binding.mcp.endpoint,
                        "config": binding.mcp.config,
                    }
                ),
                "transport": binding.mcp.transport,
                "endpoint": binding.mcp.endpoint,
                "config": binding.mcp.config,
                "load_config": binding.load_config,
            }
        )
    return loaded


def _content_hash(value):
    """Return a stable sha256 hash for JSON-serializable content."""

    payload = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_loaded_skill_environment(loaded_skills):
    """Add decrypted per-Skill values to an ephemeral runtime payload."""

    runtime_skills = []
    for skill in loaded_skills or []:
        runtime_skill = dict(skill)
        variable_set_uuid = skill.get("environment_variable_set_uuid")
        variable_set = None
        if variable_set_uuid:
            variable_set = EnvironmentVariableSet.objects.filter(
                uuid=variable_set_uuid,
                enabled=True,
            ).first()
        values = variable_set.get_values() if variable_set else {}
        declarations = (skill.get("definition") or {}).get("environment") or []
        declared_names = {
            item.get("name")
            for item in declarations
            if isinstance(item, dict) and item.get("name")
        }
        runtime_skill["environment"] = {
            name: str(values[name])
            for name in declared_names
            if name in values
        }
        runtime_skills.append(runtime_skill)
    return runtime_skills


def task_names(lensnode):
    """Return task names reported by a LensNode."""

    names = set()
    for task in lensnode.tasks or []:
        if isinstance(task, dict) and task.get("name"):
            names.add(task["name"])
    return names


def available_dir_paths(lensnode):
    """Return directory paths reported by a LensNode."""

    paths = set()
    for item in lensnode.available_dirs or []:
        if isinstance(item, str):
            paths.add(item)
        elif isinstance(item, dict) and item.get("path"):
            paths.add(item["path"])
    return paths


def validate_run_dispatch(run):
    """Validate current runtime state and the frozen execution snapshot."""

    assistant = run.session.assistant
    lensnode = run.lensnode
    execution = run.execution
    if assistant.status != Assistant.Status.ACTIVE:
        raise LensNodeDispatchError("ASSISTANT_ARCHIVED")
    if lensnode is None:
        raise LensNodeDispatchError("LENSNODE_REQUIRED")
    if lensnode.status == LensNode.Status.DRAINING:
        raise LensNodeDispatchError("LENSNODE_DRAINING")
    if lensnode.status != LensNode.Status.ONLINE:
        raise LensNodeDispatchError("LENSNODE_OFFLINE")
    if lensnode.enrollment_status != LensNode.EnrollmentStatus.APPROVED:
        raise LensNodeDispatchError("LENSNODE_NOT_APPROVED")
    if lensnode.token_revoked:
        raise LensNodeDispatchError("LENSNODE_TOKEN_REVOKED")
    if execution.task not in task_names(lensnode):
        raise LensNodeDispatchError("LENSNODE_TASK_UNAVAILABLE")

    runtime_skills = resolve_loaded_skill_environment(execution.loaded_skills)
    if execution.task == "general_chat":
        if not runtime_skills:
            raise LensNodeDispatchError("GENERAL_CHAT_SKILL_REQUIRED")
    else:
        available = available_dir_paths(lensnode)
        for item in execution.target_dirs or []:
            if item.get("path") not in available:
                raise LensNodeDispatchError("LENSNODE_DIR_UNAVAILABLE")

    for skill in runtime_skills:
        declarations = (skill.get("definition") or {}).get("environment") or []
        required = {
            item["name"]
            for item in declarations
            if isinstance(item, dict)
            and item.get("required")
            and item.get("name")
        }
        values = skill.get("environment") or {}
        if any(not str(values.get(name) or "") for name in required):
            raise LensNodeDispatchError("SKILL_ENVIRONMENT_REQUIRED")


TOKEN_BUDGET_PROFILES = {
    Assistant.TokenBudgetProfile.STANDARD: {
        "max_tokens": 200000,
        "final_reserve_tokens": 40000,
    },
    Assistant.TokenBudgetProfile.DEEP: {
        "max_tokens": 500000,
        "final_reserve_tokens": 75000,
    },
    Assistant.TokenBudgetProfile.UNLIMITED: {
        "max_tokens": 0,
        "final_reserve_tokens": 0,
    },
}

RUN_TIMEOUT_SECONDS_BY_ROUNDS = {
    Assistant.AgentRounds.FLASH: 300,
    Assistant.AgentRounds.FAST: 600,
    Assistant.AgentRounds.BALANCED: 900,
    Assistant.AgentRounds.DEEP: 1800,
    Assistant.AgentRounds.MAX: 3600,
}


def token_budget_for_profile(profile):
    """Return the bounded token budget for an Assistant profile."""

    selected = profile if profile in TOKEN_BUDGET_PROFILES else "standard"
    return {
        "profile": selected,
        **TOKEN_BUDGET_PROFILES[selected],
    }


def run_timeout_for_rounds(agent_rounds):
    """Return the Run timeout for one Assistant analysis level."""

    return RUN_TIMEOUT_SECONDS_BY_ROUNDS.get(
        agent_rounds,
        RUN_TIMEOUT_SECONDS_BY_ROUNDS[Assistant.AgentRounds.BALANCED],
    )


@transaction.atomic
def create_run_execution_snapshot(run):
    """Create or return the per-run LensNode execution snapshot."""

    assistant = run.session.assistant
    token_budget = token_budget_for_profile(assistant.token_budget_profile)
    profile = getattr(run.session.user, "profile", None)
    answer_language = normalize_answer_language(
        getattr(profile, "language", None)
    )
    runtime_snapshot = _build_run_runtime_snapshot(
        assistant,
        run.lensnode,
        answer_language,
    )
    execution, _ = RunExecution.objects.get_or_create(
        run=run,
        defaults={
            "lensnode": run.lensnode,
            "task": assistant.selected_task,
            "loaded_skills": build_loaded_skills(assistant),
            "loaded_mcps": build_loaded_mcps(assistant),
            "agent_rounds": assistant.agent_rounds,
            "run_timeout_s": run_timeout_for_rounds(assistant.agent_rounds),
            "target_dirs": (
                []
                if assistant.selected_task == "general_chat"
                else assistant.selected_dirs
            ),
            "runtime_snapshot": runtime_snapshot,
            "token_budget_profile": token_budget["profile"],
            "token_budget_max_tokens": token_budget["max_tokens"],
            "token_budget_final_reserve_tokens": token_budget[
                "final_reserve_tokens"
            ],
            "status": RunExecution.Status.QUEUED,
        },
    )
    return execution


def _build_run_runtime_snapshot(assistant, lensnode, answer_language):
    """Return execution provenance that later edits cannot change."""

    model_refs = {
        "agent": str(assistant.agent_model_ref or ""),
        "multimodal": str(assistant.multimodal_model_ref or ""),
    }
    model_config_hashes = {
        name: _llm_config_hash(model_ref)
        for name, model_ref in model_refs.items()
        if model_ref
    }
    settings_payload = assistant.settings or {}
    return {
        "assistant_uuid": str(assistant.uuid),
        "assistant_updated_at": assistant.updated_at.isoformat(),
        "lensnode_uuid": str(lensnode.uuid) if lensnode else "",
        "lensnode_agent_version": (lensnode.agent_version if lensnode else ""),
        "answer_language": normalize_answer_language(answer_language),
        "model_refs": model_refs,
        "model_config_hashes": model_config_hashes,
        "settings": settings_payload,
        "settings_hash": _canonical_hash(settings_payload),
    }


def _llm_config_hash(model_ref):
    """Return a stable hash for the referenced model configuration."""

    try:
        from agentcore_metering.adapters.django.models import LLMConfig

        config = (
            LLMConfig.objects.filter(uuid=model_ref)
            .values_list(
                "config",
                flat=True,
            )
            .first()
        )
    except (ImportError, ValueError):
        return ""
    return _canonical_hash(config) if config is not None else ""


def _canonical_hash(value):
    """Return the SHA-256 of canonical JSON data."""

    serialized = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


AGENT_TURNS_BY_ROUNDS = {
    "flash": 5,
    "fast": 13,
    "balanced": 26,
    "deep": 50,
    "max": 100,
}


def build_run_history(run):
    """Return trusted prior Run turns in chronological order."""

    history, _ = _build_run_history_data(run)
    return history


def build_run_history_metadata(run):
    """Return non-sensitive counts describing Run history filtering."""

    _, metadata = _build_run_history_data(run)
    return metadata


def build_run_history_manifest(run):
    """Return identifiers and hashes for history actually sent to execution."""

    _, metadata = _build_run_history_data(run)
    return metadata["included_history"]


def _build_run_history_data(run):
    """Build trusted history and the corresponding filter counts."""

    all_prior_runs = list(
        Run.objects.filter(
            session=run.session,
            input_message__sequence__lt=run.input_message.sequence,
        )
        .select_related(
            "input_message",
            "output_message",
        )
        .order_by("input_message__sequence")
    )
    runs_by_id = {item.pk: item for item in all_prior_runs}
    cutoff_sequence = run.input_message.sequence
    superseded_current_attempts = 0
    if run.retry_of_run_id:
        root, superseded_current_attempts = _retry_chain_root(
            run,
            runs_by_id,
        )
        cutoff_sequence = root.input_message.sequence
    prior_runs = [
        item
        for item in all_prior_runs
        if item.input_message.sequence < cutoff_sequence
    ]
    latest_attempts = _latest_retry_attempts(prior_runs)
    limited_pairs = []
    limited_manifests = []
    total_chars = 0
    for prior in reversed(latest_attempts):
        entries = _trusted_history_entries(prior)
        pair_chars = sum(len(item["content"]) for item in entries)
        if total_chars + pair_chars > HISTORY_MAX_TOTAL_CHARS:
            break
        if entries:
            limited_pairs.append(entries)
            message_by_role = {
                "user": prior.input_message,
                "assistant": prior.output_message,
            }
            limited_manifests.append(
                {
                    "run_uuid": str(prior.uuid),
                    "messages": [
                        {
                            "message_uuid": str(
                                message_by_role[item["role"]].uuid
                            ),
                            "role": item["role"],
                            "chars": len(item["content"]),
                            "sha256": hashlib.sha256(
                                item["content"].encode()
                            ).hexdigest(),
                        }
                        for item in entries
                        if message_by_role[item["role"]] is not None
                    ],
                }
            )
            total_chars += pair_chars
        if len(limited_pairs) >= HISTORY_MAX_PAIRS:
            break
    history = [item for pair in reversed(limited_pairs) for item in pair]
    metadata = {
        "history_runs_before_filtering": len(all_prior_runs),
        "history_runs_after_filtering": len(latest_attempts),
        "superseded_retry_attempts_removed": (
            superseded_current_attempts
            + len(prior_runs)
            - len(latest_attempts)
        ),
        "non_completed_assistant_outputs_excluded": sum(
            bool(
                prior.output_message_id
                and (prior.output_message.content or "").strip()
            )
            and not _assistant_output_is_trusted(prior)
            for prior in latest_attempts
        ),
        "included_history": list(reversed(limited_manifests)),
    }
    return history, metadata


def _retry_chain_root(run, runs_by_id):
    """Return the first Run in a valid Retry chain."""

    seen = set()
    current = run
    attempts = 0
    while current.retry_of_run_id and current.pk not in seen:
        seen.add(current.pk)
        parent = runs_by_id.get(current.retry_of_run_id)
        if parent is None:
            break
        current = parent
        attempts += 1
    return current, attempts


def _latest_retry_attempts(prior_runs):
    """Collapse each Retry chain to its latest prior attempt."""

    runs_by_id = {item.pk: item for item in prior_runs}
    latest_by_root = {}
    for prior in prior_runs:
        root_id = prior.pk
        current = prior
        seen = set()
        while current.retry_of_run_id in runs_by_id and current.pk not in seen:
            seen.add(current.pk)
            current = runs_by_id[current.retry_of_run_id]
            root_id = current.pk
        latest_by_root[root_id] = prior
    return sorted(
        latest_by_root.values(),
        key=lambda item: item.input_message.sequence,
    )


def _trusted_history_entries(run):
    """Build one bounded Run turn, excluding untrusted assistant output."""

    entries = []
    question = (run.input_message.content or "").strip()
    if question:
        entries.append(
            {
                "role": Message.Role.USER,
                "content": question[:HISTORY_MAX_MESSAGE_CHARS],
            }
        )
    if _assistant_output_is_trusted(run) and run.output_message_id:
        answer = (run.output_message.content or "").strip()
        if answer:
            entries.append(
                {
                    "role": Message.Role.ASSISTANT,
                    "content": answer[:HISTORY_MAX_MESSAGE_CHARS],
                }
            )
    return entries


def _assistant_output_is_trusted(run):
    """Return whether a Run's assistant output is safe as history."""

    return run.status == Run.Status.DONE and run.outcome in {
        "",
        Run.Outcome.COMPLETED,
    }


def _recent_history_context(run):
    """Return the recent turns as a 'role: content' text block."""

    history = build_run_history(run)[-(QUERY_REWRITE_HISTORY_TURNS * 2) :]
    return "\n".join(f"{item['role']}: {item['content']}" for item in history)


def rewrite_query(run):
    """Rewrite a run's question into a contextual, search-optimized query.

    Uses the assistant's preprocess model to resolve conversational
    references and normalize wording toward the documents' terminology.
    Falls back to the original question when no preprocess model is set
    or the call fails, so dispatch never blocks on this step.
    """

    assistant = run.session.assistant
    original = run.input_message.content
    if not assistant.preprocess_model_ref:
        return {"question": original, "rewritten": False}

    context = _recent_history_context(run)
    user = (
        f"Conversation so far:\n{context}\n\n" if context else ""
    ) + f"Latest question: {original}\n\nRewritten search query:"
    try:
        result = run_completion(
            model_ref=assistant.preprocess_model_ref,
            system=QUERY_REWRITE_SYSTEM,
            user=user,
            node_name="lens.query_rewrite",
            user_id=run.session.user_id,
        )
    except Exception as exc:
        return {"question": original, "rewritten": False, "error": str(exc)}

    text = (result.content or "").strip()
    rewritten = " ".join(text.split())[:QUERY_REWRITE_MAX_CHARS]
    if not rewritten:
        return {
            "question": original,
            "rewritten": False,
            "usage": result.usage,
        }
    return {
        "question": rewritten,
        "rewritten": rewritten != original.strip(),
        "original": original,
        "usage": result.usage,
    }


def dispatch_run_to_lensnode(
    run,
    rewritten_question,
    subject_documents=None,
):
    """Send a run_start command to the connected LensNode."""

    execution = run.execution
    runtime_snapshot = execution.runtime_snapshot or {}
    model_refs = runtime_snapshot.get("model_refs") or {}
    runtime_settings = runtime_snapshot.get("settings")
    if not isinstance(runtime_settings, dict):
        runtime_settings = run.session.assistant.settings
    if subject_documents is None:
        subject_documents = get_run_document_attachments(run.uuid)
    subject_documents = [
        {
            "uuid": item["uuid"],
            "original_name": item["original_name"],
            "mime_type": item["mime_type"],
            "byte_size": item["byte_size"],
            "content_hash": item["content_hash"],
        }
        for item in subject_documents
    ]
    if subject_documents and not supports_document_attachments(run.lensnode):
        raise LensNodeDispatchError(
            "DOCUMENT_ATTACHMENTS_UNSUPPORTED_BY_LENSNODE"
        )
    channel_layer = get_channel_layer()
    if channel_layer is None:
        raise LensNodeDispatchError("LENS_CHANNEL_LAYER_UNAVAILABLE")

    agent_rounds = (
        execution.agent_rounds
        or run.session.assistant.agent_rounds
        or Assistant.AgentRounds.BALANCED
    )
    run_timeout_s = execution.run_timeout_s or run_timeout_for_rounds(
        agent_rounds
    )
    profile = getattr(run.session.user, "profile", None)
    answer_language = normalize_answer_language(
        runtime_snapshot.get("answer_language")
        or getattr(profile, "language", None)
    )
    async_to_sync(channel_layer.group_send)(
        lensnode_group_name(run.lensnode.uuid),
        {
            "type": "lensnode.command",
            "payload": {
                "type": "run_start",
                "run_uuid": str(run.uuid),
                "task": execution.task,
                "question": rewritten_question,
                "answer_language": answer_language,
                "subject_documents": subject_documents,
                "vision_model_ref": (
                    model_refs.get("multimodal")
                    or str(run.session.assistant.multimodal_model_ref or "")
                ),
                "history": build_run_history(run),
                "target_dirs": execution.target_dirs,
                "loaded_skills": resolve_loaded_skill_environment(
                    execution.loaded_skills
                ),
                "loaded_mcps": execution.loaded_mcps,
                "agent_model_ref": (
                    model_refs.get("agent")
                    or str(run.session.assistant.agent_model_ref or "")
                ),
                "max_agent_turns": AGENT_TURNS_BY_ROUNDS.get(agent_rounds, 26),
                "agent_rounds": agent_rounds,
                "run_timeout_s": run_timeout_s,
                "trace_context": {
                    "trace_id": trace_id_for_run(run.uuid),
                    "root_observation_id": root_observation_id_for_run(
                        run.uuid
                    ),
                },
                "token_budget": {
                    "profile": execution.token_budget_profile,
                    "max_tokens": execution.token_budget_max_tokens,
                    "final_reserve_tokens": (
                        execution.token_budget_final_reserve_tokens
                    ),
                },
                "settings": runtime_settings,
            },
        },
    )


def cancel_run_on_lensnode(run):
    """Send a run_cancel command to the connected LensNode."""

    if run.lensnode is None:
        return None
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return None
    async_to_sync(channel_layer.group_send)(
        lensnode_group_name(run.lensnode.uuid),
        {
            "type": "lensnode.command",
            "payload": {
                "type": "run_cancel",
                "run_uuid": str(run.uuid),
            },
        },
    )
    return None


def cancel_datasource_sync_on_lensnode(lensnode, task_id):
    """Send a datasource_cancel command to the connected LensNode."""

    if lensnode is None or not task_id:
        return None
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return None
    async_to_sync(channel_layer.group_send)(
        lensnode_group_name(lensnode.uuid),
        {
            "type": "lensnode.command",
            "payload": {
                "type": "datasource_cancel",
                "task_id": str(task_id),
            },
        },
    )
    return None


RUN_ACTIVITY_THROTTLE_SECONDS = 15


def touch_run_activity(run_pk):
    """Bump a run's last_activity_at, throttled to avoid per-token writes.

    Streamed output and node events call this on every frame; the
    conditional update only writes when the stamp is stale, so the idle
    reaper has a fresh signal without a database write per token.
    """

    now = timezone.now()
    Run.objects.filter(pk=run_pk).filter(
        Q(last_activity_at__isnull=True)
        | Q(
            last_activity_at__lt=now
            - timedelta(seconds=RUN_ACTIVITY_THROTTLE_SECONDS)
        )
    ).update(last_activity_at=now)


def append_lensnode_output(
    run_uuid, content_delta="", final_content=None, reset=False
):
    """Persist output content streamed back from a LensNode.

    When reset is True the accumulated content is replaced by the delta
    rather than appended. Reset remains supported for older LensNodes;
    current nodes buffer tool-call turns and publish only final answers.
    """

    run = Run.objects.select_related("output_message").get(uuid=run_uuid)
    if run.status in TERMINAL_RUN_STATUSES:
        return run
    if run.output_message is None:
        return run
    if final_content:
        run.output_message.content = final_content
    elif final_content is not None:
        # an empty final reconciliation must not wipe streamed content
        pass
    elif reset:
        run.output_message.content = content_delta
    else:
        run.output_message.content = (
            f"{run.output_message.content}{content_delta}"
        )
    run.output_message.run = run
    run.output_message.save(update_fields=["content", "run"])
    touch_run_activity(run.pk)
    return run


def record_lensnode_run_event(run_uuid, step_type, status, detail):
    """Persist a structured LensNode event into a RunStep row.

    Events for a run that already reached a terminal state are dropped:
    a cancelled agent thread can keep emitting for a while, and those
    late events must not rewrite the trace of a settled run. The warning
    makes orphan-thread activity observable.
    """

    run = Run.objects.get(uuid=run_uuid)
    if run.status in TERMINAL_RUN_STATUSES:
        logger.warning(
            "run %s: dropping late %s event (run already %s)",
            run_uuid,
            step_type,
            run.status,
        )
        return None
    sequence = _step_sequence(step_type)
    step, _ = RunStep.objects.get_or_create(
        run=run,
        sequence=sequence,
        defaults={
            "step_type": step_type,
            "status": status,
            "detail": {},
        },
    )
    step.step_type = step_type
    step.status = status
    step.detail = {
        **(step.detail or {}),
        "events": [*(step.detail or {}).get("events", []), detail],
    }
    step.save(update_fields=["step_type", "status", "detail", "updated_at"])
    touch_run_activity(run.pk)
    return step


@transaction.atomic
def finish_lensnode_run(
    run_uuid,
    status,
    error="",
    outcome="",
    termination_detail=None,
):
    """Mark a LensNode-dispatched run finished."""

    run = (
        Run.objects.select_related(
            "input_message",
            "output_message",
            "session",
            "session__assistant",
            "session__user",
        )
        .select_for_update(of=("self",))
        .get(uuid=run_uuid)
    )
    if run.status in TERMINAL_RUN_STATUSES:
        return run
    now = timezone.now()

    if status == Run.Status.FAILED and error == "LENSNODE_BUSY":
        elapsed = (now - run.created_at).total_seconds()
        if elapsed < BUSY_RETRY_WINDOW_S:
            logger.warning(
                "run %s: LENSNODE_BUSY (elapsed=%.0fs < window=%ds),"
                " re-queueing in %ds",
                run_uuid,
                elapsed,
                BUSY_RETRY_WINDOW_S,
                BUSY_RETRY_INTERVAL_S,
            )
            run.status = Run.Status.QUEUED
            run.error = ""
            run.outcome = ""
            run.termination_detail = {}
            run.save(
                update_fields=[
                    "status",
                    "error",
                    "outcome",
                    "termination_detail",
                    "updated_at",
                ]
            )
            from .tasks import enqueue_answer_run_task

            expected_document_count = get_run_document_expectation(run_uuid)
            enqueue_answer_run_task(
                run_uuid,
                (
                    expected_document_count
                    if expected_document_count is not None
                    else -1
                ),
                countdown=BUSY_RETRY_INTERVAL_S,
            )
            return run
        logger.error(
            "run %s: LENSNODE_BUSY retry window exceeded (elapsed=%.0fs > %ds),"
            " failing run",
            run_uuid,
            elapsed,
            BUSY_RETRY_WINDOW_S,
        )

    if status == Run.Status.DONE:
        run.status = Run.Status.DONE
        run.error = ""
        default_outcome = Run.Outcome.COMPLETED
        execution_status = RunExecution.Status.COMPLETED
    else:
        run.status = Run.Status.FAILED
        run.error = error or "LENS_RUN_FAILED"
        default_outcome = Run.Outcome.BLOCKED
        execution_status = RunExecution.Status.FAILED
    valid_outcomes = {choice for choice, _ in Run.Outcome.choices}
    run.outcome = outcome if outcome in valid_outcomes else default_outcome
    run.termination_detail = sanitize_termination_detail(
        termination_detail or {}
    )
    run.finished_at = now
    run.save(
        update_fields=[
            "status",
            "error",
            "outcome",
            "termination_detail",
            "finished_at",
            "updated_at",
        ]
    )

    if hasattr(run, "execution"):
        run.execution.status = execution_status
        run.execution.finished_at = now
        run.execution.save(update_fields=["status", "finished_at"])

    should_generate_title = (
        run.status == Run.Status.DONE
        and run.outcome != Run.Outcome.BLOCKED
        and run.output_message is not None
        and bool((run.output_message.content or "").strip())
        and not run.session.title_manually_edited
        and run.session.title_generation_status
        == Session.TitleGenerationStatus.PENDING
    )
    if should_generate_title:
        transaction.on_commit(
            lambda run_uuid=run.uuid, session_uuid=run.session.uuid: (
                _enqueue_session_title_generation(session_uuid, run_uuid)
            )
        )

    if _run_has_trace_observations(run):
        trace_export, _created = RunTraceExport.objects.get_or_create(run=run)
        transaction.on_commit(
            lambda export_uuid=trace_export.uuid: _enqueue_trace_export(
                export_uuid
            )
        )

    _promote_next_queued_run(run.session.assistant)
    return run


def _enqueue_trace_export(export_uuid):
    """Enqueue optional trace export after Run state is durable."""

    from .tasks import export_run_trace_task

    export_run_trace_task.delay(str(export_uuid))


def _run_has_trace_observations(run):
    """Return whether persisted RunStep events contain an observation."""

    for detail in run.steps.values_list("detail", flat=True):
        for event in (detail or {}).get("events", []):
            if isinstance(event, dict) and isinstance(
                event.get("observation"),
                dict,
            ):
                return True
    return False


def _promote_next_queued_run(assistant):
    """Enqueue the oldest queued run for this assistant, if any."""

    next_run = (
        Run.objects.filter(
            session__assistant=assistant,
            status=Run.Status.QUEUED,
        )
        .order_by("created_at")
        .first()
    )
    if next_run:
        logger.info(
            "assistant %s: promoting queued run %s",
            assistant.slug,
            next_run.uuid,
        )
        from .tasks import enqueue_answer_run_task

        expected_document_count = get_run_document_expectation(next_run.uuid)
        enqueue_answer_run_task(
            next_run.uuid,
            (
                expected_document_count
                if expected_document_count is not None
                else -1
            ),
        )


def _step_sequence(step_type):
    """Return the canonical sequence for a step type."""

    mapping = {
        RunStep.StepType.QUERY_REWRITE: 0,
        RunStep.StepType.MULTIMODAL: 1,
        RunStep.StepType.RETRIEVAL: 2,
        RunStep.StepType.GENERAL_CHAT: 3,
        RunStep.StepType.ANSWER: 4,
        RunStep.StepType.STREAM: 5,
    }
    return mapping.get(step_type, 4)


def stream_run_events(run):
    """Yield SSE event payloads for a run until it reaches a terminal state."""

    emitted_steps = set()
    emitted_content = ""
    last_status = None
    last_queue_position = None
    last_ping_at = timezone.now()

    run = _load_run_stream_state(run.pk)
    yield _build_sync_event(run)
    # the sync event already carries the current content; seed emitted_content
    # so the loop streams only new deltas (avoids resending it on reconnect)
    emitted_content = _run_content(run)

    while True:
        run = _load_run_stream_state(run.pk)
        content = _run_content(run)

        if run.status != last_status:
            last_status = run.status
            yield {
                "type": "status",
                "status": run.status,
                "ts": timezone.now().isoformat(),
            }

        if run.status == Run.Status.QUEUED:
            position = _queue_position(run)
            if position != last_queue_position:
                last_queue_position = position
                yield {
                    "type": "queue_position",
                    "position": position,
                    "ts": timezone.now().isoformat(),
                }
        else:
            last_queue_position = None

        for step in run.steps.all():
            step_key = (step.sequence, step.status, step.updated_at)
            if step_key not in emitted_steps:
                emitted_steps.add(step_key)
                yield {
                    "type": "step",
                    "step": step.step_type,
                    "status": step.status,
                    "detail": public_step_detail(step.detail),
                    "sequence": step.sequence,
                    "ts": timezone.now().isoformat(),
                }

        if content != emitted_content:
            if not content.startswith(emitted_content):
                emitted_content = ""
                yield {
                    "type": "token_reset",
                    "ts": timezone.now().isoformat(),
                }
            delta = content[len(emitted_content) :]
            emitted_content = content
            if delta:
                yield {
                    "type": "token",
                    "content": delta,
                    "ts": timezone.now().isoformat(),
                }

        if run.status in TERMINAL_RUN_STATUSES:
            yield _terminal_stream_event(run)
            return

        now = timezone.now()
        if (
            now - last_ping_at
        ).total_seconds() >= STREAM_PING_INTERVAL_SECONDS:
            last_ping_at = now
            yield {
                "type": "ping",
                "ts": now.isoformat(),
            }

        sleep(STREAM_POLL_INTERVAL_SECONDS)


async def stream_run_events_async(run):
    """Yield SSE event payloads using an async iterator for ASGI streaming."""

    emitted_steps = set()
    emitted_content = ""
    last_status = None
    last_queue_position = None
    last_ping_at = timezone.now()
    run_pk = run.pk

    run = await sync_to_async(_load_run_stream_state)(run_pk)
    yield _build_sync_event(run)
    # the sync event already carries the current content; seed emitted_content
    # so the loop streams only new deltas (avoids resending it on reconnect)
    emitted_content = _run_content(run)

    while True:
        run = await sync_to_async(_load_run_stream_state)(run_pk)
        content = _run_content(run)

        if run.status != last_status:
            last_status = run.status
            yield {
                "type": "status",
                "status": run.status,
                "ts": timezone.now().isoformat(),
            }

        if run.status == Run.Status.QUEUED:
            position = await sync_to_async(_queue_position)(run)
            if position != last_queue_position:
                last_queue_position = position
                yield {
                    "type": "queue_position",
                    "position": position,
                    "ts": timezone.now().isoformat(),
                }
        else:
            last_queue_position = None

        for step in run.steps.all():
            step_key = (step.sequence, step.status, step.updated_at)
            if step_key not in emitted_steps:
                emitted_steps.add(step_key)
                yield {
                    "type": "step",
                    "step": step.step_type,
                    "status": step.status,
                    "detail": public_step_detail(step.detail),
                    "sequence": step.sequence,
                    "ts": timezone.now().isoformat(),
                }

        if content != emitted_content:
            if not content.startswith(emitted_content):
                emitted_content = ""
                yield {
                    "type": "token_reset",
                    "ts": timezone.now().isoformat(),
                }
            delta = content[len(emitted_content) :]
            emitted_content = content
            if delta:
                yield {
                    "type": "token",
                    "content": delta,
                    "ts": timezone.now().isoformat(),
                }

        if run.status in TERMINAL_RUN_STATUSES:
            yield _terminal_stream_event(run)
            return

        now = timezone.now()
        if (
            now - last_ping_at
        ).total_seconds() >= STREAM_PING_INTERVAL_SECONDS:
            last_ping_at = now
            yield {
                "type": "ping",
                "ts": now.isoformat(),
            }

        await asyncio.sleep(STREAM_POLL_INTERVAL_SECONDS)


def _load_run_stream_state(run_pk):
    """Load the latest run state needed for SSE snapshots."""

    return (
        Run.objects.select_related("output_message", "session__assistant")
        .prefetch_related("steps")
        .get(pk=run_pk)
    )


def _queue_position(run):
    """Return the number of QUEUED runs ahead of this run for the assistant."""

    return Run.objects.filter(
        session__assistant=run.session.assistant,
        status=Run.Status.QUEUED,
        created_at__lt=run.created_at,
    ).count()


def _run_content(run):
    """Return accumulated assistant content for a run."""

    if not run.output_message:
        return ""
    return run.output_message.content


def _build_sync_event(run):
    """Build a persisted snapshot event for new or reconnected SSE clients."""

    return {
        "type": "sync",
        "status": run.status,
        "outcome": run.outcome,
        "termination_detail": sanitize_termination_detail(
            run.termination_detail
        ),
        "steps": [
            {
                "step": step.step_type,
                "status": step.status,
                "detail": public_step_detail(step.detail),
                "sequence": step.sequence,
            }
            for step in run.steps.all()
        ],
        "content": _run_content(run),
        "ts": timezone.now().isoformat(),
    }


def _terminal_stream_event(run):
    """Build the terminal SSE event for a run."""

    if run.status == Run.Status.FAILED:
        return {
            "type": "error",
            "status": run.status,
            "outcome": run.outcome,
            "termination_detail": sanitize_termination_detail(
                run.termination_detail
            ),
            "error": {
                "code": run.error or "LENS_RUN_FAILED",
                "message": run.error or "Run failed.",
            },
            "ts": timezone.now().isoformat(),
        }
    if run.status == Run.Status.CANCELLED:
        return {
            "type": "error",
            "status": run.status,
            "outcome": run.outcome,
            "termination_detail": sanitize_termination_detail(
                run.termination_detail
            ),
            "error": {
                "code": "LENS_RUN_CANCELLED",
                "message": "Run was cancelled.",
            },
            "ts": timezone.now().isoformat(),
        }
    return {
        "type": "done",
        "status": run.status,
        "outcome": run.outcome,
        "termination_detail": sanitize_termination_detail(
            run.termination_detail
        ),
        "ts": timezone.now().isoformat(),
    }
