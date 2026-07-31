import hashlib
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role
from lens.llm import LensLLMResult
from lens.models import (
    Assistant,
    LensNode,
    Run,
    RunDiagnostic,
    RunDiagnosticEvidence,
    RunStep,
    Session,
)
from lens.run_diagnostics import (
    DiagnosticResultError,
    create_diagnostic_turn,
    create_run_diagnostic,
    execute_diagnostic,
    validate_diagnostic_result,
)
from lens.services import create_execution_run

User = get_user_model()


class RunDiagnosticsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="diagnostics-admin",
            is_staff=True,
        )
        self.client.force_authenticate(self.admin)
        self.lensnode = LensNode.objects.create(
            name="Diagnostics Node",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
        )
        self.assistant = Assistant.objects.create(
            name="Diagnostics Assistant",
            slug="diagnostics-assistant",
            lensnode=self.lensnode,
            selected_task="knowledge_qa",
            agent_model_ref="11111111-1111-1111-1111-111111111111",
            settings={
                "runtime_mode": "knowledge_qa",
                "api_token": "assistant-secret",
            },
        )
        self.session = Session.objects.create(
            assistant=self.assistant,
            user=self.admin,
        )
        self.prior_run = create_execution_run(
            session=self.session,
            question="Earlier private question",
            enqueue=False,
        )
        self.prior_run.output_message.content = "Earlier private answer"
        self.prior_run.output_message.save(update_fields=["content"])
        self.prior_run.status = Run.Status.DONE
        self.prior_run.outcome = Run.Outcome.COMPLETED
        self.prior_run.finished_at = timezone.now()
        self.prior_run.save(
            update_fields=[
                "status",
                "outcome",
                "finished_at",
                "updated_at",
            ]
        )
        self.run = create_execution_run(
            session=self.session,
            question="Why did this Run fail?",
            enqueue=False,
        )
        self.run.status = Run.Status.FAILED
        self.run.outcome = Run.Outcome.BLOCKED
        self.run.error = "LENS_RUN_FAILED"
        self.run.finished_at = timezone.now()
        self.run.save(
            update_fields=[
                "status",
                "outcome",
                "error",
                "finished_at",
                "updated_at",
            ]
        )

    def diagnostics_url(self, run=None):
        return reverse(
            "lens-admin-run-diagnostics",
            kwargs={"run_uuid": (run or self.run).uuid},
        )

    def turns_url(self, diagnostic, run=None):
        return reverse(
            "lens-admin-run-diagnostic-turns",
            kwargs={
                "run_uuid": (run or self.run).uuid,
                "diagnostic_uuid": diagnostic.uuid,
            },
        )

    @patch("lens.run_diagnostics.enqueue_run_diagnostic")
    def test_create_is_idempotent_and_captures_sanitized_evidence(
        self,
        enqueue,
    ):
        RunStep.objects.create(
            run=self.run,
            step_type=RunStep.StepType.GENERAL_CHAT,
            sequence=1,
            status=RunStep.Status.FAILED,
            detail={
                "stdout": "private tool output",
                "authorization": "Bearer private-token",
                "events": [
                    {
                        "agent_event": "deepagents.runtime.outcome",
                        "status": "failed",
                        "error_type": "tool",
                        "scope": "unresolved",
                        "capability": "skill",
                        "secret": "event-secret",
                    }
                ],
            },
        )
        self.run.error = "private raw failure details"
        self.run.save(update_fields=["error", "updated_at"])

        with self.captureOnCommitCallbacks(execute=True):
            first = self.client.post(self.diagnostics_url(), {}, format="json")
        with self.captureOnCommitCallbacks(execute=True):
            second = self.client.post(
                self.diagnostics_url(), {}, format="json"
            )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["uuid"], second.data["uuid"])
        self.assertEqual(RunDiagnostic.objects.count(), 1)
        self.assertEqual(RunDiagnosticEvidence.objects.count(), 1)
        enqueue.assert_called_once()
        evidence = RunDiagnosticEvidence.objects.get()
        serialized = json.dumps(evidence.payload)
        self.assertNotIn("private tool output", serialized)
        self.assertNotIn("private-token", serialized)
        self.assertNotIn("assistant-secret", serialized)
        self.assertNotIn("event-secret", serialized)
        self.assertNotIn("private raw failure details", serialized)
        self.assertEqual(
            evidence.payload["evidence"]["E-RUN"]["data"]["error_code"],
            "UNCLASSIFIED_RUN_ERROR",
        )
        self.assertIn("E-RUN", evidence.payload["evidence"])
        self.assertIn("E-HISTORY", evidence.payload["evidence"])
        self.assertIn("E-EXECUTION", evidence.payload["evidence"])
        self.assertIn("E-PROVENANCE", evidence.payload["evidence"])
        self.assertIn("E-STEP-001", evidence.payload["evidence"])
        history = evidence.payload["evidence"]["E-HISTORY"]["data"]
        self.assertEqual(history[0]["run_uuid"], str(self.prior_run.uuid))
        self.assertEqual(
            history[0]["messages"][0]["message_uuid"],
            str(self.prior_run.input_message.uuid),
        )
        self.assertEqual(
            history[0]["messages"][0]["sha256"],
            hashlib.sha256(b"Earlier private question").hexdigest(),
        )
        self.assertNotIn("Earlier private question", serialized)
        self.assertNotIn("Earlier private answer", serialized)

    def test_non_terminal_run_is_rejected(self):
        self.run.status = Run.Status.RUNNING
        self.run.finished_at = None
        self.run.save(update_fields=["status", "finished_at", "updated_at"])

        response = self.client.post(self.diagnostics_url(), {}, format="json")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "RUN_NOT_TERMINAL")
        self.assertFalse(RunDiagnostic.objects.exists())

    def test_diagnostics_require_separate_permission(self):
        user = User.objects.create_user(username="observation-only")
        role = Role.objects.create(
            name="Observation only",
            visible_features=["admin_console"],
        )
        role.users.add(user)
        client = APIClient()
        client.force_authenticate(user)

        denied = client.post(self.diagnostics_url(), {}, format="json")

        self.assertEqual(denied.status_code, 403)
        permission = Permission.objects.get(codename="run_diagnostics")
        user.user_permissions.add(permission)
        user = User.objects.get(pk=user.pk)
        client.force_authenticate(user)
        with self.captureOnCommitCallbacks(execute=False):
            allowed = client.post(self.diagnostics_url(), {}, format="json")
        self.assertEqual(allowed.status_code, 202)

    def test_evidence_is_immutable(self):
        diagnostic, _created = create_run_diagnostic(self.run, self.admin)
        evidence = diagnostic.evidence
        evidence.payload = {"evidence": {}}

        with self.assertRaises(ValidationError):
            evidence.save()

    def test_result_rejects_unknown_evidence_reference(self):
        diagnostic, _created = create_run_diagnostic(self.run, self.admin)
        result = {
            "summary": "A bounded summary.",
            "severity": "high",
            "confidence": 0.8,
            "findings": [
                {
                    "kind": "fact",
                    "title": "Failure",
                    "statement": "The Run failed.",
                    "confidence": 1.0,
                    "evidence_refs": ["E-NOT-THERE"],
                }
            ],
            "cause_categories": ["execution"],
            "recommendations": [],
            "unknowns": [],
        }

        with self.assertRaises(DiagnosticResultError) as raised:
            validate_diagnostic_result(result, diagnostic.evidence)

        self.assertEqual(raised.exception.code, "INVALID_EVIDENCE_REFERENCE")

    @patch("lens.run_diagnostics.run_completion")
    def test_execute_diagnostic_persists_validated_result(self, completion):
        diagnostic, _created = create_run_diagnostic(self.run, self.admin)
        result = {
            "summary": "The Run stopped after an execution failure.",
            "severity": "high",
            "confidence": 0.9,
            "findings": [
                {
                    "kind": "fact",
                    "title": "Terminal failure",
                    "statement": "The executor marked the Run failed.",
                    "confidence": 1,
                    "evidence_refs": ["E-RUN"],
                }
            ],
            "cause_categories": ["execution"],
            "recommendations": [
                {
                    "title": "Inspect the trace",
                    "action": "Review the failed execution events.",
                    "evidence_refs": ["E-HISTORY"],
                }
            ],
            "unknowns": [],
        }
        completion.return_value = LensLLMResult(
            content=json.dumps(result),
            usage={"total_tokens": 321},
            metered=True,
        )

        completed = execute_diagnostic(diagnostic.uuid)

        self.assertTrue(completed)
        diagnostic.refresh_from_db()
        self.assertEqual(diagnostic.status, RunDiagnostic.Status.COMPLETED)
        self.assertEqual(diagnostic.result["severity"], "high")
        self.assertEqual(diagnostic.usage, {"total_tokens": 321})
        completion.assert_called_once()

    def test_result_requires_citations_for_conclusions(self):
        diagnostic, _created = create_run_diagnostic(self.run, self.admin)
        result = {
            "summary": "A bounded summary.",
            "severity": "low",
            "confidence": 0.5,
            "findings": [
                {
                    "kind": "hypothesis",
                    "title": "Possible cause",
                    "statement": "More evidence is required.",
                    "confidence": 0.5,
                    "evidence_refs": [],
                }
            ],
            "cause_categories": [],
            "recommendations": [],
            "unknowns": [],
        }

        with self.assertRaises(DiagnosticResultError) as raised:
            validate_diagnostic_result(result, diagnostic.evidence)

        self.assertEqual(raised.exception.code, "MODEL_RESPONSE_INVALID")

    @patch("lens.run_diagnostics.enqueue_diagnostic_turn")
    def test_follow_up_is_bound_to_completed_diagnostic(self, enqueue):
        diagnostic, _created = create_run_diagnostic(self.run, self.admin)
        diagnostic.status = RunDiagnostic.Status.COMPLETED
        diagnostic.result = {
            "summary": "The Run failed after a tool error.",
            "severity": "high",
            "confidence": 0.8,
            "findings": [],
            "cause_categories": [],
            "recommendations": [],
            "unknowns": [],
        }
        diagnostic.save(update_fields=["status", "result", "updated_at"])

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.turns_url(diagnostic),
                {"question": "Which evidence supports that?"},
                format="json",
            )

        self.assertEqual(response.status_code, 202)
        turn = diagnostic.turns.get()
        self.assertEqual(turn.question, "Which evidence supports that?")
        enqueue.assert_called_once_with(turn.uuid)

        other_run = create_execution_run(
            session=self.session,
            question="Another Run",
            enqueue=False,
        )
        other_run.status = Run.Status.DONE
        other_run.finished_at = timezone.now()
        other_run.save(update_fields=["status", "finished_at", "updated_at"])
        mismatch = self.client.post(
            self.turns_url(diagnostic, run=other_run),
            {"question": "Cross-run question"},
            format="json",
        )
        self.assertEqual(mismatch.status_code, 404)

    def test_follow_up_question_is_bounded(self):
        diagnostic, _created = create_run_diagnostic(self.run, self.admin)
        diagnostic.status = RunDiagnostic.Status.COMPLETED
        diagnostic.save(update_fields=["status", "updated_at"])

        with self.assertRaises(ValidationError):
            create_diagnostic_turn(
                diagnostic,
                self.admin,
                "x" * 2001,
            )
