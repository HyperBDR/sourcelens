import asyncio
import hashlib
import json
from time import sleep

from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import Message, LensNode, Run, RunExecution, RunStep

TERMINAL_RUN_STATUSES = {
    Run.Status.DONE,
    Run.Status.FAILED,
    Run.Status.CANCELLED,
}
STREAM_POLL_INTERVAL_SECONDS = 1
STREAM_PING_INTERVAL_SECONDS = 15


class LensNodeDispatchError(RuntimeError):
    """Raised when a run cannot be dispatched to its LensNode."""


def lensnode_group_name(lensnode_uuid):
    """Return the Channels group name for a LensNode."""

    return f"lens.lensnode.{lensnode_uuid}"


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
                "target_dirs": execution.target_dirs,
                "loaded_skills": execution.loaded_skills,
                "loaded_mcps": execution.loaded_mcps,
                "agent_model_ref": (
                    str(run.session.assistant.agent_model_ref)
                    if run.session.assistant.agent_model_ref
                    else ""
                ),
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


def append_lensnode_output(run_uuid, content_delta="", final_content=None):
    """Persist output content streamed back from a LensNode."""

    run = Run.objects.select_related("output_message").get(uuid=run_uuid)
    if run.status in TERMINAL_RUN_STATUSES:
        return run
    if run.output_message is None:
        return run
    if final_content is not None:
        run.output_message.content = final_content
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
    if status == Run.Status.DONE:
        try:
            _postprocess_lensnode_answer(run)
            run.status = Run.Status.DONE
            run.error = ""
        except Exception as exc:
            run.status = Run.Status.FAILED
            run.error = str(exc)
            execution_status = RunExecution.Status.FAILED
        else:
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
    return run


def _postprocess_lensnode_answer(run):
    """Run optional control-plane answer post-processing."""

    assistant = run.session.assistant
    if not assistant.postprocess_model_ref:
        return None
    if run.output_message is None:
        return None

    from .llm import postprocess_answer

    step, _ = RunStep.objects.get_or_create(
        run=run,
        sequence=_step_sequence(RunStep.StepType.ANSWER),
        defaults={
            "step_type": RunStep.StepType.ANSWER,
            "status": RunStep.Status.RUNNING,
            "detail": {},
        },
    )
    step.step_type = RunStep.StepType.ANSWER
    step.status = RunStep.Status.RUNNING
    step.detail = {
        **(step.detail or {}),
        "raw_answer_length": len(run.output_message.content),
    }
    step.save(update_fields=["step_type", "status", "detail", "updated_at"])

    try:
        result = postprocess_answer(
            assistant,
            run.session.user,
            run.input_message.content,
            run.output_message.content,
        )
    except Exception as exc:
        step.status = RunStep.Status.FAILED
        step.detail = {
            **(step.detail or {}),
            "error": str(exc),
        }
        step.save(update_fields=["status", "detail", "updated_at"])
        raise

    run.output_message.content = result.content
    run.output_message.run = run
    run.output_message.save(update_fields=["content", "run"])
    step.status = RunStep.Status.DONE
    step.detail = {
        **(step.detail or {}),
        "postprocessed_answer_length": len(result.content),
        "metered": result.metered,
        "usage": result.usage,
    }
    step.save(update_fields=["status", "detail", "updated_at"])
    return result


def _step_sequence(step_type):
    """Return the canonical sequence for a step type."""

    mapping = {
        RunStep.StepType.QUERY_REWRITE: 1,
        RunStep.StepType.RETRIEVAL: 2,
        RunStep.StepType.ANSWER: 3,
        RunStep.StepType.STREAM: 4,
    }
    return mapping.get(step_type, 2)


def stream_run_events(run):
    """Yield SSE event payloads for a run until it reaches a terminal state."""

    emitted_steps = set()
    emitted_content = ""
    last_status = None
    last_ping_at = timezone.now()

    run = _load_run_stream_state(run.pk)
    yield _build_sync_event(run)

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
    last_ping_at = timezone.now()
    run_pk = run.pk

    run = await sync_to_async(_load_run_stream_state)(run_pk)
    yield _build_sync_event(run)

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
        Run.objects.select_related("output_message")
        .prefetch_related("steps")
        .get(pk=run_pk)
    )


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
