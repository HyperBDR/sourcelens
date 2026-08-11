"""Admin observability views and helpers for Q&A runs."""

from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from agentcore_metering.adapters.django.models import LLMUsage

from accounts.permissions import HasRequiredFeature
from lens.attachments import get_session_image_attachments
from lens.document_attachments import (
    document_attachment_response,
    get_run_document_attachments,
)
from lens.models import Run
from lens.runtime_events import (
    sanitize_loaded_mcps,
    sanitize_loaded_skills,
    sanitize_termination_detail,
)
from lens.serializers import (
    MessageAttachmentSerializer,
    RunOutputFileSerializer,
)


def _admin_safe_int(value, default, *, minimum=1, maximum=None):
    """Return a clamped positive int parsed from a query value."""

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(parsed, maximum)
    return parsed


def _admin_run_duration(run):
    """Return execution seconds (started -> finished) or None."""

    if run.started_at and run.finished_at:
        return round((run.finished_at - run.started_at).total_seconds(), 1)
    return None


def _admin_step_detail(step):
    """Return a mapping and object-only events from persisted step data."""

    detail = step.detail if isinstance(step.detail, dict) else {}
    events = detail.get("events")
    if not isinstance(events, list):
        events = []
    return detail, [event for event in events if isinstance(event, dict)]


def _admin_run_step_counts(run):
    """Aggregate event/subagent/LLM counts and token usage from steps."""

    counts = {
        "event_count": 0,
        "subagent_count": 0,
        "subagent_denied_count": 0,
        "artifact_calls": 0,
        "artifact_call_limit_hits": 0,
        "structured_analysis_calls": 0,
        "structured_analysis_limit_hits": 0,
        "structured_analysis_max_calls": None,
        "structured_validation_calls": 0,
        "structured_validation_limit_hits": 0,
        "structured_validation_max_calls": None,
        "transform_calls": 0,
        "transform_call_limit_hits": 0,
        "llm_calls": 0,
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "planned_evidence": {},
    }
    total_cost = 0.0
    has_cost = False
    for step in run.steps.all():
        detail, events = _admin_step_detail(step)
        for event in events:
            counts["event_count"] += 1
            agent_event = event.get("agent_event")
            if agent_event == "tool.task.invoke":
                counts["subagent_count"] += 1
            elif agent_event == "tool.task.denied":
                counts["subagent_denied_count"] += 1
            elif agent_event == "tool.run_skill_artifact.start":
                counts["artifact_calls"] += 1
            elif agent_event == (
                "tool.run_skill_artifact.budget_exceeded"
            ):
                counts["artifact_call_limit_hits"] += 1
            elif agent_event == "tool.analyze_structured_output.start":
                if event.get("operation") == "validate_records":
                    prefix = "structured_validation"
                else:
                    prefix = "structured_analysis"
                counts[f"{prefix}_calls"] += 1
                try:
                    max_calls = max(int(event.get("max_calls") or 0), 0)
                except (TypeError, ValueError):
                    max_calls = 0
                if max_calls:
                    counts[f"{prefix}_max_calls"] = max_calls
            elif agent_event == (
                "tool.analyze_structured_output.budget_exceeded"
            ):
                if event.get("operation") == "validate_records":
                    prefix = "structured_validation"
                else:
                    prefix = "structured_analysis"
                counts[f"{prefix}_limit_hits"] += 1
                try:
                    max_calls = max(int(event.get("max_calls") or 0), 0)
                except (TypeError, ValueError):
                    max_calls = 0
                if max_calls:
                    counts[f"{prefix}_max_calls"] = max_calls
            elif agent_event == "tool.run_skill_transform.start":
                counts["transform_calls"] += 1
            elif agent_event == (
                "tool.run_skill_transform.budget_exceeded"
            ):
                counts["transform_call_limit_hits"] += 1
            elif agent_event == "llm.response":
                counts["llm_calls"] += 1
                counts["total_tokens"] += event.get("total_tokens") or 0
                counts["prompt_tokens"] += event.get("prompt_tokens") or 0
                counts["completion_tokens"] += (
                    event.get("completion_tokens") or 0
                )
                cost = event.get("cost")
                if cost:
                    total_cost += cost
                    has_cost = True
            elif agent_event == "planned_evidence.metrics":
                counts["planned_evidence"] = {
                    key: event.get(key)
                    for key in (
                        "plan_version",
                        "planned_operation_count",
                        "planned_codegraph_operations",
                        "model_call_count",
                        "retrieval_call_count",
                        "codegraph_call_count",
                        "literal_search_call_count",
                        "file_read_call_count",
                        "evidence_tokens",
                        "evidence_item_count",
                        "evidence_files",
                        "deduplicated_item_count",
                        "fallback_rounds",
                        "evidence_gap_count",
                        "citation_count",
                        "unsupported_claim_count",
                        "citation_coverage_ratio",
                        "sufficient",
                        "gap_categories",
                    )
                    if key in event
                }
        # Control-plane preprocess calls (query rewrite, vision intent)
        # record their usage on the step itself, not as node events.
        usage = detail.get("usage")
        if usage:
            counts["llm_calls"] += 1
            counts["total_tokens"] += usage.get("total_tokens") or 0
            counts["prompt_tokens"] += usage.get("prompt_tokens") or 0
            counts["completion_tokens"] += usage.get("completion_tokens") or 0
            cost = usage.get("cost")
            if cost:
                total_cost += cost
                has_cost = True
    counts["subagent_count"] = max(
        0,
        counts["subagent_count"] - counts["subagent_denied_count"],
    )
    counts["total_cost"] = round(total_cost, 6) if has_cost else None
    return counts


