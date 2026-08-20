"""General Chat restrictions for built-in Deep Agent capabilities."""

import json

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage


class NoTaskMiddleware(AgentMiddleware):
    """Enforce General Chat restrictions on built-in agent tools."""

    def __init__(self, emit_event=None, allow_task_tool=False):
        self.emit_event = emit_event
        self.allow_task_tool = allow_task_tool
        self.model_round = 0

    def _filter_tools(self, tools):
        if self.allow_task_tool:
            return list(tools)
        return [
            tool
            for tool in tools
            if getattr(tool, "name", None) != "task"
        ]

    def wrap_model_call(self, request, handler):
        """Filter synchronous model requests."""

        request = request.override(
            tools=self._filter_tools(request.tools)
        )
        invocation_id = self._start_model_round()
        try:
            result = handler(request)
        except Exception:
            self._finish_model_round(invocation_id, "failed")
            raise
        self._finish_model_round(invocation_id, "done")
        return result

    async def awrap_model_call(self, request, handler):
        """Filter asynchronous model requests."""

        request = request.override(
            tools=self._filter_tools(request.tools)
        )
        invocation_id = self._start_model_round()
        try:
            result = await handler(request)
        except Exception:
            self._finish_model_round(invocation_id, "failed")
            raise
        self._finish_model_round(invocation_id, "done")
        return result

    def _start_model_round(self):
        """Emit the start of one real General Chat model round."""

        self.model_round += 1
        invocation_id = f"model-round-{self.model_round}"
        if self.emit_event is not None:
            self.emit_event(
                "model.round.start",
                {
                    "invocation_id": invocation_id,
                    "round": self.model_round,
                },
            )
        return invocation_id

    def _finish_model_round(self, invocation_id, suffix):
        """Emit the terminal state for one General Chat model round."""

        if self.emit_event is not None:
            round_number = int(invocation_id.rsplit("-", 1)[-1])
            self.emit_event(
                f"model.round.{suffix}",
                {
                    "invocation_id": invocation_id,
                    "round": round_number,
                },
            )

    def _deny_task_call(self, request):
        """Return a tool error without executing the subagent handler."""

        tool_call = request.tool_call or {}
        if self.emit_event is not None:
            self.emit_event(
                "tool.task.denied",
                {
                    "tool_call_id": tool_call.get("id"),
                    "summary": "General Chat subagent call denied",
                },
            )
        return ToolMessage(
            content=json.dumps(
                {
                    "ok": False,
                    "error": "SUBAGENT_DISABLED",
                    "instruction": (
                        "Do not request task again. Use the current context "
                        "and available non-subagent tools, then answer."
                    ),
                }
            ),
            name="task",
            status="error",
            tool_call_id=tool_call.get("id") or "task-denied",
        )

    @staticmethod
    def _is_task_call(request):
        tool_call = request.tool_call or {}
        return (
            tool_call.get("name") == "task"
            or getattr(request.tool, "name", None) == "task"
        )

    def wrap_tool_call(self, request, handler):
        """Block synchronous task execution for General Chat."""

        if self._is_task_call(request) and not self.allow_task_tool:
            return self._deny_task_call(request)
        return handler(request)

    async def awrap_tool_call(self, request, handler):
        """Block asynchronous task execution for General Chat."""

        if self._is_task_call(request) and not self.allow_task_tool:
            return self._deny_task_call(request)
        return await handler(request)
