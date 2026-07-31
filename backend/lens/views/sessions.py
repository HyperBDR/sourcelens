"""Session, run, attachment, and run-stream conversation views."""

import json
import logging

from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import Exists, F, OuterRef
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.http import content_disposition_header
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from lens.assistant_lifecycle import AssistantNotRunnableError
from lens.attachments import AttachmentError, store_message_attachment
from lens.document_attachments import (
    DocumentAttachmentError,
    delete_document_attachment,
    delete_session_document_attachments,
    document_attachment_response,
    document_attachment_storage,
    get_document_attachment,
    get_run_document_attachments,
    get_runs_document_attachments,
    is_document_upload,
    store_document_attachment,
)
from lens.models import (
    Assistant,
    Message,
    MessageAttachment,
    Run,
    RunExecution,
    RunOutputFile,
    Session,
    SharedQA,
)
from lens.qa_pdf import build_qa_pdf_filename, render_qa_pdf
from lens.session_lifecycle import (
    SessionStateError,
    archive_session,
    lock_active_session,
    pin_session,
    restore_session,
    unpin_session,
)
from lens.serializers import (
    MessageAttachmentSerializer,
    MessageSerializer,
    RunCreateSerializer,
    RunFeedbackSerializer,
    RunSerializer,
    SessionCreateSerializer,
    SessionSerializer,
    SharedQAMineSerializer,
)
from lens.services import (
    cancel_run_on_lensnode,
    stream_run_events_async,
    supports_document_attachments,
)
from lens.shared_qa_files import snapshot_shared_qa_files

from .base import (
    BaseAuthenticatedViewSet,
    EventStreamRenderer,
    _authenticate_stream_request,
    _get_user_run,
)
from .shares import _shared_qa_default_title, _unique_share_token

logger = logging.getLogger(__name__)


async def run_stream_view(request, uuid):
    """Stream run events as SSE without DRF response buffering."""

    user = await sync_to_async(_authenticate_stream_request)(request)
    if user is None:
        return HttpResponse("Unauthorized", status=401)

    run = await sync_to_async(_get_user_run)(uuid, user)
    if run is None:
        return HttpResponse("Not found", status=404)

    async def event_stream():
        async for event in stream_run_events_async(run):
            payload = json.dumps(event, ensure_ascii=False)
            yield f"data: {payload}\n\n".encode("utf-8")

    response = StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream; charset=utf-8",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


