import asyncio
import logging

from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware.subagents import GENERAL_PURPOSE_SUBAGENT

from .agent_tools import build_agent_tools
from .gateway_model import LensGatewayChatModel
from .logging_utils import elapsed_since, task_log, utc_now
from .runtime_resources import cleanup_runtime_resources
from .runtime_resources import prepare_runtime_resources

LOGGER = logging.getLogger("lensnode")

SCENARIOS = {
    "knowledge_qa": {
        "title": "Knowledge Q&A",
        "prompt": (
            "You answer questions STRICTLY from the selected documents and "
            "code workspace. Use the tools to gather evidence first, and "
            "cite file paths when evidence comes from files. Answer ONLY "
            "what the workspace evidence supports. "
            "Bridge the user's wording to the workspace's own terminology: "
            "if the question contains a likely typo, homophone, synonym or "
            "related concept, map it to the matching term, briefly note the "
            "mapping (\"you likely mean …\"), and answer from that evidence. "
            "Do NOT refuse over a surface wording mismatch when related "
            "evidence exists. Only when the workspace has genuinely NO "
            "related evidence — including general-knowledge or off-topic "
            "questions you could answer on your own (e.g. geography, "
            "cooking, news) — you MUST NOT answer from your own knowledge; "
            "instead politely tell the user you could not find relevant "
            "information in the current workspace and suggest contacting "
            "our expert support team. Never invent facts the workspace "
            "does not support."
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


class LensDeepAgentRuntime:
    """Run a real LangChain Deep Agents execution for one LensNode command."""

    def __init__(self, config):
        self.config = config

    async def answer(self, command, emit_progress=None, emit_output=None):
        """Execute a run_start command with create_deep_agent."""

        return await asyncio.to_thread(
            self._answer_sync,
            command,
            emit_progress,
            emit_output,
        )

    def _answer_sync(self, command, emit_progress=None, emit_output=None):
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
            )
            tools = build_agent_tools(command, emit_event=emit_agent_event)
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
            if resources.skill_paths:
                kwargs["skills"] = resources.skill_paths

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
                agent, messages, max_turns, emit_event=emit_agent_event
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
        "Inspect them only via search_workspace, find_files and "
        "read_workspace_file; never write into them, as they may be "
        "mounted read-only.\n"
        "- You also have a private, writable scratch directory (your "
        "filesystem root, accessed via write_file, read_file, and ls). Put "
        "any generated or converted artifacts there. For example, if you "
        "convert a PDF to markdown, write the result to the scratch "
        "directory, not the source directories.\n\n"
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
        "Apply this guidance before using workspace tools. Treat it as "
        "authoritative for repository layout, search priority, and stopping "
        f"rules.\n\n{joined}"
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


def _run_agent_with_turn_limit(agent, messages, max_turns, emit_event=None):
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
    seen_model_calls.update(range(1, baseline_ai + 1))

    for state in agent.stream(
        {"messages": messages},
        stream_mode="values",
        config={"recursion_limit": 500},
    ):
        last_state = state
        current = state.get("messages", [])
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
    if truncated:
        answer += (
            "\n\n---\n*已达到当前分析深度上限，"
            "如需更完整的结果，请调高分析档位后重试。*"
        )
    return answer, truncated


def _emit_new_model_calls(messages, seen, emit_event):
    """Emit an event for each new AI response (one LLM round).

    Each AI message is one round-trip to the model. The gateway returns
    token usage in the message's response_metadata, so surfacing these
    makes every LLM call visible in the trace and attributes token usage
    to the run.
    """

    ai_index = 0
    for message in messages:
        if getattr(message, "type", "") != "ai":
            continue
        ai_index += 1
        if ai_index in seen:
            continue
        seen.add(ai_index)
        meta = getattr(message, "response_metadata", None) or {}
        usage = meta.get("usage") or {}
        emit_event(
            "llm.response",
            {
                "round": ai_index,
                "model": usage.get("model"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "cost": usage.get("cost"),
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
