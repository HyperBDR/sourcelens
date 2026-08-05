"""Privacy-bounded tracing middleware for LensNode agent runs."""

import re
import uuid

from langchain.agents.middleware import AgentMiddleware

from ..logging_utils import utc_now


class TraceObservationMiddleware(AgentMiddleware):
    """Emit privacy-bounded spans around synchronous and async tool calls."""

    def __init__(self, emit_observation, root_observation_id):
        self.emit_observation = emit_observation
        self.root_observation_id = root_observation_id

    def wrap_tool_call(self, request, handler):
        """Wrap one synchronous tool call in a trace observation."""

        observation_id = self._start(request)
        try:
            result = handler(request)
        except Exception as exc:
            self._finish(observation_id, "failed", exc)
            raise
        status = (
            "failed"
            if getattr(result, "status", None) == "error"
            else "done"
        )
        self._finish(observation_id, status)
        return result

    async def awrap_tool_call(self, request, handler):
        """Wrap one asynchronous tool call in a trace observation."""

        observation_id = self._start(request)
        try:
            result = await handler(request)
        except Exception as exc:
            self._finish(observation_id, "failed", exc)
            raise
        status = (
            "failed"
            if getattr(result, "status", None) == "error"
            else "done"
        )
        self._finish(observation_id, status)
        return result

    def _start(self, request):
        """Emit a start event without tool arguments."""

        observation_id = uuid.uuid4().hex
        tool = getattr(request, "tool", None)
        raw_name = getattr(tool, "name", None) or "unknown"
        tool_name = re.sub(r"[^A-Za-z0-9._-]", "_", str(raw_name))[:96]
        self.emit_observation(
            {
                "action": "start",
                "id": observation_id,
                "parent_observation_id": self.root_observation_id,
                "name": f"tool.{tool_name or 'unknown'}",
                "started_at": observation_timestamp(),
            }
        )
        return observation_id

    def _finish(self, observation_id, status, error=None):
        """Emit an end event without tool output or exception text."""

        event = {
            "action": "end",
            "id": observation_id,
            "status": status,
            "ended_at": observation_timestamp(),
        }
        if error is not None:
            event["error_type"] = type(error).__name__
        self.emit_observation(event)


def observation_timestamp():
    """Return an ingestion-compatible UTC timestamp."""

    return utc_now().isoformat().replace("+00:00", "Z")
