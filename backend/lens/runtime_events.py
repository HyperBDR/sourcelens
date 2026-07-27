"""Sanitize LensNode runtime events before exposing them to end users."""

PUBLIC_EVENT_TYPES = {
    "artifact.created",
    "capability.blocked",
    "phase.changed",
    "plan.updated",
    "route.selected",
    "stage.updated",
}

ROUTE_VALUES = {
    "intent": {"informational", "action", "clarification"},
    "complexity": {"simple", "complex"},
    "route": {"direct_answer", "direct_execute", "plan_execute"},
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

PUBLIC_TERMINATION_REASONS = {
    "capability_unavailable",
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
    "configuration": "Ask an administrator to configure or authorize it.",
    "policy": "Continue from the evidence already collected.",
    "transient": "Retry later or use another available capability.",
    "request": "Provide the missing or corrected input, then retry.",
    "tool": "Use another available capability or contact an administrator.",
    "verification": (
        "Confirm the required integration is bound and authorized, then "
        "retry."
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
    if event_type == "capability.blocked":
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
