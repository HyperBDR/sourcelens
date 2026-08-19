"""Safety policy for resuming an agent run from a checkpoint."""

from langchain_core.messages import ToolMessage

from ..checkpoint import CheckpointResumeError

_POTENTIALLY_SIDE_EFFECTING_TOOLS = {
    "call_skill_api",
    "run_skill_script",
    "run_skill_transform",
    "save_deliverable",
}


def pending_checkpoint_tool_calls(
    messages,
    pending_write_tool_call_ids=(),
):
    """Return tool calls whose result is absent from checkpoint messages."""

    completed = {
        str(tool_call_id) for tool_call_id in pending_write_tool_call_ids
    }
    for message in reversed(tuple(messages or ())):
        if isinstance(message, ToolMessage):
            tool_call_id = getattr(message, "tool_call_id", None)
            if tool_call_id:
                completed.add(str(tool_call_id))
            continue
        tool_calls = getattr(message, "tool_calls", None) or []
        pending = [
            call
            for call in tool_calls
            if str(call.get("id") or "") not in completed
        ]
        if pending:
            return pending
    return []


def reject_unsafe_resume_tool_replay(
    messages,
    tools,
    pending_write_tool_call_ids=(),
):
    """Fail closed if resume could repeat an external write operation."""

    tools_by_name = {
        str(getattr(tool, "name", "") or ""): tool for tool in tools or []
    }
    for message in tuple(messages or ()):
        for call in getattr(message, "tool_calls", None) or []:
            arguments = call.get("args") or {}
            if (
                call.get("name") == "call_skill_api"
                and isinstance(arguments, dict)
                and arguments.get("capture")
            ):
                raise CheckpointResumeError(
                    "Cannot resume a checkpoint that depends on ephemeral "
                    "Skill API session values."
                )
    for call in pending_checkpoint_tool_calls(
        messages,
        pending_write_tool_call_ids,
    ):
        name = str(call.get("name") or "")
        tool = tools_by_name.get(name)
        if tool is None:
            raise CheckpointResumeError(
                "Cannot resume a checkpoint with an unclassified pending "
                "tool operation."
            )
        metadata = getattr(tool, "metadata", None) or {}
        if not isinstance(metadata, dict):
            metadata = {}
        if metadata.get("idempotent") is True:
            continue
        if (
            metadata.get("read_only") is True
            or metadata.get("operation") == "read"
        ):
            continue
        is_write = (
            metadata.get("operation") == "write"
            or metadata.get("read_only") is False
            or metadata.get("side_effects") is True
            or name.startswith("mcp__")
            or name in _POTENTIALLY_SIDE_EFFECTING_TOOLS
        )
        if is_write:
            raise CheckpointResumeError(
                "Cannot resume a checkpoint with a pending non-idempotent "
                "write operation."
            )
