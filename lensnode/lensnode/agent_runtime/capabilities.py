"""Capability recovery and evidence boundaries for agent runs."""

import hashlib
import json
from collections import defaultdict

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from ..checkpoint import CheckpointResumeError
from ..gateway_model import _tool_result_metadata
from .messages import normalize_plan_steps as _normalize_plan_steps
class CapabilityBoundaryMiddleware(AgentMiddleware):
    """Apply bounded recovery without stopping the whole agent run."""

    CAPABILITY_CORRECTION_LIMIT = 4
    TOOL_BUDGET_ERRORS = {
        "ARTIFACT_CALL_LIMIT",
        "ARTIFACT_REPEATED_CALL",
        "ARTIFACT_STALLED",
        "SAVED_OUTPUT_INSPECTION_CALL_LIMIT",
        "STRUCTURED_ANALYSIS_CALL_LIMIT",
        "STRUCTURED_VALIDATION_CALL_LIMIT",
        "TRANSFORM_CALL_LIMIT",
    }

    def __init__(
        self,
        emit_event=None,
        required_capabilities=None,
        require_initial_plan=False,
        on_state_change=None,
    ):
        self.emit_event = emit_event
        self.required_capabilities = set(required_capabilities or [])
        self.require_initial_plan = require_initial_plan
        self.on_state_change = on_state_change
        self.initial_plan_exists = False
        self.blocked_tools = set()
        self.blocked_capabilities = set()
        self.failure_counts = defaultdict(int)
        self.capability_failure_counts = defaultdict(int)
        self.capability_correction_counts = defaultdict(int)
        self.success_count = 0
        self.successful_capabilities = set()
        self.successful_evidence = []
        self.failed_capabilities = set()
        self.recovered_capabilities = set()
        self.correction_recovery_count = 0
        self.alternative_recovery_count = 0
        self.termination_detail = {}
        self.exhaustion_details = []
        self.failure_records = {}

    def export_state(self):
        """Return a JSON-safe snapshot of execution-gate state."""

        return {
            "initial_plan_exists": self.initial_plan_exists,
            "blocked_tools": sorted(self.blocked_tools),
            "blocked_capabilities": sorted(self.blocked_capabilities),
            "failure_counts": [
                [*key, count]
                for key, count in sorted(self.failure_counts.items())
            ],
            "capability_failure_counts": dict(
                self.capability_failure_counts
            ),
            "capability_correction_counts": dict(
                self.capability_correction_counts
            ),
            "success_count": self.success_count,
            "successful_capabilities": sorted(
                self.successful_capabilities
            ),
            "successful_evidence": [
                dict(item) for item in self.successful_evidence
            ],
            "failed_capabilities": sorted(self.failed_capabilities),
            "recovered_capabilities": sorted(
                self.recovered_capabilities
            ),
            "correction_recovery_count": self.correction_recovery_count,
            "alternative_recovery_count": self.alternative_recovery_count,
            "termination_detail": dict(self.termination_detail),
            "exhaustion_details": list(self.exhaustion_details),
            "failure_records": [
                [*key, detail]
                for key, detail in self.failure_records.items()
            ],
        }

    def restore_state(self, state):
        """Restore a previously exported execution-gate snapshot."""

        if not isinstance(state, dict):
            raise CheckpointResumeError(
                "Resume checkpoint has invalid execution-gate state."
            )
        try:
            self.initial_plan_exists = bool(
                state.get("initial_plan_exists", False)
            )
            self.blocked_tools = set(state.get("blocked_tools") or [])
            self.blocked_capabilities = set(
                state.get("blocked_capabilities") or []
            )
            self.failure_counts = defaultdict(
                int,
                {
                    tuple(item[:3]): int(item[3])
                    for item in state.get("failure_counts") or []
                },
            )
            self.capability_failure_counts = defaultdict(
                int,
                state.get("capability_failure_counts") or {},
            )
            self.capability_correction_counts = defaultdict(
                int,
                state.get("capability_correction_counts") or {},
            )
            self.success_count = int(state.get("success_count") or 0)
            self.successful_capabilities = set(
                state.get("successful_capabilities") or []
            )
            self.successful_evidence = [
                dict(item)
                for item in state.get("successful_evidence") or []
            ]
            self.failed_capabilities = set(
                state.get("failed_capabilities") or []
            )
            self.recovered_capabilities = set(
                state.get("recovered_capabilities") or []
            )
            self.correction_recovery_count = int(
                state.get("correction_recovery_count") or 0
            )
            self.alternative_recovery_count = int(
                state.get("alternative_recovery_count") or 0
            )
            self.termination_detail = dict(
                state.get("termination_detail") or {}
            )
            self.exhaustion_details = list(
                state.get("exhaustion_details") or []
            )
            self.failure_records = {
                tuple(item[:3]): dict(item[3])
                for item in state.get("failure_records") or []
            }
        except (TypeError, ValueError, IndexError) as exc:
            raise CheckpointResumeError(
                "Resume checkpoint has invalid execution-gate state."
            ) from exc

    def _notify_state_change(self):
        if self.on_state_change is not None:
            self.on_state_change(self.export_state())

    @property
    def warning_count(self):
        """Return the number of warning-only request failures."""

        return sum(
            1
            for detail in self.failure_records.values()
            if detail.get("scope") == "warning"
        )

    @property
    def outcome(self):
        """Return the user-facing business outcome for this run."""

        if not self.termination_detail:
            return "completed"
        return "partial" if self.success_count else "blocked"

    @staticmethod
    def _tool_name(request):
        tool_call = request.tool_call or {}
        return str(
            tool_call.get("name")
            or getattr(request.tool, "name", None)
            or "tool"
        )

    @staticmethod
    def _capability_name(tool_name):
        if tool_name.startswith("mcp__") or tool_name == "tool_search":
            return "mcp"
        if tool_name.startswith("run_skill") or tool_name == "call_skill_api":
            return "skill"
        if "workspace" in tool_name or tool_name in {
            "find_files",
            "git_diff",
            "git_log",
            "summarize_recent_changes",
        }:
            return "workspace"
        if tool_name == "save_deliverable":
            return "artifact_delivery"
        return "tool"

    @classmethod
    def _evidence_capability(cls, tool_name):
        """Return the business capability proven by a tool result."""

        capability = cls._capability_name(tool_name)
        if tool_name == "tool_search" or capability == "tool":
            return None
        return capability

    @staticmethod
    def _parse_result(result):
        content = getattr(result, "content", None)
        if not isinstance(content, str):
            return None
        try:
            value = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _normalized_arguments(request):
        tool_call = request.tool_call or {}
        arguments = tool_call.get("args") or {}
        try:
            normalized = json.dumps(
                arguments,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError):
            normalized = str(arguments)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _record_recovery(self, capability, tool_name):
        pending = self.failed_capabilities - self.recovered_capabilities
        recovery_type = None
        recovered_capabilities = set()
        if capability in pending:
            self.correction_recovery_count += 1
            self.recovered_capabilities.add(capability)
            recovery_type = "corrected_request"
            recovered_capabilities.add(capability)
        else:
            alternatives = (
                pending & self.required_capabilities
            ) - {capability}
            if capability in self.required_capabilities and alternatives:
                self.alternative_recovery_count += 1
                self.recovered_capabilities.update(alternatives)
                recovery_type = "alternative_capability"
                recovered_capabilities.update(alternatives)
        for detail in self.failure_records.values():
            if (
                detail.get("capability") in recovered_capabilities
                and detail.get("scope") == "unresolved"
            ):
                detail["scope"] = "recovered"
                detail["affects_required_evidence"] = False
        if recovery_type is None:
            recovered = [
                detail
                for detail in self.failure_records.values()
                if detail.get("capability") == capability
                and detail.get("tool") == tool_name
                and detail.get("scope") == "warning"
            ]
            if recovered:
                for detail in recovered:
                    detail["scope"] = "recovered"
                    detail["affects_required_evidence"] = False
                self.correction_recovery_count += 1
                recovery_type = "corrected_request"
        if recovery_type and self.emit_event is not None:
            self.emit_event(
                "deepagents.capability.recovered",
                {
                    "capability": capability,
                    "recovery_type": recovery_type,
                    "correction_recovery_count": (
                        self.correction_recovery_count
                    ),
                    "alternative_recovery_count": (
                        self.alternative_recovery_count
                    ),
                },
            )

    @staticmethod
    def _evidence_source(capability, tool_name, request):
        """Return a secret-safe source label for verified evidence."""

        tool_call = request.tool_call or {}
        arguments = tool_call.get("args") or {}
        if capability == "skill" and isinstance(arguments, dict):
            skill = str(arguments.get("skill") or "").strip()[:128]
            if skill:
                return f"skill:{skill}"
        return tool_name

    def _record_success(self, capability, tool_name, request):
        if capability is None:
            return
        self.success_count += 1
        self.successful_capabilities.add(capability)
        self.successful_evidence.append(
            {
                "capability": capability,
                "tool": tool_name,
                "source": self._evidence_source(
                    capability,
                    tool_name,
                    request,
                ),
                "request_sha256": self._normalized_arguments(request),
            }
        )
        self._record_recovery(capability, tool_name)

    def _record_warning(self, key, capability, error_type, tool_name):
        detail = {
            "capability": capability,
            "error_type": error_type,
            "tool": tool_name,
            "scope": "warning",
            "required": capability in self.required_capabilities,
            "affects_required_evidence": False,
        }
        self.failure_records[key] = detail
        if self.emit_event is not None:
            self.emit_event("deepagents.capability.warning", dict(detail))

    def failure_diagnostics(self, required_capabilities, outcome):
        """Return secret-safe terminal failure scope diagnostics."""

        required = set(required_capabilities or [])
        failures = []
        for detail in self.failure_records.values():
            item = dict(detail)
            item["required"] = item.get("capability") in required
            item["affects_required_evidence"] = bool(
                item["required"]
                and item.get("scope") == "unresolved"
                and outcome != "completed"
            )
            failures.append(item)
        return {
            "unresolved_failure_count": sum(
                item.get("scope") == "unresolved" for item in failures
            ),
            "recovered_failure_count": sum(
                item.get("scope") == "recovered" for item in failures
            ),
            "warning_count": sum(
                item.get("scope") == "warning" for item in failures
            ),
            "failures": failures[:12],
        }

    @staticmethod
    def _is_non_idempotent_write(request):
        metadata = getattr(request.tool, "metadata", None) or {}
        if not isinstance(metadata, dict):
            return False
        is_write = (
            metadata.get("operation") == "write"
            or metadata.get("read_only") is False
            or metadata.get("side_effects") is True
        )
        if not is_write:
            return False
        return metadata.get("idempotent") is not True

    def _failure_budget(self, request, error_type):
        if error_type == "transient" and self._is_non_idempotent_write(
            request
        ):
            return 1
        if error_type in {"transient", "request", "tool"}:
            return 2
        return 1

    @staticmethod
    def _recovery_message(error_type):
        if error_type == "configuration":
            return "Ask an administrator to configure or authorize it."
        if error_type == "policy":
            return "Continue from the evidence already collected."
        if error_type == "transient":
            return "Retry later or use another available capability."
        if error_type == "request":
            return "Provide the missing or corrected input, then retry."
        return "Use another available capability or contact an administrator."

    def _record_result(self, request, result):
        tool_name = self._tool_name(request)
        capability = self._evidence_capability(tool_name)
        payload = self._parse_result(result)
        if payload is None or "ok" not in payload:
            if not tool_name.startswith("mcp__"):
                return result
            if getattr(result, "status", None) != "error":
                self._record_success("mcp", tool_name, request)
                return result
            payload = {"ok": False, "error": "MCP_TOOL_FAILED"}
        if payload.get("ok") is True:
            self._record_success(capability, tool_name, request)
            if payload.get("call_budget_exhausted") is True:
                self.blocked_tools.add(tool_name)
            return result
        if str(payload.get("error") or "") in self.TOOL_BUDGET_ERRORS:
            self.blocked_tools.add(tool_name)
            key = (
                tool_name,
                "policy",
                self._normalized_arguments(request),
            )
            self._record_warning(key, capability, "policy", tool_name)
            return result
        if capability is None:
            return result

        metadata = _tool_result_metadata(payload, tool_name)
        error_type = metadata.get("error_type") or "tool"
        key = (
            tool_name,
            error_type,
            self._normalized_arguments(request),
        )
        self.failure_counts[key] += 1
        self.capability_failure_counts[capability] += 1
        if error_type in {"request", "tool"}:
            self.capability_correction_counts[capability] += 1
        exact_failures = self.failure_counts[key]
        capability_failures = self.capability_failure_counts[capability]
        capability_corrections = self.capability_correction_counts[
            capability
        ]
        block_capability = error_type in {"configuration", "policy"}
        if error_type in {"request", "tool"}:
            block_capability = block_capability or (
                capability_corrections
                >= self.CAPABILITY_CORRECTION_LIMIT
            )
        block_tool = exact_failures >= self._failure_budget(
            request,
            error_type,
        )
        if not block_capability and not block_tool:
            self._record_warning(key, capability, error_type, tool_name)
            return result

        self.failed_capabilities.add(capability)
        self.recovered_capabilities.discard(capability)

        if block_capability:
            self.blocked_capabilities.add(capability)
            blocked_scope = "capability"
        else:
            self.blocked_tools.add(tool_name)
            blocked_scope = "tool"
        detail = {
            "reason": "execution_failed",
            "capability": capability,
            "error_type": error_type,
            "tool": tool_name,
            "recovery": self._recovery_message(error_type),
        }
        self.failure_records[key] = {
            "capability": capability,
            "error_type": error_type,
            "tool": tool_name,
            "scope": "unresolved",
            "required": capability in self.required_capabilities,
            "affects_required_evidence": (
                capability in self.required_capabilities
            ),
        }
        self.exhaustion_details.append(detail)
        if not self.termination_detail:
            self.termination_detail = detail
        if self.emit_event is not None:
            self.emit_event(
                "deepagents.capability.exhausted",
                {
                    **detail,
                    "blocked_scope": blocked_scope,
                    "exact_request_failures": exact_failures,
                    "capability_failures": capability_failures,
                    "capability_corrections": capability_corrections,
                },
            )
        return result

    def _deny_blocked_call(self, request):
        tool_call = request.tool_call or {}
        return ToolMessage(
            content=json.dumps(
                {
                    "ok": False,
                    "error": "CAPABILITY_BLOCKED",
                    "message": (
                        "This capability reached its recovery limit. "
                        "Use existing evidence and finish the answer."
                    ),
                }
            ),
            name=self._tool_name(request),
            status="error",
            tool_call_id=tool_call.get("id") or "capability-blocked",
        )

    def _requires_initial_plan(self, tool_name):
        if not self.require_initial_plan or self.initial_plan_exists:
            return False
        business_helpers = {
            "analyze_structured_output",
            "inspect_saved_output",
            "run_skill_transform",
        }
        return (
            self._evidence_capability(tool_name) is not None
            or tool_name in business_helpers
        )

    def _deny_unplanned_call(self, request):
        tool_name = self._tool_name(request)
        if self.emit_event is not None:
            self.emit_event(
                "deepagents.plan.required",
                {"tool": tool_name, "blocked_scope": "invocation"},
            )
        tool_call = request.tool_call or {}
        return ToolMessage(
            content=json.dumps(
                {
                    "ok": False,
                    "error": "INITIAL_PLAN_REQUIRED",
                    "message": (
                        "Call write_todos with the initial execution plan "
                        "before any business tool."
                    ),
                }
            ),
            name=tool_name,
            status="error",
            tool_call_id=(
                tool_call.get("id") or "initial-plan-required"
            ),
        )

    def _observe_plan_call(self, request, result):
        if self._tool_name(request) != "write_todos":
            return
        if getattr(result, "status", None) == "error":
            return
        arguments = (request.tool_call or {}).get("args") or {}
        if _normalize_plan_steps(arguments.get("todos")):
            self.initial_plan_exists = True

    def _filter_tools(self, tools):
        return [
            tool
            for tool in tools
            if getattr(tool, "name", None) not in self.blocked_tools
            and self._capability_name(getattr(tool, "name", ""))
            not in self.blocked_capabilities
        ]

    def _is_blocked(self, tool_name):
        return (
            tool_name in self.blocked_tools
            or self._capability_name(tool_name)
            in self.blocked_capabilities
        )

    def wrap_model_call(self, request, handler):
        """Hide exhausted tools from subsequent model requests."""

        request = request.override(tools=self._filter_tools(request.tools))
        return handler(request)

    async def awrap_model_call(self, request, handler):
        """Hide exhausted tools from asynchronous model requests."""

        request = request.override(tools=self._filter_tools(request.tools))
        return await handler(request)

    def wrap_tool_call(self, request, handler):
        """Classify one synchronous tool result and enforce its budget."""

        tool_name = self._tool_name(request)
        if self._requires_initial_plan(tool_name):
            return self._deny_unplanned_call(request)
        if self._is_blocked(tool_name):
            return self._deny_blocked_call(request)
        result = handler(request)
        self._observe_plan_call(request, result)
        result = self._record_result(request, result)
        self._notify_state_change()
        return result

    async def awrap_tool_call(self, request, handler):
        """Classify one asynchronous tool result and enforce its budget."""

        tool_name = self._tool_name(request)
        if self._requires_initial_plan(tool_name):
            return self._deny_unplanned_call(request)
        if self._is_blocked(tool_name):
            return self._deny_blocked_call(request)
        result = await handler(request)
        self._observe_plan_call(request, result)
        result = self._record_result(request, result)
        self._notify_state_change()
        return result
