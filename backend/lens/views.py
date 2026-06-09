import json

from asgiref.sync import sync_to_async
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import (
    Assistant,
    DataSource,
    GlobalSetting,
    MCPServer,
    LensNode,
    Run,
    ScheduledTask,
    Session,
    Skill,
)
from .lensnode_auth import issue_lensnode_token, token_matches
from .periodic_tasks import (
    GLOBAL_PERIODIC_TASKS,
    ensure_datasource_periodic_task,
    sync_global_periodic_task,
)
from .serializers import (
    AssistantSerializer,
    DataSourceSerializer,
    GlobalSettingSerializer,
    MCPServerSerializer,
    MessageSerializer,
    LensNodeSerializer,
    RunCreateSerializer,
    RunSerializer,
    SessionCreateSerializer,
    SessionSerializer,
    SkillSerializer,
)
from .services import cancel_run_on_lensnode, stream_run_events_async
from .source_sync import SourceSyncError
from .tasks import source_sync_task


class BaseAuthenticatedViewSet(viewsets.ModelViewSet):
    """Base viewset requiring authentication."""

    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "uuid"


class EventStreamRenderer(BaseRenderer):
    """Renderer used only for SSE content negotiation."""

    media_type = "text/event-stream"
    format = "event-stream"
    charset = None

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """Return bytes for DRF negotiation fallback paths."""

        del accepted_media_type, renderer_context
        return data or b""


def _authenticate_stream_request(request):
    """Authenticate a native Django SSE request with JWT."""

    if getattr(request, "user", None) is not None:
        if request.user.is_authenticated:
            return request.user

    authenticated = JWTAuthentication().authenticate(request)
    if authenticated is None:
        return None
    user, _ = authenticated
    return user


def _get_user_run(run_uuid, user):
    """Return a run visible to the authenticated user."""

    return (
        Run.objects.filter(uuid=run_uuid, session__user=user)
        .select_related("output_message")
        .first()
    )


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


class BaseAdminViewSet(BaseAuthenticatedViewSet):
    """Base viewset requiring staff access."""

    permission_classes = [permissions.IsAdminUser]


