import asyncio
import logging

from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware.subagents import GENERAL_PURPOSE_SUBAGENT
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import RemoveMessage

from .agent_tools import (
    SELF_REPORTING_TOOLS,
    build_agent_tools,
    build_general_chat_tools,
)
from .gateway_model import LensGatewayChatModel, RunCancelledError
from .logging_utils import elapsed_since, task_log, utc_now
from .runtime_resources import cleanup_runtime_resources
from .runtime_resources import prepare_runtime_resources

LOGGER = logging.getLogger("lensnode")

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


CONTINUATION_SUMMARY_PROMPT = (
    "You are compacting the context of an IN-PROGRESS investigation to "
    "free up space. The user's question has NOT been answered yet — you "
    "are still gathering evidence from the workspace and MUST keep working "
    "after this compaction. The notes below replace the older conversation "
    "history.\n\n"
    "Extract only what you need to continue and ultimately answer the "
    "question. Use these sections, writing 'None' where empty:\n\n"
    "## ORIGINAL QUESTION\n"
    "The user's exact question, verbatim.\n\n"
    "## EVIDENCE GATHERED SO FAR\n"
    "Concrete findings already discovered, with file paths and the key "
    "facts/identifiers/values they contain. Be specific.\n\n"
    "## STILL TO DO\n"
    "What evidence is still missing to fully answer the question.\n\n"
    "Do NOT write a final answer here. Do NOT imply the task is complete "
    "or already answered. This is a working note to yourself so you can "
    "keep investigating, then produce the final answer in a later step.\n\n"
    "<messages>\n{messages}\n</messages>"
)


class LensSummarizationMiddleware(SummarizationMiddleware):
    """Compact older turns once the running context grows past a threshold.

    Deep investigations accumulate large tool outputs (file reads) that
    make every later LLM round re-send a growing transcript, and per-round
    latency scales with that context. Compacting the oldest turns into a
    summary keeps the recent working set verbatim while bounding context,
    cutting tail latency and the risk of context overflow. The workspace
    stays fully re-queryable, so any evidence dropped from the summary can
    simply be searched again.
    """

    def before_model(self, state, runtime):
        """Summarize on threshold and report what was compacted."""

        before_tokens = self.token_counter(state["messages"])
        result = super().before_model(state, runtime)
        emit = getattr(self, "_emit_event", None)
        if result is not None and emit is not None:
            kept = [
                message
                for message in result["messages"]
                if not isinstance(message, RemoveMessage)
            ]
            after_tokens = self.token_counter(kept)
            emit(
                "deepagents.summarization.compacted",
                {
                    "before_tokens": before_tokens,
                    "after_tokens": after_tokens,
                    "saved_tokens": max(before_tokens - after_tokens, 0),
                },
            )
        return result


