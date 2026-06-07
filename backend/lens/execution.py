from contextlib import contextmanager

from django.db import transaction
from django.utils import timezone

from .models import Run, RunExecution, RunStep
from .services import (
    LensNodeDispatchError,
    create_run_execution_snapshot,
    dispatch_run_to_lensnode,
    finish_lensnode_run,
    validate_run_dispatch,
)


class LensExecutionError(Exception):
    """Base exception for Lens execution failures."""


@contextmanager
def run_step(run, step_type, sequence):
    """Create and finalize a RunStep around one execution phase."""

    step = RunStep.objects.create(
        run=run,
        step_type=step_type,
        status=RunStep.Status.RUNNING,
        sequence=sequence,
    )
    try:
        yield step
    except Exception as exc:
        step.status = RunStep.Status.FAILED
        step.detail = {
            **step.detail,
            "error": str(exc),
        }
        step.save(update_fields=["status", "detail", "updated_at"])
        raise
    else:
        step.status = RunStep.Status.DONE
        step.save(update_fields=["status", "detail", "updated_at"])


def _mark_run_failed(run, exc):
    """Persist terminal failure state for a run."""

    run.status = Run.Status.FAILED
    run.error = str(exc)
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "error", "finished_at", "updated_at"])
    if hasattr(run, "execution"):
        run.execution.status = RunExecution.Status.FAILED
        run.execution.finished_at = run.finished_at
        run.execution.save(update_fields=["status", "finished_at"])


def _lensnode_query_rewrite(state):
    """LangGraph node for query preflight and rewrite."""

    from .llm import preflight_question

    run = state["run"]
    assistant = state["assistant"]
    with run_step(run, RunStep.StepType.QUERY_REWRITE, 1) as step:
        preflight = preflight_question(
            assistant,
            run.session.user,
            run.input_message.content,
        )
        step.detail = {
            "original_question": run.input_message.content,
            "rewritten_question": preflight.rewritten_question,
            "decision": preflight.decision,
            "reason": preflight.reason,
            "message": preflight.message,
            "metered": preflight.metered,
            "usage": preflight.usage,
        }
    if preflight.decision != "allow":
        _complete_preflight_response(run, preflight)
    return {
        **state,
        "preflight_decision": preflight.decision,
        "rewritten_question": preflight.rewritten_question,
    }


def _complete_preflight_response(run, preflight):
    """Complete a run without LensNode dispatch after preflight."""

    now = timezone.now()
    with transaction.atomic():
        with run_step(run, RunStep.StepType.ANSWER, 3) as step:
            step.detail = {
                "preflight_decision": preflight.decision,
                "reason": preflight.reason,
                "answer_length": len(preflight.message),
            }
        if run.output_message is not None:
            run.output_message.content = preflight.message
            run.output_message.run = run
            run.output_message.save(update_fields=["content", "run"])
        run.status = Run.Status.DONE
        run.error = ""
        run.finished_at = now
        run.save(update_fields=["status", "error", "finished_at", "updated_at"])


def _lensnode_dispatch(state):
    """LangGraph node for creating a snapshot and dispatching to LensNode."""

    run = state["run"]
    with run_step(run, RunStep.StepType.RETRIEVAL, 2) as step:
        validate_run_dispatch(run)
        execution = create_run_execution_snapshot(run)
        execution.status = RunExecution.Status.RUNNING
        execution.started_at = timezone.now()
        execution.save(update_fields=["status", "started_at"])
        dispatch_run_to_lensnode(run, state["rewritten_question"])
        step.detail = {
            "lensnode_uuid": str(run.lensnode.uuid),
            "task": execution.task,
            "target_dirs": execution.target_dirs,
            "dispatched": True,
        }
    return state


def _lensnode_inline_done(state):
    """Complete an inline test run without waiting for an external LensNode."""

    run = state["run"]
    answer = (
        f"Dispatched {run.session.assistant.selected_task} to "
        f"{run.lensnode.name}."
    )
    with transaction.atomic():
        with run_step(run, RunStep.StepType.ANSWER, 3) as step:
            step.detail = {
                "answer_length": len(answer),
                "inline": True,
            }
        with run_step(run, RunStep.StepType.STREAM, 4) as step:
            run.output_message.content = answer
            run.output_message.run = run
            run.output_message.save(update_fields=["content", "run"])
            step.detail = {"content_length": len(answer)}
        finish_lensnode_run(run.uuid, Run.Status.DONE)
    return state


def _build_execution_graph(dispatch):
    """Build the Lens execution LangGraph."""

    from langgraph.graph import END, StateGraph

    graph = StateGraph(dict)
    graph.add_node("query_rewrite", _lensnode_query_rewrite)
    graph.add_node("dispatch", _lensnode_dispatch)
    graph.set_entry_point("query_rewrite")
    graph.add_conditional_edges(
        "query_rewrite",
        _route_after_preflight,
        {
            "dispatch": "dispatch",
            "end": END,
        },
    )
    if dispatch:
        graph.add_edge("dispatch", END)
    else:
        graph.add_node("inline_done", _lensnode_inline_done)
        graph.add_edge("dispatch", "inline_done")
        graph.add_edge("inline_done", END)
    return graph.compile()


def _route_after_preflight(state):
    """Route execution based on query preflight decision."""

    if state.get("preflight_decision") == "allow":
        return "dispatch"
    return "end"


def execute_answer_run(run, dispatch=True):
    """Execute a Lens answer run through LensNode dispatch flow."""

    assistant = run.session.assistant
    try:
        run.status = Run.Status.RUNNING
        run.started_at = run.started_at or timezone.now()
        run.save(update_fields=["status", "started_at", "updated_at"])

        graph = _build_execution_graph(dispatch)
        graph.invoke(
            {
                "run": run,
                "assistant": assistant,
            }
        )
        run.refresh_from_db()
        if dispatch and run.status not in [
            Run.Status.DONE,
            Run.Status.FAILED,
            Run.Status.CANCELLED,
        ]:
            run.status = Run.Status.STREAMING
            run.save(update_fields=["status", "updated_at"])

    except LensNodeDispatchError as exc:
        _mark_run_failed(run, exc)
        raise
    except Exception as exc:
        _mark_run_failed(run, exc)
        raise

    return run