class LensNodeViewSet(BaseAdminViewSet):
    """CRUD and enrollment actions for LensNode workers."""

    queryset = LensNode.objects.all()
    serializer_class = LensNodeSerializer

    @action(detail=True, methods=["post"])
    def approve(self, request, uuid=None):
        """Approve a pending LensNode for token-based access."""

        lensnode = self.get_object()
        lensnode.enrollment_status = LensNode.EnrollmentStatus.APPROVED
        lensnode.save(update_fields=["enrollment_status", "updated_at"])
        return Response(LensNodeSerializer(lensnode).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, uuid=None):
        """Reject a LensNode enrollment request."""

        lensnode = self.get_object()
        lensnode.enrollment_status = LensNode.EnrollmentStatus.REJECTED
        lensnode.token_revoked = True
        lensnode.save(
            update_fields=[
                "enrollment_status",
                "token_revoked",
                "updated_at",
            ]
        )
        return Response(LensNodeSerializer(lensnode).data)

    @action(detail=True, methods=["post"], url_path="issue-token")
    def issue_token(self, request, uuid=None):
        """Issue a plaintext LensNode token once."""

        lensnode = self.get_object()
        if lensnode.enrollment_status != LensNode.EnrollmentStatus.APPROVED:
            return Response(
                {
                    "detail": (
                        "LensNode must be approved before issuing a token."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        token = issue_lensnode_token(lensnode)
        return Response(
            {
                "lensnode_uuid": str(lensnode.uuid),
                "token": token,
                "token_issued_at": lensnode.token_issued_at,
            }
        )

    @action(detail=True, methods=["post"], url_path="revoke-token")
    def revoke_token(self, request, uuid=None):
        """Revoke the current LensNode token."""

        lensnode = self.get_object()
        lensnode.token_revoked = True
        lensnode.status = LensNode.Status.OFFLINE
        lensnode.connection_id = ""
        lensnode.save(
            update_fields=[
                "token_revoked",
                "status",
                "connection_id",
                "updated_at",
            ]
        )
        return Response(LensNodeSerializer(lensnode).data)


class AssistantViewSet(BaseAuthenticatedViewSet):
    """CRUD for assistants."""

    queryset = Assistant.objects.select_related("lensnode").prefetch_related(
        "skill_bindings",
        "mcp_bindings",
    )
    serializer_class = AssistantSerializer

    def destroy(self, request, *args, **kwargs):
        """Soft-retire assistant instead of hard delete."""

        assistant = self.get_object()
        assistant.status = Assistant.Status.DISABLED
        assistant.save(update_fields=["status", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        serializer = MessageSerializer(session.message_set.all(), many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def runs(self, request, uuid=None):
        """Create an execution run for a session."""

        session = self.get_object()
        serializer = RunCreateSerializer(
            data=request.data,
            context={"session": session},
        )
        serializer.is_valid(raise_exception=True)
        run = serializer.save()
        run.refresh_from_db()
        return Response(RunSerializer(run).data, status=201)


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

        run.status = Run.Status.CANCELLED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at", "updated_at"])
        cancel_run_on_lensnode(run)
        return Response(RunSerializer(run).data)


class DataSourceViewSet(BaseAdminViewSet):
    """CRUD for datasources."""

    queryset = DataSource.objects.all()
    serializer_class = DataSourceSerializer

    def perform_create(self, serializer):
        """Create datasource and register its sync schedule."""

        datasource = serializer.save()
        ensure_datasource_periodic_task(datasource)

    def perform_update(self, serializer):
        """Update datasource and register its sync schedule."""

        datasource = serializer.save()
        ensure_datasource_periodic_task(datasource)

    @action(detail=True, methods=["post"])
    def sync(self, request, uuid=None):
        """Enqueue or run datasource synchronization."""

        datasource = self.get_object()
        run_inline = bool(request.data.get("run_inline", False))
        if run_inline:
            try:
                source_sync_task(str(datasource.uuid))
            except SourceSyncError as exc:
                return Response(
                    {"detail": str(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            datasource.refresh_from_db()
            return Response(DataSourceSerializer(datasource).data)

        result = source_sync_task.delay(str(datasource.uuid))
        return Response(
            {
                "uuid": str(datasource.uuid),
                "task_id": result.id or "",
                "status": datasource.status,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class SkillViewSet(BaseAdminViewSet):
    """CRUD for skills."""

    queryset = Skill.objects.all()
    serializer_class = SkillSerializer

    def destroy(self, request, *args, **kwargs):
        skill = self.get_object()
        if skill.assistantskill_set.exists():
            return Response(
                {"detail": "Skill is still bound to assistants."},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)


class MCPServerViewSet(BaseAdminViewSet):
    """CRUD for MCP servers."""

    queryset = MCPServer.objects.all()
    serializer_class = MCPServerSerializer

    def destroy(self, request, *args, **kwargs):
        mcp = self.get_object()
        if mcp.assistantmcp_set.exists():
            return Response(
                {"detail": "MCP server is still bound to assistants."},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)


class GlobalSettingViewSet(BaseAdminViewSet):
    """CRUD for global settings."""

    queryset = GlobalSetting.objects.all()
    serializer_class = GlobalSettingSerializer
    lookup_field = "key"
    lookup_value_regex = "[^/]+"

    def perform_create(self, serializer):
        """Create a global setting and sync derived runtime config."""

        setting = serializer.save()
        self._sync_runtime_schedule(setting)

    def perform_update(self, serializer):
        """Update a global setting and sync derived runtime config."""

        setting = serializer.save()
        self._sync_runtime_schedule(setting)

    def _sync_runtime_schedule(self, setting):
        """Propagate interval settings to celery beat rows."""

        if setting.key not in {
            meta["setting_key"] for meta in GLOBAL_PERIODIC_TASKS.values()
        }:
            return

        for task_type, meta in GLOBAL_PERIODIC_TASKS.items():
            if meta["setting_key"] == setting.key:
                sync_global_periodic_task(task_type)
                break

    @action(detail=False, methods=["get", "patch"], url_path="system-health")
    def system_health(self, request):
        """Expose and update the enabled state for global scheduled tasks."""

        if request.method == "GET":
            tasks = ScheduledTask.objects.filter(
                task_type__in=[
                    ScheduledTask.TaskType.LENSNODE_CLEANUP,
                    ScheduledTask.TaskType.LENSNODE_HEALTH,
                    ScheduledTask.TaskType.RUN_RETENTION,
                ]
            ).order_by("task_type")
            data = [
                {
                    "name": task.name,
                    "task_type": task.task_type,
                    "enabled": task.enabled,
                    "last_status": task.last_status,
                    "last_run_at": task.last_run_at,
                    "last_error": task.last_error,
                    "last_metrics": task.last_metrics,
                }
                for task in tasks
            ]
            return Response(data)

        task_type = request.data.get("task_type")
        enabled = request.data.get("enabled")

        valid_task_types = {
            ScheduledTask.TaskType.LENSNODE_CLEANUP,
            ScheduledTask.TaskType.LENSNODE_HEALTH,
            ScheduledTask.TaskType.RUN_RETENTION,
        }
        if task_type not in valid_task_types:
            return Response(
                {"detail": "Invalid task_type."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(enabled, bool):
            return Response(
                {"detail": "enabled must be a boolean."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        task_name_map = {
            ScheduledTask.TaskType.LENSNODE_CLEANUP: "lens-lensnode-cleanup",
            ScheduledTask.TaskType.LENSNODE_HEALTH: "lens-lensnode-health",
            ScheduledTask.TaskType.RUN_RETENTION: "lens-run-retention",
        }
        task, _ = ScheduledTask.objects.get_or_create(
            task_type=task_type,
            target_type=None,
            target_id=None,
            defaults={
                "name": task_name_map[task_type],
                "enabled": enabled,
            },
        )
        if task.enabled != enabled:
            task.enabled = enabled
            task.save(update_fields=["enabled", "updated_at"])

        from django_celery_beat.models import PeriodicTask

        periodic_task_name = task_name_map[task_type]
        periodic_task = PeriodicTask.objects.filter(
            name=periodic_task_name
        ).first()
        if periodic_task is not None and periodic_task.enabled != enabled:
            periodic_task.enabled = enabled
            periodic_task.save(update_fields=["enabled"])
            from django_celery_beat.models import PeriodicTasks

            PeriodicTasks.update_changed()

        return Response(
            {
                "name": task.name,
                "task_type": task.task_type,
                "enabled": task.enabled,
                "last_status": task.last_status,
                "last_run_at": task.last_run_at,
                "last_error": task.last_error,
                "last_metrics": task.last_metrics,
            }
        )


class LensNodeAIGatewayView(APIView):
    """AI gateway endpoint authenticated by the LensNode token."""

    authentication_classes = []
    permission_classes = []
    renderer_classes = [JSONRenderer, EventStreamRenderer]

    def post(self, request):
        """Proxy one metered LLM call on behalf of a LensNode."""

        lensnode = self._authenticate_lensnode(request)
        if lensnode is None:
            return Response(
                {"detail": "Invalid LensNode token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        model_ref = request.data.get("model_ref")
        messages = request.data.get("messages")
        if not model_ref or not isinstance(messages, list):
            return Response(
                {"detail": "model_ref and messages are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from agentcore_metering.adapters.django import LLMTracker

        tracker_state = {
            "source_type": "lensnode_gateway",
            "lensnode_uuid": str(lensnode.uuid),
        }
        if request.data.get("stream"):
            return self._stream_response(
                lensnode,
                model_ref,
                messages,
                tracker_state,
                request.data,
            )

        content, usage = LLMTracker.call_and_track(
            messages=messages,
            model_uuid=model_ref,
            node_name=f"lensnode:{lensnode.uuid}",
            state=tracker_state,
            tools=request.data.get("tools"),
            tool_choice=request.data.get("tool_choice"),
            temperature=request.data.get("temperature"),
            max_tokens=request.data.get("max_tokens"),
            return_message=bool(request.data.get("return_message")),
        )
        data = {
            "usage": usage,
            "lensnode_uuid": str(lensnode.uuid),
        }
        if request.data.get("return_message"):
            data["message"] = content
            data["content"] = content.get("content", "")
        else:
            data["content"] = content
        return Response(data)

    def _stream_response(
        self,
        lensnode,
        model_ref,
        messages,
        tracker_state,
        payload,
    ):
        """Stream a metered LLM call as SSE chunks."""

        from agentcore_metering.adapters.django import LLMTracker

        def event_stream():
            generator = LLMTracker.call_and_track(
                messages=messages,
                model_uuid=model_ref,
                node_name=f"lensnode:{lensnode.uuid}",
                state=tracker_state,
                stream=True,
                tools=payload.get("tools"),
                tool_choice=payload.get("tool_choice"),
                temperature=payload.get("temperature"),
                max_tokens=payload.get("max_tokens"),
            )
            while True:
                try:
                    kind, text = next(generator)
                except StopIteration as exc:
                    usage = exc.value or {}
                    yield self._sse(
                        {
                            "type": "done",
                            "usage": usage,
                            "lensnode_uuid": str(lensnode.uuid),
                        }
                    )
                    return
                yield self._sse(
                    {
                        "type": "token",
                        "kind": kind,
                        "content": text,
                    }
                )

        response = StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _sse(self, event):
        """Serialize one SSE event."""

        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    def _authenticate_lensnode(self, request):
        """Authenticate bearer token against approved LensNodes."""

        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        token = header.removeprefix("Bearer ").strip()
        for lensnode in LensNode.objects.filter(
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
            token_revoked=False,
        ).exclude(auth_token_hash=""):
            if token_matches(lensnode, token):
                return lensnode
        return None
