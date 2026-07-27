"""Sanitize LensNode runtime events before exposing them to end users."""

from datetime import datetime

PUBLIC_EVENT_TYPES = {
    "artifact.created",
    "capability.blocked",
    "execution.failed",
    "phase.changed",
    "plan.updated",
    "route.selected",
    "stage.updated",
}

ROUTE_VALUES = {
    "intent": {"informational", "action", "clarification"},
    "complexity": {"simple", "complex"},
    "route": {
        "capability_unavailable",
        "direct_answer",
        "direct_execute",
        "plan_execute",
    },
    "evidence_requirement": {
        "none",
        "tool_result",
        "artifact",
        "user_input",
    },
}

PUBLIC_CAPABILITIES = {
    "skill",
    "mcp",
    "workspace",
    "artifact_delivery",
    "tool",
}

PUBLIC_PHASES = {
    "analyzing",
    "planning",
    "executing",
    "answering",
    "completed",
}

PUBLIC_PLAN_STATUSES = {"pending", "in_progress", "completed"}

PUBLIC_STAGE_STATUSES = {
    "pending",
    "in_progress",
    "completed",
    "failed",
    "skipped",
}

TOOL_ACTIVITY_STATUSES = {
    "done": "completed",
    "failed": "failed",
    "invoke": "in_progress",
    "start": "in_progress",
    "timeout": "failed",
}

MODEL_ACTIVITY_STATUSES = {
    "done": "completed",
    "failed": "failed",
    "start": "in_progress",
}

PUBLIC_TERMINATION_REASONS = {
    "capability_unavailable",
    "execution_failed",
    "evidence_unavailable",
    "execution_limit",
    "turn_limit",
    "soft_deadline",
    "token_budget",
    "safety_terminated",
    "model_length_capped",
    "token_capped",
    "token_budget_wrapup",
    "loop_capped",
    "runtime_failure",
}

PUBLIC_ERROR_TYPES = {
    "capability",
    "configuration",
    "policy",
    "transient",
    "request",
    "tool",
    "verification",
}

PUBLIC_RUNTIME_CODES = {
    "EMPTY_AGENT_RESPONSE",
    "MODEL_STREAM_ERROR",
    "MODEL_TIMEOUT",
    "NO_ACTIVITY_TIMEOUT",
    "RUN_CANCELLED",
    "RUN_TIMEOUT",
}

RECOVERY_MESSAGES = {
    "capability": (
        "Use an assistant with the required operation or ask an "
        "administrator to bind that capability."
    ),
    "configuration": "Ask an administrator to configure or authorize it.",
    "policy": "Continue from the evidence already collected.",
    "transient": "Retry later or use another available capability.",
    "request": "Provide the missing or corrected input, then retry.",
    "tool": "Use another available capability or contact an administrator.",
    "verification": (
        "Review the execution details and retry; no verified result was "
        "returned."
    ),
}


def sanitize_loaded_skills(items):
    """Return Skill identities without definitions or environment data."""

    fields = (
        "skill_uuid",
        "skill_slug",
        "skill_name",
        "version",
        "content_hash",
    )
    return [
        {key: item.get(key) for key in fields if item.get(key) is not None}
        for item in items or []
        if isinstance(item, dict)
    ]


def sanitize_loaded_mcps(items):
    """Return MCP identities without endpoints, headers, or config."""

    fields = (
        "mcp_uuid",
        "mcp_name",
        "version",
        "content_hash",
        "transport",
    )
    return [
        {key: item.get(key) for key in fields if item.get(key) is not None}
        for item in items or []
        if isinstance(item, dict)
    ]


def _text(value, limit=240):
    return str(value or "")[:limit]


def _safe_activity_id(value):
    activity_id = _text(value, 64).strip()
    if not activity_id:
        return ""
    if not activity_id.isascii() or not all(
        char.isalnum() or char in "-_" for char in activity_id
    ):
        return ""
    return activity_id


def _date_argument(arguments, name):
    """Return one ISO date from an allowlisted command argument."""

    if not isinstance(arguments, list):
        return ""
    try:
        index = arguments.index(name)
        value = str(arguments[index + 1])
    except (IndexError, ValueError):
        return ""
    if value == "[REDACTED]" or len(value) > 64:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except ValueError:
        return ""


