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

from .assistant_lifecycle import lock_assistant_for_new_work
from .attachments import attachment_data_url, bind_attachments_to_message
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
)
from .runtime_events import public_step_detail, sanitize_termination_detail

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

HISTORY_MAX_PAIRS = 5
HISTORY_MAX_MESSAGE_CHARS = 2000
HISTORY_MAX_TOTAL_CHARS = 8000

QUERY_REWRITE_HISTORY_TURNS = 3
QUERY_REWRITE_MAX_CHARS = 400
QUERY_REWRITE_SYSTEM = (
    "You rewrite a user's latest question into ONE concise, self-contained "
    "search query for a document and code knowledge base. Resolve pronouns "
    "and references (\"it\", \"that\", \"the above\") using the conversation. "
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
    "(\"it\", \"this error\", \"the above\") using the conversation. Keep "
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
    Run.objects.filter(
        lensnode__uuid=lensnode_uuid,
        status__in=[Run.Status.RUNNING, Run.Status.STREAMING],
    ).update(
        status=Run.Status.FAILED,
        error="LENSNODE_DISCONNECTED",
        finished_at=now,
        updated_at=now,
    )


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
    candidates = Run.objects.filter(
        lensnode__uuid=lensnode_uuid,
        status__in=[Run.Status.RUNNING, Run.Status.STREAMING],
        started_at__lt=now - timedelta(seconds=RECONCILE_GRACE_SECONDS),
    ).exclude(uuid__in=active).values_list("uuid", flat=True)
    count = 0
    for run_uuid in candidates:
        schedule_reconcile_orphan_confirmation(run_uuid)
        count += 1
    return count


def _next_sequence(session):
    """Return next message sequence for a session."""

    last_sequence = session.message_set.aggregate(Max("sequence"))["sequence__max"]
    return (last_sequence or 0) + 1


@transaction.atomic
def create_execution_run(
    session,
    question,
    idempotency_key="",
    enqueue=True,
    attachment_uuids=None,
    user=None,
):
    """Create a queued run for LensNode execution."""

    assistant = lock_assistant_for_new_work(session.assistant, user)
    session = session.__class__.objects.select_for_update().get(pk=session.pk)
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
        lensnode=session.assistant.lensnode,
        idempotency_key=idempotency_key,
    )
    input_message.run = run
    input_message.save(update_fields=["run"])
    bind_attachments_to_message(session, input_message, attachment_uuids)
    create_run_execution_snapshot(run)

    if enqueue:
        transaction.on_commit(lambda: _enqueue_answer_run(run.uuid))

    return run


def _enqueue_answer_run(run_uuid):
    """Enqueue a run after transaction commit."""

    from .tasks import execute_answer_run

    execute_answer_run.delay(str(run_uuid))


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
        run.input_message.attachments.filter(
            kind=MessageAttachment.Kind.IMAGE
        )
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

    runtime_skills = resolve_loaded_skill_environment(
        execution.loaded_skills
    )
    if execution.task == "general_chat":
        if not runtime_skills:
            raise LensNodeDispatchError("GENERAL_CHAT_SKILL_REQUIRED")
    else:
        available = available_dir_paths(lensnode)
        for item in execution.target_dirs or []:
            if item.get("path") not in available:
                raise LensNodeDispatchError("LENSNODE_DIR_UNAVAILABLE")

    for skill in runtime_skills:
        declarations = (skill.get("definition") or {}).get(
            "environment"
        ) or []
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
    execution, _ = RunExecution.objects.get_or_create(
        run=run,
        defaults={
            "lensnode": run.lensnode,
            "task": assistant.selected_task,
            "loaded_skills": build_loaded_skills(assistant),
            "loaded_mcps": build_loaded_mcps(assistant),
            "agent_rounds": assistant.agent_rounds,
            "run_timeout_s": run_timeout_for_rounds(
                assistant.agent_rounds
            ),
            "target_dirs": (
                []
                if assistant.selected_task == "general_chat"
                else assistant.selected_dirs
            ),
            "token_budget_profile": token_budget["profile"],
            "token_budget_max_tokens": token_budget["max_tokens"],
            "token_budget_final_reserve_tokens": token_budget[
                "final_reserve_tokens"
            ],
            "status": RunExecution.Status.QUEUED,
        },
    )
    return execution


