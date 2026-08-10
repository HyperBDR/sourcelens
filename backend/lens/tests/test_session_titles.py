from datetime import timedelta
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from lens.assistant_lifecycle import create_assistant_session
from lens.llm import LensLLMResult
from lens.models import Assistant, LensNode, Message, Run, Session
from lens.serializers import SessionSerializer
from lens.services import create_execution_run, finish_lensnode_run
from lens.session_titles import (
    fallback_session_title,
    generate_semantic_session_title,
    normalize_generated_title,
)
from lens.tasks import (
    expire_stale_session_titles,
    generate_session_title,
    generate_session_title_legacy,
)


class SessionTitleTests(TestCase):
    """Cover semantic title generation and manual-rename precedence."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="title-user",
            password="pass12345",
        )
        self.lensnode = LensNode.objects.create(
            name="Title Node",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            workspace_path="/workspace",
            available_dirs=[{"path": "/workspace/repo"}],
            tasks=[{"name": "general_chat"}],
        )
        self.assistant = Assistant.objects.create(
            name="Title Assistant",
            slug="title-assistant",
            lensnode=self.lensnode,
            selected_task="general_chat",
            agent_model_ref=uuid.uuid4(),
            visibility=Assistant.Visibility.PUBLIC,
        )
        self.session = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
            title_generation_status=Session.TitleGenerationStatus.PENDING,
        )

    def _completed_run(self, question="What caused this error?", session=None):
        session = session or self.session
        run = create_execution_run(
            session=session,
            question=question,
            enqueue=False,
        )
        run.output_message.content = (
            "PostgreSQL lock timeout caused the error."
        )
        run.output_message.save(update_fields=["content"])
        return run

    def test_first_question_is_persisted_as_fallback(self):
        question = "Explain why this deployment command keeps failing today"

        self._completed_run(question)

        self.session.refresh_from_db()
        self.assertEqual(
            self.session.title,
            fallback_session_title(question),
        )
        self.assertEqual(
            self.session.title_generation_status,
            Session.TitleGenerationStatus.PENDING,
        )

    def test_new_sessions_distinguish_pending_and_manual_titles(self):
        pending = create_assistant_session(
            self.assistant.uuid,
            self.user,
        )
        manual = create_assistant_session(
            self.assistant.uuid,
            self.user,
            "  Manual   title  ",
        )

        self.assertEqual(
            pending.title_generation_status,
            Session.TitleGenerationStatus.PENDING,
        )
        self.assertFalse(pending.title_manually_edited)
        self.assertEqual(manual.title, "Manual title")
        self.assertEqual(
            manual.title_generation_status,
            Session.TitleGenerationStatus.SKIPPED,
        )
        self.assertTrue(manual.title_manually_edited)

    def test_empty_session_creation_reuses_existing_session(self):
        first = create_assistant_session(self.assistant.uuid, self.user)
        second = create_assistant_session(self.assistant.uuid, self.user)

        self.assertEqual(first.uuid, second.uuid)
        self.assertEqual(
            Session.objects.filter(
                assistant=self.assistant,
                user=self.user,
                title="",
            ).count(),
            1,
        )

    def test_session_with_messages_is_not_reused(self):
        first = create_assistant_session(self.assistant.uuid, self.user)
        Message.objects.create(
            session=first,
            role=Message.Role.USER,
            content="Existing conversation",
            sequence=1,
        )

        second = create_assistant_session(self.assistant.uuid, self.user)

        self.assertNotEqual(first.uuid, second.uuid)

    def test_legacy_session_gets_fallback_on_first_run(self):
        legacy = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
            title_generation_status=Session.TitleGenerationStatus.SKIPPED,
        )

        run = create_execution_run(
            session=legacy,
            question="Explain the legacy session title behavior",
            enqueue=False,
        )

        legacy.refresh_from_db()
        self.assertEqual(
            legacy.title,
            fallback_session_title(run.input_message.content),
        )
        self.assertEqual(
            legacy.title_generation_status,
            Session.TitleGenerationStatus.PENDING,
        )

    @patch("lens.tasks.generate_session_title.apply_async")
    def test_backfill_command_queues_completed_legacy_session(self, delay):
        legacy = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
            title_generation_status=Session.TitleGenerationStatus.SKIPPED,
        )
        run = self._completed_run(session=legacy)
        run.status = Run.Status.DONE
        run.outcome = Run.Outcome.COMPLETED
        run.save(update_fields=["status", "outcome"])
        legacy.title = ""
        legacy.title_generation_status = Session.TitleGenerationStatus.SKIPPED
        legacy.save(update_fields=["title", "title_generation_status"])

        call_command("backfill_session_titles")

        legacy.refresh_from_db()
        self.assertEqual(
            legacy.title,
            fallback_session_title(run.input_message.content),
        )
        self.assertEqual(
            legacy.title_generation_status,
            Session.TitleGenerationStatus.PENDING,
        )
        delay.assert_called_once()
        self.assertEqual(
            delay.call_args.kwargs["args"],
            [str(legacy.uuid), str(run.uuid)],
        )
        self.assertEqual(
            delay.call_args.kwargs["expires"],
            900,
        )

    @patch("lens.tasks.generate_session_title.apply_async")
    def test_backfill_queues_attachment_only_completed_session(self, delay):
        legacy = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
            title_generation_status=Session.TitleGenerationStatus.SKIPPED,
        )
        run = self._completed_run(question="", session=legacy)
        run.status = Run.Status.DONE
        run.outcome = Run.Outcome.COMPLETED
        run.save(update_fields=["status", "outcome"])

        call_command("backfill_session_titles")

        legacy.refresh_from_db()
        self.assertEqual(legacy.title, "")
        self.assertEqual(
            legacy.title_generation_status,
            Session.TitleGenerationStatus.PENDING,
        )
        delay.assert_called_once_with(
            args=[str(legacy.uuid), str(run.uuid)],
            expires=900,
        )

    def test_title_task_is_versioned_and_stale_titles_expire(self):
        stale_pending = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
            title="Stale fallback",
            title_generation_status=Session.TitleGenerationStatus.PENDING,
        )
        stale_generating = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
            title="Stale generating fallback",
            title_generation_status=Session.TitleGenerationStatus.GENERATING,
        )
        active = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
            title="Active run fallback",
            title_generation_status=Session.TitleGenerationStatus.PENDING,
        )
        active_run = self._completed_run(session=active)
        active_run.status = Run.Status.RUNNING
        active_run.save(update_fields=["status"])
        fresh = Session.objects.create(
            assistant=self.assistant,
            user=self.user,
            title="Fresh fallback",
            title_generation_status=Session.TitleGenerationStatus.PENDING,
        )
        stale_time = timezone.now() - timedelta(minutes=16)
        Session.objects.filter(
            pk__in=[stale_pending.pk, stale_generating.pk, active.pk],
        ).update(updated_at=stale_time)

        expired = expire_stale_session_titles()

        self.assertEqual(expired, 2)
        stale_pending.refresh_from_db()
        stale_generating.refresh_from_db()
        active.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(
            stale_pending.title_generation_status,
            Session.TitleGenerationStatus.FAILED,
        )
        self.assertEqual(
            stale_generating.title_generation_status,
            Session.TitleGenerationStatus.FAILED,
        )
        self.assertEqual(
            active.title_generation_status,
            Session.TitleGenerationStatus.PENDING,
        )
        self.assertEqual(
            fresh.title_generation_status,
            Session.TitleGenerationStatus.PENDING,
        )
        self.assertEqual(
            generate_session_title.name,
            "lens.generate_session_title.v2",
        )
        self.assertEqual(
            generate_session_title_legacy.name,
            "lens.generate_session_title",
        )

    def test_database_defaults_support_old_session_inserts(self):
        session_uuid = uuid.uuid4()
        timestamp = timezone.now()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO lens_session (
                    uuid,
                    created_at,
                    updated_at,
                    title,
                    status,
                    assistant_id,
                    user_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    session_uuid.hex,
                    timestamp,
                    timestamp,
                    "Legacy session",
                    Session.Status.ACTIVE,
                    self.assistant.pk,
                    self.user.pk,
                ],
            )

        legacy_session = Session.objects.get(uuid=session_uuid)
        self.assertFalse(legacy_session.title_manually_edited)
        self.assertEqual(
            legacy_session.title_generation_status,
            Session.TitleGenerationStatus.SKIPPED,
        )

    @patch("lens.session_titles.run_completion")
    def test_generated_title_replaces_fallback_once(self, mock_completion):
        run = self._completed_run()
        mock_completion.return_value = LensLLMResult(
            content="**PostgreSQL Lock Timeout**\n",
            usage={"total_tokens": 12},
            metered=True,
        )

        first = generate_semantic_session_title(
            self.session.uuid,
            run.uuid,
        )
        second = generate_semantic_session_title(
            self.session.uuid,
            run.uuid,
        )

        self.session.refresh_from_db()
        self.assertEqual(first, "PostgreSQL Lock Timeout")
        self.assertEqual(second, "")
        self.assertEqual(self.session.title, "PostgreSQL Lock Timeout")
        self.assertEqual(
            self.session.title_generation_status,
            Session.TitleGenerationStatus.GENERATED,
        )
        mock_completion.assert_called_once()

    @patch("lens.session_titles.run_completion")
    def test_generated_title_uses_run_answer_language(self, mock_completion):
        self.user.profile.language = "zh-CN"
        self.user.profile.save(update_fields=["language"])
        run = self._completed_run("How many orders were created?")
        self.user.profile.language = "en-US"
        self.user.profile.save(update_fields=["language"])
        mock_completion.return_value = LensLLMResult(
            content="订单数量",
            usage={},
            metered=True,
        )

        generate_semantic_session_title(self.session.uuid, run.uuid)

        system_prompt = mock_completion.call_args.kwargs["system"]
        self.assertIn("Simplified Chinese", system_prompt)
        self.assertNotIn("conversation's primary language", system_prompt)

    @patch("lens.session_titles.run_completion")
    def test_manual_rename_wins_while_generation_is_running(
        self,
        mock_completion,
    ):
        run = self._completed_run()

        def rename_during_generation(**kwargs):
            del kwargs
            Session.objects.filter(pk=self.session.pk).update(
                title="Manual database investigation",
                title_manually_edited=True,
                title_generation_status=Session.TitleGenerationStatus.SKIPPED,
            )
            return LensLLMResult(
                content="PostgreSQL Lock Timeout",
                usage={},
                metered=True,
            )

        mock_completion.side_effect = rename_during_generation

        result = generate_semantic_session_title(
            self.session.uuid,
            run.uuid,
        )

        self.session.refresh_from_db()
        self.assertEqual(result, "")
        self.assertEqual(self.session.title, "Manual database investigation")
        self.assertTrue(self.session.title_manually_edited)

    @patch("lens.session_titles.run_completion", side_effect=RuntimeError)
    def test_generation_failure_preserves_fallback(self, mock_completion):
        run = self._completed_run()
        fallback = fallback_session_title(run.input_message.content)

        result = generate_semantic_session_title(
            self.session.uuid,
            run.uuid,
        )

        self.session.refresh_from_db()
        self.assertEqual(result, "")
        self.assertEqual(self.session.title, fallback)
        self.assertEqual(
            self.session.title_generation_status,
            Session.TitleGenerationStatus.FAILED,
        )
        mock_completion.assert_called_once()

    @patch("lens.session_titles.run_completion")
    def test_missing_assistant_model_uses_metering_default(
        self,
        mock_completion,
    ):
        run = self._completed_run()
        self.assistant.agent_model_ref = None
        self.assistant.save(update_fields=["agent_model_ref"])
        mock_completion.return_value = LensLLMResult(
            content="Default Model Title",
            usage={},
            metered=True,
        )

        result = generate_semantic_session_title(
            self.session.uuid,
            run.uuid,
        )

        self.session.refresh_from_db()
        self.assertEqual(result, "Default Model Title")
        self.assertEqual(
            self.session.title_generation_status,
            Session.TitleGenerationStatus.GENERATED,
        )
        self.assertIsNone(mock_completion.call_args.kwargs["model_ref"])

    def test_manual_title_validation_marks_generation_skipped(self):
        empty = SessionSerializer(
            self.session,
            data={"title": "   "},
            partial=True,
        )
        renamed = SessionSerializer(
            self.session,
            data={"title": "  Manual   title  "},
            partial=True,
        )

        self.assertFalse(empty.is_valid())
        self.assertTrue(renamed.is_valid(), renamed.errors)
        renamed.save()
        self.session.refresh_from_db()
        self.assertEqual(self.session.title, "Manual title")
        self.assertTrue(self.session.title_manually_edited)
        self.assertEqual(
            self.session.title_generation_status,
            Session.TitleGenerationStatus.SKIPPED,
        )

    def test_generated_title_rejects_sensitive_or_payload_content(self):
        self.assertEqual(
            normalize_generated_title("Authorization: Bearer hidden"),
            "",
        )
        self.assertEqual(normalize_generated_title('{"title": "Secret"}'), "")

    @patch("lens.services._enqueue_session_title_generation")
    def test_first_successful_answer_enqueues_generation(self, mock_enqueue):
        run = self._completed_run()

        with self.captureOnCommitCallbacks(execute=True):
            finish_lensnode_run(run.uuid, Run.Status.DONE)

        mock_enqueue.assert_called_once_with(self.session.uuid, run.uuid)

    @patch("lens.services._enqueue_session_title_generation")
    def test_blocked_answer_does_not_enqueue_generation(self, mock_enqueue):
        run = self._completed_run()

        with self.captureOnCommitCallbacks(execute=True):
            finish_lensnode_run(
                run.uuid,
                Run.Status.DONE,
                outcome=Run.Outcome.BLOCKED,
            )

        mock_enqueue.assert_not_called()