def _contains_command(arguments, *parts):
    if not isinstance(arguments, list):
        return False
    normalized = [str(item).strip().lower() for item in arguments]
    expected = list(parts)
    width = len(expected)
    return any(
        normalized[index : index + width] == expected
        for index in range(len(normalized) - width + 1)
    )


def _tool_activity_kind(tool_name, item):
    """Return a safe semantic kind derived from an observed tool event."""

    if tool_name == "run_skill_artifact":
        arguments = item.get("args_redacted")
        if _contains_command(arguments, "order", "list"):
            return "query_orders"
        if (
            _contains_command(arguments, "order")
            and isinstance(arguments, list)
            and any(
                str(argument).strip().lower() in {"--help", "-h", "help"}
                for argument in arguments
            )
        ):
            return "reading_order_commands"
        if _contains_command(arguments, "order", "get"):
            return "get_order_detail"
        if _contains_command(
            arguments,
            "auth",
            "status",
        ) or _contains_command(arguments, "version"):
            return "checking_capability"
        return "querying_data"
    if tool_name == "analyze_structured_output":
        operation = str(item.get("operation") or "").strip().lower()
        if operation == "count":
            return "count_results"
        if operation == "group_count":
            return "group_results"
        return "analyzing_results"
    if tool_name in {"inspect_saved_output", "run_skill_transform"}:
        return "analyzing_results"
    if tool_name == "call_skill_api":
        return "querying_data"
    return ""


def _activity_stage_kind(activity_kind):
    """Return the safe stage that owns one General Chat step."""

    if activity_kind in {
        "checking_capability",
        "get_order_detail",
        "query_orders",
        "reading_order_commands",
    }:
        return "order_query"
    if activity_kind in {
        "analyzing_results",
        "count_results",
        "group_results",
    }:
        return "result_analysis"
    return "data_query"


def _sanitize_tool_activity(item):
    """Return one replayable activity without raw model/tool arguments."""

    if item.get("runtime_scope") != "general_chat":
        return None
    agent_event = _text(item.get("agent_event"), 128)
    if not agent_event.startswith("tool."):
        return None
    body = agent_event[5:]
    tool_name, separator, suffix = body.rpartition(".")
    status = TOOL_ACTIVITY_STATUSES.get(suffix)
    if not separator or not status:
        return None
    activity_id = _safe_activity_id(item.get("invocation_id"))
    kind = _tool_activity_kind(tool_name, item)
    if not activity_id or not kind:
        return None
    payload = {
        "id": activity_id,
        "kind": kind,
        "stage_kind": _activity_stage_kind(kind),
        "status": status,
    }
    if kind == "query_orders" and status == "in_progress":
        arguments = item.get("args_redacted")
        start_date = _date_argument(
            arguments,
            "--start-time",
        ) or _date_argument(arguments, "--start")
        end_date = _date_argument(
            arguments,
            "--end-time",
        ) or _date_argument(arguments, "--end")
        if start_date:
            payload["start_date"] = start_date
        if end_date:
            payload["end_date"] = end_date
    return {
        "event_type": "activity.recorded",
        "visibility": "user",
        "payload": payload,
    }


def _sanitize_model_activity(item):
    """Return one safe, replayable General Chat model-round step."""

    if item.get("runtime_scope") != "general_chat":
        return None
    agent_event = _text(item.get("agent_event"), 128)
    prefix = "model.round."
    if not agent_event.startswith(prefix):
        return None
    status = MODEL_ACTIVITY_STATUSES.get(agent_event[len(prefix) :])
    activity_id = _safe_activity_id(item.get("invocation_id"))
    if not activity_id or not status:
        return None
    try:
        round_number = min(max(int(item.get("round") or 1), 1), 100)
    except (TypeError, ValueError):
        round_number = 1
    return {
        "event_type": "activity.recorded",
        "visibility": "user",
        "payload": {
            "id": activity_id,
            "kind": "analyzing_request",
            "stage_kind": "reasoning",
            "status": status,
            "round": round_number,
        },
    }


