"""Evidence-backed, read-only diagnostics for terminal Runs."""

import hashlib
import json
import logging
import re
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .llm import run_completion
from .models import (
    GlobalSetting,
    Run,
    RunDiagnostic,
    RunDiagnosticEvidence,
    RunDiagnosticTurn,
)
from .runtime_events import sanitize_termination_detail
from .services import build_run_history_manifest

logger = logging.getLogger(__name__)

TERMINAL_RUN_STATUSES = {
    Run.Status.DONE,
    Run.Status.FAILED,
    Run.Status.CANCELLED,
}
DIAGNOSTIC_PROMPT_VERSION = "run-diagnosis-v1"
MAX_QUESTION_CHARS = 2000
MAX_SUMMARY_CHARS = 4000
MAX_ANSWER_CHARS = 8000
MAX_FINDINGS = 20
MAX_LIST_ITEMS = 20
VALID_SEVERITIES = {"low", "medium", "high", "critical"}
VALID_FINDING_KINDS = {"fact", "hypothesis"}
SAFE_EVENT_FIELDS = {
    "agent_event",
    "status",
    "error_type",
    "scope",
    "capability",
    "required",
    "affects_required_evidence",
    "unresolved_failure_count",
    "recovered_failure_count",
    "warning_count",
}
SAFE_OBSERVATION_FIELDS = {
    "action",
    "id",
    "parent_observation_id",
    "name",
    "status",
    "error_type",
    "started_at",
    "ended_at",
}
SAFE_CODE_PATTERN = re.compile(r"[A-Za-z0-9_.:-]{1,96}")
SAFE_MIME_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9.+-]*/[A-Za-z0-9][A-Za-z0-9.+-]*"
)


class RunDiagnosticStateError(RuntimeError):
    """Raised when a Run or diagnosis cannot accept the requested action."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class DiagnosticResultError(ValueError):
    """Raised when untrusted model output violates the result contract."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


@transaction.atomic
def create_run_diagnostic(run, requested_by, idempotency_key="initial-v1"):
    """Create or return one idempotent diagnosis and immutable evidence."""

    run = (
        Run.objects.select_for_update(of=("self",))
        .select_related(
            "session__assistant",
            "session__user",
            "input_message",
            "output_message",
            "lensnode",
            "execution",
        )
        .prefetch_related("output_files", "steps")
        .get(pk=run.pk)
    )
    if run.status not in TERMINAL_RUN_STATUSES:
        raise RunDiagnosticStateError("RUN_NOT_TERMINAL")

    evidence = _get_or_create_evidence(run)
    model_ref, model_config_hash = _diagnostic_model_snapshot(run)
    diagnostic, created = RunDiagnostic.objects.get_or_create(
        run=run,
        idempotency_key=idempotency_key,
        defaults={
            "evidence": evidence,
            "requested_by": requested_by,
            "model_ref": model_ref,
            "model_config_hash": model_config_hash,
            "prompt_version": DIAGNOSTIC_PROMPT_VERSION,
        },
    )
    should_enqueue = created
    if not created and diagnostic.status == RunDiagnostic.Status.FAILED:
        diagnostic.status = RunDiagnostic.Status.QUEUED
        diagnostic.error_code = ""
        diagnostic.started_at = None
        diagnostic.finished_at = None
        diagnostic.save(
            update_fields=[
                "status",
                "error_code",
                "started_at",
                "finished_at",
                "updated_at",
            ]
        )
        should_enqueue = True
    if should_enqueue:
        transaction.on_commit(
            lambda diagnostic_uuid=diagnostic.uuid: (
                enqueue_run_diagnostic(diagnostic_uuid)
            )
        )
    return diagnostic, should_enqueue


def enqueue_run_diagnostic(diagnostic_uuid):
    """Enqueue one diagnosis without importing Celery during model loading."""

    from .tasks import execute_run_diagnostic

    execute_run_diagnostic.delay(str(diagnostic_uuid))


