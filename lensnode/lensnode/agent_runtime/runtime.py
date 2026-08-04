import asyncio
import json
import logging
import re
import threading

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends.filesystem import FilesystemBackend
from ..agent_tools import (
    build_agent_tools,
    build_general_chat_tools,
)
from ..checkpoint import (
    checkpoint_enabled,
    get_checkpoint_saver,
    load_resume_state,
    save_initial_checkpoint,
    save_resume_metadata,
    save_runtime_state,
    thread_config,
)
from ..gateway_model import (
    LensGatewayChatModel,
    RunCancelledError,
)
from ..logging_utils import elapsed_since, task_log, utc_now
from ..mcp_tools import build_deferred_mcp_tools, load_mcp_tools
from ..runtime_modes import runtime_mode_for
from .assembly import _agent_middleware, _fast_subagent
from .capabilities import CapabilityBoundaryMiddleware
from .direct_answer import (
    _answer_general_chat_directly,
    _contains_unfulfilled_action_promise,
)
from .execution import (
    EmptyAgentResponseError,
    _emit_new_model_calls,
    _emit_new_tool_calls,
    _model_summary,
    _response_stop_reason,
    _run_agent_with_turn_limit,
    _strip_dangling_tool_call,
    _synthesize_wrapup_answer,
)
from .limits import resolve_token_budget as _resolve_token_budget
from .messages import (
    activity_from_event as _activity_from_event,
    build_initial_messages as _build_initial_messages,
    detail_lines as _detail_lines,
    extract_final_message as _extract_final_message,
    normalize_plan_steps as _normalize_plan_steps,
    tool_call_summary as _tool_call_summary,
)
from .offload import apply_offload_thresholds as _apply_offload_thresholds
from .outcomes import (
    _capability_termination_detail,
    _evidence_termination_detail,
    _finalize_runtime_outcome,
    _unverified_execution_answer,
)
from .prompts import (
    answer_language_requirement as _answer_language_requirement,
    command_answer_language as _command_answer_language,
    detect_answer_language as _detect_answer_language,
    pick_text as _pick_text,
)
from .resume import (
    pending_checkpoint_tool_calls as _pending_checkpoint_tool_calls,
    reject_unsafe_resume_tool_replay as _reject_unsafe_resume_tool_replay,
)
from .restrictions import NoTaskMiddleware as _NoTaskMiddleware
from .routing import (
    _normalize_route_evidence_capabilities,
    _parse_route_decision,
    _select_general_chat_route,
)
from .scenarios import SCENARIOS
from .summarization import (
    CONTINUATION_SUMMARY_PROMPT,
    LensSummarizationMiddleware,
    build_summarization_middleware as _build_summarization_middleware_impl,
)
from .system_prompts import (
    _context_guidance,
    _general_chat_guidance,
    _general_chat_system_prompt,
    _is_general_chat,
    _knowledge_system_prompt,
    _subagent_guidance,
    _system_prompt,
)
from .tracing import (
    TraceObservationMiddleware,
    observation_timestamp as _observation_timestamp,
)
from ..runtime_resources import (
    cleanup_runtime_resources,
    prepare_runtime_resources,
)

LOGGER = logging.getLogger("lensnode")

register_harness_profile(
    "lensgatewaychatmodel",
    HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(
            enabled=False,
        ),
    ),
)








def _build_summarization_middleware(
    config,
    model_ref,
    emit_event,
    cancel_event=None,
    run_uuid="",
    http_client=None,
    trace_context=None,
    emit_observation=None,
):
    """Build summarization while preserving facade monkeypatches."""

    return _build_summarization_middleware_impl(
        config,
        model_ref,
        emit_event,
        cancel_event,
        run_uuid,
        http_client,
        trace_context,
        emit_observation,
        model_class=LensGatewayChatModel,
        middleware_class=LensSummarizationMiddleware,
    )


