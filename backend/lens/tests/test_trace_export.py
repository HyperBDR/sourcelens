import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from lens.models import Assistant, LensNode, Run, RunStep, Session
from lens.services import create_execution_run, finish_lensnode_run
from lens.trace_context import root_observation_id_for_run
from lens.trace_export import (
    _observation_summaries_enabled,
    build_ingestion_batch,
    export_run_trace,
)

User = get_user_model()


class LangfuseTraceExportTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="trace-user")
        lensnode = LensNode.objects.create(
            name="Trace Node",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
        )
        assistant = Assistant.objects.create(
            name="Trace Assistant",
            slug="trace-assistant",
            lensnode=lensnode,
            selected_task="knowledge_qa",
        )
        session = Session.objects.create(
            assistant=assistant,
            user=user,
        )
        self.run = create_execution_run(
            session=session,
            question="Do not export this secret input",
            enqueue=False,
        )
        self.started_at = timezone.now() - timedelta(seconds=3)
        self.finished_at = timezone.now()
        self.run.started_at = self.started_at
        self.run.finished_at = self.finished_at
        self.run.status = Run.Status.DONE
        self.run.save(update_fields=["started_at", "finished_at", "status"])

    def test_observation_summary_switch_accepts_only_enabled_values(self):
        for value in ("1", "TRUE", " yes ", "On"):
            with self.subTest(value=value):
                with patch.dict(
                    "os.environ",
                    {"LANGFUSE_OBSERVATION_SUMMARY_ENABLED": value},
                ):
                    self.assertTrue(_observation_summaries_enabled())

        for value in ("", "0", "false", "disabled", "2"):
            with self.subTest(value=value):
                with patch.dict(
                    "os.environ",
                    {"LANGFUSE_OBSERVATION_SUMMARY_ENABLED": value},
                ):
                    self.assertFalse(_observation_summaries_enabled())

    def test_build_ingestion_batch_creates_run_tree_without_contents(self):
        model_id = "a" * 16
        tool_id = "b" * 32
        root_id = "c" * 32
        RunStep.objects.create(
            run=self.run,
            step_type=RunStep.StepType.GENERAL_CHAT,
            sequence=3,
            status=RunStep.Status.DONE,
            detail={
                "events": [
                    {
                        "observation": {
                            "action": "start",
                            "id": model_id,
                            "parent_observation_id": root_id,
                            "name": "model.agent",
                            "started_at": self.started_at.isoformat(),
                            "secret": "must not be exported",
                        }
                    },
                    {
                        "observation": {
                            "action": "end",
                            "id": model_id,
                            "status": "done",
                            "ended_at": self.finished_at.isoformat(),
                        }
                    },
                    {
                        "observation": {
                            "action": "start",
                            "id": tool_id,
                            "parent_observation_id": root_id,
                            "name": "tool.search_workspace",
                            "started_at": self.started_at.isoformat(),
                        }
                    },
                    {
                        "observation": {
                            "action": "end",
                            "id": tool_id,
                            "status": "failed",
                            "error_type": "TimeoutError",
                            "error": "secret exception text",
                            "ended_at": self.finished_at.isoformat(),
                        }
                    },
                ]
            },
        )

        batch = build_ingestion_batch(
            self.run,
            root_id,
            include_summaries=True,
        )

        event_types = [event["type"] for event in batch]
        self.assertEqual(
            event_types,
            [
                "trace-create",
                "span-create",
                "span-create",
                "span-update",
                "span-create",
                "span-update",
                "span-update",
            ],
        )
        trace_body = batch[0]["body"]
        self.assertEqual(
            trace_body["userId"],
            str(self.run.session.user_id),
        )
        self.assertEqual(
            trace_body["sessionId"],
            str(self.run.session.uuid),
        )
        root_span = batch[1]["body"]
        self.assertEqual(
            root_span["metadata"]["comment"],
            "Run the SourceLens agent workflow for this request.",
        )
        child_creates = [
            event["body"]
            for event in batch
            if event["type"] == "span-create"
            and event["body"]["id"] != root_id
        ]
        self.assertEqual(
            {item["parentObservationId"] for item in child_creates},
            {root_id},
        )
        comments = {
            item["name"]: item["metadata"]["comment"] for item in child_creates
        }
        self.assertEqual(
            comments["model.agent"],
            "Run one agent model reasoning and response round.",
        )
        self.assertEqual(
            comments["tool.search_workspace"],
            "Execute the search_workspace tool.",
        )
        tool_update = next(
            event["body"]
            for event in batch
            if event["type"] == "span-update"
            and event["body"]["id"] == tool_id
        )
        self.assertEqual(tool_update["level"], "ERROR")
        self.assertEqual(
            tool_update["metadata"],
            {"status": "failed", "errorType": "TimeoutError"},
        )
        serialized = json.dumps(batch)
        self.assertNotIn("secret input", serialized)
        self.assertNotIn("secret exception", serialized)
        self.assertNotIn("must not be exported", serialized)

        batch_without_summaries = build_ingestion_batch(
            self.run,
            root_id,
            include_summaries=False,
        )
        self.assertNotIn("comment", json.dumps(batch_without_summaries))

    def test_trace_metadata_reports_retry_filtering_without_content(self):
        retry = create_execution_run(
            session=self.run.session,
            question="Do not export retried content",
            idempotency_key="retry-trace",
            retry_of_run=self.run,
            enqueue=False,
        )
        retry.status = Run.Status.DONE
        retry.outcome = Run.Outcome.COMPLETED
        retry.save(update_fields=["status", "outcome"])

        batch = build_ingestion_batch(
            retry,
            root_observation_id_for_run(retry.uuid),
        )

        metadata = batch[0]["body"]["metadata"]
        self.assertEqual(metadata["retryOfRunUuid"], str(self.run.uuid))
        self.assertTrue(metadata["explicitRetry"])
        self.assertEqual(metadata["historyRunsBeforeFiltering"], 1)
        self.assertEqual(metadata["historyRunsAfterFiltering"], 0)
        self.assertEqual(metadata["supersededRetryAttemptsRemoved"], 1)
        self.assertEqual(metadata["nonCompletedAssistantOutputsExcluded"], 0)
        serialized = json.dumps(metadata)
        self.assertNotIn("Do not export", serialized)

    @patch("lens.trace_export.request.urlopen")
    def test_export_skips_network_without_observation_events(
        self,
        urlopen,
    ):
        with patch.dict(
            "os.environ",
            {
                "LANGFUSE_PUBLIC_KEY": "public-key",
                "LANGFUSE_SECRET_KEY": "secret-key",
                "LANGFUSE_OTEL_HOST": "http://langfuse:3000",
            },
            clear=False,
        ):
            exported = export_run_trace(self.run.pk)

        self.assertFalse(exported)
        urlopen.assert_not_called()

    def test_finish_schedules_export_after_observations_are_committed(self):
        root_id = root_observation_id_for_run(self.run.uuid)
        self.run.status = Run.Status.RUNNING
        self.run.finished_at = None
        self.run.save(update_fields=["status", "finished_at"])
        RunStep.objects.create(
            run=self.run,
            step_type=RunStep.StepType.GENERAL_CHAT,
            sequence=3,
            status=RunStep.Status.DONE,
            detail={
                "events": [
                    {
                        "observation": {
                            "action": "start",
                            "id": "d" * 32,
                            "parent_observation_id": root_id,
                            "name": "model.agent",
                            "started_at": self.started_at.isoformat(),
                        }
                    }
                ]
            },
        )

        with patch("lens.services.export_run_trace") as export:
            with self.captureOnCommitCallbacks(execute=True):
                finish_lensnode_run(self.run.uuid, Run.Status.DONE)

        export.assert_called_once_with(self.run.pk)