@transaction.atomic
def create_diagnostic_turn(diagnostic, requested_by, question):
    """Create an idempotent follow-up bound to a completed diagnosis."""

    diagnostic = (
        RunDiagnostic.objects.select_for_update(of=("self",))
        .select_related("evidence", "run")
        .get(pk=diagnostic.pk)
    )
    if diagnostic.status != RunDiagnostic.Status.COMPLETED:
        raise RunDiagnosticStateError("DIAGNOSTIC_NOT_COMPLETED")
    normalized_question = " ".join(str(question or "").split())
    if (
        not normalized_question
        or len(normalized_question) > MAX_QUESTION_CHARS
    ):
        raise ValidationError(
            f"Question must contain 1 to {MAX_QUESTION_CHARS} characters."
        )
    idempotency_key = hashlib.sha256(normalized_question.encode()).hexdigest()
    turn, created = RunDiagnosticTurn.objects.get_or_create(
        diagnostic=diagnostic,
        idempotency_key=idempotency_key,
        defaults={
            "requested_by": requested_by,
            "question": normalized_question,
        },
    )
    if created:
        transaction.on_commit(
            lambda turn_uuid=turn.uuid: enqueue_diagnostic_turn(turn_uuid)
        )
    return turn, created


def enqueue_diagnostic_turn(turn_uuid):
    """Enqueue one controlled follow-up."""

    from .tasks import execute_diagnostic_turn

    execute_diagnostic_turn.delay(str(turn_uuid))