def _duration_ms(started_at, finished_at):
    """Return non-negative elapsed milliseconds or None."""

    if not started_at or not finished_at:
        return None
    return max(0, round((finished_at - started_at).total_seconds() * 1000))


def _admin_run_model_usage(run):
    """Return metered model calls correlated to one Run UUID."""

    usages = LLMUsage.objects.filter(
        metadata__run_uuid=str(run.uuid),
    ).order_by("created_at")
    calls = []
    total_cost = 0.0
    has_cost = False
    for usage in usages:
        metadata = usage.metadata or {}
        if usage.cost is not None:
            total_cost += float(usage.cost)
            has_cost = True
        calls.append({
            "uuid": str(usage.id),
            "model": usage.model,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "cached_tokens": usage.cached_tokens,
            "reasoning_tokens": usage.reasoning_tokens,
            "cost": float(usage.cost) if usage.cost is not None else None,
            "cost_currency": usage.cost_currency,
            "success": usage.success,
            "is_streaming": usage.is_streaming,
            "is_subagent": bool(metadata.get("is_subagent")),
            "source_type": metadata.get("source_type"),
            "started_at": (
                usage.started_at.isoformat() if usage.started_at else None
            ),
            "finished_at": usage.created_at.isoformat(),
            "duration_ms": _duration_ms(
                usage.started_at,
                usage.created_at,
            ),
            "ttft_ms": _duration_ms(
                usage.started_at,
                usage.first_chunk_at,
            ),
        })
    if not calls:
        return None
    return {
        "llm_calls": len(calls),
        "models_used": list(
            dict.fromkeys(
                item["model"] for item in calls if item["model"]
            )
        ),
        "subagent_model_calls": sum(
            1 for item in calls if item["is_subagent"]
        ),
        "total_tokens": sum(item["total_tokens"] for item in calls),
        "prompt_tokens": sum(item["prompt_tokens"] for item in calls),
        "completion_tokens": sum(
            item["completion_tokens"] for item in calls
        ),
        "cached_tokens": sum(item["cached_tokens"] for item in calls),
        "reasoning_tokens": sum(
            item["reasoning_tokens"] for item in calls
        ),
        "total_cost": round(total_cost, 6) if has_cost else None,
        "model_calls": calls,
    }


