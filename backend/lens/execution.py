from contextlib import contextmanager

from django.db import transaction
from django.utils import timezone

from .models import Run, RunExecution, RunStep
from .services import (
    LensNodeDispatchError,
    create_run_execution_snapshot,
    dispatch_run_to_lensnode,
    finish_lensnode_run,
    rewrite_query,
    validate_run_dispatch,
)


class LensExecutionError(Exception):
    """Base exception for Lens execution failures."""


@contextmanager
def run_step(run, step_type, sequence):
    """Create and finalize a RunStep around one execution phase."""

    step, _ = RunStep.objects.update_or_create(
        run=run,
        sequence=sequence,
        defaults={
            "step_type": step_type,
            "status": RunStep.Status.RUNNING,
            "detail": {},
        },
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



def _lensnode_dispatch(state):
    """LangGraph node for creating a snapshot and dispatching to LensNode."""

    run = state["run"]
    question = run.input_message.content
    if run.session.assistant.preprocess_model_ref:
        with run_step(run, RunStep.StepType.QUERY_REWRITE, 0) as step:
            rewrite = rewrite_query(run)
            question = rewrite["question"]
            step.detail = {
                "rewritten": rewrite["rewritten"],
                "original": rewrite.get("original", run.input_message.content),
                "query": question,
            }
            if rewrite.get("error"):
                step.detail["error"] = rewrite["error"]
    with run_step(run, RunStep.StepType.RETRIEVAL, 1) as step:
        validate_run_dispatch(run)
        execution = create_run_execution_snapshot(run)
        execution.status = RunExecution.Status.RUNNING
        execution.started_at = timezone.now()
        execution.save(update_fields=["status", "started_at"])
        dispatch_run_to_lensnode(run, question)
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
        with run_step(run, RunStep.StepType.ANSWER, 2) as step:
            step.detail = {
                "answer_length": len(answer),
                "inline": True,
            }
        with run_step(run, RunStep.StepType.STREAM, 3) as step:
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
    graph.add_node("dispatch", _lensnode_dispatch)
    graph.set_entry_point("dispatch")
    if dispatch:
        graph.add_edge("dispatch", END)
    else:
        graph.add_node("inline_done", _lensnode_inline_done)
        graph.add_edge("dispatch", "inline_done")
        graph.add_edge("inline_done", END)
    return graph.compile()


def execute_answer_run(run, dispatch=True):
    """Execute a Lens answer run through LensNode dispatch flow."""

    assistant = run.session.assistant
    max_concurrency = assistant.max_concurrency
    if max_concurrency > 0:
        active_count = (
            Run.objects.filter(
                session__assistant=assistant,
                status__in=[Run.Status.RUNNING, Run.Status.STREAMING],
            )
            .exclude(uuid=run.uuid)
            .count()
        )
        if active_count >= max_concurrency:
            from .tasks import execute_answer_run as _task
            _task.apply_async(args=[str(run.uuid)], countdown=3)
            return run

    try:
        run.status = Run.Status.RUNNING
        run.started_at = run.started_at or timezone.now()
        run.save(update_fields=["status", "started_at", "updated_at"])

        graph = _build_execution_graph(dispatch)
        graph.invoke({"run": run})
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
