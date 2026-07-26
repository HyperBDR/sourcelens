import asyncio
import logging
import threading

from .agent_runtime import LensDeepAgentRuntime
from .logging_utils import elapsed_since, format_duration, task_log, utc_now

LOGGER = logging.getLogger("lensnode")

# How often the inactivity watchdog checks for stalled output.
WATCHDOG_INTERVAL_S = 5


def _wrapup_grace_seconds(timeout_s):
    """Reserve bounded time for a tool-free answer before hard timeout."""

    return min(60.0, max(5.0, timeout_s * 0.2), timeout_s * 0.5)


class RunStalledError(TimeoutError):
    """No transport activity at all for the whole idle window.

    The gateway heartbeats every few seconds while a model call is in
    flight, so tripping this means the pipe to the gateway is dead or
    the agent is wedged between calls — distinct from MODEL_TIMEOUT,
    which the gateway reports when the provider itself times out.
    """

    code = "NO_ACTIVITY_TIMEOUT"


class RunDeadlineExceededError(TimeoutError):
    """The run exceeded its configured total wall-clock duration."""

    code = "RUN_TIMEOUT"


def _failure_error_code(exc):
    """Map a run failure to a stable, user-facing error code.

    Timeouts (the inactivity watchdog, the gateway httpx read timeout, or
    a litellm timeout after its retries) all collapse to MODEL_TIMEOUT so
    the UI can explain that the model was too slow rather than showing a
    raw exception. Other failures keep their message for debugging.
    """

    code = getattr(exc, "code", "")
    if code:
        return str(code)
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in name or "timeout" in message:
        return "MODEL_TIMEOUT"
    stream_error_markers = [
        "chunked",
        "incomplete",
        "peer closed",
        "remote protocol",
        "connection reset",
        "connection closed",
    ]
    if any(marker in name or marker in message for marker in stream_error_markers):
        return "MODEL_STREAM_ERROR"
    return str(exc)


def _execution_step_type(command):
    """Return the run step type for progress events."""

    if command.get("task") == "general_chat":
        return "general_chat"
    return "retrieval"


TASKS = [
    {
        "name": "knowledge_qa",
        "title": "Knowledge Q&A",
        "description": (
            "Answer questions over selected documents and code workspaces "
            "using read-only search and evidence reading."
        ),
        "recommended_questions": [
            "What does this project do?",
            "Where is this feature documented or implemented?",
            "What does this configuration mean?",
        ],
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "target_dirs": {"type": "array"},
            },
            "required": ["question", "target_dirs"],
        },
    },
    {
        "name": "code_analysis",
        "title": "Code Analysis",
        "description": (
            "Analyze implementation logic, module responsibilities, "
            "important files, and code flows in selected workspaces."
        ),
        "recommended_questions": [
            "How is the login flow implemented?",
            "Which files implement the billing feature?",
            "What is the call path for this API?",
        ],
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "target_dirs": {"type": "array"},
            },
            "required": ["question", "target_dirs"],
        },
    },
    {
        "name": "general_chat",
        "title": "General Chat",
        "description": (
            "Chat and complete tasks with bound Skills and bundled scripts "
            "without searching workspace directories."
        ),
        "recommended_questions": [
            "Use the available capabilities to complete this task.",
            "Follow the configured workflow for this request.",
            "Help me complete this request without workspace retrieval.",
        ],
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
            },
            "required": ["question"],
        },
    },
]


