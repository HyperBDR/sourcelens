"""Session, run, attachment, and run-stream conversation views."""

import json

from asgiref.sync import sync_to_async
from django.db import transaction
from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from lens.assistant_lifecycle import AssistantNotRunnableError
from lens.attachments import AttachmentError, store_message_attachment
from lens.models import (
    Assistant,
    MessageAttachment,
    Run,
    RunExecution,
    RunOutputFile,
    Session,
    SharedQA,
)
from lens.qa_pdf import (
    QAPdfGenerationError,
    generate_qa_pdf,
    run_pdf_context,
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
)
from lens.shared_qa_files import snapshot_shared_qa_files
from .base import (
    BaseAuthenticatedViewSet,
    EventStreamRenderer,
    _authenticate_stream_request,
    _get_user_run,
)
from .shares import _shared_qa_default_title, _unique_share_token


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
        return queryset.filter(user=self.request.user)

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
        messages = session.message_set.select_related("run").prefetch_related(
            "run__steps",
            "response_runs__steps",
            "attachments",
            "output_files",
        )
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)

    def perform_destroy(self, instance):
        """Delete runs first to avoid PROTECT conflict on Run.input_message.

        Django 5.1's deletion collector checks PROTECT constraints during
        the collection phase. It processes Message.session (CASCADE) before
        Run.session (CASCADE), so Run.input_message (PROTECT) blocks Message
        deletion before Run is added to the deletion set. Deleting Runs
        explicitly first removes the PROTECT reference.
        """
        instance.run_set.all().delete()
        instance.delete()

    @action(detail=True, methods=["post"])
    def runs(self, request, uuid=None):
        """Create an execution run for a session."""

        session = self.get_object()
        if (
            session.assistant.status != Assistant.Status.ACTIVE
            or not session.assistant.is_accessible_by(request.user)
        ):
            raise PermissionDenied("You do not have access to this assistant.")
        serializer = RunCreateSerializer(
            data=request.data,
            context={"session": session, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        run = serializer.save()
        run.refresh_from_db()
        return Response(RunSerializer(run).data, status=201)

    @action(
        detail=True,
        methods=["post"],
        url_path="attachments",
        parser_classes=[MultiPartParser, FormParser],
    )
    def attachments(self, request, uuid=None):
        """Upload one image attachment for a session question."""

        session = self.get_object()
        if (
            session.assistant.status != Assistant.Status.ACTIVE
            or not session.assistant.is_accessible_by(request.user)
        ):
            raise PermissionDenied("You do not have access to this assistant.")
        if not session.assistant.multimodal_model_ref:
            raise ValidationError("This assistant does not accept images.")
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationError("No file provided.")
        try:
            attachment = store_message_attachment(session, request.user, uploaded)
        except AssistantNotRunnableError:
            raise PermissionDenied("You do not have access to this assistant.")
        except AttachmentError as exc:
            raise ValidationError(str(exc))
        return Response(
            MessageAttachmentSerializer(attachment).data,
            status=status.HTTP_201_CREATED,
        )


class LensAttachmentView(APIView):
    """Serve a question image attachment to its owner or any admin."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, uuid):
        """Return the image bytes for the session owner or a staff admin."""

        attachment = get_object_or_404(
            MessageAttachment.objects.select_related("session"),
            uuid=uuid,
        )
        is_owner = attachment.session.user_id == request.user.id
        if not is_owner and not request.user.is_staff:
            raise PermissionDenied("You do not have access to this image.")
        response = FileResponse(
            attachment.file.open("rb"),
            content_type=attachment.mime_type or "application/octet-stream",
        )
        response["Cache-Control"] = "private, max-age=3600"
        return response


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
        "session__assistant",
        "input_message",
        "output_message",
        "lensnode",
    ).prefetch_related(
        "steps",
        "input_message__attachments",
        "output_files",
    )
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

    @action(detail=True, methods=["get"], url_path="export-pdf")
    def export_pdf(self, request, uuid=None):
        """Download a completed owned run as a server-generated PDF."""

        run = self.get_object()
        if run.status != Run.Status.DONE or run.output_message is None:
            return Response(
                {"detail": "RUN_NOT_EXPORTABLE"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            pdf = generate_qa_pdf(run_pdf_context(run))
        except QAPdfGenerationError:
            return Response(
                {"detail": "PDF_GENERATION_UNAVAILABLE"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="qa-{run.uuid}.pdf"'
        response["Cache-Control"] = "private, no-store"
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