def _build_summarization_middleware(
    config, model_ref, emit_event, cancel_event=None
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
        cancel_event=cancel_event,
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

    def __init__(self, config):
        self.config = config

    async def answer(
        self,
        command,
        emit_progress=None,
        emit_output=None,
        on_activity=None,
        cancel_event=None,
    ):
        """Execute a run_start command with create_deep_agent."""

        return await asyncio.to_thread(
            self._answer_sync,
            command,
            emit_progress,
            emit_output,
            on_activity,
            cancel_event,
        )

    def _answer_sync(
        self,
        command,
        emit_progress=None,
        emit_output=None,
        on_activity=None,
        cancel_event=None,
    ):
        """Synchronous Deep Agents invocation run in a worker thread."""

        started_at = utc_now()
        question = command.get("question", "")
        scenario = _scenario_for_task(command.get("task"))
        model_ref = command.get("agent_model_ref")
        if not model_ref:
            raise ValueError("agent_model_ref is required for Deep Agents")

        def emit_agent_event(event, detail=None):
            message = task_log(event, details=_detail_lines(detail))
            LOGGER.info(message)
            if emit_progress is not None:
                emit_progress(
                    message,
                    {
                        "agent_event": event,
                        "activity": _activity_from_event(event),
                        **(detail or {}),
                    },
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
        resources = prepare_runtime_resources(
            self.config,
            command,
            emit_event=emit_agent_event,
        )
        try:
            model = LensGatewayChatModel(
                model_ref=str(model_ref),
                ai_gateway_url=self.config.ai_gateway_url,
                token=self.config.token,
                request_timeout_s=self.config.request_timeout_s,
                emit_output=emit_output,
                on_activity=on_activity,
                cancel_event=cancel_event,
                run_uuid=str(command.get("run_uuid") or ""),
            )
            if _is_general_chat(command):
                tools = build_general_chat_tools(
                    command,
                    resources,
                    self.config,
                    emit_event=emit_agent_event,
                )
            else:
                tools = build_agent_tools(
                    command,
                    resources,
                    self.config,
                    emit_event=emit_agent_event,
                )
            kwargs = {
                "model": model,
                "tools": tools,
                "system_prompt": _system_prompt(
                    scenario,
                    command,
                    resources.context_skill_contents,
                ),
                "backend": FilesystemBackend(
                    root_dir=str(resources.root),
                    virtual_mode=True,
                ),
                "subagents": [_fast_subagent()],
                "name": f"lensnode-{command.get('task') or 'agent'}",
            }
            if resources.skill_paths and not _is_general_chat(command):
                kwargs["skills"] = resources.skill_paths

            summarizer = _build_summarization_middleware(
                self.config, model_ref, emit_agent_event, cancel_event
            )
            if summarizer is not None:
                kwargs["middleware"] = [summarizer]
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
                    "mcp_config_path": str(resources.mcp_config_path),
                },
            )
            agent = create_deep_agent(**kwargs)
            max_turns = command.get("max_agent_turns", 26)
            emit_agent_event(
                "deepagents.agent.invoke",
                {"max_agent_turns": max_turns},
            )
            messages = _build_initial_messages(
                command.get("history"), question
            )
            answer, truncated = _run_agent_with_turn_limit(
                agent,
                messages,
                max_turns,
                emit_event=emit_agent_event,
                answer_language=_detect_answer_language(question),
                cancel_event=cancel_event,
            )
            if not (answer or "").strip():
                # the model finished a turn without emitting answer text (e.g.
                # a reasoning-only final turn). Leave the answer empty so the
                # frontend can show a transient retry hint instead of a
                # persisted system-looking message.
                emit_agent_event("deepagents.answer.empty", {})
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
                },
            )
            return {
                "answer": answer,
                "samples": [],
            }
        finally:
            cleanup_runtime_resources(resources)


def _detect_answer_language(question):
    """Return the answer language name detected from the question.

    Short questions break statistical detectors (a Chinese question
    carrying an English product name is misread as a European
    language), so the language is keyed off Unicode script ranges,
    which stay reliable for the scripts we serve. Latin or
    undetermined input falls back to English.
    """

    text = question or ""

    def has(low, high):
        return any(low <= ord(ch) <= high for ch in text)

    if has(0x3040, 0x30FF):
        return "Japanese"
    if has(0xAC00, 0xD7A3):
        return "Korean"
    if has(0x4E00, 0x9FFF) or has(0x3400, 0x4DBF):
        return "Chinese"
    if has(0x0E00, 0x0E7F):
        return "Thai"
    if has(0x0400, 0x04FF):
        return "Russian"
    if has(0x0600, 0x06FF):
        return "Arabic"
    return "English"


def _system_prompt(scenario, command, context_skill_contents=None):
    """Build the per-task Deep Agents system prompt."""

    if _is_general_chat(command):
        return _general_chat_system_prompt(command, context_skill_contents)
    return _knowledge_system_prompt(scenario, command, context_skill_contents)


def _is_general_chat(command):
    """Return whether this command should run as General Chat."""

    return command.get("task") == "general_chat"