class LensNodeExecutor:
    """Translate LensNode protocol commands into Deep Agents execution."""

    def __init__(self, config):
        self.agent = LensDeepAgentRuntime(config)

    async def execute(self, command, emit):
        """Execute one run_start command and emit protocol frames."""

        started_at = utc_now()
        run_uuid = command["run_uuid"]
        task = command.get("task") or "unknown"
        step_type = _execution_step_type(command)
        target_dirs = command.get("target_dirs") or []
        timeout_s = getattr(self.agent.config, "request_timeout_s", 120)
        idle_timeout_s = getattr(
            self.agent.config, "run_idle_timeout_s", 180
        )
        target_dir_names = ", ".join(
            item.get("path", "") for item in target_dirs
        ) or "none"
        start_message = task_log(
            (
                f"Starting to run command: {task}({run_uuid}). "
                f"Request timeout {format_duration(timeout_s)}, "
                f"idle timeout {format_duration(idle_timeout_s)}."
            ),
            started_at,
            [
                f"Task: {task}",
                f"TargetDirs: {target_dir_names}",
                f"AgentModelRef: {command.get('agent_model_ref') or 'none'}",
            ],
        )
        LOGGER.info(start_message)
        emit(
            {
                "type": "run_event",
                "run_uuid": run_uuid,
                "step_type": step_type,
                "status": "running",
                "detail": {
                    "message": start_message,
                    "task": task,
                    "target_dirs": target_dirs,
                    "request_timeout_s": timeout_s,
                    "idle_timeout_s": idle_timeout_s,
                },
            }
        )

        try:
            progress_message = task_log(
                (
                    f"Running command {task}({run_uuid}). Current status is "
                    "running Deep Agents. Elapsed time so far: "
                    f"{elapsed_since(started_at)}. Remaining Timeout: "
                    f"{format_duration(timeout_s)}."
                )
            )
            LOGGER.info(progress_message)
            emit(
                {
                    "type": "run_event",
                    "run_uuid": run_uuid,
                    "step_type": step_type,
                    "status": "running",
                    "detail": {
                        "message": progress_message,
                    },
                }
            )

            loop = asyncio.get_running_loop()
            activity = {"at": loop.time()}
            deadline_at = loop.time() + timeout_s
            wrapup_at = deadline_at - _wrapup_grace_seconds(timeout_s)
            cancel_event = threading.Event()
            wrapup_event = threading.Event()

            def touch_activity():
                activity["at"] = loop.time()

            def emit_progress(message, extra_detail=None):
                if cancel_event.is_set():
                    return
                touch_activity()
                detail = {
                    "message": message,
                }
                if extra_detail:
                    detail.update(extra_detail)
                emit(
                    {
                        "type": "run_event",
                        "run_uuid": run_uuid,
                        "step_type": step_type,
                        "status": "running",
                        "detail": detail,
                    }
                )

            def emit_output(content, reset=False):
                if cancel_event.is_set():
                    return
                touch_activity()
                emit(
                    {
                        "type": "run_output",
                        "run_uuid": run_uuid,
                        "content_delta": content,
                        "reset": reset,
                    }
                )

            # Inactivity watchdog on TRANSPORT activity, not user-visible
            # output: any gateway SSE event (heartbeats, reasoning and
            # tool-call tokens) refreshes the clock via on_activity, so a
            # silent long model call never trips it. Provider stalls are
            # the gateway's call to make (litellm read timeout -> error
            # event); this watchdog only fires when the pipe itself dies.
            # Cancelling the asyncio task cannot stop the agent worker
            # thread, so cancel_event tells the thread to unwind at its
            # next chunk or model-call boundary and mutes its late emits.
            answer_task = asyncio.create_task(
                self.agent.answer(
                    command,
                    emit_progress=emit_progress,
                    emit_output=emit_output,
                    on_activity=touch_activity,
                    cancel_event=cancel_event,
                    wrapup_event=wrapup_event,
                )
            )

            async def cancel_answer_task():
                """Stop the coroutine and signal its worker thread."""

                cancel_event.set()
                answer_task.cancel()
                try:
                    await answer_task
                except (asyncio.CancelledError, Exception):
                    pass

            try:
                while True:
                    remaining_s = deadline_at - loop.time()
                    if remaining_s <= 0:
                        await cancel_answer_task()
                        raise RunDeadlineExceededError(
                            "Run exceeded total request timeout of "
                            f"{format_duration(timeout_s)}."
                        )
                    if not wrapup_event.is_set() and loop.time() >= wrapup_at:
                        wrapup_event.set()
                        emit_progress(
                            task_log(
                                "Soft deadline reached; requesting a "
                                "best-effort final answer."
                            ),
                            {
                                "agent_event": (
                                    "deepagents.agent.soft_deadline.requested"
                                ),
                                "remaining_s": max(0, int(remaining_s)),
                            },
                        )
                    wait_timeout_s = min(
                        WATCHDOG_INTERVAL_S,
                        remaining_s,
                    )
                    if not wrapup_event.is_set():
                        wait_timeout_s = min(
                            wait_timeout_s,
                            max(0, wrapup_at - loop.time()),
                        )
                    done, _ = await asyncio.wait(
                        {answer_task},
                        timeout=wait_timeout_s,
                    )
                    if answer_task in done:
                        result = answer_task.result()
                        break
                    if loop.time() >= deadline_at:
                        await cancel_answer_task()
                        raise RunDeadlineExceededError(
                            "Run exceeded total request timeout of "
                            f"{format_duration(timeout_s)}."
                        )
                    if loop.time() - activity["at"] > idle_timeout_s:
                        await cancel_answer_task()
                        raise RunStalledError(
                            "Run saw no gateway activity for "
                            f"{format_duration(idle_timeout_s)}; aborting."
                        )
            except asyncio.CancelledError:
                # run_cancel cancels this coroutine, which does not cancel
                # answer_task or its worker thread on its own. Signal both
                # so the agent stops issuing model calls for a dead run.
                cancel_event.set()
                answer_task.cancel()
                raise
            samples = result.get("samples") or []
            sample_paths = [item["path"] for item in samples]
            retrieval_done_message = task_log(
                (
                    "Finish running Deep Agents for "
                    f"{task}({run_uuid}). "
                    f"Actual duration: {elapsed_since(started_at)}."
                ),
                details=[
                    f"SampleCount: {len(samples)}",
                    f"SamplePaths: {', '.join(sample_paths) or 'none'}",
                ],
            )
            LOGGER.info(retrieval_done_message)
            emit(
                {
                    "type": "run_event",
                    "run_uuid": run_uuid,
                    "step_type": step_type,
                    "status": "done",
                    "detail": {
                        "message": retrieval_done_message,
                        "sample_count": len(samples),
                        "sample_paths": sample_paths,
                        "stop_reason": result.get("stop_reason"),
                        "token_usage": result.get("token_usage") or {},
                    },
                }
            )
            emit(
                {
                    "type": "run_output",
                    "run_uuid": run_uuid,
                    "final_content": result["answer"],
                }
            )
            done_message = task_log(
                (
                    f"Finish running command {task}({run_uuid}). Actual "
                    f"duration: {elapsed_since(started_at)}."
                )
            )
            LOGGER.info(done_message)
            emit(
                {
                    "type": "run_done",
                    "run_uuid": run_uuid,
                    "status": "done",
                    "detail": {
                        "message": done_message,
                    },
                }
            )
        except Exception as exc:
            error_code = _failure_error_code(exc)
            failed_message = task_log(
                (
                    f"Failed running command {task}({run_uuid}). Actual "
                    f"duration: {elapsed_since(started_at)}."
                ),
                details=[
                    f"ErrorType: {type(exc).__name__}",
                    f"Error: {exc}",
                ],
            )
            LOGGER.error(failed_message)
            emit(
                {
                    "type": "run_event",
                    "run_uuid": run_uuid,
                    "step_type": step_type,
                    "status": "failed",
                    "detail": {
                        "message": failed_message,
                        "error": error_code,
                        "exception": str(exc),
                    },
                }
            )
            emit(
                {
                    "type": "run_done",
                    "run_uuid": run_uuid,
                    "status": "failed",
                    "error": error_code,
                    "detail": {
                        "message": failed_message,
                    },
                }
            )
