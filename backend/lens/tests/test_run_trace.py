import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from lens.consumers import LensNodeConsumer
from lens.models import Assistant, LensNode, RunTraceEvent, Session
from lens.run_trace import RunTraceValidationError, append_run_trace_events
from lens.services import create_execution_run, dispatch_run_to_lensnode

User = get_user_model()


class RunTraceFixtureMixin:
    """Build a run assigned to one approved LensNode."""

    def create_trace_fixture(self):
        self.user = User.objects.create_user(
            username=f"trace-user-{uuid.uuid4()}",
            password="x",
        )
        self.node = LensNode.objects.create(
            name=f"Trace node {uuid.uuid4()}",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
        )
        assistant = Assistant.objects.create(
            name=f"Trace assistant {uuid.uuid4()}",
            slug=f"trace-{uuid.uuid4()}",
            lensnode=self.node,
            selected_task="general_chat",
        )
        session = Session.objects.create(
            assistant=assistant,
            user=self.user,
        )
        self.run = create_execution_run(
            session,
            "Explain this run",
            enqueue=False,
        )

    def trace_event(self, sequence=1, **overrides):
        event = {
            "event_id": str(uuid.uuid4()),
            "sequence": sequence,
            "attempt": 1,
            "event_type": "model.completed",
            "timestamp": timezone.now().isoformat(),
            "call_id": "model-call-1",
            "payload": {
                "model": "test-model",
                "duration_ms": 125,
                "ttft_ms": 20,
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        }
        event.update(overrides)
        return event


class RunTraceServiceTests(RunTraceFixtureMixin, TransactionTestCase):
    def setUp(self):
        self.create_trace_fixture()

    def test_appends_ordered_events_and_replays_idempotently(self):
        first = self.trace_event(sequence=1)
        second = self.trace_event(
            sequence=2,
            event_type="tool.started",
            call_id="tool-call-1",
            parent_call_id="model-call-1",
            payload={"name": "search", "arguments": {"q": "trace"}},
        )

        result = append_run_trace_events(
            self.run.uuid,
            self.node.uuid,
            [first, second],
        )
        replay = append_run_trace_events(
            self.run.uuid,
            self.node.uuid,
            [first, second],
        )

        self.assertEqual(result.inserted_count, 2)
        self.assertEqual(result.duplicate_count, 0)
        self.assertEqual(replay.inserted_count, 0)
        self.assertEqual(replay.duplicate_count, 2)
        self.assertEqual(
            list(
                RunTraceEvent.objects.filter(run=self.run).values_list(
                    "sequence", flat=True
                )
            ),
            [1, 2],
        )

    def test_rejects_conflicting_event_id_transactionally(self):
        existing = self.trace_event(sequence=1)
        append_run_trace_events(
            self.run.uuid,
            self.node.uuid,
            [existing],
        )
        valid = self.trace_event(sequence=2)
        conflict = self.trace_event(
            sequence=3,
            event_id=existing["event_id"],
            event_type="tool.failed",
        )

        with self.assertRaises(RunTraceValidationError):
            append_run_trace_events(
                self.run.uuid,
                self.node.uuid,
                [valid, conflict],
            )

        self.assertEqual(self.run.trace_events.count(), 1)

    def test_rejects_sequence_conflict_and_wrong_node(self):
        first = self.trace_event(sequence=1)
        append_run_trace_events(
            self.run.uuid,
            self.node.uuid,
            [first],
        )
        other_node = LensNode.objects.create(
            name="Other trace node",
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
        )

        with self.assertRaises(RunTraceValidationError):
            append_run_trace_events(
                self.run.uuid,
                self.node.uuid,
                [self.trace_event(sequence=1)],
            )
        with self.assertRaises(RunTraceValidationError):
            append_run_trace_events(
                self.run.uuid,
                other_node.uuid,
                [self.trace_event(sequence=2)],
            )

    def test_rejects_sequence_gap_transactionally(self):
        append_run_trace_events(
            self.run.uuid,
            self.node.uuid,
            [self.trace_event(sequence=1)],
        )

        with self.assertRaises(RunTraceValidationError):
            append_run_trace_events(
                self.run.uuid,
                self.node.uuid,
                [self.trace_event(sequence=3)],
            )

        self.assertEqual(self.run.trace_events.count(), 1)

    def test_validates_external_event_shape(self):
        invalid = self.trace_event(
            sequence=0,
            event_type="Model Completed",
            payload=["not", "an", "object"],
        )

        with self.assertRaises(RunTraceValidationError) as captured:
            append_run_trace_events(
                self.run.uuid,
                self.node.uuid,
                [invalid],
            )

        self.assertIn("sequence", str(captured.exception))
        self.assertEqual(self.run.trace_events.count(), 0)

    def test_rejects_non_finite_json_numbers(self):
        invalid = self.trace_event(
            sequence=1,
            payload={"duration_ms": float("nan")},
        )

        with self.assertRaises(RunTraceValidationError):
            append_run_trace_events(
                self.run.uuid,
                self.node.uuid,
                [invalid],
            )

        self.assertEqual(self.run.trace_events.count(), 0)

    def test_websocket_frame_returns_durable_cursor_ack(self):
        consumer = LensNodeConsumer()
        consumer.lensnode = self.node
        consumer.send_json = AsyncMock()

        async_to_sync(consumer._handle_run_trace_events)(
            {
                "run_uuid": str(self.run.uuid),
                "events": [self.trace_event(sequence=1)],
            }
        )

        response = consumer.send_json.await_args.args[0]
        self.assertEqual(response["type"], "run_trace_events_ack")
        self.assertEqual(response["last_sequence"], 1)
        self.assertEqual(response["inserted_count"], 1)

    @patch("lens.services.async_to_sync")
    @patch("lens.services.get_channel_layer")
    def test_resume_dispatch_uses_persisted_trace_cursor(
        self,
        get_channel_layer,
        mock_async_to_sync,
    ):
        del get_channel_layer
        append_run_trace_events(
            self.run.uuid,
            self.node.uuid,
            [
                self.trace_event(sequence=sequence, attempt=2)
                for sequence in range(1, 10)
            ],
        )

        dispatch_run_to_lensnode(
            self.run,
            "Explain this run",
            resume=True,
        )

        payload = mock_async_to_sync.return_value.call_args.args[1]["payload"]
        self.assertEqual(payload["trace_cursor"], 9)
        self.assertEqual(payload["trace_attempt"], 3)


class AdminRunTrajectoryAPITests(RunTraceFixtureMixin, TestCase):
    def setUp(self):
        self.create_trace_fixture()
        self.admin = User.objects.create_user(
            username="trace-admin",
            password="x",
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_admin_reads_filtered_cursor_page_with_summary(self):
        started_at = timezone.now() - timedelta(seconds=1)
        events = [
            self.trace_event(
                sequence=1,
                event_type="model.started",
                timestamp=started_at.isoformat(),
                payload={"model": "test-model", "input": "full prompt"},
            ),
            self.trace_event(sequence=2),
            self.trace_event(
                sequence=3,
                event_type="tool.completed",
                call_id="tool-call-1",
                payload={
                    "name": "search",
                    "result": {"answer": "needle"},
                    "duration_ms": 40,
                },
            ),
        ]
        append_run_trace_events(self.run.uuid, self.node.uuid, events)

        response = self.client.get(
            f"/api/lens/admin/runs/{self.run.uuid}/trajectory/",
            {
                "after_sequence": 1,
                "page_size": 1,
                "category": "model",
                "q": "test-model",
            },
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["results"][0]["sequence"], 2)
        self.assertEqual(response.data["next_after_sequence"], 2)
        self.assertEqual(response.data["summary"]["event_count"], 3)
        self.assertEqual(response.data["summary"]["model_calls"], 1)
        self.assertEqual(response.data["summary"]["tool_calls"], 1)
        self.assertEqual(response.data["summary"]["total_tokens"], 15)
        self.assertGreaterEqual(
            response.data["summary"]["duration_ms"],
            900,
        )

    def test_admin_pages_parent_and_child_events_with_one_global_cursor(self):
        child_assistant = Assistant.objects.create(
            name="Delegated trace assistant",
            slug=f"delegated-trace-{uuid.uuid4()}",
            lensnode=self.node,
            selected_task="general_chat",
        )
        child_session = Session.objects.create(
            assistant=child_assistant,
            user=self.user,
        )
        child_run = create_execution_run(
            child_session,
            "Inspect the delegated run",
            enqueue=False,
            parent_run=self.run,
        )
        started_at = timezone.now() - timedelta(seconds=3)
        append_run_trace_events(
            self.run.uuid,
            self.node.uuid,
            [
                self.trace_event(
                    sequence=1,
                    timestamp=started_at.isoformat(),
                ),
                self.trace_event(
                    sequence=2,
                    timestamp=(started_at + timedelta(seconds=2)).isoformat(),
                ),
            ],
        )
        append_run_trace_events(
            child_run.uuid,
            self.node.uuid,
            [
                self.trace_event(
                    sequence=1,
                    timestamp=(started_at + timedelta(seconds=1)).isoformat(),
                )
            ],
        )

        first_page = self.client.get(
            f"/api/lens/admin/runs/{self.run.uuid}/trajectory/",
            {"page_size": 2},
        )
        second_page = self.client.get(
            f"/api/lens/admin/runs/{self.run.uuid}/trajectory/",
            {
                "page_size": 2,
                "after_sequence": first_page.data["next_after_sequence"],
            },
        )

        self.assertEqual(first_page.status_code, 200, first_page.data)
        self.assertEqual(
            [event["sequence"] for event in first_page.data["results"]],
            [1, 2],
        )
        self.assertTrue(first_page.data["has_more"])
        self.assertEqual(second_page.status_code, 200, second_page.data)
        self.assertEqual(
            [event["sequence"] for event in second_page.data["results"]],
            [3],
        )
        self.assertEqual(
            second_page.data["results"][0]["trace_run_role"],
            "child",
        )
        self.assertFalse(second_page.data["has_more"])

    def test_non_admin_cannot_read_trajectory(self):
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.get(f"/api/lens/admin/runs/{self.run.uuid}/trajectory/")

        self.assertEqual(response.status_code, 403)