def _knowledge_system_prompt(scenario, command, context_skill_contents=None):
    """Build the workspace-grounded system prompt."""

    target_dirs = command.get("target_dirs") or []
    dirs = "\n".join(f"- {item.get('path')}" for item in target_dirs)
    answer_language = _detect_answer_language(command.get("question", ""))
    context_guidance = _context_guidance(context_skill_contents or [])
    return (
        f"{scenario['prompt']}\n\n"
        "You are running inside SourceLens LensNode. The control plane has "
        "selected the workspace directories below.\n\n"
        "Workspace and scratch space:\n"
        "- The selected directories below are READ-ONLY source material. "
        "Inspect them ONLY via search_workspace, find_files and "
        "read_workspace_file; never write into them, as they may be "
        "mounted read-only.\n"
        "- CRITICAL: the built-in ls / read_file / write_file tools act "
        "ONLY on your private scratch directory (your filesystem root), "
        "which starts almost empty (just internal setup such as /mcp and "
        "/skills). They do NOT see the workspace directories above. NEVER "
        "use ls or read_file to decide whether the workspace exists, and "
        "NEVER conclude that the workspace is missing, unmounted, or empty "
        "from them — that conclusion is always wrong. The workspace is "
        "always present and reachable ONLY through search_workspace / "
        "find_files / read_workspace_file.\n"
        "- Your FIRST action for any project or code question MUST be a "
        "search_workspace call, or a find_files call with a RECURSIVE "
        "pattern (\"**/*\", never a bare \"*\", which only lists the top "
        "level). If find_files returns nothing, retry with \"**/*\" or a "
        "broader search_workspace before drawing any conclusion.\n"
        "- Use the scratch directory (write_file / read_file / ls) only "
        "for artifacts you generate. For example, if you convert a PDF to "
        "markdown, write the result there, not into the source "
        "directories. The scratch directory is discarded when the run ends "
        "and the user cannot see it; when you produce a file deliverable "
        "the user should keep, write it to scratch and then call "
        "save_deliverable(path) to deliver it for download.\n\n"
        "Work in parallel whenever steps are independent — this is the "
        "biggest lever on response speed. Batch independent tool calls "
        "into a single step instead of running them one by one: read "
        "multiple files at once, or run multiple searches at once, by "
        "issuing several tool calls in one message. Only go step by step "
        "when a later action genuinely depends on an earlier result.\n\n"
        f"{_subagent_guidance(command.get('agent_rounds'))}"
        "How search and read work:\n"
        "- search_workspace returns matching LINES (path + line number + "
        "surrounding context), not whole files, and works on files of any "
        "size. Pass FOCUSED keywords (the core noun / feature / command "
        "name), not the full question sentence — a whole sentence dilutes "
        "results with common words. Search with keywords as they appear IN "
        "THE FILES; if the question is in a different language than the "
        "documents, translate the key names/terms into the documents' "
        "language first. If the first search is thin or the user's wording "
        "may be a typo/synonym, try a few keyword variants (likely correct "
        "term, synonyms, the documents' own term). For precise patterns set "
        "regex=True; to limit by file type pass a glob (e.g. \"**/*.md\"); "
        "use output_mode=\"files\" to see just which files match.\n"
        "- find_files locates files by name/path glob (e.g. \"**/*.md\", "
        "\"**/*install*\"). Use it when you know a filename or want to "
        "enumerate a file type rather than search their contents.\n"
        "- read_workspace_file reads a line window: pass offset (1-based "
        "start line) and limit (number of lines). Use the line numbers from "
        "search_workspace as offsets, and page by increasing offset when "
        "the relevant part is longer than one window. File size never "
        "blocks a read.\n"
        "- If search_workspace returns no matches but a 'files' listing, "
        "open those files with read_workspace_file (offset/limit) to browse "
        "their contents.\n\n"
        "Required workflow:\n"
        "1. Call search_workspace before answering any project or code "
        "analysis question.\n"
        "2. Read the relevant matches with read_workspace_file around their "
        "line numbers. When several matches look relevant, issue those "
        "calls together in one step so they run concurrently, rather than "
        "reading and paging one at a time.\n"
        "3. For questions about recent changes, call "
        "summarize_recent_changes first. Use git_log or git_diff only when "
        "the summary evidence is insufficient.\n"
        "4. For recent-change questions, do not inspect every repository or "
        "every commit one by one.\n"
        "5. If any tool returns TOOL_BUDGET_EXCEEDED, stop requesting that "
        "tool and produce the final answer from the evidence already "
        "collected.\n"
        "6. Do not answer from memory when workspace tools can provide "
        "evidence.\n"
        "7. Bridge surface wording to the workspace's terminology before "
        "giving up: if the question has a likely typo / synonym / related "
        "concept that DOES match workspace evidence, map it (note the "
        "mapping) and answer from that evidence. Only when there is "
        "genuinely no related evidence, do not guess or answer from "
        "general knowledge — politely tell the user you could not find "
        "relevant information in the current workspace and suggest "
        "contacting our expert support team. Keep the tone warm and "
        "professional.\n\n"
        f"Selected directories:\n{dirs or '- none'}"
        f"{context_guidance}"
        f"\n\nFINAL REMINDER ON LANGUAGE: The user's question is written "
        f"in {answer_language}. You MUST write your ENTIRE final answer "
        f"in {answer_language}, even when the workspace files you read "
        f"are in another language. Never switch to the language of the "
        f"source files you read."
    )