def _admin_run_failure_summary(run):
    """Return safe terminal failure-scope diagnostics from Run events."""

    empty = {
        "unresolved_failure_count": 0,
        "recovered_failure_count": 0,
        "warning_count": 0,
        "failures": [],
    }
    allowed_capabilities = {
        "artifact_delivery",
        "mcp",
        "skill",
        "tool",
        "workspace",
    }
    allowed_error_types = {
        "capability",
        "configuration",
        "policy",
        "request",
        "tool",
        "transient",
        "verification",
    }
    allowed_scopes = {"recovered", "unresolved", "warning"}
    outcome_event = None
    for step in run.steps.all():
        _detail, events = _admin_step_detail(step)
        for event in events:
            if event.get("agent_event") == "deepagents.runtime.outcome":
                outcome_event = event
    if outcome_event is None:
        return empty

    summary = {}
    for key in (
        "unresolved_failure_count",
        "recovered_failure_count",
        "warning_count",
    ):
        try:
            summary[key] = max(int(outcome_event.get(key) or 0), 0)
        except (TypeError, ValueError):
            summary[key] = 0
    failure_items = outcome_event.get("failures")
    if not isinstance(failure_items, list):
        failure_items = []
    failures = []
    for item in failure_items[:12]:
        if not isinstance(item, dict):
            continue
        capability = item.get("capability")
        error_type = item.get("error_type")
        scope = item.get("scope")
        if (
            capability not in allowed_capabilities
            or error_type not in allowed_error_types
            or scope not in allowed_scopes
        ):
            continue
        failures.append({
            "capability": capability,
            "error_type": error_type,
            "scope": scope,
            "required": item.get("required") is True,
            "affects_required_evidence": (
                item.get("affects_required_evidence") is True
            ),
        })
    summary["failures"] = failures
    return summary


def _admin_run_row(run):
    """Serialize one run for the observability list."""

    session = run.session
    user = session.user if session else None
    assistant = session.assistant if session else None
    question = (run.input_message.content if run.input_message else "") or ""
    counts = _admin_run_step_counts(run)
    execution = run.execution if hasattr(run, "execution") else None
    return {
        "uuid": str(run.uuid),
        "status": run.status,
        "executor_status": execution.status if execution else run.status,
        "outcome": run.outcome,
        "termination_detail": sanitize_termination_detail(
            run.termination_detail
        ),
        "username": user.username if user else None,
        "assistant_name": assistant.name if assistant else None,
        "assistant_slug": assistant.slug if assistant else None,
        "question": question[:160],
        "feedback": run.feedback,
        "feedback_updated_at": (
            run.feedback_updated_at.isoformat()
            if run.feedback_updated_at
            else None
        ),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": (
            run.finished_at.isoformat() if run.finished_at else None
        ),
        "duration_seconds": _admin_run_duration(run),
        "lensnode_name": run.lensnode.name if run.lensnode else None,
        "event_count": counts["event_count"],
        "subagent_count": counts["subagent_count"],
        "subagent_denied_count": counts["subagent_denied_count"],
        "artifact_calls": counts["artifact_calls"],
        "artifact_call_limit_hits": counts[
            "artifact_call_limit_hits"
        ],
        "structured_analysis_calls": counts["structured_analysis_calls"],
        "structured_analysis_limit_hits": counts[
            "structured_analysis_limit_hits"
        ],
        "structured_analysis_max_calls": counts[
            "structured_analysis_max_calls"
        ],
        "structured_validation_calls": counts[
            "structured_validation_calls"
        ],
        "structured_validation_limit_hits": counts[
            "structured_validation_limit_hits"
        ],
        "structured_validation_max_calls": counts[
            "structured_validation_max_calls"
        ],
        "transform_calls": counts["transform_calls"],
        "transform_call_limit_hits": counts[
            "transform_call_limit_hits"
        ],
        "llm_calls": counts["llm_calls"],
        "total_tokens": counts["total_tokens"],
        "prompt_tokens": counts["prompt_tokens"],
        "completion_tokens": counts["completion_tokens"],
        "total_cost": counts["total_cost"],
        "planned_evidence": counts["planned_evidence"],
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _admin_run_detail(run):
    """Serialize a run with full Q&A, timeline and execution snapshot."""

    row = _admin_run_row(run)
    out = run.output_message
    assistant = run.session.assistant if run.session else None
    execution = run.execution if hasattr(run, "execution") else None
    agent_rounds = execution.agent_rounds if execution else None
    if agent_rounds is None and assistant:
        agent_rounds = assistant.agent_rounds
    model_usage = _admin_run_model_usage(run)
    steps = []
    for step in run.steps.all():
        detail, events = _admin_step_detail(step)
        item = {
            "step_type": step.step_type,
            "status": step.status,
            "sequence": step.sequence,
            "events": events,
            "usage": detail.get("usage"),
            "updated_at": (
                step.updated_at.isoformat() if step.updated_at else None
            ),
        }
        if step.step_type == "multimodal":
            item["multimodal"] = {
                "query": detail.get("query"),
                "image_count": detail.get("image_count"),
                "rewritten": detail.get("rewritten"),
            }
        steps.append(item)
    attachments = []
    if run.input_message:
        selected = (
            run.execution.runtime_snapshot or {}
        ).get("session_attachment_uuids", [])
        selected_images = get_session_image_attachments(
            run.session,
            selected,
        )
        if selected:
            attachments = MessageAttachmentSerializer(
                selected_images,
                many=True,
            ).data
        else:
            attachments = MessageAttachmentSerializer(
                run.input_message.attachments.all(),
                many=True,
            ).data
    attachments.extend(
        document_attachment_response(item)
        for item in get_run_document_attachments(
            run.uuid,
            fail_silently=True,
        )
    )
    output_files = RunOutputFileSerializer(
        run.output_files.all(), many=True
    ).data
    row.update({
        "question": (
            run.input_message.content if run.input_message else ""
        ) or "",
        "attachments": attachments,
        "answer": (out.content if out else "") or "",
        "output_files": output_files,
        "error": run.error or "",
        "agent_rounds": agent_rounds,
        "failure_summary": _admin_run_failure_summary(run),
        "steps": steps,
        "execution": {
            "task": execution.task,
            "status": execution.status,
            "target_dirs": execution.target_dirs,
            "loaded_skills": sanitize_loaded_skills(
                execution.loaded_skills
            ),
            "loaded_mcps": sanitize_loaded_mcps(execution.loaded_mcps),
        } if execution else None,
    })
    if model_usage:
        row.update(model_usage)
    else:
        row.update({
            "cached_tokens": 0,
            "reasoning_tokens": 0,
            "subagent_model_calls": 0,
            "models_used": [],
            "model_calls": [],
        })
    return row


