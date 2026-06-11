import asyncio
import logging

from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend

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
            "You answer questions over selected documents and code "
            "workspaces. Use tools to gather evidence before answering. "
            "Cite file paths when evidence comes from files. If the evidence "
            "is insufficient, say what is missing."
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
            answer, truncated = _run_agent_with_turn_limit(
                agent, question, max_turns, emit_event=emit_agent_event
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


def _system_prompt(scenario, command, context_skill_contents=None):
    """Build the per-task Deep Agents system prompt."""

    target_dirs = command.get("target_dirs") or []
    dirs = "\n".join(f"- {item.get('path')}" for item in target_dirs)
    context_guidance = _context_guidance(context_skill_contents or [])
    return (
        f"{scenario['prompt']}\n\n"
        "You are running inside SourceLens LensNode. The control plane has "
        "selected the workspace directories below. Keep the final answer in "
        "the user's language when possible.\n\n"
        "Workspace and scratch space:\n"
        "- The selected directories below are READ-ONLY source material. "
        "Inspect them only via search_workspace and read_workspace_file; "
        "never write into them, as they may be mounted read-only.\n"
        "- You also have a private, writable scratch directory (your "
        "filesystem root, accessed via write_file, read_file, and ls). Put "
        "any generated or converted artifacts there. For example, if you "
        "convert a PDF to markdown, write the result to the scratch "
        "directory, not the source directories.\n\n"
        "Required workflow:\n"
        "1. Call search_workspace before answering any project or code "
        "analysis question.\n"
        "2. Call read_workspace_file for at least one relevant search hit.\n"
        "3. For questions about recent changes, call "
        "summarize_recent_changes first. Use git_log or git_diff only when "
        "the summary evidence is insufficient.\n"
        "4. For recent-change questions, do not inspect every repository or "
        "every commit one by one.\n"
        "5. If any tool returns TOOL_BUDGET_EXCEEDED, stop requesting that "
        "tool and produce the final answer from the evidence already "
        "collected.\n"
        "6. Do not answer from memory when workspace tools can provide "
        "evidence.\n\n"
        f"Selected directories:\n{dirs or '- none'}"
        f"{context_guidance}"
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


def _run_agent_with_turn_limit(agent, question, max_turns, emit_event=None):
    """Stream agent events and stop after max_turns AI turns.

    Returns (answer, truncated) where truncated=True means the agent
    was stopped before it finished naturally.
    """

    last_state = None
    truncated = False
    seen_tool_calls = set()

    for state in agent.stream(
        {"messages": [{"role": "user", "content": question}]},
        stream_mode="values",
        config={"recursion_limit": 500},
    ):
        last_state = state
        messages = state.get("messages", [])
        if emit_event is not None:
            _emit_new_tool_calls(messages, seen_tool_calls, emit_event)
        ai_turns = sum(
            1
            for m in messages
            if getattr(m, "type", "") == "ai"
        )
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