def _general_chat_system_prompt(command, context_skill_contents=None):
    """Build the General Chat system prompt."""

    answer_language = _detect_answer_language(command.get("question", ""))
    skill_guidance = _general_chat_guidance(context_skill_contents or [])
    return (
        "You are running inside SourceLens LensNode as General Chat.\n\n"
        "The bound Skills are your primary behavior contract. Follow their "
        "SKILL.md instructions and use bundled resources only when the Skill "
        "indicates they are relevant. Do not search or inspect local "
        "workspace source directories; this mode is not a knowledge-base "
        "retrieval assistant. If loaded Skill instructions are listed below, "
        "you MUST treat them as available Skills even if another framework "
        "message says no Skills are available.\n\n"
        "You have a private writable scratch directory via the built-in "
        "filesystem tools. Put generated artifacts there. The scratch "
        "directory is discarded when the run ends and the user cannot see "
        "it, so it is not how the user receives files. When you produce a "
        "file deliverable the user should keep (for example an HTML brief "
        "or a report), write it to scratch and then call "
        "save_deliverable(path) with that path to deliver it for download. "
        "Only deliver the final artifact, not intermediate scratch files. "
        "You may use "
        "run_skill_script to execute scripts bundled inside loaded Skills' "
        "scripts/ directories. Only run scripts that the Skill instructions "
        "directly call for, pass focused arguments, and inspect stdout/stderr "
        "before deciding what to do next.\n\n"
        "Always end with a written answer to the user; never finish with an "
        "empty reply. When you delivered a file, briefly say what it is and "
        "that it is available to download. If required user inputs are "
        "missing, ask a concise clarification "
        "question instead of guessing. If a Skill cannot perform the task, "
        "say so plainly and explain what capability or input is missing."
        f"{skill_guidance}"
        f"\n\nFINAL REMINDER ON LANGUAGE: The user's question is written "
        f"in {answer_language}. You MUST write your ENTIRE final answer "
        f"in {answer_language}."
    )