class LensDeepAgentRuntime:
    """Run a real LangChain Deep Agents execution for one LensNode command."""

    def __init__(self, config, http_client=None):
        self.config = config
        self.http_client = http_client

    async def answer(
        self,
        command,
        emit_progress=None,
        emit_output=None,
        on_activity=None,
        cancel_event=None,
        wrapup_event=None,
        on_checkpoint_ready=None,
    ):
        """Execute a run_start command with create_deep_agent."""

        return await asyncio.to_thread(
            self._answer_sync,
            command,
            emit_progress,
            emit_output,
            on_activity,
            cancel_event,
            wrapup_event,
            on_checkpoint_ready,
        )

    def _answer_sync(
        self,
        command,
        emit_progress=None,
        emit_output=None,
        on_activity=None,
        cancel_event=None,
        wrapup_event=None,
        on_checkpoint_ready=None,
    ):
        """Synchronous Deep Agents invocation run in a worker thread."""

        started_at = utc_now()
        question = command.get("question", "")
        run_uuid = str(command.get("run_uuid") or "")
        resume_state = None
        if command.get("resume"):
            resume_state = load_resume_state(
                run_uuid,
                self.config.workspace_path,
            )
        scenario = _scenario_for_task(command.get("task"))
        runtime_mode = runtime_mode_for(command)
        model_ref = command.get("agent_model_ref")
        if not model_ref:
            raise ValueError("agent_model_ref is required for Deep Agents")
        trace_context = command.get("trace_context")
        if not isinstance(trace_context, dict):
            trace_context = {}
        root_observation_id = trace_context.get("root_observation_id")
        if not isinstance(root_observation_id, str) or not re.fullmatch(
            r"[0-9a-f]{32}",
            root_observation_id,
        ):
            trace_context = {}
            root_observation_id = None

        def emit_agent_event(event, detail=None):
            detail = runtime_mode.decorate_event(detail)
            message = task_log(event, details=_detail_lines(detail))
            LOGGER.info(message)
            if emit_progress is not None:
                emit_progress(
                    message,
                    {
                        "agent_event": event,
                        "activity": _activity_from_event(event),
                        **detail,
                    },
                )

        def emit_user_event(event_type, payload):
            emit_agent_event(
                f"workflow.{event_type}",
                {
                    "event_type": event_type,
                    "visibility": "user",
                    "payload": payload,
                },
            )

        def emit_trace_observation(observation):
            if emit_progress is not None:
                emit_progress(
                    task_log("trace.observation"),
                    {"observation": observation},
                )

        emit_agent_event(
            "deepagents.runtime.start",
            {
                "scenario": scenario["title"],
                "question_chars": len(question),
                "target_dirs": len(command.get("target_dirs") or []),
                "history_turns": len(command.get("history") or []),
            },
        )
        _apply_offload_thresholds(self.config)
        emit_agent_event(
            "deepagents.offload.configured",
            {
                "tool_tokens": self.config.offload_tool_tokens,
                "human_tokens": self.config.offload_human_tokens,
            },
        )
        if runtime_mode.general_chat:
            emit_user_event("phase.changed", {"phase": "analyzing"})
        resources = prepare_runtime_resources(
            self.config,
            command,
            emit_event=emit_agent_event,
            cancel_event=cancel_event,
            on_activity=on_activity,
        )
        try:
            initial_messages = _build_initial_messages(
                command.get("history"),
                question,
            )
            history_assistant_turns = sum(
                1
                for item in command.get("history") or []
                if item.get("role") == "assistant"
            )
            runtime_evidence = dict(
                resume_state.runtime_evidence if resume_state else {}
            )
            capability_middleware = None
            checkpoint_ready = resume_state is not None
            initial_checkpoint_seeded = False
            resume_from_graph_checkpoint = resume_state is not None
            checkpoint_ready_notified = False

            def notify_checkpoint_ready():
                nonlocal checkpoint_ready_notified
                if checkpoint_ready_notified or on_checkpoint_ready is None:
                    return
                on_checkpoint_ready()
                checkpoint_ready_notified = True

            if checkpoint_ready:
                notify_checkpoint_ready()
            if (
                runtime_mode.execution_gates
                and resume_state is not None
                and resume_state.checkpoint_step < 0
            ):
                initial_checkpoint_seeded = True
                resume_from_graph_checkpoint = False

            def persist_execution_state(
                capability_state=None,
                guardrail_state=None,
            ):
                if not checkpoint_ready:
                    return
                if capability_state is None and capability_middleware:
                    capability_state = capability_middleware.export_state()
                save_runtime_state(
                    run_uuid,
                    self.config.workspace_path,
                    capability_state=capability_state or {},
                    runtime_evidence=runtime_evidence,
                    guardrail_state=(
                        guardrail_state
                        if guardrail_state is not None
                        else model.export_runtime_state()
                    ),
                )
            token_budget = _resolve_token_budget(self.config, command)
            token_budget_wrapup_event = (
                threading.Event() if runtime_mode.execution_gates else None
            )
            model = LensGatewayChatModel(
                model_ref=str(model_ref),
                ai_gateway_url=self.config.ai_gateway_url,
                token=self.config.token,
                request_timeout_s=self.config.request_timeout_s,
                tls_skip_verify=getattr(
                    self.config, "tls_skip_verify", False
                ),
                tls_ca_file=getattr(self.config, "tls_ca_file", None),
                http_client=self.http_client,
                emit_output=emit_output,
                on_activity=on_activity,
                cancel_event=cancel_event,
                run_uuid=run_uuid,
                trace_context=trace_context,
                emit_observation=emit_trace_observation,
                observation_name="agent",
                general_chat_execution_gates=runtime_mode.execution_gates,
                token_budget_max_tokens=token_budget["max_tokens"],
                token_budget_final_reserve_tokens=token_budget[
                    "final_reserve_tokens"
                ],
                token_budget_warn_ratio=getattr(
                    self.config,
                    "token_budget_warn_ratio",
                    0.8,
                ),
                token_budget_wrapup_event=token_budget_wrapup_event,
                on_runtime_state_change=lambda state: (
                    persist_execution_state(guardrail_state=state)
                ),
            )
            if resume_state is not None:
                model.restore_runtime_state(
                    resume_state.messages,
                    resume_state.guardrail_state,
                )
            if runtime_mode.general_chat:
                tools = build_general_chat_tools(
                    command,
                    resources,
                    self.config,
                    emit_event=emit_agent_event,
                    runtime_evidence=runtime_evidence,
                    on_runtime_evidence=lambda _state: (
                        persist_execution_state()
                    ),
                )
            else:
                tools = build_agent_tools(
                    command,
                    resources,
                    self.config,
                    emit_event=emit_agent_event,
                )
            mcp_tools = load_mcp_tools(
                resources.mcp_configs,
                discovery_timeout_s=getattr(
                    self.config,
                    "mcp_discovery_timeout_s",
                    30,
                ),
                tool_timeout_s=getattr(
                    self.config,
                    "mcp_tool_timeout_s",
                    60,
                ),
                emit_event=emit_agent_event,
            )
            registered_mcp_tools, mcp_middleware = (
                build_deferred_mcp_tools(
                    mcp_tools,
                    threshold=getattr(
                        self.config,
                        "mcp_defer_threshold",
                        12,
                    ),
                )
            )
            tools.extend(registered_mcp_tools)
            if resume_state is not None:
                _reject_unsafe_resume_tool_replay(
                    resume_state.messages,
                    [*tools, *mcp_tools],
                    resume_state.pending_write_tool_call_ids,
                )
            evidence_requirement = "none"
            required_capabilities = []
            if runtime_mode.execution_gates:
                route_was_resumed = bool(
                    resume_state is not None
                    and resume_state.route_decision.get("route")
                )
                if route_was_resumed:
                    route_decision = resume_state.route_decision
                else:
                    if resume_state is None and checkpoint_enabled():
                        try:
                            get_checkpoint_saver(
                                self.config.workspace_path
                            )
                            save_resume_metadata(
                                run_uuid,
                                self.config.workspace_path,
                                history_assistant_turns=(
                                    history_assistant_turns
                                ),
                            )
                            save_initial_checkpoint(
                                run_uuid,
                                self.config.workspace_path,
                                initial_messages,
                            )
                            checkpoint_ready = True
                            initial_checkpoint_seeded = True
                            notify_checkpoint_ready()
                        except Exception:
                            LOGGER.exception(
                                "Failed to enable route checkpoint"
                            )
                    route_decision = _select_general_chat_route(
                        model,
                        question,
                        history=command.get("history"),
                        history_artifacts=command.get(
                            "history_artifact_paths"
                        ),
                        context_skill_contents=(
                            resources.context_skill_contents
                        ),
                        available_tools=[*tools, *mcp_tools],
                        has_bound_skills=bool(resources.skill_paths),
                    )
                    if checkpoint_ready:
                        save_resume_metadata(
                            run_uuid,
                            self.config.workspace_path,
                            route_decision=route_decision,
                            history_assistant_turns=history_assistant_turns,
                        )
                        persist_execution_state()
                command = {
                    **command,
                    "runtime_route": route_decision["route"],
                }
                emit_user_event(
                    (
                        "route.resumed"
                        if route_was_resumed
                        else "route.selected"
                    ),
                    route_decision,
                )
                evidence_requirement = route_decision[
                    "evidence_requirement"
                ]
                required_capabilities = route_decision[
                    "required_capabilities"
                ]
                if route_decision["route"] == "capability_unavailable":
                    required = route_decision["required_capabilities"]
                    capability = next(
                        (
                            item
                            for item in required
                            if item
                            in {
                                "artifact_delivery",
                                "mcp",
                                "skill",
                                "tool",
                                "workspace",
                            }
                        ),
                        "tool",
                    )
                    termination_detail = _capability_termination_detail(
                        capability
                    )
                    emit_user_event(
                        "capability.blocked",
                        termination_detail,
                    )
                    emit_user_event(
                        "phase.changed",
                        {"phase": "completed"},
                    )
                    return {
                        "answer": _unverified_execution_answer(
                            question,
                            termination_detail,
                            answer_language=_command_answer_language(command),
                        ),
                        "samples": [],
                        "stop_reason": model.stop_reason,
                        "token_usage": model.token_usage,
                        "outcome": "blocked",
                        "termination_detail": termination_detail,
                    }
                if route_decision["route"] == "direct_answer":
                    emit_user_event("phase.changed", {"phase": "answering"})
                    if resume_state is not None and emit_output is not None:
                        emit_output("", reset=True)
                    runtime_mode.emit_model_round(
                        emit_agent_event,
                        "start",
                        1,
                    )
                    try:
                        answer = _answer_general_chat_directly(
                            model,
                            command,
                            _system_prompt(
                                scenario,
                                command,
                                resources.context_skill_contents,
                            ),
                            messages=(
                                resume_state.messages
                                if resume_state is not None
                                else None
                            ),
                            emit_event=emit_agent_event,
                            emit_output=emit_output,
                        )
                    except Exception:
                        runtime_mode.emit_model_round(
                            emit_agent_event,
                            "failed",
                            1,
                        )
                        raise
                    runtime_mode.emit_model_round(
                        emit_agent_event,
                        "done",
                        1,
                    )
                    if not answer.strip():
                        raise EmptyAgentResponseError(
                            "Direct route returned no answer."
                        )
                    emit_user_event(
                        "phase.changed",
                        {"phase": "completed"},
                    )
                    return {
                        "answer": answer,
                        "samples": [],
                        "stop_reason": model.stop_reason,
                        "token_usage": model.token_usage,
                        "outcome": "completed",
                        "termination_detail": {},
                    }
                capability_middleware = CapabilityBoundaryMiddleware(
                    emit_event=emit_agent_event,
                    required_capabilities=required_capabilities,
                    require_initial_plan=(
                        route_decision["route"] == "plan_execute"
                    ),
                    on_state_change=persist_execution_state,
                )
                if resume_state is not None:
                    capability_middleware.restore_state(
                        resume_state.capability_state
                    )
                phase = (
                    "planning"
                    if route_decision["route"] == "plan_execute"
                    else "executing"
                )
                emit_user_event("phase.changed", {"phase": phase})
            trace_middleware = (
                TraceObservationMiddleware(
                    emit_trace_observation,
                    root_observation_id,
                )
                if root_observation_id
                else None
            )
            kwargs = {
                "model": model,
                "tools": tools,
                "system_prompt": _system_prompt(
                    scenario,
                    command,
                    resources.context_skill_contents,
                    mcp_deferred=mcp_middleware is not None,
                ),
                "backend": FilesystemBackend(
                    root_dir=str(resources.root),
                    virtual_mode=True,
                ),
                "subagents": (
                    []
                    if runtime_mode.general_chat
                    else [
                        _fast_subagent(
                            mcp_middleware,
                            trace_middleware,
                        )
                    ]
                ),
                "name": f"lensnode-{command.get('task') or 'agent'}",
            }
            if resources.skill_paths and not runtime_mode.general_chat:
                kwargs["skills"] = resources.skill_paths

            summarizer = _build_summarization_middleware(
                self.config,
                model_ref,
                emit_agent_event,
                cancel_event,
                run_uuid=run_uuid,
                http_client=self.http_client,
                trace_context=trace_context,
                emit_observation=emit_trace_observation,
            )
            middleware = _agent_middleware(
                command,
                summarizer,
                emit_agent_event,
                capability_middleware=capability_middleware,
                mcp_middleware=mcp_middleware,
                trace_middleware=trace_middleware,
            )
            if middleware:
                kwargs["middleware"] = middleware
            if summarizer is not None:
                emit_agent_event(
                    "deepagents.summarization.enabled",
                    {
                        "trigger_tokens": self.config.summary_trigger_tokens,
                        "keep_tokens": self.config.summary_keep_tokens,
                    },
                )

            emit_agent_event(
                "deepagents.agent.create",
                {
                    "tool_count": len(tools),
                    "skill_count": len(resources.skill_paths),
                    "mcp_tool_count": len(mcp_tools),
                    "mcp_deferred": mcp_middleware is not None,
                    "task_tool_enabled": not runtime_mode.general_chat,
                    "mcp_config_path": str(resources.mcp_config_path),
                },
            )
            checkpoint_thread = thread_config(run_uuid)
            if checkpoint_enabled():
                if resume_state is not None:
                    kwargs["checkpointer"] = get_checkpoint_saver(
                        self.config.workspace_path
                    )
                    checkpoint_ready = True
                elif checkpoint_ready:
                    kwargs["checkpointer"] = get_checkpoint_saver(
                        self.config.workspace_path
                    )
                else:
                    try:
                        kwargs["checkpointer"] = get_checkpoint_saver(
                            self.config.workspace_path
                        )
                        save_resume_metadata(
                            run_uuid,
                            self.config.workspace_path,
                            route_decision=(
                                route_decision
                                if runtime_mode.execution_gates
                                else {}
                            ),
                            history_assistant_turns=(
                                history_assistant_turns
                            ),
                        )
                        save_initial_checkpoint(
                            run_uuid,
                            self.config.workspace_path,
                            initial_messages,
                        )
                        checkpoint_ready = True
                        initial_checkpoint_seeded = True
                        notify_checkpoint_ready()
                    except Exception:
                        kwargs.pop("checkpointer", None)
                        LOGGER.exception(
                            "Failed to enable agent run checkpoints"
                        )
            agent = create_deep_agent(**kwargs)
            max_turns = command.get("max_agent_turns", 26)
            invoke_detail = {"max_agent_turns": max_turns}
            if runtime_mode.execution_gates:
                invoke_detail.update(
                    {
                        "token_budget_profile": token_budget["profile"],
                        "token_budget_max_tokens": token_budget[
                            "max_tokens"
                        ],
                        "token_budget_final_reserve_tokens": token_budget[
                            "final_reserve_tokens"
                        ],
                    }
                )
            emit_agent_event(
                "deepagents.agent.invoke",
                invoke_detail,
            )
            messages = initial_messages
            turn_baseline_ai = None
            event_baseline_ai = None
            if resume_state is not None:
                if emit_output is not None:
                    emit_output("", reset=True)
                messages = list(resume_state.messages)
                turn_baseline_ai = resume_state.history_assistant_turns
                event_baseline_ai = sum(
                    1
                    for message in resume_state.messages
                    if getattr(message, "type", "") == "ai"
                )
                emit_agent_event(
                    "deepagents.runtime.resume",
                    {
                        "checkpoint_ai_turns": event_baseline_ai,
                        "history_ai_turns": turn_baseline_ai,
                    },
                )
            (
                answer,
                truncated,
                termination_reason,
            ) = _run_agent_with_turn_limit(
                agent,
                messages,
                max_turns,
                model=model,
                thread=checkpoint_thread,
                turn_baseline_ai=turn_baseline_ai,
                event_baseline_ai=event_baseline_ai,
                resume_from_checkpoint=resume_from_graph_checkpoint,
                emit_event=emit_agent_event,
                answer_language=_command_answer_language(command),
                cancel_event=cancel_event,
                wrapup_event=(
                    wrapup_event if runtime_mode.execution_gates else None
                ),
                token_budget_wrapup_event=token_budget_wrapup_event,
                on_checkpoint_state=(
                    persist_execution_state if checkpoint_ready else None
                ),
                input_checkpoint_seeded=initial_checkpoint_seeded,
            )
            if truncated:
                emit_agent_event(
                    "deepagents.agent.truncated",
                    {"max_agent_turns": max_turns},
                )
            emit_agent_event(
                "deepagents.runtime.done",
                {
                    "actual_duration": elapsed_since(started_at),
                    "answer_chars": len(answer),
                    "stop_reason": model.stop_reason,
                    "termination_reason": termination_reason,
                    "token_usage": model.token_usage,
                },
            )
            outcome, termination_detail = _finalize_runtime_outcome(
                capability_middleware=capability_middleware,
                evidence_requirement=evidence_requirement,
                required_capabilities=required_capabilities,
                truncated=truncated or bool(termination_reason),
                stop_reason=termination_reason or model.stop_reason,
                execution_gate_enabled=runtime_mode.execution_gates,
                runtime_evidence=runtime_evidence,
            )
            if capability_middleware is not None:
                emit_agent_event(
                    "deepagents.runtime.outcome",
                    {
                        "outcome": outcome,
                        **capability_middleware.failure_diagnostics(
                            required_capabilities,
                            outcome,
                        ),
                    },
                )
            if outcome == "blocked" and capability_middleware is not None:
                reason = termination_detail.get("reason")
                if reason == "execution_failed":
                    emit_user_event(
                        "execution.failed",
                        termination_detail,
                    )
                elif reason == "evidence_unavailable":
                    emit_user_event(
                        "verification.failed",
                        termination_detail,
                    )
                answer = _unverified_execution_answer(
                    question,
                    termination_detail,
                    answer_language=_command_answer_language(command),
                )
            if runtime_mode.general_chat:
                emit_user_event("phase.changed", {"phase": "completed"})
            return {
                "answer": answer,
                "samples": [],
                "stop_reason": model.stop_reason,
                "token_usage": model.token_usage,
                "outcome": outcome,
                "termination_detail": termination_detail,
            }
        finally:
            if cancel_event is None or not cancel_event.is_set():
                cleanup_runtime_resources(resources)
















def _scenario_for_task(task):
    """Return scenario metadata for a LensNode task name."""

    return SCENARIOS.get(task or "", SCENARIOS["knowledge_qa"])
