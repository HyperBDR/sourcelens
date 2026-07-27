from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from agentcore_task.adapters.django.models import TaskExecution
from django_celery_beat.models import PeriodicTask

from core.asgi import application
from core.management.commands.register_periodic_tasks import (
    discover_and_register,
)
from core.periodic_registry import TASK_REGISTRY
from lens.consumers import LensNodeConsumer
from lens.datasource_services import dispatch_datasource_sync_async
from lens.execution import execute_answer_run
from lens.lensnode_auth import issue_lensnode_token
from lens.models import (
    Assistant,
    DataSource,
    GlobalSetting,
    LensNode,
    Message,
    Run,
    RunStep,
    ScheduledTask,
    Session,
)
from lens.periodic_tasks import (
    ensure_datasource_periodic_task,
    register_periodic_tasks,
)
from lens.runtime_events import (
    sanitize_runtime_event,
    sanitize_termination_detail,
)
from lens.serializers import RunSerializer
from lens.services import (
    _build_sync_event,
    _step_sequence,
    append_lensnode_output,
    build_run_history,
    create_run_execution_snapshot,
    create_execution_run,
    dispatch_run_to_lensnode,
    finish_lensnode_run,
    rewrite_query,
)
from lens.tasks import (
    acquire_datasource_lock,
    complete_datasource_sync_task,
    cleanup_stale_datasource_sync_tasks,
    datasource_lock,
    lensnode_health_task,
    register_datasource_sync_task,
    release_datasource_lock,
    source_sync_task,
)

User = get_user_model()

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
}

TEST_CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}