def _fast_subagent():
    """General-purpose subagent that parallelizes its own tool calls.

    By default a delegated subagent runs deepagents' stock prompt and
    tends to do serial ReAct (one file at a time) — the main reason a
    subtask is slow. Overriding the same-named general-purpose subagent
    and prepending the parallel guidance makes it batch its reads and
    searches like the main agent. Tools and model are inherited from the
    parent (tools default to the parent's set).
    """

    parallel = (
        "Work in parallel whenever steps are independent — this is the "
        "biggest lever on speed. When several files or searches are "
        "needed, issue those tool calls together in one message so they "
        "run concurrently; do not read and validate hits one at a time. "
        "Keep the number of parallel calls reasonable.\n\n"
    )
    return {
        **GENERAL_PURPOSE_SUBAGENT,
        "system_prompt": parallel + GENERAL_PURPOSE_SUBAGENT["system_prompt"],
    }


def _subagent_guidance(agent_rounds):
    """Return depth-tiered guidance on when to use the task subagent.

    Subagents are a completed agent loop each (multi-round, minute-scale),
    so they only pay off for heavy, independent subtasks and are a net
    loss on light multi-file work. Only the deep/max tiers encourage
    parallel delegation; lighter tiers steer the model to stay in the
    main loop and parallelize with batched tool calls instead.
    """

    if agent_rounds in ("deep", "max"):
        return (
            "Delegating subtasks (task tool): when the question splits "
            "into genuinely independent, heavy subtasks — each needing "
            "its own multi-round search/read exploration — delegate them "
            "to `task` subagents in parallel (issue multiple task calls "
            "in one message), then synthesize their results. Do NOT "
            "delegate light work (reading a few files): handle that "
            "directly with batched tool calls, which is faster.\n\n"
        )
    return (
        "Stay in the main loop: handle the work directly with batched "
        "tool calls (parallel reads/searches). Do NOT delegate to `task` "
        "subagents for this — at this depth, direct batched work is "
        "faster than spinning up subagents.\n\n"
    )


def _context_guidance(contents):
    """Build the injected context skill prompt block."""

    if not contents:
        return ""
    joined = "\n\n".join(contents)[:12000]
    return (
        "\n\nWorkspace Guidance from bound context skills:\n"
        "This guidance is authoritative for this assistant — follow it "
        "throughout the whole task. It governs not only repository layout, "
        "search priority and stopping rules, but ALSO how you write the "
        "final answer: output format, wording, and link / URL / path "
        "conventions. When it conflicts with your default behavior, the "
        "guidance wins. If it defines how links or paths should be "
        "presented, apply that transformation in the final answer instead "
        f"of emitting raw or relative paths.\n\n{joined}"
    )


def _general_chat_guidance(contents):
    """Build the injected General Chat prompt block."""

    if not contents:
        return (
            "\n\nLoaded Skills:\n"
            "- None were received in this run. Report this as a SourceLens "
            "assistant configuration issue instead of suggesting that the "
            "user create a new Skill inside the runtime directory."
        )
    joined = "\n\n".join(contents)[:16000]
    return (
        "\n\nLoaded Skills:\n"
        "The following SKILL.md instructions were loaded from the assistant's "
        "bound Skills. They are authoritative for this run. Use these Skills "
        "to answer or perform the task. Do not claim that no Skills are "
        "available.\n\n"
        "When multiple Skills are loaded, select the smallest relevant "
        "subset for the user's request. Do not run every Skill automatically. "
        "If multiple Skills conflict, follow the Skill that best matches the "
        "current request and briefly explain that choice when it matters.\n\n"
        f"{joined}"
    )


def _extract_final_message(response):
    """Extract final assistant content from a Deep Agents response."""

    if not isinstance(response, dict):
        return str(response).strip()
    messages = response.get("messages") or []
    if not messages:
        return ""
    last = messages[-1]
    content = getattr(last, "content", None)
    if isinstance(content, str):
        return content.strip()
    return str(content or "").strip()


def _scenario_for_task(task):
    """Return scenario metadata for a LensNode task name."""

    return SCENARIOS.get(task or "", SCENARIOS["knowledge_qa"])


def _detail_lines(detail):
    """Convert event detail dict to normalized log lines."""

    if not detail:
        return None
    return [
        f"{_title_key(key)}: {value}"
        for key, value in detail.items()
    ]