class SessionViewSet(BaseAuthenticatedViewSet):
    """CRUD for sessions and nested run/message actions."""

    queryset = Session.objects.select_related("assistant", "user")
    serializer_class = SessionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        assistant_slug = self.request.query_params.get("assistant_slug")
        if assistant_slug:
            queryset = queryset.filter(assistant__slug=assistant_slug)
        queryset = queryset.filter(user=self.request.user)
        if self.action == "list":
            archived = self.request.query_params.get("archived", "").lower()
            session_status = (
                Session.Status.ARCHIVED
                if archived == "true"
                else Session.Status.ACTIVE
            )
            shareable_runs = Run.objects.filter(
                session=OuterRef("pk"),
                status=Run.Status.DONE,
                output_message__isnull=False,
            )
            return queryset.filter(status=session_status).annotate(
                has_shareable_answer=Exists(shareable_runs),
            ).order_by(
                F("pinned_at").desc(nulls_last=True),
                "-created_at",
                "-pk",
            )
        if self.action in ("pin", "unpin", "archive"):
            return queryset.filter(status=Session.Status.ACTIVE)
        if self.action == "restore":
            return queryset.filter(status=Session.Status.ARCHIVED)
        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return SessionCreateSerializer
        return SessionSerializer

    def create(self, request, *args, **kwargs):
        """Create a session and return the full session payload."""

        serializer = self.get_serializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        session = serializer.save()
        return Response(SessionSerializer(session).data, status=201)

    @action(detail=True, methods=["get"])
    def messages(self, request, uuid=None):
        """Return ordered messages for a session."""

        session = self.get_object()
        messages = list(
            session.message_set.select_related("run").prefetch_related(
                "run__steps",
                "response_runs__steps",
                "attachments",
                "output_files",
            )
        )
        documents_by_run = get_runs_document_attachments(
            [
                message.run.uuid
                for message in messages
                if message.role == Message.Role.USER
                and message.run_id is not None
            ],
            fail_silently=True,
        )
        serializer = MessageSerializer(
            messages,
            many=True,
            context={
                "document_attachments_by_run": documents_by_run,
            },
        )
        return Response(serializer.data)

    def perform_destroy(self, instance):
        """Delete runs first to avoid PROTECT conflict on Run.input_message.

        Django 5.1's deletion collector checks PROTECT constraints during
        the collection phase. It processes Message.session (CASCADE) before
        Run.session (CASCADE), so Run.input_message (PROTECT) blocks Message
        deletion before Run is added to the deletion set. Deleting Runs
        explicitly first removes the PROTECT reference.
        """
        session_uuid = instance.uuid
        user_id = instance.user_id
        instance.run_set.all().delete()
        instance.delete()
        try:
            delete_session_document_attachments(
                session_uuid,
                user_id=user_id,
            )
        except Exception:
            logger.exception(
                "Unable to delete temporary documents for Session %s.",
                session_uuid,
            )

    @action(detail=True, methods=["post"])
    def pin(self, request, uuid=None):
        """Pin an active session above ordinary recent sessions."""

        session = pin_session(self.get_object())
        return Response(self.get_serializer(session).data)

    @action(detail=True, methods=["post"])
    def unpin(self, request, uuid=None):
        """Remove an active session from the pinned group."""

        session = unpin_session(self.get_object())
        return Response(self.get_serializer(session).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, uuid=None):
        """Archive an active session without deleting its history."""

        session = archive_session(self.get_object())
        return Response(self.get_serializer(session).data)

    @action(detail=True, methods=["post"])
    def restore(self, request, uuid=None):
        """Restore an archived session to active use."""

        session = restore_session(self.get_object())
        return Response(self.get_serializer(session).data)

    @action(detail=True, methods=["post"])
    def runs(self, request, uuid=None):
        """Create an execution run for a session."""

        session = self.get_object()
        if (
            session.assistant.status != Assistant.Status.ACTIVE
            or not session.assistant.is_accessible_by(request.user)
        ):
            raise PermissionDenied(
                "You do not have access to this assistant."
            )
        serializer = RunCreateSerializer(
            data=request.data,
            context={"session": session, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        try:
            run = serializer.save()
        except SessionStateError:
            raise ValidationError("SESSION_ARCHIVED")
        run.refresh_from_db()
        return Response(RunSerializer(run).data, status=201)

    @action(
        detail=True,
        methods=["post"],
        url_path="attachments",
        parser_classes=[MultiPartParser, FormParser],
    )
    def attachments(self, request, uuid=None):
        """Upload one attachment for a session question."""

        session = self.get_object()
        if (
            session.assistant.status != Assistant.Status.ACTIVE
            or not session.assistant.is_accessible_by(request.user)
        ):
            raise PermissionDenied(
                "You do not have access to this assistant."
            )
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationError("No file provided.")
        is_document = is_document_upload(uploaded)
        if is_document and session.assistant.selected_task == "general_chat":
            raise ValidationError(
                "This assistant does not accept document attachments."
            )
        if is_document and not supports_document_attachments(
            session.assistant.lensnode
        ):
            raise ValidationError(
                "DOCUMENT_ATTACHMENTS_UNSUPPORTED_BY_LENSNODE"
            )
        if not is_document and not session.assistant.multimodal_model_ref:
            raise ValidationError("This assistant does not accept images.")
        try:
            if is_document:
                with transaction.atomic():
                    session = lock_active_session(session)
                    attachment = store_document_attachment(
                        session,
                        request.user,
                        uploaded,
                    )
            else:
                attachment = store_message_attachment(
                    session,
                    request.user,
                    uploaded,
                )
        except SessionStateError:
            raise ValidationError("SESSION_ARCHIVED")
        except AssistantNotRunnableError:
            raise PermissionDenied(
                "You do not have access to this assistant."
            )
        except (AttachmentError, DocumentAttachmentError) as exc:
            raise ValidationError(str(exc))
        if is_document:
            return Response(
                document_attachment_response(attachment),
                status=status.HTTP_201_CREATED,
            )
        return Response(
            MessageAttachmentSerializer(attachment).data,
            status=status.HTTP_201_CREATED,
        )


class LensAttachmentView(APIView):
    """Serve a question attachment to its owner or any admin."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, uuid):
        """Return the image bytes for the session owner or a staff admin."""

        attachment = (
            MessageAttachment.objects.select_related("session")
            .filter(uuid=uuid)
            .first()
        )
        if attachment is not None:
            is_owner = attachment.session.user_id == request.user.id
            if not is_owner and not request.user.is_staff:
                raise PermissionDenied("You do not have access to this image.")
            response = FileResponse(
                attachment.file.open("rb"),
                content_type=(
                    attachment.mime_type or "application/octet-stream"
                ),
            )
            response["Cache-Control"] = "private, max-age=3600"
            return response

        metadata = get_document_attachment(uuid)
        if metadata is None:
            raise Http404
        is_owner = metadata["uploaded_by_id"] == request.user.id
        if not is_owner and not request.user.is_staff:
            raise PermissionDenied("You do not have access to this document.")
        storage = document_attachment_storage()
        if not storage.exists(metadata["storage_name"]):
            raise Http404
        response = FileResponse(
            storage.open(metadata["storage_name"], "rb"),
            as_attachment=True,
            filename=metadata["original_name"],
            content_type=metadata["mime_type"],
        )
        response["Cache-Control"] = "private, no-store"
        response["Content-Length"] = metadata["byte_size"]
        response["X-Attachment-Hash"] = metadata["content_hash"]
        return response

    def delete(self, request, uuid):
        """Delete one still-valid transient document attachment."""

        metadata = get_document_attachment(uuid)
        if metadata is None:
            raise Http404
        is_owner = metadata["uploaded_by_id"] == request.user.id
        if not is_owner and not request.user.is_staff:
            raise PermissionDenied("You do not have access to this document.")
        run_uuid = metadata.get("run_uuid")
        if (
            run_uuid
            and Run.objects.filter(
                uuid=run_uuid,
                status__in=[
                    Run.Status.QUEUED,
                    Run.Status.RUNNING,
                    Run.Status.STREAMING,
                ],
            ).exists()
        ):
            return Response(
                {"detail": "ATTACHMENT_IN_USE"},
                status=status.HTTP_409_CONFLICT,
            )
        delete_document_attachment(uuid)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RunOutputFileDownloadView(APIView):
    """Serve a delivered run output file to its owner or any admin.

    Always sent as an attachment (Content-Disposition: attachment) so
    untrusted agent-produced content is downloaded rather than rendered
    inline in the app origin; preview is handled separately later.

    Authorization is DELIBERATELY private: only the session owner (or a
    staff admin) may download. Sharing a run (SharedQA) copies the Q&A
    text only and does NOT expose output files or this URL, so shared
    viewers cannot reach deliverables. If public sharing of a deliverable
    is ever wanted, do NOT relax this owner check -- add a separate
    token-scoped download that validates the SharedQA token instead.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, uuid):
        """Return the file bytes for the session owner or a staff admin."""

        output = get_object_or_404(
            RunOutputFile.objects.select_related("session"),
            uuid=uuid,
        )
        is_owner = output.session.user_id == request.user.id
        if not is_owner and not request.user.is_staff:
            raise PermissionDenied("You do not have access to this file.")
        response = FileResponse(
            output.file.open("rb"),
            as_attachment=True,
            filename=output.filename,
            content_type=output.content_type or "application/octet-stream",
        )
        response["Cache-Control"] = "private, max-age=3600"
        return response


class RunViewSet(BaseAuthenticatedViewSet):
    """CRUD for runs."""

    queryset = Run.objects.select_related(
        "session",
        "input_message",
        "output_message",
        "lensnode",
    ).prefetch_related("steps")
    serializer_class = RunSerializer

    def get_queryset(self):
        """Limit run access to the current user's sessions."""

        queryset = super().get_queryset()
        return queryset.filter(session__user=self.request.user)

    @action(detail=True, methods=["patch"])
    def feedback(self, request, uuid=None):
        """Set, switch, or clear feedback for a completed answer."""

        run = self.get_object()
        serializer = RunFeedbackSerializer(run, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def pdf(self, request, uuid=None):
        """Download one completed answer as a styled text PDF."""

        run = self.get_object()
        if run.status != Run.Status.DONE or run.output_message is None:
            return Response(
                {"detail": "RUN_NOT_EXPORTABLE"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        question = run.input_message.content or ""
        title = " ".join(question.split())[:80]
        input_files = [
            *run.input_message.attachments.all(),
            *get_run_document_attachments(run.uuid, fail_silently=True),
        ]
        pdf_bytes = render_qa_pdf(
            title=title,
            question=question,
            answer=run.output_message.content or "",
            assistant_name=run.session.assistant.name,
            published_at=run.output_message.created_at,
            input_files=input_files,
            output_files=run.output_files.all(),
            language_code=getattr(request, "LANGUAGE_CODE", "en"),
        )
        filename = build_qa_pdf_filename(run.session.title, question)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = content_disposition_header(
            True,
            filename,
        )
        response["Cache-Control"] = "private, max-age=0, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @action(
        detail=True,
        methods=["get"],
        renderer_classes=[EventStreamRenderer],
    )
    def stream(self, request, uuid=None):
        """Stream run events using SSE."""

        run = self.get_object()

        async def event_stream():
            async for event in stream_run_events_async(run):
                payload = json.dumps(event, ensure_ascii=False)
                yield f"data: {payload}\n\n"

        response = StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    @action(detail=True, methods=["post"])
    def cancel(self, request, uuid=None):
        """Cancel a queued or running run."""

        run = self.get_object()
        if run.status in [
            Run.Status.DONE,
            Run.Status.FAILED,
            Run.Status.CANCELLED,
        ]:
            return Response(RunSerializer(run).data)

        now = timezone.now()
        with transaction.atomic():
            run.status = Run.Status.CANCELLED
            run.finished_at = now
            run.save(update_fields=["status", "finished_at", "updated_at"])
            if hasattr(run, "execution"):
                run.execution.status = RunExecution.Status.CANCELLED
                run.execution.finished_at = now
                run.execution.save(
                    update_fields=["status", "finished_at"]
                )
        cancel_run_on_lensnode(run)
        return Response(RunSerializer(run).data)

    @action(detail=True, methods=["post"])
    def share(self, request, uuid=None):
        """Publish this run's Q&A as a public, link-shareable snapshot.

        Idempotent per (run, user): re-sharing returns the existing
        snapshot. The snapshot copies the question/answer text so the
        public page is decoupled from the private session.
        """

        run = self.get_object()
        if run.status != Run.Status.DONE or run.output_message is None:
            return Response(
                {"detail": "RUN_NOT_SHAREABLE"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        existing = SharedQA.objects.filter(
            run=run,
            published_by=request.user,
        ).first()
        if existing is not None:
            return Response(SharedQAMineSerializer(existing).data)

        question = run.input_message.content if run.input_message else ""
        answer = run.output_message.content or ""
        assistant = run.session.assistant
        title = (request.data.get("title") or "").strip()[:200]
        if not title:
            title = _shared_qa_default_title(question)
        with transaction.atomic():
            share = SharedQA.objects.create(
                token=_unique_share_token(),
                run=run,
                assistant=assistant,
                assistant_name=assistant.name if assistant else "",
                assistant_slug=assistant.slug if assistant else "",
                question=question,
                answer=answer,
                title=title,
                published_by=request.user,
                published_at=timezone.now(),
            )
            snapshot_shared_qa_files(share)
        return Response(
            SharedQAMineSerializer(share).data,
            status=status.HTTP_201_CREATED,
        )