def execute_diagnostic(diagnostic_uuid):
    """Run deterministic checks and one bounded model analysis."""

    diagnostic = _mark_diagnostic_running(diagnostic_uuid)
    if diagnostic is None:
        return False
    findings = _deterministic_findings(diagnostic.run, diagnostic.evidence)
    diagnostic.deterministic_findings = findings
    diagnostic.save(update_fields=["deterministic_findings", "updated_at"])
    try:
        completion = run_completion(
            model_ref=diagnostic.model_ref,
            system=_diagnostic_system_prompt(),
            user=json.dumps(
                {
                    "evidence_snapshot": diagnostic.evidence.payload,
                    "deterministic_findings": findings,
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            node_name="run_diagnostics",
            user_id=diagnostic.requested_by_id,
        )
        result = validate_diagnostic_result(
            _parse_json_object(completion.content),
            diagnostic.evidence,
        )
    except DiagnosticResultError as exc:
        _fail_diagnostic(diagnostic, exc.code)
        return False
    except Exception:
        logger.error(
            "Run diagnosis model call failed: diagnostic_uuid=%s",
            diagnostic.uuid,
        )
        _fail_diagnostic(diagnostic, "MODEL_CALL_FAILED")
        return False

    now = timezone.now()
    diagnostic.status = RunDiagnostic.Status.COMPLETED
    diagnostic.result = result
    diagnostic.usage = completion.usage or {}
    diagnostic.error_code = ""
    diagnostic.finished_at = now
    diagnostic.save(
        update_fields=[
            "status",
            "result",
            "usage",
            "error_code",
            "finished_at",
            "updated_at",
        ]
    )
    return True


def execute_diagnostic_follow_up(turn_uuid):
    """Answer one question using only its bound result and evidence."""

    turn = _mark_turn_running(turn_uuid)
    if turn is None:
        return False
    diagnostic = turn.diagnostic
    try:
        completion = run_completion(
            model_ref=diagnostic.model_ref,
            system=_follow_up_system_prompt(),
            user=json.dumps(
                {
                    "diagnosis": diagnostic.result,
                    "evidence_snapshot": diagnostic.evidence.payload,
                    "question": turn.question,
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            node_name="run_diagnostics_follow_up",
            user_id=turn.requested_by_id,
        )
        result = _validate_follow_up_result(
            _parse_json_object(completion.content),
            diagnostic.evidence,
        )
    except DiagnosticResultError as exc:
        _fail_turn(turn, exc.code)
        return False
    except Exception:
        logger.error(
            "Run diagnosis follow-up failed: turn_uuid=%s",
            turn.uuid,
        )
        _fail_turn(turn, "MODEL_CALL_FAILED")
        return False

    turn.status = RunDiagnosticTurn.Status.COMPLETED
    turn.answer = result["answer"]
    turn.evidence_refs = result["evidence_refs"]
    turn.usage = completion.usage or {}
    turn.error_code = ""
    turn.finished_at = timezone.now()
    turn.save(
        update_fields=[
            "status",
            "answer",
            "evidence_refs",
            "usage",
            "error_code",
            "finished_at",
            "updated_at",
        ]
    )
    return True


def validate_diagnostic_result(result, evidence):
    """Validate and normalize untrusted model diagnosis JSON."""

    if not isinstance(result, dict):
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    summary = _bounded_text(result.get("summary"), MAX_SUMMARY_CHARS)
    severity = result.get("severity")
    if severity not in VALID_SEVERITIES:
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    confidence = _confidence(result.get("confidence"))
    findings = result.get("findings")
    if not isinstance(findings, list) or len(findings) > MAX_FINDINGS:
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    normalized_findings = [
        _validate_finding(item, evidence) for item in findings
    ]
    cause_categories = _short_string_list(
        result.get("cause_categories"),
        MAX_LIST_ITEMS,
    )
    recommendations = _validate_recommendations(
        result.get("recommendations"),
        evidence,
    )
    unknowns = _validate_unknowns(result.get("unknowns"), evidence)
    return {
        "summary": summary,
        "severity": severity,
        "confidence": confidence,
        "findings": normalized_findings,
        "cause_categories": cause_categories,
        "recommendations": recommendations,
        "unknowns": unknowns,
    }


def serialize_diagnostic(diagnostic):
    """Return one diagnosis and its controlled follow-up turns."""

    return {
        "uuid": str(diagnostic.uuid),
        "run_uuid": str(diagnostic.run.uuid),
        "status": diagnostic.status,
        "evidence_uuid": str(diagnostic.evidence.uuid),
        "evidence_hash": diagnostic.evidence.payload_hash,
        "evidence_ids": list(
            (diagnostic.evidence.payload.get("evidence") or {}).keys()
        ),
        "deterministic_findings": diagnostic.deterministic_findings,
        "prompt_version": diagnostic.prompt_version,
        "result": diagnostic.result,
        "usage": diagnostic.usage,
        "error_code": diagnostic.error_code,
        "requested_by": diagnostic.requested_by_id,
        "created_at": diagnostic.created_at.isoformat(),
        "started_at": (
            diagnostic.started_at.isoformat()
            if diagnostic.started_at
            else None
        ),
        "finished_at": (
            diagnostic.finished_at.isoformat()
            if diagnostic.finished_at
            else None
        ),
        "turns": [
            serialize_diagnostic_turn(item) for item in diagnostic.turns.all()
        ],
    }


def serialize_diagnostic_turn(turn):
    """Return one follow-up without exposing model prompts."""

    return {
        "uuid": str(turn.uuid),
        "status": turn.status,
        "question": turn.question,
        "answer": turn.answer,
        "evidence_refs": turn.evidence_refs,
        "usage": turn.usage,
        "error_code": turn.error_code,
        "created_at": turn.created_at.isoformat(),
        "started_at": turn.started_at.isoformat() if turn.started_at else None,
        "finished_at": (
            turn.finished_at.isoformat() if turn.finished_at else None
        ),
    }


def _get_or_create_evidence(run):
    evidence = RunDiagnosticEvidence.objects.filter(run=run).first()
    if evidence is not None:
        return evidence
    return RunDiagnosticEvidence.objects.create(
        run=run,
        schema_version=1,
        payload=_build_evidence_payload(run),
        payload_hash="",
    )


def _build_evidence_payload(run):
    execution = run.execution if hasattr(run, "execution") else None
    runtime_snapshot = execution.runtime_snapshot if execution else {}
    safe_provenance = {
        key: runtime_snapshot.get(key)
        for key in (
            "assistant_uuid",
            "assistant_updated_at",
            "lensnode_uuid",
            "lensnode_agent_version",
            "model_refs",
            "model_config_hashes",
            "settings_hash",
        )
        if key in runtime_snapshot
    }
    evidence = {
        "E-RUN": {
            "kind": "run",
            "data": {
                "run_uuid": str(run.uuid),
                "session_uuid": str(run.session.uuid),
                "retry_of_run_uuid": (
                    str(run.retry_of_run.uuid) if run.retry_of_run_id else None
                ),
                "status": run.status,
                "outcome": run.outcome,
                "error_code": _safe_run_error_code(run.error),
                "termination_detail": sanitize_termination_detail(
                    run.termination_detail
                ),
                "created_at": run.created_at.isoformat(),
                "started_at": (
                    run.started_at.isoformat() if run.started_at else None
                ),
                "finished_at": (
                    run.finished_at.isoformat() if run.finished_at else None
                ),
            },
        },
        "E-HISTORY": {
            "kind": "history_manifest",
            "data": build_run_history_manifest(run),
        },
        "E-EXECUTION": {
            "kind": "execution_snapshot",
            "data": _execution_evidence(execution),
        },
        "E-PROVENANCE": {
            "kind": "provenance",
            "data": safe_provenance,
        },
        "E-USAGE": {
            "kind": "model_usage",
            "data": _usage_evidence(run),
        },
    }
    for index, step in enumerate(run.steps.all(), start=1):
        evidence[f"E-STEP-{index:03d}"] = {
            "kind": "run_step",
            "data": _step_evidence(step),
        }
    for index, output_file in enumerate(run.output_files.all(), start=1):
        evidence[f"E-FILE-{index:03d}"] = {
            "kind": "output_file",
            "data": {
                "file_uuid": str(output_file.uuid),
                "content_type": _safe_content_type(output_file.content_type),
                "byte_size": output_file.byte_size,
                "content_hash": output_file.content_hash,
                "created_at": output_file.created_at.isoformat(),
            },
        }
    missing = []
    if not runtime_snapshot:
        missing.append("runtime_snapshot")
    if not evidence["E-USAGE"]["data"]:
        missing.append("model_usage")
    return {
        "schema_version": 1,
        "target_run_uuid": str(run.uuid),
        "captured_at": timezone.now().isoformat(),
        "evidence": evidence,
        "missing_evidence": missing,
    }


def _execution_evidence(execution):
    if execution is None:
        return None
    return {
        "execution_uuid": str(execution.uuid),
        "status": execution.status,
        "task": execution.task,
        "agent_rounds": execution.agent_rounds,
        "run_timeout_s": execution.run_timeout_s,
        "token_budget": {
            "profile": execution.token_budget_profile,
            "max_tokens": execution.token_budget_max_tokens,
            "final_reserve_tokens": (
                execution.token_budget_final_reserve_tokens
            ),
        },
        "target_dirs_hash": _canonical_hash(execution.target_dirs),
        "skills": _binding_refs(execution.loaded_skills),
        "mcps": _binding_refs(execution.loaded_mcps),
    }


def _binding_refs(items):
    safe = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        safe.append(
            {
                key: item.get(key)
                for key in ("uuid", "name", "version", "content_hash")
                if item.get(key) not in (None, "")
            }
        )
    return safe


def _step_evidence(step):
    detail = step.detail if isinstance(step.detail, dict) else {}
    events = []
    for event in detail.get("events") or []:
        if not isinstance(event, dict):
            continue
        safe_event = {}
        for key in SAFE_EVENT_FIELDS:
            value = _safe_event_value(key, event.get(key))
            if value is not None:
                safe_event[key] = value
        observation = event.get("observation")
        if isinstance(observation, dict):
            safe_observation = {}
            for key in SAFE_OBSERVATION_FIELDS:
                value = _safe_observation_value(key, observation.get(key))
                if value is not None:
                    safe_observation[key] = value
            if safe_observation:
                safe_event["observation"] = safe_observation
        if safe_event:
            events.append(safe_event)
    return {
        "step_uuid": str(step.uuid),
        "step_type": step.step_type,
        "status": step.status,
        "sequence": step.sequence,
        "events": events[:100],
        "updated_at": step.updated_at.isoformat(),
    }


def _usage_evidence(run):
    try:
        from agentcore_metering.adapters.django.models import LLMUsage

        usages = LLMUsage.objects.filter(
            metadata__run_uuid=str(run.uuid)
        ).order_by("created_at")
    except ImportError:
        return []
    return [
        {
            "usage_uuid": str(item.id),
            "model": item.model,
            "prompt_tokens": item.prompt_tokens,
            "completion_tokens": item.completion_tokens,
            "total_tokens": item.total_tokens,
            "success": item.success,
            "started_at": (
                item.started_at.isoformat() if item.started_at else None
            ),
            "finished_at": item.created_at.isoformat(),
        }
        for item in usages
    ]


def _diagnostic_model_snapshot(run):
    configured = (
        GlobalSetting.objects.filter(key="diagnostics.model_ref")
        .values_list("value", flat=True)
        .first()
    )
    runtime_snapshot = getattr(run.execution, "runtime_snapshot", {}) or {}
    model_refs = runtime_snapshot.get("model_refs") or {}
    raw_model_ref = configured or model_refs.get("agent")
    try:
        model_ref = uuid.UUID(str(raw_model_ref)) if raw_model_ref else None
    except (TypeError, ValueError):
        model_ref = None
    config_hashes = runtime_snapshot.get("model_config_hashes") or {}
    if model_ref and str(model_ref) == str(model_refs.get("agent")):
        config_hash = config_hashes.get("agent", "")
    else:
        config_hash = _model_config_hash(model_ref)
    return model_ref, config_hash


def _deterministic_findings(run, evidence):
    findings = [
        {
            "kind": "fact",
            "title": "Terminal Run state",
            "statement": (
                f"The Run finished with executor status {run.status}"
                f" and business outcome {run.outcome or 'unknown'}."
            ),
            "confidence": 1.0,
            "evidence_refs": ["E-RUN"],
        }
    ]
    missing = evidence.payload.get("missing_evidence") or []
    if missing:
        findings.append(
            {
                "kind": "unknown",
                "title": "Missing evidence",
                "statement": ", ".join(str(item) for item in missing),
                "evidence_refs": [],
            }
        )
    return findings


@transaction.atomic
def _mark_diagnostic_running(diagnostic_uuid):
    diagnostic = (
        RunDiagnostic.objects.select_for_update(of=("self",))
        .select_related("run", "evidence", "requested_by")
        .filter(uuid=diagnostic_uuid)
        .first()
    )
    if diagnostic is None:
        return None
    if diagnostic.status in {
        RunDiagnostic.Status.RUNNING,
        RunDiagnostic.Status.COMPLETED,
    }:
        return None
    diagnostic.status = RunDiagnostic.Status.RUNNING
    diagnostic.started_at = timezone.now()
    diagnostic.error_code = ""
    diagnostic.save(
        update_fields=["status", "started_at", "error_code", "updated_at"]
    )
    return diagnostic


@transaction.atomic
def _mark_turn_running(turn_uuid):
    turn = (
        RunDiagnosticTurn.objects.select_for_update(of=("self",))
        .select_related(
            "diagnostic__evidence",
            "diagnostic__run",
            "requested_by",
        )
        .filter(uuid=turn_uuid)
        .first()
    )
    if turn is None or turn.status != RunDiagnosticTurn.Status.QUEUED:
        return None
    turn.status = RunDiagnosticTurn.Status.RUNNING
    turn.started_at = timezone.now()
    turn.error_code = ""
    turn.save(
        update_fields=["status", "started_at", "error_code", "updated_at"]
    )
    return turn


def _fail_diagnostic(diagnostic, error_code):
    diagnostic.status = RunDiagnostic.Status.FAILED
    diagnostic.error_code = error_code
    diagnostic.finished_at = timezone.now()
    diagnostic.save(
        update_fields=[
            "status",
            "error_code",
            "finished_at",
            "updated_at",
        ]
    )


def _fail_turn(turn, error_code):
    turn.status = RunDiagnosticTurn.Status.FAILED
    turn.error_code = error_code
    turn.finished_at = timezone.now()
    turn.save(
        update_fields=[
            "status",
            "error_code",
            "finished_at",
            "updated_at",
        ]
    )


def _parse_json_object(content):
    raw = str(content or "").strip()
    if raw.startswith("```"):
        raw = raw.removeprefix("```json").removeprefix("```")
        raw = raw.removesuffix("```").strip()
    try:
        result = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID") from exc
    if not isinstance(result, dict):
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    return result


def _diagnostic_system_prompt():
    return (
        "You are a read-only Run Diagnostics Assistant. Analyze only the "
        "provided immutable evidence snapshot. Do not request tools, perform "
        "actions, reveal hidden reasoning, or infer facts without labeling "
        "them as hypotheses. Return strict JSON with summary, severity, "
        "confidence, findings, cause_categories, recommendations, and "
        "unknowns. Every fact, hypothesis, and recommendation must cite only "
        "Evidence IDs present in the snapshot."
    )


def _follow_up_system_prompt():
    return (
        "Answer only about the single target Run using its bound diagnosis and "
        "immutable evidence. Do not use tools, search for other Runs, perform "
        "actions, or reveal hidden reasoning. Return strict JSON with answer "
        "and evidence_refs. Cite only Evidence IDs present in the snapshot."
    )


def _validate_finding(item, evidence):
    if (
        not isinstance(item, dict)
        or item.get("kind") not in VALID_FINDING_KINDS
    ):
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    return {
        "kind": item["kind"],
        "title": _bounded_text(item.get("title"), 240),
        "statement": _bounded_text(item.get("statement"), 2000),
        "confidence": _confidence(item.get("confidence")),
        "evidence_refs": _evidence_refs(
            item.get("evidence_refs"),
            evidence,
            required=True,
        ),
    }


def _validate_recommendations(items, evidence):
    if not isinstance(items, list) or len(items) > MAX_LIST_ITEMS:
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
        normalized.append(
            {
                "title": _bounded_text(item.get("title"), 240),
                "action": _bounded_text(item.get("action"), 2000),
                "evidence_refs": _evidence_refs(
                    item.get("evidence_refs"),
                    evidence,
                    required=True,
                ),
            }
        )
    return normalized


def _validate_unknowns(items, evidence):
    if not isinstance(items, list) or len(items) > MAX_LIST_ITEMS:
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
        normalized.append(
            {
                "statement": _bounded_text(item.get("statement"), 2000),
                "evidence_refs": _evidence_refs(
                    item.get("evidence_refs", []),
                    evidence,
                ),
            }
        )
    return normalized


def _validate_follow_up_result(result, evidence):
    if not isinstance(result, dict):
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    return {
        "answer": _bounded_text(result.get("answer"), MAX_ANSWER_CHARS),
        "evidence_refs": _evidence_refs(
            result.get("evidence_refs"),
            evidence,
            required=True,
        ),
    }


def _evidence_refs(refs, evidence, *, required=False):
    if not isinstance(refs, list) or not all(
        isinstance(item, str) for item in refs
    ):
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    if required and not refs:
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    available = set((evidence.payload.get("evidence") or {}).keys())
    if any(item not in available for item in refs):
        raise DiagnosticResultError("INVALID_EVIDENCE_REFERENCE")
    return list(dict.fromkeys(refs))


def _bounded_text(value, maximum):
    if not isinstance(value, str):
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    value = value.strip()
    if not value or len(value) > maximum:
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    return value


def _confidence(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    if value < 0 or value > 1:
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    return float(value)


def _short_string_list(value, maximum):
    if not isinstance(value, list) or len(value) > maximum:
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    if not all(
        isinstance(item, str) and 0 < len(item.strip()) <= 80 for item in value
    ):
        raise DiagnosticResultError("MODEL_RESPONSE_INVALID")
    return [item.strip() for item in value]


def _canonical_hash(value):
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def _model_config_hash(model_ref):
    if not model_ref:
        return ""
    try:
        from agentcore_metering.adapters.django.models import LLMConfig

        config = (
            LLMConfig.objects.filter(uuid=model_ref)
            .values_list(
                "config",
                flat=True,
            )
            .first()
        )
    except ImportError:
        return ""
    return _canonical_hash(config) if config is not None else ""


def _safe_run_error_code(value):
    value = str(value or "")
    if not value:
        return ""
    if SAFE_CODE_PATTERN.fullmatch(value):
        return value
    return "UNCLASSIFIED_RUN_ERROR"


def _safe_event_value(key, value):
    if key in {"required", "affects_required_evidence"}:
        return value if isinstance(value, bool) else None
    if key.endswith("_count"):
        return value if isinstance(value, int) and value >= 0 else None
    if isinstance(value, str) and SAFE_CODE_PATTERN.fullmatch(value):
        return value
    return None


def _safe_observation_value(key, value):
    if not isinstance(value, str):
        return None
    if key in {"started_at", "ended_at"}:
        return value if len(value) <= 40 and "T" in value else None
    return value if SAFE_CODE_PATTERN.fullmatch(value) else None


def _safe_content_type(value):
    value = str(value or "")
    if SAFE_MIME_PATTERN.fullmatch(value):
        return value
    return "application/octet-stream"