def sanitize_termination_detail(detail):
    """Return the allowlisted user-visible termination fields."""

    if not isinstance(detail, dict):
        return {}
    output = {}
    reason = detail.get("reason")
    if reason in PUBLIC_TERMINATION_REASONS:
        output["reason"] = reason
    capability = detail.get("capability")
    if capability in PUBLIC_CAPABILITIES:
        output["capability"] = capability
    error_type = detail.get("error_type")
    if error_type in PUBLIC_ERROR_TYPES:
        output["error_type"] = error_type
        output["recovery"] = RECOVERY_MESSAGES[error_type]
    code = detail.get("code")
    if code in PUBLIC_RUNTIME_CODES:
        output["code"] = code
    return output


def _sanitize_payload(event_type, payload):
    if not isinstance(payload, dict):
        return {}
    if event_type == "route.selected":
        output = {}
        for key, allowed in ROUTE_VALUES.items():
            value = payload.get(key)
            if value in allowed:
                output[key] = value
        capabilities = payload.get("required_capabilities")
        if isinstance(capabilities, list):
            output["required_capabilities"] = [
                item
                for item in capabilities[:8]
                if item in PUBLIC_CAPABILITIES
            ]
        return output
    if event_type == "phase.changed":
        phase = payload.get("phase")
        return {"phase": phase} if phase in PUBLIC_PHASES else {}
    if event_type == "plan.updated":
        steps = []
        for item in (payload.get("steps") or [])[:12]:
            if not isinstance(item, dict):
                continue
            status = item.get("status")
            steps.append(
                {
                    "id": _text(item.get("id"), 64),
                    "title": _text(item.get("title")),
                    "status": (
                        status
                        if status in PUBLIC_PLAN_STATUSES
                        else "pending"
                    ),
                }
            )
        try:
            revision = max(int(payload.get("revision") or 0), 0)
        except (TypeError, ValueError):
            revision = 0
        return {"revision": revision, "steps": steps}
    if event_type == "stage.updated":
        stage_id = _text(payload.get("id"), 64).strip()
        title = _text(payload.get("title")).strip()
        status = payload.get("status")
        if not stage_id or not title or status not in PUBLIC_STAGE_STATUSES:
            return {}
        try:
            order = min(max(int(payload.get("order") or 1), 1), 12)
        except (TypeError, ValueError):
            order = 1
        try:
            revision = max(int(payload.get("revision") or 0), 0)
        except (TypeError, ValueError):
            revision = 0
        output = {
            "id": stage_id,
            "title": title,
            "status": status,
            "order": order,
            "revision": revision,
        }
        summary = _text(payload.get("summary")).strip()
        if summary:
            output["summary"] = summary
        return output
    if event_type in {"capability.blocked", "execution.failed"}:
        return sanitize_termination_detail(payload)
    if event_type == "artifact.created":
        output = {
            key: _text(payload.get(key), 240)
            for key in ("filename", "content_type")
            if payload.get(key)
        }
        try:
            output["byte_size"] = max(int(payload.get("byte_size") or 0), 0)
        except (TypeError, ValueError):
            output["byte_size"] = 0
        return output
    return {}


def sanitize_runtime_event(item):
    """Return a public event without raw tool arguments or model output."""

    if not isinstance(item, dict):
        return None
    event_type = item.get("event_type")
    if (
        item.get("visibility") == "user"
        and event_type in PUBLIC_EVENT_TYPES
    ):
        activity = (
            "completed"
            if event_type == "phase.changed"
            and (item.get("payload") or {}).get("phase") == "completed"
            else "running"
        )
        return {
            "agent_event": f"workflow.{event_type}",
            "activity": activity,
            "event_type": event_type,
            "visibility": "user",
            "payload": _sanitize_payload(event_type, item.get("payload")),
        }
    model_activity = _sanitize_model_activity(item)
    if model_activity is not None:
        return model_activity
    tool_activity = _sanitize_tool_activity(item)
    if tool_activity is not None:
        return tool_activity
    agent_event = _text(item.get("agent_event"), 128)
    activity = _text(item.get("activity"), 64)
    if not agent_event and not activity:
        return None
    return {
        "agent_event": agent_event,
        "activity": activity,
    }


def public_step_detail(detail):
    """Return only safe runtime events from one persisted step detail."""

    if not isinstance(detail, dict):
        return {"events": []}
    events = []
    for item in detail.get("events") or []:
        event = sanitize_runtime_event(item)
        if event is not None:
            events.append(event)
    return {"events": events}
