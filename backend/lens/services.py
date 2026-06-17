import asyncio
import hashlib
import json
from time import sleep

from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .llm import run_completion
from .models import Message, LensNode, Run, RunExecution, RunStep

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


class LensNodeDispatchError(RuntimeError):
    """Raised when a run cannot be dispatched to its LensNode."""


def lensnode_group_name(lensnode_uuid):
    """Return the Channels group name for a LensNode."""

    return f"lens.lensnode.{lensnode_uuid}"


def fail_active_runs_for_lensnode(lensnode_uuid):
    """Mark all non-terminal runs for a lensnode as failed on disconnect."""

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


def _next_sequence(session):
    """Return next message sequence for a session."""

    last_sequence = session.message_set.aggregate(Max("sequence"))["sequence__max"]
    return (last_sequence or 0) + 1


@transaction.atomic
def create_execution_run(session, question, idempotency_key="", enqueue=True):
    """Create a queued run for LensNode execution."""

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

    session = session.__class__.objects.select_for_update().get(pk=session.pk)
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

    if enqueue:
        transaction.on_commit(lambda: _enqueue_answer_run(run.uuid))

    return run


def _enqueue_answer_run(run_uuid):
    """Enqueue a run after transaction commit."""

    from .tasks import execute_answer_run

    execute_answer_run.delay(str(run_uuid))


def build_loaded_skills(assistant):
    """Snapshot active skill bindings for LensNode dispatch."""

    loaded = []
    for binding in assistant.skill_bindings.select_related("skill").filter(
        enabled=True
    ):
        loaded.append(
            {
                "skill_uuid": str(binding.skill.uuid),
                "skill_slug": binding.skill.slug,
                "skill_name": binding.skill.name,
                "version": binding.skill.version,
                "content_hash": _content_hash(binding.skill.definition),
                "definition": binding.skill.definition,
                "load_config": binding.load_config,
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
    """Validate that a run can be dispatched to its selected LensNode."""

    assistant = run.session.assistant
    lensnode = run.lensnode
    if lensnode is None:
        raise LensNodeDispatchError("LENSNODE_REQUIRED")
    if lensnode.status != LensNode.Status.ONLINE:
        raise LensNodeDispatchError("LENSNODE_OFFLINE")
    if lensnode.enrollment_status != LensNode.EnrollmentStatus.APPROVED:
        raise LensNodeDispatchError("LENSNODE_NOT_APPROVED")
    if lensnode.token_revoked:
        raise LensNodeDispatchError("LENSNODE_TOKEN_REVOKED")
    if assistant.selected_task not in task_names(lensnode):
        raise LensNodeDispatchError("LENSNODE_TASK_UNAVAILABLE")

    available = available_dir_paths(lensnode)
    for item in assistant.selected_dirs or []:
        if item.get("path") not in available:
            raise LensNodeDispatchError("LENSNODE_DIR_UNAVAILABLE")


@transaction.atomic
def create_run_execution_snapshot(run):
    """Create or return the per-run LensNode execution snapshot."""

    assistant = run.session.assistant
    execution, _ = RunExecution.objects.get_or_create(
        run=run,
        defaults={
            "lensnode": run.lensnode,
            "task": assistant.selected_task,
            "loaded_skills": build_loaded_skills(assistant),
            "loaded_mcps": build_loaded_mcps(assistant),
            "target_dirs": assistant.selected_dirs,
            "status": RunExecution.Status.DISPATCHED,
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
    cannot blow up from a long session.
    """

    messages = Message.objects.filter(
        session=run.session,
        sequence__lt=run.input_message.sequence,
        role__in=[Message.Role.USER, Message.Role.ASSISTANT],
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

    history = build_run_history(run)[-(QUERY_REWRITE_HISTORY_TURNS * 2):]
    context = "\n".join(
        f"{item['role']}: {item['content']}" for item in history
    )
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
        return {"question": original, "rewritten": False}
    return {
        "question": rewritten,
        "rewritten": rewritten != original.strip(),
        "original": original,
    }


def dispatch_run_to_lensnode(run, rewritten_question):
    """Send a run_start command to the connected LensNode."""

    execution = run.execution
    channel_layer = get_channel_layer()
    if channel_layer is None:
        raise LensNodeDispatchError("LENS_CHANNEL_LAYER_UNAVAILABLE")

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
                "loaded_skills": execution.loaded_skills,
                "loaded_mcps": execution.loaded_mcps,
                "agent_model_ref": (
                    str(run.session.assistant.agent_model_ref)
                    if run.session.assistant.agent_model_ref
                    else ""
                ),
                "max_agent_turns": AGENT_TURNS_BY_ROUNDS.get(
                    run.session.assistant.agent_rounds, 26
                ),
                "agent_rounds": run.session.assistant.agent_rounds,
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


def append_lensnode_output(
    run_uuid, content_delta="", final_content=None, reset=False
):
    """Persist output content streamed back from a LensNode.

    When reset is True the accumulated content is replaced by the delta
    rather than appended. The agent uses this at the start of each model
    turn so intermediate reasoning is superseded by the next turn,
    letting the SSE layer emit a token_reset and move prior text into
    the frontend thinking panel.
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
    return run


def record_lensnode_run_event(run_uuid, step_type, status, detail):
    """Persist a structured LensNode event into a RunStep row."""

    run = Run.objects.get(uuid=run_uuid)
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
    return step


@transaction.atomic
def finish_lensnode_run(run_uuid, status, error=""):
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
            run.status = Run.Status.QUEUED
            run.error = ""
            run.save(update_fields=["status", "error", "updated_at"])
            from .tasks import execute_answer_run
            execute_answer_run.apply_async(
                args=[str(run_uuid)],
                countdown=BUSY_RETRY_INTERVAL_S,
            )
            return run

    if status == Run.Status.DONE:
        run.status = Run.Status.DONE
        run.error = ""
        execution_status = RunExecution.Status.COMPLETED
    else:
        run.status = Run.Status.FAILED
        run.error = error or "LENS_RUN_FAILED"
        execution_status = RunExecution.Status.FAILED
    run.finished_at = now
    run.save(update_fields=["status", "error", "finished_at", "updated_at"])

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
        from .tasks import execute_answer_run
        execute_answer_run.delay(str(next_run.uuid))



def _step_sequence(step_type):
    """Return the canonical sequence for a step type."""

    mapping = {
        RunStep.StepType.QUERY_REWRITE: 0,
        RunStep.StepType.RETRIEVAL: 1,
        RunStep.StepType.ANSWER: 2,
        RunStep.StepType.STREAM: 3,
    }
    return mapping.get(step_type, 2)


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
                    "detail": step.detail,
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
                    "detail": step.detail,
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
        "steps": [
            {
                "step": step.step_type,
                "status": step.status,
                "detail": step.detail,
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
            "error": {
                "code": "LENS_RUN_CANCELLED",
                "message": "Run was cancelled.",
            },
            "ts": timezone.now().isoformat(),
        }
    return {
        "type": "done",
        "status": run.status,
        "ts": timezone.now().isoformat(),
    }