class AdminRunListView(APIView):
    """Admin-only cross-user list of Q&A runs for observability."""

    permission_classes = [HasRequiredFeature]
    required_feature = "admin_console"

    def get(self, request):
        """Return a filtered, paginated list of runs."""

        params = request.query_params
        page = _admin_safe_int(params.get("page"), 1)
        page_size = _admin_safe_int(params.get("page_size"), 20, maximum=100)
        qs = (
            Run.objects.select_related(
                "session__user",
                "session__assistant",
                "input_message",
                "lensnode",
                "execution",
            )
            .prefetch_related("steps")
            .order_by("-created_at")
        )
        username = (params.get("username") or "").strip()
        if username:
            qs = qs.filter(session__user__username__icontains=username)
        user_id = (params.get("user_id") or "").strip()
        if user_id:
            qs = qs.filter(session__user_id=user_id)
        group_id = (params.get("group_id") or "").strip()
        if group_id:
            qs = qs.filter(session__user__groups__id=group_id).distinct()
        assistant = (params.get("assistant") or "").strip()
        if assistant:
            qs = qs.filter(session__assistant__slug=assistant)
        run_status = (params.get("status") or "").strip()
        if run_status:
            qs = qs.filter(status=run_status)
        keyword = (params.get("q") or "").strip()
        if keyword:
            qs = qs.filter(input_message__content__icontains=keyword)
        start_date = parse_date((params.get("start_date") or "").strip())
        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)
        end_date = parse_date((params.get("end_date") or "").strip())
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)

        total = qs.count()
        start = (page - 1) * page_size
        rows = [_admin_run_row(run) for run in qs[start:start + page_size]]
        return Response({
            "results": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
        })


class AdminRunDetailView(APIView):
    """Admin-only full trace of a single Q&A run."""

    permission_classes = [HasRequiredFeature]
    required_feature = "admin_console"

    def get(self, request, uuid):
        """Return the full trace for one run."""

        try:
            run = (
                Run.objects.select_related(
                    "session__user",
                    "session__assistant",
                    "input_message",
                    "output_message",
                    "lensnode",
                    "execution",
                )
                .prefetch_related("output_files", "steps")
                .get(uuid=uuid)
            )
        except Run.DoesNotExist:
            return Response(
                {"detail": "Run not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(_admin_run_detail(run))
