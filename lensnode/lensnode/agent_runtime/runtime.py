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
from langchain_core.messages import HumanMessage

from ..agent_tools import (
    SELF_REPORTING_TOOLS,
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
from .summarization import (
    CONTINUATION_SUMMARY_PROMPT,
    LensSummarizationMiddleware,
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


class EmptyAgentResponseError(RuntimeError):
    """The agent and its one recovery attempt both returned no text."""

    code = "EMPTY_AGENT_RESPONSE"




SCENARIOS = {
    "knowledge_qa": {
        "title": "Knowledge Q&A",
        "prompt": (
            "You are a knowledge-base Q&A assistant. Your ONLY source of "
            "truth is the workspace files. Obey these rules without "
            "exception:\n\n"
            "RULE 1 — SEARCH BEFORE ANSWERING\n"
            "Always use tools to locate evidence before writing any answer. "
            "Never answer from memory.\n\n"
            "RULE 2 — CITE EVERY FACT\n"
            "Every factual claim must name the file it came from. A claim "
            "with no file citation is not allowed.\n\n"
            "RULE 3 — NO INFERENCE BEYOND WHAT IS WRITTEN\n"
            "A fact exists only if it is explicitly written in the workspace. "
            "Finding an entity (company, person, product, domain) does NOT "
            "license you to state any of its attributes unless those "
            "attributes are also explicitly written. Example: a file "
            "containing 'example.com' does not tell you the company's legal "
            "name, address, or registration — those are absent even if you "
            "know them from training.\n\n"
            "RULE 4 — HANDLE NOT-FOUND HONESTLY\n"
            "When the workspace lacks the requested information, say exactly: "
            "'I could not find this information in the current workspace.' "
            "State what you searched. Do not guess, estimate, or fill gaps "
            "with general knowledge.\n\n"
            "RULE 5 — BRIDGE TERMINOLOGY\n"
            "If the question uses a typo, synonym, or related term, map it "
            "to the workspace's own wording, note the mapping briefly "
            "(\"you likely mean …\"), then answer from evidence. Do not "
            "refuse over a surface wording mismatch when related evidence "
            "exists.\n\n"
            "RULE 6 — DECLINE OFF-TOPIC QUESTIONS\n"
            "For questions the workspace has no coverage of (general "
            "knowledge, news, geography, cooking, etc.), decline clearly "
            "and suggest the user contact the support team directly."
        ),
    },
    "code_analysis": {
        "title": "Code Analysis",
        "prompt": (
            "You analyze implementation logic, module responsibilities, "
            "important files, data flow, API flow, and call paths. Use code "
            "search and file-reading tools before drawing conclusions."
        ),
    },
}


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
    """Build context-compaction middleware, or None when disabled.

    The summary is produced by a non-streaming gateway model so its tokens
    never leak into the user-facing answer stream. A trigger of 0 disables
    compaction (useful for A/B latency comparisons).

    create_deep_agent also wires its own summarization middleware (default
    trigger ~170k tokens for a profile-less model). Keeping this trigger
    well below that ceiling guarantees ours fires first and holds context
    below the built-in's threshold, so the built-in stays dormant and only
    one summarizer ever acts. Do not raise summary_trigger_tokens near 170k.
    """

    trigger_tokens = config.summary_trigger_tokens
    if trigger_tokens <= 0:
        return None
    summary_model = LensGatewayChatModel(
        model_ref=str(model_ref),
        ai_gateway_url=config.ai_gateway_url,
        token=config.token,
        request_timeout_s=config.request_timeout_s,
        tls_skip_verify=getattr(config, "tls_skip_verify", False),
        tls_ca_file=getattr(config, "tls_ca_file", None),
        http_client=http_client,
        cancel_event=cancel_event,
        run_uuid=run_uuid,
        trace_context=trace_context or {},
        emit_observation=emit_observation,
        observation_name="summarization",
    )
    middleware = LensSummarizationMiddleware(
        model=summary_model,
        trigger=("tokens", trigger_tokens),
        keep=("tokens", config.summary_keep_tokens),
        trim_tokens_to_summarize=32000,
        summary_prompt=CONTINUATION_SUMMARY_PROMPT,
    )
    middleware._emit_event = emit_event
    return middleware


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


def _run_agent_with_turn_limit(
    agent,
    messages,
    max_turns,
    model=None,
    thread=None,
    turn_baseline_ai=None,
    event_baseline_ai=None,
    resume_from_checkpoint=False,
    emit_event=None,
    answer_language="English",
    cancel_event=None,
    wrapup_event=None,
    token_budget_wrapup_event=None,
    on_checkpoint_state=None,
    input_checkpoint_seeded=False,
):
    """Stream agent events and stop after max_turns NEW AI turns.

    `messages` may be prefixed with prior conversation turns. Historical
    assistant turns are excluded from both the turn count and event
    emission, so the limit and trace reflect only the current run.

    On resume, ``turn_baseline_ai`` remains the original history count so
    turns already consumed by this Run still count. ``event_baseline_ai``
    suppresses re-emitting model events already present in the checkpoint.

    A subagent ``task`` delegation runs to completion inside a single
    parent-graph step (deepagents calls it via a plain, synchronous
    ``subagent.invoke(...)``), so the turn count can only be checked
    between parent steps — a delegation in flight when the budget is
    reached can overshoot max_turns by however many turns it used
    internally before returning. This is expected, not a bug in the
    count itself; it is the reason a forced wrap-up (see
    _synthesize_wrapup_answer) matters more than counting precisely.

    Returns (answer, truncated, termination_reason). ``truncated`` is true
    when the agent was stopped before it finished naturally, and the reason
    preserves the gate that requested wrap-up.
    """

    last_state = {"messages": messages} if resume_from_checkpoint else None
    truncated = False
    truncation_reason = None
    seen_tool_calls = set()
    seen_model_calls = set()
    plan_state = {"revision": 0}
    baseline_ai = (
        turn_baseline_ai
        if turn_baseline_ai is not None
        else sum(1 for m in messages if m.get("role") == "assistant")
    )
    emitted_baseline_ai = (
        event_baseline_ai
        if event_baseline_ai is not None
        else baseline_ai
    )
    seeded_baseline = False

    if resume_from_checkpoint:
        graph_input = None
    elif input_checkpoint_seeded:
        graph_input = {"messages": []}
    else:
        graph_input = {"messages": messages}
    for state in agent.stream(
        graph_input,
        stream_mode="values",
        config={
            "recursion_limit": 500,
            **(thread or {}),
        },
    ):
        if cancel_event is not None and cancel_event.is_set():
            raise RunCancelledError(
                "Run was cancelled; stopping the agent loop."
            )
        last_state = state
        if on_checkpoint_state is not None:
            on_checkpoint_state()
        current = state.get("messages", [])
        if not seeded_baseline:
            # Seed the historical assistant turns by their (now-assigned)
            # message and tool-call ids so they are never emitted or counted
            # as new turns. Reusing the tool event reducer also restores its
            # plan revision/state without publishing the old events again.
            baseline_messages = []
            ai_count = 0
            for message in current:
                if getattr(message, "type", "") != "ai":
                    continue
                ai_count += 1
                if ai_count <= emitted_baseline_ai:
                    baseline_messages.append(message)
                    seen_model_calls.add(
                        getattr(message, "id", None) or id(message)
                    )
            _emit_new_tool_calls(
                baseline_messages,
                seen_tool_calls,
                lambda _name, _detail: None,
                plan_state=plan_state,
            )
            seeded_baseline = True
        if emit_event is not None:
            _emit_new_model_calls(current, seen_model_calls, emit_event)
            _emit_new_tool_calls(
                current,
                seen_tool_calls,
                emit_event,
                plan_state=plan_state,
            )
        ai_turns = sum(
            1
            for m in current
            if getattr(m, "type", "") == "ai"
        ) - baseline_ai
        if wrapup_event is not None and wrapup_event.is_set():
            truncated = True
            truncation_reason = "soft_deadline"
            if emit_event is not None:
                emit_event("deepagents.agent.soft_deadline", {})
            break
        if (
            token_budget_wrapup_event is not None
            and token_budget_wrapup_event.is_set()
        ):
            truncated = True
            truncation_reason = "token_budget_wrapup"
            if emit_event is not None:
                emit_event("deepagents.agent.token_budget", {})
            break
        if ai_turns >= max_turns:
            truncated = True
            truncation_reason = "turn_limit"
            break

    answer = _extract_final_message(last_state or {})
    force_wrapup = truncation_reason in {
        "soft_deadline",
        "token_budget_wrapup",
    }
    needs_wrapup = force_wrapup or not answer.strip()
    if truncated and model is not None and needs_wrapup:
        # The cutoff landed mid-turn (e.g. right after a tool call, before
        # any answer text), so there is nothing to extract — but the
        # conversation likely still holds real findings from every prior
        # turn. Ask once more, without tools, for a best-effort synthesis
        # instead of discarding all of that work.
        synthesis = _synthesize_wrapup_answer(
            model,
            (last_state or {}).get("messages", []),
            answer_language,
            emit_event,
            reason=truncation_reason or "limit",
        )
        if synthesis:
            answer = synthesis
    if not truncated and not answer.strip() and model is not None:
        answer = _synthesize_wrapup_answer(
            model,
            (last_state or {}).get("messages", []),
            answer_language,
            emit_event,
            reason="empty",
        )
    if not answer.strip():
        raise EmptyAgentResponseError(
            "Agent returned no answer after one recovery attempt."
        )
    if truncated and answer.strip():
        if truncation_reason == "soft_deadline":
            answer += _pick_text(
                "\n\n---\n*即将达到硬截止时间，以上回答由当前已有证据"
                "综合生成，调查可能尚未完全完成。*",
                "\n\n---\n*Approaching the hard deadline, this answer was "
                "synthesized from the evidence already collected and the "
                "investigation may be incomplete.*",
                answer_language,
            )
        else:
            answer += _pick_text(
                "\n\n---\n*已达到当前分析深度上限，本次调查未完全完成。"
                "如需更完整的结果，请调高分析档位后重试。*",
                "\n\n---\n*Reached the current analysis-depth limit before "
                "the investigation fully completed. Raise the analysis "
                "tier for a more complete result.*",
                answer_language,
            )
    termination_reason = truncation_reason
    if termination_reason is None and model is not None:
        model_reason = getattr(model, "stop_reason", None)
        if model_reason in {
            "loop_capped",
            "model_length_capped",
            "safety_terminated",
            "token_budget_wrapup",
            "token_capped",
        }:
            termination_reason = model_reason
    return answer, truncated, termination_reason


def _strip_dangling_tool_call(messages):
    """Drop a trailing AI message with unresolved tool_calls.

    A truncated loop can stop right after the model requested a tool call
    but before the tool result was recorded. Most providers reject a
    follow-up call whose history ends on a tool_calls message with no
    matching tool response, so that dangling turn is dropped before
    asking for a wrap-up answer — every earlier, resolved turn is kept.
    """

    if not messages:
        return messages
    last = messages[-1]
    if getattr(last, "type", "") == "ai" and getattr(
        last, "tool_calls", None
    ):
        return messages[:-1]
    return messages


def _synthesize_wrapup_answer(
    model,
    current,
    answer_language,
    emit_event,
    reason="limit",
):
    """Ask once for a tool-free answer after cutoff or an empty terminal.

    The prompt asks the model to synthesize its best answer from the current
    conversation, so prior work is not discarded. Returns "" if this call
    fails; the caller decides whether existing partial text is sufficient or
    an explicit empty-response error should be raised.

    A RunCancelledError is deliberately NOT caught here: model.invoke()
    checks cancel_event at the top of the gateway call
    (LensGatewayChatModel._check_cancelled), so a cancellation landing in
    the narrow window between the turn-limit loop exiting and this call
    starting must still stop the run, not be swallowed into an empty
    "wrap-up failed" result.
    """

    if reason == "empty":
        instruction = _pick_text(
            "你上一轮没有输出可见答案。不要调用任何工具，请仅基于当前对话"
            "和已取得的结果，直接向用户给出完整答案。",
            "Your previous turn produced no visible answer. Do not call "
            "tools. Based only on the current conversation and collected "
            "results, write the complete answer to the user now.",
            answer_language,
        )
    elif reason == "token_budget_wrapup":
        instruction = _pick_text(
            "你已经达到本次调查的 Token 预算，不能再调用任何工具。请仅基于"
            "当前对话和已取得的结果，直接给出最完整的最终答案；未确认或未覆盖"
            "的部分必须明确说明。不要向用户提及内部 Token 预算或运行控制状态。",
            "You have reached the token budget for this investigation and "
            "cannot call more tools. Based only on the current conversation "
            "and collected results, write the most complete final answer. "
            "Clearly identify anything unconfirmed or not covered. Do not "
            "mention internal token budgets or runtime control state.",
            answer_language,
        )
    elif reason == "execution_failed":
        instruction = _pick_text(
            "能力执行已达到恢复上限，不能再调用任何工具。请仅基于当前"
            "对话和已取得的信息给出简洁回答，并明确说明执行失败及未完成"
            "的部分。",
            "Capability execution reached its recovery limit. Do not call "
            "tools. Give a concise answer from the current conversation and "
            "collected information, and state what failed or remains undone.",
            answer_language,
        )
    else:
        instruction = _pick_text(
            "你已经达到本次分析的步数上限，不能再调用任何工具。请基于目前"
            "为止已经掌握的全部信息，直接给出你能给出的最完整回答。如果"
            "调查还有尚未确认或未覆盖到的部分，请明确说明。",
            "You have reached the step limit for this analysis and cannot "
            "call any more tools. Based on everything you have gathered so "
            "far, write the most complete answer you can now. Clearly note "
            "any part of the investigation you were not able to confirm.",
            answer_language,
        )
    instruction = (
        f"{instruction}\n\n"
        f"{_answer_language_requirement(answer_language)}"
    )
    wrapup_messages = _strip_dangling_tool_call(current) + [
        HumanMessage(content=instruction)
    ]
    if emit_event is not None:
        event = (
            "deepagents.answer.recovery"
            if reason == "empty"
            else "deepagents.agent.wrapup"
        )
        emit_event(event, {})
    try:
        response = model.invoke(
            wrapup_messages,
            runtime_final_synthesis=True,
        )
    except RunCancelledError:
        raise
    except Exception:
        LOGGER.exception("Wrap-up synthesis call failed after truncation")
        return ""
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content.strip()
    return str(content or "").strip()


def _model_summary(message, limit=160):
    """Return a short preview of a model turn for the trace.

    Prefers the assistant's own text; when the turn only issued tool
    calls (no text), shows the tools it decided to call instead.
    """

    content = getattr(message, "content", "")
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
            else:
                parts.append(str(block))
        content = " ".join(parts)
    text = " ".join(str(content or "").split())
    if text:
        return text[:limit] + ("…" if len(text) > limit else "")
    calls = [
        call.get("name")
        for call in (getattr(message, "tool_calls", None) or [])
        if call.get("name")
    ]
    if calls:
        ordered, counts = [], {}
        for name in calls:
            if name not in counts:
                ordered.append(name)
            counts[name] = counts.get(name, 0) + 1
        parts = [
            f"{name}×{counts[name]}" if counts[name] > 1 else name
            for name in ordered
        ]
        return "→ " + ", ".join(parts)
    return ""


def _emit_new_model_calls(messages, seen, emit_event):
    """Emit an event for each new AI response (one LLM round).

    Each AI message is one round-trip to the model. The gateway returns
    token usage in the message's response_metadata, so surfacing these
    makes every LLM call visible in the trace and attributes token usage
    to the run. Dedup keys on the stable message id rather than position,
    so summarization (which rewrites the message list) cannot make a new
    final turn collide with an already-seen positional index.
    """

    for message in messages:
        if getattr(message, "type", "") != "ai":
            continue
        key = getattr(message, "id", None) or id(message)
        if key in seen:
            continue
        seen.add(key)
        meta = getattr(message, "response_metadata", None) or {}
        usage = meta.get("usage") or {}
        emit_event(
            "llm.response",
            {
                "round": len(seen),
                "model": usage.get("model"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "cached_tokens": (
                    usage.get("cached_tokens")
                    or usage.get("prompt_cache_hit_tokens")
                    or 0
                ),
                "reasoning_tokens": usage.get("reasoning_tokens") or 0,
                "cost": usage.get("cost"),
                "latency_ms": meta.get("latency_ms"),
                "finish_reason": meta.get("finish_reason"),
                "stop_reason": _response_stop_reason(meta),
                "run_token_usage": meta.get("run_token_usage"),
                "summary": _model_summary(message),
            },
        )


def _response_stop_reason(metadata):
    """Return the normalized runtime stop reason for one model response."""

    for key, reason in (
        ("token_capped", "token_capped"),
        ("loop_capped", "loop_capped"),
        ("safety_terminated", "safety_terminated"),
        ("model_length_capped", "model_length_capped"),
    ):
        if metadata.get(key):
            return reason
    return None


def _emit_new_tool_calls(
    messages,
    seen,
    emit_event,
    *,
    plan_state=None,
):
    """Emit a progress event for each not-yet-seen agent tool call.

    The built-in workspace tools emit their own start/done events, but
    the Deep Agent loop also calls model-driven tools (write_file, ls,
    task delegation, MCP tools) that are otherwise invisible. Surfacing
    every tool call here lets the frontend show real progress instead of
    a frozen status during long turns.
    """

    for message in messages:
        if getattr(message, "type", "") != "ai":
            continue
        for call in getattr(message, "tool_calls", None) or []:
            call_id = call.get("id") or ""
            if not call_id or call_id in seen:
                continue
            seen.add(call_id)
            name = call.get("name") or "tool"
            if name == "write_todos":
                state = plan_state if plan_state is not None else {
                    "revision": 0
                }
                state["revision"] = int(state.get("revision") or 0) + 1
                todos = (call.get("args") or {}).get("todos") or []
                incoming_steps = _normalize_plan_steps(todos)
                initial_steps = state.get("steps") or []
                if initial_steps:
                    incoming_by_id = {
                        item["id"]: item for item in incoming_steps
                    }
                    steps = [
                        {
                            **item,
                            "status": incoming_by_id.get(
                                item["id"], item
                            )["status"],
                        }
                        for item in initial_steps
                    ]
                else:
                    steps = incoming_steps
                state["steps"] = steps
                emit_event(
                    "workflow.plan.updated",
                    {
                        "event_type": "plan.updated",
                        "visibility": "user",
                        "payload": {
                            "revision": state["revision"],
                            "steps": steps,
                        },
                    },
                )
                if (
                    todos
                    and all(
                        item.get("status") == "completed" for item in todos
                    )
                    and not state.get("answering_phase_emitted")
                ):
                    state["answering_phase_emitted"] = True
                    state["execution_phase_emitted"] = True
                    emit_event(
                        "workflow.phase.changed",
                        {
                            "event_type": "phase.changed",
                            "visibility": "user",
                            "payload": {"phase": "answering"},
                        },
                    )
                continue
            if (
                plan_state is not None
                and not plan_state.get("execution_phase_emitted")
            ):
                plan_state["execution_phase_emitted"] = True
                emit_event(
                    "workflow.phase.changed",
                    {
                        "event_type": "phase.changed",
                        "visibility": "user",
                        "payload": {"phase": "executing"},
                    },
                )
            if name in SELF_REPORTING_TOOLS:
                # avoids a duplicate trace line; the tool emits its own
                # .start/.done with a richer argument summary
                continue
            emit_event(
                f"tool.{name}.invoke",
                {"tool": name, "summary": _tool_call_summary(call)},
            )
