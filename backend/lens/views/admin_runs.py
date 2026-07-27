"""Admin observability views and helpers for Q&A runs."""

from django.utils.dateparse import parse_date
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from lens.models import Run
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


def _admin_run_step_counts(run):
    """Aggregate event/subagent/LLM counts and token usage from steps."""

    counts = {
        "event_count": 0,
        "subagent_count": 0,
        "llm_calls": 0,
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }
    total_cost = 0.0
    has_cost = False
    for step in run.steps.all():
        detail = step.detail or {}
        for event in detail.get("events", []):
            counts["event_count"] += 1
            agent_event = event.get("agent_event")
            if agent_event == "tool.task.invoke":
                counts["subagent_count"] += 1
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
    counts["total_cost"] = round(total_cost, 6) if has_cost else None
    return counts


def _admin_run_row(run):
    """Serialize one run for the observability list."""

    session = run.session
    user = session.user if session else None
    assistant = session.assistant if session else None
    question = (run.input_message.content if run.input_message else "") or ""
    counts = _admin_run_step_counts(run)
    return {
        "uuid": str(run.uuid),
        "status": run.status,
        "username": user.username if user else None,
        "assistant_name": assistant.name if assistant else None,
        "assistant_slug": assistant.slug if assistant else None,
        "question": question[:160],
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": (
            run.finished_at.isoformat() if run.finished_at else None
        ),
        "duration_seconds": _admin_run_duration(run),
        "lensnode_name": run.lensnode.name if run.lensnode else None,
        "event_count": counts["event_count"],
        "subagent_count": counts["subagent_count"],
        "llm_calls": counts["llm_calls"],
        "total_tokens": counts["total_tokens"],
        "prompt_tokens": counts["prompt_tokens"],
        "completion_tokens": counts["completion_tokens"],
        "total_cost": counts["total_cost"],
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _admin_run_detail(run):
    """Serialize a run with full Q&A, timeline and execution snapshot."""

    row = _admin_run_row(run)
    out = run.output_message
    assistant = run.session.assistant if run.session else None
    execution = run.execution if hasattr(run, "execution") else None
    steps = []
    for step in run.steps.all():
        detail = step.detail or {}
        item = {
            "step_type": step.step_type,
            "status": step.status,
            "sequence": step.sequence,
            "events": detail.get("events", []),
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
    attachments = (
        MessageAttachmentSerializer(
            run.input_message.attachments.all(), many=True
        ).data
        if run.input_message
        else []
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
        "agent_rounds": assistant.agent_rounds if assistant else None,
        "steps": steps,
        "execution": {
            "task": execution.task,
            "target_dirs": execution.target_dirs,
            "loaded_skills": execution.loaded_skills,
            "loaded_mcps": execution.loaded_mcps,
        } if execution else None,
    })
    return row


class AdminRunListView(APIView):
    """Admin-only cross-user list of Q&A runs for observability."""

    permission_classes = [permissions.IsAdminUser]

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
            )
            .prefetch_related("steps")
            .order_by("-created_at")
        )
        username = (params.get("username") or "").strip()
        if username:
            qs = qs.filter(session__user__username__icontains=username)
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

    permission_classes = [permissions.IsAdminUser]

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
