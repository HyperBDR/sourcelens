import io
import tempfile
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from lens.llm import LensLLMResult
from lens.models import (
    Assistant,
    LensNode,
    Message,
    MessageAttachment,
    Session,
)
from lens.serializers import RunCreateSerializer
from lens.attachments import (
    AttachmentError,
    bind_attachments_to_message,
    store_message_attachment,
)
from lens.services import analyze_multimodal_intent, create_execution_run

User = get_user_model()


def _png_upload(name="shot.png", size=(2000, 1200), color=(120, 200, 80)):
    """Return a SimpleUploadedFile holding a real PNG image."""

    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return SimpleUploadedFile(
        name, buffer.getvalue(), content_type="image/png"
    )


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class AttachmentServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="img-user",
            email="img-user@example.com",
            password="pass12345",
        )
        self.lensnode = LensNode.objects.create(
            name="Local LensNode",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            workspace_path="/workspace",
        )
        self.assistant = Assistant.objects.create(
            name="Code Advisor",
            slug="code-advisor",
            lensnode=self.lensnode,
            selected_task="knowledge_qa",
            selected_dirs=[{"path": "/workspace/repo"}],
            visibility=Assistant.Visibility.PUBLIC,
            multimodal_model_ref=uuid.uuid4(),
        )
        self.session = Session.objects.create(
            assistant=self.assistant, user=self.user, title=""
        )

    def test_store_downscales_and_strips_metadata(self):
        attachment = store_message_attachment(
            self.session, self.user, _png_upload()
        )

        self.assertEqual(attachment.session, self.session)
        self.assertEqual(attachment.uploaded_by, self.user)
        self.assertEqual(attachment.mime_type, "image/png")
        self.assertLessEqual(max(attachment.width, attachment.height), 1600)
        self.assertGreater(attachment.byte_size, 0)
        self.assertIsNone(attachment.message_id)

    def test_store_rejects_oversized(self):
        big = _png_upload()
        big.size = 11 * 1024 * 1024
        with self.assertRaises(AttachmentError):
            store_message_attachment(self.session, self.user, big)

    def test_store_rejects_non_image(self):
        bad = SimpleUploadedFile(
            "notes.txt", b"hello not an image", content_type="text/plain"
        )
        with self.assertRaises(AttachmentError):
            store_message_attachment(self.session, self.user, bad)

    def test_bind_links_in_order_and_ignores_foreign(self):
        first = store_message_attachment(
            self.session, self.user, _png_upload()
        )
        second = store_message_attachment(
            self.session, self.user, _png_upload()
        )
        other_session = Session.objects.create(
            assistant=self.assistant, user=self.user
        )
        foreign = store_message_attachment(
            other_session, self.user, _png_upload()
        )
        message = Message.objects.create(
            session=self.session,
            role=Message.Role.USER,
            content="why?",
            sequence=1,
        )

        bind_attachments_to_message(
            self.session,
            message,
            [str(second.uuid), str(first.uuid), str(foreign.uuid)],
        )

        first.refresh_from_db()
        second.refresh_from_db()
        foreign.refresh_from_db()
        self.assertEqual(second.order, 0)
        self.assertEqual(first.order, 1)
        self.assertIsNone(foreign.message_id)

    def test_create_execution_run_binds_attachments(self):
        attachment = store_message_attachment(
            self.session, self.user, _png_upload()
        )

        run = create_execution_run(
            session=self.session,
            question="why this error?",
            enqueue=False,
            attachment_uuids=[str(attachment.uuid)],
        )

        attachment.refresh_from_db()
        self.assertEqual(attachment.message_id, run.input_message_id)
        self.assertEqual(run.input_message.attachments.count(), 1)

    @patch("lens.services.run_completion_multimodal")
    def test_analyze_multimodal_intent_folds_image_and_text(self, mock_call):
        mock_call.return_value = LensLLMResult(
            content="KeyError missing 'token' in auth middleware",
            usage={
                "total_tokens": 1234,
                "prompt_tokens": 1000,
                "completion_tokens": 234,
                "cost": 0.012,
            },
            metered=True,
        )
        attachment = store_message_attachment(
            self.session, self.user, _png_upload()
        )
        run = create_execution_run(
            session=self.session,
            question="为什么报错",
            enqueue=False,
            attachment_uuids=[str(attachment.uuid)],
        )

        result = analyze_multimodal_intent(run)

        self.assertTrue(mock_call.called)
        self.assertEqual(result["image_count"], 1)
        self.assertTrue(result["rewritten"])
        self.assertIn("KeyError", result["question"])
        self.assertEqual(result["usage"]["total_tokens"], 1234)

    def test_admin_run_step_counts_includes_preprocess_usage(self):
        from lens.models import RunStep
        from lens.views import _admin_run_step_counts

        run = create_execution_run(
            session=self.session, question="q", enqueue=False
        )
        RunStep.objects.create(
            run=run,
            sequence=0,
            step_type=RunStep.StepType.MULTIMODAL,
            status=RunStep.Status.DONE,
            detail={
                "usage": {
                    "total_tokens": 500,
                    "prompt_tokens": 400,
                    "completion_tokens": 100,
                    "cost": 0.02,
                }
            },
        )

        counts = _admin_run_step_counts(run)

        self.assertEqual(counts["llm_calls"], 1)
        self.assertEqual(counts["total_tokens"], 500)
        self.assertEqual(counts["prompt_tokens"], 400)
        self.assertEqual(counts["completion_tokens"], 100)
        self.assertEqual(counts["total_cost"], 0.02)

    def test_analyze_multimodal_intent_passthrough_without_model(self):
        self.assistant.multimodal_model_ref = None
        self.assistant.save(update_fields=["multimodal_model_ref"])
        attachment = store_message_attachment(
            self.session, self.user, _png_upload()
        )
        run = create_execution_run(
            session=self.session,
            question="原始问题",
            enqueue=False,
            attachment_uuids=[str(attachment.uuid)],
        )

        result = analyze_multimodal_intent(run)

        self.assertFalse(result["rewritten"])
        self.assertEqual(result["question"], "原始问题")

    def test_run_create_serializer_requires_text_or_image(self):
        serializer = RunCreateSerializer(
            data={"question": "   "},
            context={"session": self.session},
        )
        self.assertFalse(serializer.is_valid())

    def test_run_create_serializer_accepts_image_only(self):
        attachment = store_message_attachment(
            self.session, self.user, _png_upload()
        )
        serializer = RunCreateSerializer(
            data={
                "question": "",
                "enqueue": False,
                "attachment_uuids": [str(attachment.uuid)],
            },
            context={"session": self.session},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        run = serializer.save()
        attachment.refresh_from_db()
        self.assertEqual(attachment.message_id, run.input_message_id)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class AttachmentEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="api-user",
            email="api-user@example.com",
            password="pass12345",
        )
        self.other = User.objects.create_user(
            username="api-other",
            email="api-other@example.com",
            password="pass12345",
        )
        self.admin = User.objects.create_user(
            username="api-admin",
            email="api-admin@example.com",
            password="pass12345",
            is_staff=True,
        )
        self.lensnode = LensNode.objects.create(
            name="Local LensNode",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            workspace_path="/workspace",
        )
        self.assistant = Assistant.objects.create(
            name="Code Advisor",
            slug="code-advisor",
            lensnode=self.lensnode,
            selected_task="knowledge_qa",
            visibility=Assistant.Visibility.PUBLIC,
            multimodal_model_ref=uuid.uuid4(),
        )
        self.session = Session.objects.create(
            assistant=self.assistant, user=self.user
        )
        self.client = APIClient()

    def test_upload_then_owner_can_fetch_and_others_cannot(self):
        self.client.force_authenticate(self.user)
        upload = self.client.post(
            f"/api/lens/sessions/{self.session.uuid}/attachments/",
            {"file": _png_upload()},
            format="multipart",
        )
        self.assertEqual(upload.status_code, 201, upload.content)
        att_uuid = upload.data["uuid"]
        self.assertTrue(
            MessageAttachment.objects.filter(uuid=att_uuid).exists()
        )

        fetch = self.client.get(f"/api/lens/attachments/{att_uuid}/")
        self.assertEqual(fetch.status_code, 200)

        self.client.force_authenticate(self.other)
        denied = self.client.get(f"/api/lens/attachments/{att_uuid}/")
        self.assertEqual(denied.status_code, 403)

        # A staff admin may view any user's attachment for observability.
        self.client.force_authenticate(self.admin)
        admin_fetch = self.client.get(f"/api/lens/attachments/{att_uuid}/")
        self.assertEqual(admin_fetch.status_code, 200)

    def test_upload_rejected_when_assistant_not_multimodal(self):
        self.assistant.multimodal_model_ref = None
        self.assistant.save(update_fields=["multimodal_model_ref"])
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            f"/api/lens/sessions/{self.session.uuid}/attachments/",
            {"file": _png_upload()},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400)