@override_settings(CACHES=TEST_CACHES, CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class LensServiceTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="lens-user",
            email="lens-user@example.com",
            password="pass12345",
        )
        self.lensnode = LensNode.objects.create(
            name="Local LensNode",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            workspace_path="/workspace",
            available_dirs=[{"path": "/workspace/repo"}],
            tasks=[{"name": "knowledge_qa", "description": "Answer code questions"}],
        )
        self.assistant = Assistant.objects.create(
            name="Code Advisor",
            slug="code-advisor",
            lensnode=self.lensnode,
            selected_task="knowledge_qa",
            selected_dirs=[{"path": "/workspace/repo"}],
        )
        self.datasource = DataSource.objects.create(
            name="Repo Cache",
            source_type="git",
            lensnode=self.lensnode,
            config={"repo_url": "https://example.com/repo.git"},
            sync_policy={"interval_seconds": 3600},
            target_path="/workspace/repo-cache",
        )
        self.session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
            title="",
        )

    def test_run_step_sequences_are_distinct_for_structured_steps(self):
        step_types = [
            RunStep.StepType.QUERY_REWRITE,
            RunStep.StepType.MULTIMODAL,
            RunStep.StepType.RETRIEVAL,
            RunStep.StepType.GENERAL_CHAT,
            RunStep.StepType.ANSWER,
            RunStep.StepType.STREAM,
        ]

        sequences = [_step_sequence(step_type) for step_type in step_types]

        self.assertEqual(len(sequences), len(set(sequences)))

    def test_create_execution_run_creates_queued_run_with_lensnode(self):
        run = create_execution_run(
            session=self.session,
            question="How does SSE work?",
            idempotency_key="real-run",
            enqueue=False,
        )

        self.assertEqual(run.status, "queued")
        self.assertEqual(run.lensnode, self.lensnode)
        self.assertEqual(run.input_message.role, Message.Role.USER)
        self.assertEqual(run.output_message.role, Message.Role.ASSISTANT)
        self.assertEqual(self.session.message_set.count(), 2)

    def test_build_run_history_returns_prior_turns_and_skips_empty(self):
        run1 = create_execution_run(
            session=self.session, question="q1", enqueue=False
        )
        run1.output_message.content = "a1"
        run1.output_message.save(update_fields=["content"])
        # second turn left unanswered -> its empty answer must be skipped
        create_execution_run(
            session=self.session, question="q2", enqueue=False
        )
        current = create_execution_run(
            session=self.session, question="q3", enqueue=False
        )

        history = build_run_history(current)

        self.assertEqual(
            history,
            [
                {"role": "user", "content": "q1"},
                {"role": "assistant", "content": "a1"},
                {"role": "user", "content": "q2"},
            ],
        )

    def test_rewrite_query_passthrough_without_preprocess_model(self):
        run = create_execution_run(
            session=self.session, question="how to deploy?", enqueue=False
        )

        result = rewrite_query(run)

        self.assertFalse(result["rewritten"])
        self.assertEqual(result["question"], "how to deploy?")

    @patch("lens.services.run_completion")
    def test_rewrite_query_uses_preprocess_model(self, mock_completion):
        import uuid

        from lens.llm import LensLLMResult

        self.assistant.preprocess_model_ref = uuid.uuid4()
        self.assistant.save(update_fields=["preprocess_model_ref"])
        mock_completion.return_value = LensLLMResult(
            content="AGIOne 单机部署 步骤", usage={}, metered=True
        )
        run = create_execution_run(
            session=self.session, question="它怎么装", enqueue=False
        )

        result = rewrite_query(run)

        self.assertTrue(mock_completion.called)
        self.assertTrue(result["rewritten"])
        self.assertEqual(result["question"], "AGIOne 单机部署 步骤")

    def test_lens_smoke_test_command_passes(self):
        call_command("lens_smoke_test")

    def test_create_execution_run_reuses_idempotent_run(self):
        first = create_execution_run(
            session=self.session,
            question="How does SSE work?",
            idempotency_key="real-run",
            enqueue=False,
        )
        second = create_execution_run(
            session=self.session,
            question="How does SSE work?",
            idempotency_key="real-run",
            enqueue=False,
        )

        self.assertEqual(first.uuid, second.uuid)
        self.assertEqual(self.session.message_set.count(), 2)

    def test_execute_answer_run_creates_execution_snapshot(self):
        self.assistant.token_budget_profile = "deep"
        self.assistant.save(update_fields=["token_budget_profile"])
        run = create_execution_run(
            session=self.session,
            question="How does SSE work?",
            idempotency_key="real-run",
            enqueue=False,
        )

        execute_answer_run(run, dispatch=False)
        run.refresh_from_db()

        self.assertEqual(run.status, "done")
        self.assertEqual(run.steps.count(), 3)
        self.assertTrue(run.output_message.content)
        self.assertEqual(run.execution.task, "knowledge_qa")
        self.assertEqual(run.execution.target_dirs, [{"path": "/workspace/repo"}])
        self.assertEqual(run.execution.token_budget_profile, "deep")
        self.assertEqual(run.execution.token_budget_max_tokens, 500000)
        self.assertEqual(
            run.execution.token_budget_final_reserve_tokens,
            75000,
        )

    @patch("lens.services.async_to_sync")
    @patch("lens.services.get_channel_layer")
    def test_dispatch_uses_token_budget_execution_snapshot(
        self,
        get_channel_layer,
        mock_async_to_sync,
    ):
        sender = mock_async_to_sync.return_value
        self.assistant.token_budget_profile = "deep"
        self.assistant.save(update_fields=["token_budget_profile"])
        run = create_execution_run(
            session=self.session,
            question="Analyze everything",
            enqueue=False,
        )
        execution = create_run_execution_snapshot(run)

        self.assistant.token_budget_profile = "standard"
        self.assistant.save(update_fields=["token_budget_profile"])
        dispatch_run_to_lensnode(run, "Analyze everything")

        payload = sender.call_args.args[1]["payload"]
        self.assertEqual(
            payload["token_budget"],
            {
                "profile": "deep",
                "max_tokens": 500000,
                "final_reserve_tokens": 75000,
            },
        )
        self.assertEqual(execution.token_budget_profile, "deep")

    def test_execute_answer_run_fails_when_lensnode_offline(self):
        self.lensnode.status = LensNode.Status.OFFLINE
        self.lensnode.save(update_fields=["status"])
        run = create_execution_run(
            session=self.session,
            question="How does SSE work?",
            enqueue=False,
        )

        with self.assertRaises(Exception):
            execute_answer_run(run, dispatch=False)

        run.refresh_from_db()
        self.assertEqual(run.status, Run.Status.FAILED)
        self.assertEqual(run.error, "LENSNODE_OFFLINE")

    def test_finish_lensnode_run_does_not_overwrite_cancelled_run(self):
        run = create_execution_run(
            session=self.session,
            question="What does this project do?",
            enqueue=False,
        )
        run.status = Run.Status.CANCELLED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])

        finish_lensnode_run(run.uuid, Run.Status.DONE)

        run.refresh_from_db()
        self.assertEqual(run.status, Run.Status.CANCELLED)
        self.assertEqual(run.output_message.content, "")

    def test_finish_lensnode_run_persists_business_outcome(self):
        run = create_execution_run(
            session=self.session,
            question="Use the configured Skill",
            enqueue=False,
        )

        finish_lensnode_run(
            run.uuid,
            Run.Status.DONE,
            outcome=Run.Outcome.BLOCKED,
            termination_detail={
                "reason": "capability_unavailable",
                "capability": "skill",
            },
        )

        run.refresh_from_db()
        self.assertEqual(run.outcome, Run.Outcome.BLOCKED)
        self.assertEqual(
            run.termination_detail,
            {
                "reason": "capability_unavailable",
                "capability": "skill",
            },
        )

    def test_sync_event_exposes_safe_runtime_fields_only(self):
        run = create_execution_run(
            session=self.session,
            question="Plan this task",
            enqueue=False,
        )
        RunStep.objects.create(
            run=run,
            step_type=RunStep.StepType.GENERAL_CHAT,
            sequence=3,
            status=RunStep.Status.RUNNING,
            detail={
                "secret": "do-not-expose",
                "events": [
                    {
                        "agent_event": "tool.call_skill_api.invoke",
                        "activity": "running_tool",
                        "summary": "Authorization: secret-token",
                    },
                    {
                        "agent_event": "workflow.route.selected",
                        "activity": "running",
                        "event_type": "route.selected",
                        "visibility": "user",
                        "payload": {
                            "route": "plan_execute",
                            "complexity": "complex",
                            "evidence_requirement": "none",
                        },
                    },
                    {
                        "agent_event": "workflow.plan.updated",
                        "activity": "running",
                        "event_type": "plan.updated",
                        "visibility": "user",
                        "payload": {
                            "revision": 1,
                            "steps": [
                                {
                                    "id": "step-1",
                                    "title": "Inspect configuration",
                                    "status": "in_progress",
                                    "secret": "hidden",
                                }
                            ],
                            "secret": "hidden",
                        },
                    },
                    {
                        "agent_event": "workflow.stage.updated",
                        "activity": "running",
                        "event_type": "stage.updated",
                        "visibility": "user",
                        "payload": {
                            "id": "fetch-orders",
                            "title": "Fetch order data",
                            "status": "in_progress",
                            "summary": "Fetched 93 orders",
                            "order": 2,
                            "revision": 4,
                            "secret": "hidden",
                        },
                    },
                ],
            },
        )

        event = _build_sync_event(run)
        detail = event["steps"][0]["detail"]

        self.assertNotIn("secret", str(detail))
        self.assertNotIn("Authorization", str(detail))
        self.assertEqual(
            detail["events"][2]["payload"]["steps"][0]["title"],
            "Inspect configuration",
        )
        self.assertEqual(
            detail["events"][1]["payload"]["evidence_requirement"],
            "none",
        )
        self.assertEqual(
            detail["events"][3]["payload"],
            {
                "id": "fetch-orders",
                "title": "Fetch order data",
                "status": "in_progress",
                "summary": "Fetched 93 orders",
                "order": 2,
                "revision": 4,
            },
        )

    def test_route_event_rejects_unknown_contract_values(self):
        event = sanitize_runtime_event({
            "agent_event": "workflow.route.selected",
            "activity": "running",
            "event_type": "route.selected",
            "visibility": "user",
            "payload": {
                "intent": "secret-intent",
                "complexity": "oversized",
                "route": "arbitrary-route",
                "evidence_requirement": "secret-token",
                "required_capabilities": ["skill", "secret-token"],
            },
        })

        self.assertEqual(
            event["payload"],
            {"required_capabilities": ["skill"]},
        )

    def test_capability_unavailable_route_is_public(self):
        event = sanitize_runtime_event({
            "event_type": "route.selected",
            "visibility": "user",
            "payload": {
                "intent": "action",
                "complexity": "simple",
                "route": "capability_unavailable",
                "evidence_requirement": "tool_result",
                "required_capabilities": ["skill"],
            },
        })

        self.assertEqual(
            event["payload"]["route"],
            "capability_unavailable",
        )

    def test_execution_failure_event_is_distinct(self):
        event = sanitize_runtime_event({
            "event_type": "execution.failed",
            "visibility": "user",
            "payload": {
                "reason": "execution_failed",
                "capability": "skill",
                "error_type": "transient",
            },
        })

        self.assertEqual(event["event_type"], "execution.failed")
        self.assertEqual(event["payload"]["reason"], "execution_failed")
        self.assertEqual(event["payload"]["error_type"], "transient")

    def test_runtime_event_rejects_unknown_phase_and_status_values(self):
        phase_event = sanitize_runtime_event({
            "agent_event": "secret-token",
            "activity": "Authorization: secret-token",
            "event_type": "phase.changed",
            "visibility": "user",
            "payload": {"phase": "secret-token"},
        })
        plan_event = sanitize_runtime_event({
            "event_type": "plan.updated",
            "visibility": "user",
            "payload": {
                "steps": [
                    {
                        "id": "step-1",
                        "title": "Inspect configuration",
                        "status": "secret-token",
                    }
                ]
            },
        })

        self.assertNotIn("secret-token", str(phase_event))
        self.assertEqual(phase_event["payload"], {})
        self.assertEqual(
            plan_event["payload"]["steps"][0]["status"],
            "pending",
        )

    def test_stage_event_bounds_public_fields(self):
        event = sanitize_runtime_event({
            "event_type": "stage.updated",
            "visibility": "user",
            "payload": {
                "id": "stage-" + ("x" * 100),
                "title": "T" * 300,
                "status": "completed",
                "summary": "S" * 300,
                "order": 99,
                "revision": "7",
                "secret": "hidden",
            },
        })

        self.assertEqual(len(event["payload"]["id"]), 64)
        self.assertEqual(len(event["payload"]["title"]), 240)
        self.assertEqual(len(event["payload"]["summary"]), 240)
        self.assertEqual(event["payload"]["status"], "completed")
        self.assertEqual(event["payload"]["order"], 12)
        self.assertEqual(event["payload"]["revision"], 7)
        self.assertNotIn("secret", str(event))

    def test_stage_event_rejects_invalid_status(self):
        event = sanitize_runtime_event({
            "event_type": "stage.updated",
            "visibility": "user",
            "payload": {
                "id": "fetch-orders",
                "title": "Fetch order data",
                "status": "secret-token",
            },
        })

        self.assertEqual(event["payload"], {})
        self.assertNotIn("secret-token", str(event))

    def test_order_query_activity_exposes_safe_real_parameters(self):
        event = sanitize_runtime_event({
            "agent_event": "tool.run_skill_artifact.start",
            "activity": "running_tool",
            "runtime_scope": "general_chat",
            "invocation_id": "activity-123",
            "skill": "license-cli",
            "artifact": "income",
            "args_redacted": [
                "--profile",
                "default",
                "order",
                "list",
                "--start",
                "2026-07-20T00:00:00+08:00",
                "--end",
                "2026-07-26T23:59:59+08:00",
                "--token",
                "[REDACTED]",
            ],
        })

        self.assertEqual(event["event_type"], "activity.recorded")
        self.assertEqual(event["visibility"], "user")
        self.assertEqual(
            event["payload"],
            {
                "id": "activity-123",
                "kind": "query_orders",
                "stage_kind": "order_query",
                "status": "in_progress",
                "start_date": "2026-07-20",
                "end_date": "2026-07-26",
            },
        )
        self.assertNotIn("token", str(event).lower())
        self.assertNotIn("profile", str(event).lower())
        self.assertNotIn("run_skill_artifact", str(event))

    def test_completed_tool_activity_preserves_only_pairing_fields(self):
        event = sanitize_runtime_event({
            "agent_event": "tool.run_skill_artifact.done",
            "activity": "running_tool",
            "runtime_scope": "general_chat",
            "invocation_id": "activity-123",
            "stdout_ref": "/large_tool_results/private.txt",
            "summary": "license-cli/income · rc=0",
        })

        self.assertEqual(
            event["payload"],
            {
                "id": "activity-123",
                "kind": "querying_data",
                "stage_kind": "data_query",
                "status": "completed",
            },
        )
        self.assertNotIn("stdout", str(event))

    def test_order_detail_and_command_help_have_real_activity_kinds(self):
        detail = sanitize_runtime_event({
            "agent_event": "tool.run_skill_artifact.start",
            "activity": "running_tool",
            "runtime_scope": "general_chat",
            "invocation_id": "detail-123",
            "args_redacted": [
                "--profile",
                "default",
                "order",
                "get",
                "ORDER-123",
            ],
        })
        command_help = sanitize_runtime_event({
            "agent_event": "tool.run_skill_artifact.start",
            "activity": "running_tool",
            "runtime_scope": "general_chat",
            "invocation_id": "help-123",
            "args_redacted": ["order", "get", "--help"],
        })

        self.assertEqual(detail["payload"]["kind"], "get_order_detail")
        self.assertEqual(
            detail["payload"]["order_ref"],
            "ORDER-123",
        )
        self.assertEqual(
            command_help["payload"]["kind"],
            "reading_order_commands",
        )

    def test_order_list_by_code_exposes_only_safe_order_reference(self):
        event = sanitize_runtime_event({
            "agent_event": "tool.run_skill_artifact.start",
            "activity": "running_tool",
            "runtime_scope": "general_chat",
            "invocation_id": "lookup-123",
            "args_redacted": [
                "--profile",
                "default",
                "order",
                "list",
                "--code",
                "HWINSTAD2025071509",
                "--token",
                "[REDACTED]",
            ],
        })

        self.assertEqual(
            event["payload"]["order_ref"],
            "HWINSTAD2025071509",
        )
        self.assertNotIn("profile", str(event).lower())
        self.assertNotIn("token", str(event).lower())

    def test_order_reference_rejects_non_identifier_arguments(self):
        event = sanitize_runtime_event({
            "agent_event": "tool.run_skill_artifact.start",
            "activity": "running_tool",
            "runtime_scope": "general_chat",
            "invocation_id": "lookup-unsafe",
            "args_redacted": [
                "order",
                "get",
                "../../private-order",
            ],
        })

        self.assertNotIn("order_ref", event["payload"])

    def test_structured_analysis_activity_exposes_allowlisted_operation(self):
        event = sanitize_runtime_event({
            "agent_event": "tool.analyze_structured_output.start",
            "activity": "running_tool",
            "runtime_scope": "general_chat",
            "invocation_id": "analysis-123",
            "operation": "count",
            "input_ref": "/large_tool_results/private.txt",
        })

        self.assertEqual(
            event["payload"],
            {
                "id": "analysis-123",
                "kind": "count_results",
                "stage_kind": "result_analysis",
                "status": "in_progress",
            },
        )
        self.assertNotIn("input_ref", str(event))

    def test_non_general_chat_tool_event_keeps_original_public_shape(self):
        event = sanitize_runtime_event({
            "agent_event": "tool.run_skill_artifact.start",
            "activity": "running_tool",
            "invocation_id": "activity-123",
            "args_redacted": ["order", "list"],
        })

        self.assertEqual(
            event,
            {
                "agent_event": "tool.run_skill_artifact.start",
                "activity": "running_tool",
            },
        )

    def test_general_chat_model_round_is_not_user_visible(self):
        event = sanitize_runtime_event({
            "agent_event": "model.round.start",
            "runtime_scope": "general_chat",
            "invocation_id": "model-round-2",
            "round": 2,
            "summary": "private model reasoning",
        })

        self.assertIsNone(event)

    def test_termination_detail_uses_fixed_public_contract(self):
        detail = sanitize_termination_detail({
            "reason": "secret-token",
            "capability": "mcp",
            "error_type": "secret-token",
            "tool": "Authorization: secret-token",
            "recovery": "Authorization: secret-token",
            "code": "secret-token",
        })

        self.assertEqual(detail, {"capability": "mcp"})
        self.assertNotIn("secret-token", str(detail))

    def test_run_serializer_hides_runtime_credentials(self):
        run = create_execution_run(
            session=self.session,
            question="Use the connector",
            enqueue=False,
        )
        execution = create_run_execution_snapshot(run)
        execution.loaded_mcps = [
            {
                "mcp_uuid": "mcp-1",
                "mcp_name": "Orders",
                "transport": "streamable_http",
                "endpoint": "https://example.test/mcp",
                "config": {"headers": {"Authorization": "secret-token"}},
            }
        ]
        execution.save(update_fields=["loaded_mcps"])

        payload = RunSerializer(run).data

        self.assertNotIn("secret-token", str(payload))
        self.assertNotIn("endpoint", payload["execution"]["loaded_mcps"][0])
        self.assertEqual(
            payload["execution"]["loaded_mcps"][0]["mcp_name"],
            "Orders",
        )

    def test_append_lensnode_output_ignores_terminal_run(self):
        run = create_execution_run(
            session=self.session,
            question="What does this project do?",
            enqueue=False,
        )
        run.status = Run.Status.CANCELLED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])

        append_lensnode_output(run.uuid, content_delta="late answer")

        run.refresh_from_db()
        self.assertEqual(run.output_message.content, "")

    def test_lensnode_websocket_hello_output_and_done(self):
        token = issue_lensnode_token(self.lensnode)

        async_to_sync(self._exercise_lensnode_websocket)(token)

        self.lensnode.refresh_from_db()
        self.assertEqual(self.lensnode.protocol_version, "v1")
        self.lensnode.status = LensNode.Status.ONLINE
        self.lensnode.save(update_fields=["status"])

        run = create_execution_run(
            session=self.session,
            question="How does SSE work?",
            enqueue=False,
        )
        execute_answer_run(run, dispatch=True)

        async_to_sync(self._exercise_lensnode_run_frames)(token, run)

        run.refresh_from_db()
        self.assertEqual(run.status, Run.Status.DONE)
        self.assertEqual(run.output_message.content, "answer")

    def test_lensnode_websocket_rejects_revoked_token(self):
        token = issue_lensnode_token(self.lensnode)
        self.lensnode.token_revoked = True
        self.lensnode.save(update_fields=["token_revoked"])
        communicator = WebsocketCommunicator(
            application,
            f"/ws/lens/lensnodes/?token={token}",
        )

        connected, _ = async_to_sync(communicator.connect)()

        self.assertFalse(connected)

    async def _exercise_lensnode_websocket(self, token):
        """Connect a LensNode and send a hello frame in one event loop."""

        communicator = WebsocketCommunicator(
            application,
            f"/ws/lens/lensnodes/?token={token}",
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_json_from()
        await communicator.send_json_to(
            {
                "type": "hello",
                "protocol_version": "v1",
                "agent_version": "1.0.0",
                "workspace_path": "/workspace",
                "available_dirs": [{"path": "/workspace/repo"}],
                "tasks": [{"name": "knowledge_qa"}],
                "labels": {"region": "local"},
            }
        )
        self.assertEqual(
            (await communicator.receive_json_from())["type"],
            "hello_ack",
        )
        await communicator.disconnect()

    async def _exercise_lensnode_run_frames(self, token, run):
        """Connect a LensNode and send run result frames in one event loop."""

        communicator = WebsocketCommunicator(
            application,
            f"/ws/lens/lensnodes/?token={token}",
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.receive_json_from()
        await communicator.send_json_to(
            {
                "type": "run_event",
                "run_uuid": str(run.uuid),
                "step_type": "retrieval",
                "status": "done",
                "detail": {"hits": 2},
            }
        )
        await communicator.send_json_to(
            {
                "type": "run_output",
                "run_uuid": str(run.uuid),
                "content_delta": "answer",
            }
        )
        await communicator.send_json_to(
            {
                "type": "run_done",
                "run_uuid": str(run.uuid),
                "status": "done",
            }
        )
        await communicator.disconnect()

    def test_source_sync_task_dispatches_without_waiting_for_result(self):
        with patch("lens.tasks.dispatch_datasource_sync_async") as dispatch:
            dispatch.return_value = "request-1"
            synced = source_sync_task(str(self.datasource.uuid))
            self.datasource.refresh_from_db()

            record = ScheduledTask.objects.get(
                task_type="source_sync",
                target_type="datasource",
                target_id=self.datasource.uuid,
            )
            self.assertEqual(synced, 0)
            self.assertEqual(self.datasource.status, "active")
            self.assertIsNone(self.datasource.last_synced_at)
            self.assertEqual(record.last_status, "running")
            self.assertEqual(record.last_metrics, {})
            task = TaskExecution.objects.get(module="lens_datasource")
            self.assertEqual(task.task_name, "datasource_sync:Repo Cache")
            self.assertEqual(task.status, "STARTED")
            self.assertEqual(task.metadata["type"], "datasource")
            self.assertEqual(
                task.metadata["completion_source"],
                "lensnode_callback",
            )
            self.assertEqual(
                task.metadata["datasource_sync_request_id"],
                "request-1",
            )
            self.assertEqual(task.metadata["source_type"], "git")
            self.assertEqual(
                task.metadata["repo_url"],
                "https://example.com/repo.git",
            )
            self.assertEqual(task.metadata["lensnode_name"], "Local LensNode")
            self.assertEqual(
                task.metadata["target_path"],
                "/workspace/repo-cache",
            )
            self.assertEqual(task.metadata["conversion"], {})
            self.assertFalse(task.metadata["conversion_enabled"])
            self.assertEqual(
                task.metadata["sync_policy"],
                {"interval_seconds": 3600},
            )
            self.assertEqual(task.metadata["sync_interval_seconds"], 3600)
            steps = task.metadata.get("steps") or []
            self.assertGreaterEqual(len(steps), 2)
            self.assertEqual(steps[0]["name"], "prepare")
            self.assertEqual(steps[-1]["name"], "dispatch")

    def test_source_sync_task_reuses_registered_task_id(self):
        task_id = "manual-sync"
        register_datasource_sync_task(
            self.datasource,
            task_id,
            "manual",
            created_by=self.user,
            metadata={"celery_task_id": "celery-sync"},
        )

        with patch("lens.tasks.dispatch_datasource_sync_async") as dispatch:
            dispatch.return_value = "request-1"
            synced = source_sync_task(
                str(self.datasource.uuid),
                "manual",
                task_id,
            )

        self.assertEqual(synced, 0)
        self.assertEqual(
            TaskExecution.objects.filter(module="lens_datasource").count(),
            1,
        )
        task = TaskExecution.objects.get(task_id=task_id)
        self.assertEqual(task.status, "STARTED")
        self.assertEqual(task.created_by, self.user)
        self.assertEqual(task.metadata["celery_task_id"], "celery-sync")
        dispatch.assert_called_once_with(
            self.datasource,
            task_id=task_id,
            trigger="manual",
        )

    def test_datasource_sync_task_metadata_includes_conversion_policy(self):
        self.datasource.sync_policy = {
            "interval_seconds": 3600,
            "conversion": {
                "document": True,
                "image": False,
            },
        }
        self.datasource.save(update_fields=["sync_policy"])

        task = register_datasource_sync_task(
            self.datasource,
            "conversion-sync",
            "manual",
        )

        self.assertTrue(task.metadata["conversion_enabled"])
        self.assertEqual(
            task.metadata["conversion"],
            {
                "document": True,
                "image": False,
            },
        )

    def test_datasource_sync_dispatch_includes_max_workers(self):
        GlobalSetting.objects.create(
            key="lens.datasource_sync.workers",
            value=8,
            description="",
        )

        with patch("lens.datasource_services._send_lensnode_command") as send:
            dispatch_datasource_sync_async(
                self.datasource,
                task_id="task-1",
                trigger="manual",
            )

        payload = send.call_args.args[1]
        self.assertEqual(payload["max_workers"], 8)

    def test_complete_datasource_sync_task_updates_records(self):
        with patch("lens.tasks.dispatch_datasource_sync_async") as dispatch:
            dispatch.return_value = "request-1"
            source_sync_task(str(self.datasource.uuid))

        task = TaskExecution.objects.get(module="lens_datasource")
        complete_datasource_sync_task(
            task.task_id,
            {
                "status": "success",
                "synced": 1,
                "files": 3,
                "target_path": self.datasource.target_path,
            },
        )

        self.datasource.refresh_from_db()
        record = ScheduledTask.objects.get(
            task_type="source_sync",
            target_type="datasource",
            target_id=self.datasource.uuid,
        )
        task.refresh_from_db()
        self.assertIsNotNone(self.datasource.last_synced_at)
        self.assertEqual(record.last_status, "success")
        self.assertEqual(
            record.last_metrics,
            {
                "synced": 1,
                "files": 3,
                "folders": 0,
                "failed": 0,
                "scanned": 0,
                "changed": 1,
                "skipped": 0,
                "deleted": 0,
                "documents": 0,
                "by_extension": {},
                "by_type": {},
                "repository_summaries": [],
                "failed_repositories": [],
                "partial_success": False,
                "target_path": self.datasource.target_path,
            },
        )
        self.assertEqual(task.status, "SUCCESS")
        self.assertEqual(task.metadata["progress_percent"], 100)

    def test_complete_datasource_sync_task_preserves_zero_changed(self):
        with patch("lens.tasks.dispatch_datasource_sync_async") as dispatch:
            dispatch.return_value = "request-1"
            source_sync_task(str(self.datasource.uuid))

        task = TaskExecution.objects.get(module="lens_datasource")
        complete_datasource_sync_task(
            task.task_id,
            {
                "status": "success",
                "synced": 4,
                "changed": 0,
                "skipped": 4,
                "files": 4,
                "target_path": self.datasource.target_path,
            },
        )

        record = ScheduledTask.objects.get(
            task_type="source_sync",
            target_type="datasource",
            target_id=self.datasource.uuid,
        )
        task.refresh_from_db()
        self.assertEqual(record.last_metrics["changed"], 0)
        self.assertEqual(task.result["changed"], 0)
        self.assertEqual(task.metadata["sync_summary"]["changed"], 0)

    def test_complete_datasource_sync_task_keeps_summaries_separate(self):
        with patch("lens.tasks.dispatch_datasource_sync_async") as dispatch:
            dispatch.return_value = "request-1"
            source_sync_task(str(self.datasource.uuid))

        task = TaskExecution.objects.get(module="lens_datasource")
        complete_datasource_sync_task(
            task.task_id,
            {
                "status": "success",
                "synced": 1,
                "changed": 1,
                "files": 1,
                "details": {
                    "changed": [
                        {
                            "path": "README.md",
                            "name": "README.md",
                            "status": "synced",
                        }
                    ]
                },
                "changed_items": [
                    {
                        "path": "README.md",
                        "name": "README.md",
                        "status": "synced",
                    }
                ],
                "conversion_summary": {
                    "candidates": 1,
                    "converted": 1,
                    "items": [
                        {
                            "path": "README.md",
                            "name": "README.md",
                            "status": "converted",
                        }
                    ],
                },
                "target_path": self.datasource.target_path,
            },
        )

        task.refresh_from_db()
        self.assertIn("conversion_summary", task.metadata)
        self.assertNotIn(
            "conversion_summary",
            task.metadata["sync_summary"],
        )
        self.assertNotIn("conversion_summary", task.result)
        self.assertNotIn("details", task.result)
        self.assertNotIn("changed_items", task.metadata["sync_summary"])
        self.assertNotIn("changed_items", task.result)
        self.assertEqual(
            task.metadata["sync_summary"]["details"]["changed"][0]["path"],
            "README.md",
        )

    def test_datasource_sync_event_updates_realtime_sync_details(self):
        TaskExecution.objects.create(
            task_id="live-sync",
            task_name="datasource_sync:Repo Cache",
            module="lens_datasource",
            status="STARTED",
            metadata={
                "datasource_uuid": str(self.datasource.uuid),
                "sync_summary": {"changed": 1},
            },
        )

        LensNodeConsumer._record_datasource_sync_event(
            "live-sync",
            {
                "step": "item_done",
                "status": "done",
                "message": "Downloaded README.md.",
                "kind": "file",
                "item_name": "README.md",
                "file": "README.md",
                "file_extension": "md",
            },
        )

        task = TaskExecution.objects.get(task_id="live-sync")
        details = task.metadata["sync_summary"]["details"]
        self.assertEqual(details["changed"][0]["path"], "README.md")
        self.assertEqual(details["success"][0]["name"], "README.md")

    def test_datasource_sync_event_updates_realtime_conversion_details(self):
        TaskExecution.objects.create(
            task_id="live-conversion",
            task_name="datasource_sync:Repo Cache",
            module="lens_datasource",
            status="STARTED",
            metadata={
                "datasource_uuid": str(self.datasource.uuid),
                "conversion_summary": {"converted": 1},
            },
        )

        LensNodeConsumer._record_datasource_sync_event(
            "live-conversion",
            {
                "step": "conversion_progress",
                "status": "running",
                "category": "conversion",
                "message": "Converted 1/1 datasource files.",
                "summary": {"converted": 1, "success": 1},
                "current_file": "README.md",
                "current_status": "converted",
                "current_stats": {
                    "chars": 120,
                    "cost": {"model_calls": 1, "total_tokens": 30},
                },
            },
        )

        task = TaskExecution.objects.get(task_id="live-conversion")
        details = task.metadata["conversion_summary"]["details"]
        self.assertEqual(details["converted"][0]["path"], "README.md")
        self.assertEqual(details["model_calls"][0]["stats"]["chars"], 120)

    def test_source_sync_task_marks_invalid_source_failed(self):
        with patch("lens.tasks.dispatch_datasource_sync_async") as dispatch:
            dispatch.side_effect = RuntimeError("LENS_SOURCE_CONFIG_INVALID")
            with self.assertRaises(RuntimeError):
                source_sync_task(str(self.datasource.uuid))

        self.datasource.refresh_from_db()
        record = ScheduledTask.objects.get(
            task_type="source_sync",
            target_type="datasource",
            target_id=self.datasource.uuid,
        )
        self.assertEqual(self.datasource.status, "active")
        self.assertEqual(
            self.datasource.last_error,
            "LENS_SOURCE_CONFIG_INVALID",
        )
        self.assertEqual(record.last_status, "failed")

    def test_complete_datasource_sync_task_marks_failure(self):
        with patch("lens.tasks.dispatch_datasource_sync_async") as dispatch:
            dispatch.return_value = "request-1"
            source_sync_task(str(self.datasource.uuid))

        task = TaskExecution.objects.get(module="lens_datasource")
        complete_datasource_sync_task(
            task.task_id,
            {
                "status": "failed",
                "error": "LENS_SOURCE_CONFIG_INVALID",
            },
        )

        self.datasource.refresh_from_db()
        record = ScheduledTask.objects.get(
            task_type="source_sync",
            target_type="datasource",
            target_id=self.datasource.uuid,
        )
        task.refresh_from_db()
        self.assertEqual(
            self.datasource.last_error,
            "LENS_SOURCE_CONFIG_INVALID",
        )
        self.assertEqual(record.last_status, "failed")
        self.assertEqual(task.status, "FAILURE")

    def test_source_sync_task_rejects_concurrent_sync(self):
        # Simulate a real in-flight sync: a running task owns the lock. The
        # orphan-reclaim must keep its hands off an owned lock, so a second
        # sync is rejected as busy. (A bare lock with no owning task is now
        # treated as orphaned and reclaimable, so it would not be rejected.)
        owner_token = "owner-sync"
        acquire_datasource_lock(self.datasource.uuid, token=owner_token)
        TaskExecution.objects.create(
            task_id=owner_token,
            task_name="datasource_sync:Repo Cache",
            module="lens_datasource",
            status="STARTED",
            metadata={
                "datasource_uuid": str(self.datasource.uuid),
                "lock_token": owner_token,
            },
        )
        try:
            synced = source_sync_task(
                str(self.datasource.uuid), task_id="rejected-sync"
            )
        finally:
            release_datasource_lock(self.datasource.uuid, token=owner_token)

        self.datasource.refresh_from_db()
        record = ScheduledTask.objects.get(
            task_type="source_sync",
            target_type="datasource",
            target_id=self.datasource.uuid,
        )
        task = TaskExecution.objects.get(task_id="rejected-sync")
        self.assertEqual(synced, 0)
        self.assertEqual(self.datasource.status, "active")
        self.assertEqual(record.last_status, "running")
        self.assertEqual(record.last_error, "LENS_SOURCE_SYNC_BUSY")
        self.assertEqual(task.status, "REVOKED")
        self.assertEqual(task.error, "LENS_SOURCE_SYNC_BUSY")
        self.assertEqual(task.metadata["progress_step"], "lock")
        self.assertEqual(
            task.metadata["progress_message"],
            "LENS_SOURCE_SYNC_BUSY",
        )

    def test_cleanup_stale_datasource_sync_releases_lock(self):
        GlobalSetting.objects.create(
            key="lens.datasource_sync.timeout_s",
            value="1",
        )
        task = TaskExecution.objects.create(
            task_id="stale-sync",
            task_name="datasource_sync:Repo Cache",
            module="lens_datasource",
            status="STARTED",
            started_at=timezone.now() - timedelta(seconds=2),
            metadata={
                "datasource_uuid": str(self.datasource.uuid),
                "lock_token": "stale-sync",
            },
        )
        acquire_datasource_lock(
            self.datasource.uuid,
            token="stale-sync",
            ttl_s=60,
        )

        with patch(
            "lens.services.cancel_datasource_sync_on_lensnode"
        ) as cancel:
            result = cleanup_stale_datasource_sync_tasks()

        task.refresh_from_db()
        record = ScheduledTask.objects.get(
            task_type="source_sync",
            target_type="datasource",
            target_id=self.datasource.uuid,
        )
        self.assertEqual(result["failed"], 1)
        self.assertEqual(task.status, "FAILURE")
        self.assertEqual(task.error, "LENS_SOURCE_SYNC_TIMEOUT")
        self.assertEqual(record.last_status, "failed")
        self.assertEqual(record.last_error, "LENS_SOURCE_SYNC_TIMEOUT")
        cancel.assert_called_once_with(self.lensnode, "stale-sync")

        acquire_datasource_lock(
            self.datasource.uuid,
            token="new-sync",
            ttl_s=60,
        )
        release_datasource_lock(self.datasource.uuid, token="new-sync")

    def test_startup_cleanup_keeps_fresh_datasource_sync_running(self):
        GlobalSetting.objects.create(
            key="lens.datasource_sync.timeout_s",
            value="60",
        )
        task = TaskExecution.objects.create(
            task_id="fresh-sync",
            task_name="datasource_sync:Repo Cache",
            module="lens_datasource",
            status="STARTED",
            started_at=timezone.now(),
            metadata={
                "datasource_uuid": str(self.datasource.uuid),
                "lock_token": "fresh-sync",
                "completion_source": "lensnode_callback",
            },
        )
        acquire_datasource_lock(
            self.datasource.uuid,
            token="fresh-sync",
            ttl_s=60,
        )

        with patch(
            "lens.services.cancel_datasource_sync_on_lensnode"
        ) as cancel:
            result = cleanup_stale_datasource_sync_tasks(startup=True)

        task.refresh_from_db()
        self.assertEqual(result["failed"], 0)
        self.assertEqual(task.status, "STARTED")
        cancel.assert_not_called()
        self.assertFalse(
            release_datasource_lock(
                self.datasource.uuid,
                token="other-sync",
            )
        )
        release_datasource_lock(self.datasource.uuid, token="fresh-sync")

    def test_cleanup_releases_completed_datasource_sync_lock(self):
        GlobalSetting.objects.create(
            key="lens.datasource_sync.timeout_s",
            value="60",
        )
        TaskExecution.objects.create(
            task_id="timed-out-sync",
            task_name="datasource_sync:Repo Cache",
            module="lens_datasource",
            status="FAILURE",
            finished_at=timezone.now(),
            metadata={
                "datasource_uuid": str(self.datasource.uuid),
                "lock_token": "timed-out-sync",
            },
        )
        acquire_datasource_lock(
            self.datasource.uuid,
            token="timed-out-sync",
            ttl_s=60,
        )

        with patch(
            "lens.services.cancel_datasource_sync_on_lensnode"
        ) as cancel:
            result = cleanup_stale_datasource_sync_tasks()

        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["locks_released"], 1)
        cancel.assert_called_once_with(self.lensnode, "timed-out-sync")
        acquire_datasource_lock(
            self.datasource.uuid,
            token="new-sync",
            ttl_s=60,
        )
        release_datasource_lock(self.datasource.uuid, token="new-sync")

    def test_acquire_datasource_lock_recovers_completed_owner_lock(self):
        TaskExecution.objects.create(
            task_id="completed-sync",
            task_name="datasource_sync:Repo Cache",
            module="lens_datasource",
            status="REVOKED",
            metadata={
                "datasource_uuid": str(self.datasource.uuid),
                "lock_token": "completed-sync",
            },
        )
        acquire_datasource_lock(
            self.datasource.uuid,
            token="completed-sync",
            ttl_s=60,
        )

        acquire_datasource_lock(
            self.datasource.uuid,
            token="new-sync",
            ttl_s=60,
        )
        release_datasource_lock(self.datasource.uuid, token="new-sync")

    def test_acquire_datasource_lock_recovers_ownerless_lock(self):
        acquire_datasource_lock(
            self.datasource.uuid,
            token="missing-owner",
            ttl_s=60,
        )

        acquire_datasource_lock(
            self.datasource.uuid,
            token="new-sync",
            ttl_s=60,
        )
        release_datasource_lock(self.datasource.uuid, token="new-sync")

    def test_source_sync_task_dispatches_feishu_datasource(self):
        self.datasource.source_type = DataSource.SourceType.FEISHU
        self.datasource.config = {
            "app_token": "app-token",
            "doc_ids": ["doc-1", "doc-2"],
        }
        self.datasource.save(update_fields=["source_type", "config"])

        with patch("lens.tasks.dispatch_datasource_sync_async") as dispatch:
            dispatch.return_value = "request-1"
            synced = source_sync_task(str(self.datasource.uuid))

        self.assertEqual(synced, 0)
        dispatch.assert_called_once()

    def test_lensnode_health_marks_stale_lensnodes_offline(self):
        self.lensnode.status = LensNode.Status.ONLINE
        self.lensnode.last_heartbeat_at = timezone.now() - timedelta(seconds=120)
        self.lensnode.save(update_fields=["status", "last_heartbeat_at"])

        marked = lensnode_health_task()

        self.lensnode.refresh_from_db()
        self.assertEqual(marked, 1)
        self.assertEqual(self.lensnode.status, LensNode.Status.OFFLINE)

    def test_register_periodic_tasks_adds_lens_entries(self):
        TASK_REGISTRY.clear()

        register_periodic_tasks()

        self.assertEqual(
            ScheduledTask.objects.filter(
                task_type="lensnode_cleanup",
                target_type=None,
            ).count(),
            1,
        )
        self.assertEqual(
            ScheduledTask.objects.filter(
                task_type="lensnode_health",
                target_type=None,
            ).count(),
            1,
        )
        self.assertGreaterEqual(len(TASK_REGISTRY), 4)

    def test_register_periodic_tasks_uses_global_interval_settings(self):
        GlobalSetting.objects.create(
            key="lensnode_cleanup.interval_seconds",
            value=1800,
        )
        GlobalSetting.objects.create(
            key="lensnode_health.interval_seconds",
            value=120,
        )
        GlobalSetting.objects.create(
            key="run_retention.interval_seconds",
            value=7200,
        )

        TASK_REGISTRY.clear()
        discover_and_register()

        cleanup = PeriodicTask.objects.get(name="lens-lensnode-cleanup")
        health = PeriodicTask.objects.get(name="lens-lensnode-health")
        retention = PeriodicTask.objects.get(name="lens-run-retention")

        self.assertEqual(cleanup.interval.every, 1800)
        self.assertEqual(health.interval.every, 120)
        self.assertEqual(retention.interval.every, 7200)

    def test_datasource_periodic_task_updates_existing_beat_row(self):
        record = ensure_datasource_periodic_task(self.datasource)
        task = PeriodicTask.objects.get(pk=record.periodic_task_ref)
        task.enabled = False
        task.save(update_fields=["enabled"])

        self.datasource.sync_policy = {"interval_seconds": 120}
        self.datasource.save(update_fields=["sync_policy", "updated_at"])

        ensure_datasource_periodic_task(self.datasource)

        task.refresh_from_db()
        self.assertTrue(task.enabled)
        self.assertEqual(task.interval.every, 120)
        self.assertEqual(task.interval.period, "seconds")
        self.assertEqual(task.task, "lens.source_sync")
        self.assertEqual(task.args, f'["{self.datasource.uuid}"]')
        self.assertEqual(task.queue, "lens")

    def test_datasource_periodic_task_supports_crontab_policy(self):
        self.datasource.sync_policy = {
            "mode": "crontab",
            "cron": "0 2 * * *",
            "timezone": "Asia/Shanghai",
        }
        self.datasource.save(update_fields=["sync_policy", "updated_at"])

        record = ensure_datasource_periodic_task(self.datasource)

        task = PeriodicTask.objects.get(pk=record.periodic_task_ref)
        self.assertIsNone(task.interval_id)
        self.assertIsNotNone(task.crontab_id)
        self.assertEqual(task.crontab.minute, "0")
        self.assertEqual(task.crontab.hour, "2")
        self.assertEqual(str(task.crontab.timezone), "Asia/Shanghai")

    def test_discover_and_register_reconciles_datasource_beat_row(self):
        record = ensure_datasource_periodic_task(self.datasource)
        task = PeriodicTask.objects.get(pk=record.periodic_task_ref)
        task.enabled = False
        task.save(update_fields=["enabled"])
        self.datasource.sync_policy = {"interval_seconds": 120}
        self.datasource.save(update_fields=["sync_policy", "updated_at"])

        discover_and_register()

        task.refresh_from_db()
        self.assertTrue(task.enabled)
        self.assertEqual(task.interval.every, 120)

    def test_discover_and_register_backfills_periodic_task_refs(self):
        discover_and_register()

        task_types = {
            "lensnode_cleanup",
            "lensnode_health",
            "run_retention",
            "source_sync",
        }
        tasks = ScheduledTask.objects.filter(task_type__in=task_types)
        self.assertTrue(tasks.exists())
        self.assertFalse(tasks.filter(periodic_task_ref__isnull=True).exists())

    def _local_git_repo(self):
        """Create a temporary git repo for source sync tests."""

        import shutil
        import subprocess
        import tempfile

        @contextmanager
        def repo_context():
            root = Path(tempfile.mkdtemp(prefix="lens-git-source-"))
            try:
                subprocess.run(
                    ["git", "init", "-b", "main"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "config", "user.email", "lens@example.com"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "config", "user.name", "Lens Test"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                (root / "README.md").write_text("hello lens\n")
                subprocess.run(
                    ["git", "add", "README.md"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "commit", "-m", "Initial commit"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                yield str(root)
            finally:
                shutil.rmtree(root, ignore_errors=True)

        return repo_context()

    def _target_path(self):
        """Create an empty target path value for source sync tests."""

        import shutil
        import tempfile

        @contextmanager
        def target_context():
            root = Path(tempfile.mkdtemp(prefix="lens-target-"))
            target = root / "cache"
            try:
                yield str(target)
            finally:
                shutil.rmtree(root, ignore_errors=True)

        return target_context()