def _title_key(value):
    """Return compact TitleCase log key."""

    return "".join(part.capitalize() for part in str(value).split("_"))


def _activity_from_event(event):
    """Return a compact frontend activity name for an agent event."""

    if event.startswith("resources."):
        return "loading_resources"
    if event.startswith("tool."):
        return "running_tool"
    if event.endswith(".invoke"):
        return "thinking"
    if event.endswith(".done"):
        return "completed"
    return "running"


def _build_initial_messages(history, question):
    """Prepend prior conversation turns to the current question.

    Only user/assistant turns with content are kept; tool traces are
    never carried across turns, so the context stays bounded.
    """

    messages = []
    for item in history or []:
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})
    return messages


def _run_agent_with_turn_limit(
    agent,
    messages,
    max_turns,
    emit_event=None,
    answer_language="English",
    cancel_event=None,
):
    """Stream agent events and stop after max_turns NEW AI turns.

    `messages` may be prefixed with prior conversation turns. Historical
    assistant turns are excluded from both the turn count and event
    emission, so the limit and trace reflect only the current run.

    Returns (answer, truncated) where truncated=True means the agent
    was stopped before it finished naturally.
    """

    last_state = None
    truncated = False
    seen_tool_calls = set()
    seen_model_calls = set()
    baseline_ai = sum(1 for m in messages if m.get("role") == "assistant")
    seeded_baseline = False

    for state in agent.stream(
        {"messages": messages},
        stream_mode="values",
        config={"recursion_limit": 500},
    ):
        if cancel_event is not None and cancel_event.is_set():
            raise RunCancelledError(
                "Run was cancelled; stopping the agent loop."
            )
        last_state = state
        current = state.get("messages", [])
        if not seeded_baseline:
            # Seed the historical assistant turns by their (now-assigned)
            # message id so they are never emitted or counted as new turns.
            # Dedup keys on message id, so an integer preseed would never
            # match and would re-emit the carried-over history.
            ai_count = 0
            for message in current:
                if getattr(message, "type", "") != "ai":
                    continue
                ai_count += 1
                if ai_count <= baseline_ai:
                    seen_model_calls.add(
                        getattr(message, "id", None) or id(message)
                    )
            seeded_baseline = True
        if emit_event is not None:
            _emit_new_model_calls(current, seen_model_calls, emit_event)
            _emit_new_tool_calls(current, seen_tool_calls, emit_event)
        ai_turns = sum(
            1
            for m in current
            if getattr(m, "type", "") == "ai"
        ) - baseline_ai
        if ai_turns >= max_turns:
            truncated = True
            break

    answer = _extract_final_message(last_state or {})
    if truncated and answer.strip():
        if answer_language == "Chinese":
            answer += (
                "\n\n---\n*已达到当前分析深度上限，"
                "如需更完整的结果，请调高分析档位后重试。*"
            )
        else:
            answer += (
                "\n\n---\n*Reached the current analysis-depth limit. "
                "Raise the analysis tier for a more complete result.*"
            )
    return answer, truncated


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
                "cost": usage.get("cost"),
                "latency_ms": meta.get("latency_ms"),
                "summary": _model_summary(message),
            },
        )


def _emit_new_tool_calls(messages, seen, emit_event):
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
            if name in SELF_REPORTING_TOOLS:
                # avoids a duplicate trace line; the tool emits its own
                # .start/.done with a richer argument summary
                continue
            emit_event(
                f"tool.{name}.invoke",
                {"tool": name, "summary": _tool_call_summary(call)},
            )


def _tool_call_summary(call):
    """Return a short human summary of a tool call's arguments."""

    args = call.get("args") or {}
    if not isinstance(args, dict):
        return ""
    for key in ("path", "file_path", "query", "description", "ref"):
        value = args.get(key)
        if value:
            return str(value)[:120]
    return ""