AGENT_TURNS_BY_ROUNDS = {
    "flash":    5,
    "fast":     13,
    "balanced": 26,
    "deep":     50,
    "max":      100,
}


def build_run_history(run):
    """Return prior conversation turns for a run as role/content dicts.

    Includes only completed user and assistant messages before the
    current turn, newest-first up to the caps, then returned in
    chronological order. A Message stores only final content (never tool
    traces), so the carried history stays compact and the agent context
    cannot blow up from a long session. Capability-unavailable fallback
    answers are omitted because their boundary decision applies only to
    that request; the user message remains available for follow-up context.
    """

    blocked_runs = Run.objects.filter(
        session=run.session,
        termination_detail__reason="capability_unavailable",
        output_message_id__isnull=False,
    )
    messages = Message.objects.filter(
        session=run.session,
        sequence__lt=run.input_message.sequence,
        role__in=[Message.Role.USER, Message.Role.ASSISTANT],
    ).exclude(
        pk__in=blocked_runs.values("output_message_id")
    ).order_by("-sequence")
    history = []
    total_chars = 0
    for message in messages:
        content = (message.content or "").strip()
        if not content:
            continue
        content = content[:HISTORY_MAX_MESSAGE_CHARS]
        if total_chars + len(content) > HISTORY_MAX_TOTAL_CHARS:
            break
        history.append({"role": message.role, "content": content})
        total_chars += len(content)
        if len(history) >= HISTORY_MAX_PAIRS * 2:
            break
    history.reverse()
    return history


def _recent_history_context(run):
    """Return the recent turns as a 'role: content' text block."""

    history = build_run_history(run)[-(QUERY_REWRITE_HISTORY_TURNS * 2):]
    return "\n".join(
        f"{item['role']}: {item['content']}" for item in history
    )


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
        (f"Conversation so far:\n{context}\n\n" if context else "")
        + f"Latest question: {original}\n\nRewritten search query:"
    )
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


def dispatch_run_to_lensnode(run, rewritten_question):
    """Send a run_start command to the connected LensNode."""

    execution = run.execution
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
    async_to_sync(channel_layer.group_send)(
        lensnode_group_name(run.lensnode.uuid),
        {
            "type": "lensnode.command",
            "payload": {
                "type": "run_start",
                "run_uuid": str(run.uuid),
                "task": execution.task,
                "question": rewritten_question,
                "history": build_run_history(run),
                "target_dirs": execution.target_dirs,
                "loaded_skills": resolve_loaded_skill_environment(
                    execution.loaded_skills
                ),
                "loaded_mcps": execution.loaded_mcps,
                "agent_model_ref": (
                    str(run.session.assistant.agent_model_ref)
                    if run.session.assistant.agent_model_ref
                    else ""
                ),
                "max_agent_turns": AGENT_TURNS_BY_ROUNDS.get(
                    agent_rounds, 26
                ),
                "agent_rounds": agent_rounds,
                "run_timeout_s": run_timeout_s,
                "token_budget": {
                    "profile": execution.token_budget_profile,
                    "max_tokens": execution.token_budget_max_tokens,
                    "final_reserve_tokens": (
                        execution.token_budget_final_reserve_tokens
                    ),
                },
                "settings": run.session.assistant.settings,
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
        run.output_message.content = f"{run.output_message.content}{content_delta}"
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

    run = Run.objects.select_related(
        "input_message",
        "output_message",
        "session",
        "session__assistant",
        "session__user",
    ).select_for_update(of=("self",)).get(uuid=run_uuid)
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
            from .tasks import execute_answer_run
            execute_answer_run.apply_async(
                args=[str(run_uuid)],
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

    if not run.session.title:
        run.session.title = run.input_message.content[:160]
        run.session.save(update_fields=["title", "updated_at"])

    _promote_next_queued_run(run.session.assistant)
    return run


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
        from .tasks import execute_answer_run
        execute_answer_run.delay(str(next_run.uuid))



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
            delta = content[len(emitted_content):]
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
        if (now - last_ping_at).total_seconds() >= STREAM_PING_INTERVAL_SECONDS:
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
            delta = content[len(emitted_content):]
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
        if (now - last_ping_at).total_seconds() >= STREAM_PING_INTERVAL_SECONDS:
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
