import json
import shutil
import secrets
import uuid as uuid_mod
from urllib import error as urlerror
from urllib import parse, request

from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import F, Q
from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.permissions import HasRequiredFeature

from .models import (
    Assistant,
    AssistantSkill,
    DataSource,
    DataSourceCredential,
    GlobalSetting,
    MCPServer,
    MessageAttachment,
    LensNode,
    Run,
    ScheduledTask,
    Session,
    SharedQA,
    Skill,
)
from .lensnode_auth import issue_lensnode_token, token_matches
from .periodic_tasks import (
    GLOBAL_PERIODIC_TASKS,
    ensure_datasource_periodic_task,
    sync_global_periodic_task,
)
from .datasource_services import (
    DataSourceDispatchError,
    DataSourcePathError,
    check_datasource_path,
    normalize_workspace_target_path,
    test_datasource_connection,
)
from .serializers import (
    AssistantSerializer,
    DataSourceCredentialSerializer,
    DataSourceSerializer,
    GlobalSettingSerializer,
    MCPServerSerializer,
    MessageAttachmentSerializer,
    MessageSerializer,
    LensNodeSerializer,
    RunCreateSerializer,
    RunSerializer,
    SessionCreateSerializer,
    SessionSerializer,
    SharedQAAdminSerializer,
    SharedQAListSerializer,
    SharedQAMineSerializer,
    SharedQAPublicSerializer,
    SkillSerializer,
)
from .attachments import AttachmentError, store_message_attachment
from .services import (
    cancel_datasource_sync_on_lensnode,
    cancel_run_on_lensnode,
    stream_run_events_async,
)
from .skill_generation import (
    SkillGeneratorNotConfigured,
    beautify_skill_content,
)
from .skill_packages import (
    SkillPackageError,
    import_skill_from_github,
    import_skill_zip,
    package_zip_bytes,
    update_skill_from_github,
    update_skill_zip,
)
from .tasks import (
    register_datasource_sync_task,
    release_datasource_lock,
    source_sync_task,
)


class BaseAuthenticatedViewSet(viewsets.ModelViewSet):
    """Base viewset requiring authentication."""

    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "uuid"


class DataSourceCredentialViewSet(BaseAuthenticatedViewSet):
    """CRUD for reusable datasource credentials."""

    queryset = DataSourceCredential.objects.all().prefetch_related(
        "datasources"
    )
    serializer_class = DataSourceCredentialSerializer

    def get_queryset(self):
        """Optionally filter credentials by provider or auth type."""

        queryset = super().get_queryset()
        provider = self.request.query_params.get("provider")
        auth_type = self.request.query_params.get("auth_type")
        if provider:
            queryset = queryset.filter(provider=provider)
        if auth_type:
            queryset = queryset.filter(auth_type=auth_type)
        return queryset

    def destroy(self, request, *args, **kwargs):
        """Reject deleting credentials that are still referenced."""

        credential = self.get_object()
        if credential.datasources.exists():
            return Response(
                {"detail": "CREDENTIAL_IN_USE"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="reveal")
    def reveal(self, request, uuid=None):
        """Return decrypted credential values for the current edit session."""

        credential = self.get_object()
        secret = credential.get_secret()
        if credential.auth_type == DataSourceCredential.AuthType.FEISHU_APP:
            app_id, _, app_secret = secret.partition(":")
            return Response(
                {
                    "app_id": app_id,
                    "app_secret": app_secret,
                }
            )
        return Response({"secret": secret})

    @action(detail=True, methods=["post"], url_path="validate")
    def validate_credential(self, request, uuid=None):
        """Validate a stored datasource credential endpoint and scope."""

        credential = self.get_object()
        result = _validate_datasource_credential_connectivity(credential)
        credential.validation_status = result["status"]
        credential.validation_message = result.get("message", "")
        credential.validated_at = timezone.now()
        if credential.provider == DataSourceCredential.Provider.FEISHU:
            credential.endpoint_url = "https://open.feishu.cn"
        credential.save(
            update_fields=[
                "endpoint_url",
                "validation_status",
                "validation_message",
                "validated_at",
                "updated_at",
            ]
        )
        response_status = (
            status.HTTP_200_OK
            if result.get("status") == "success"
            else status.HTTP_400_BAD_REQUEST
        )
        return Response(result, status=response_status)


def _validate_datasource_credential_connectivity(credential):
    """Validate datasource credential connectivity from the backend."""

    if credential.auth_type == DataSourceCredential.AuthType.FEISHU_APP:
        return _validate_feishu_credential_connectivity(credential)
    if credential.provider == DataSourceCredential.Provider.GITHUB:
        return _validate_github_credential_connectivity(credential)
    if credential.provider == DataSourceCredential.Provider.GITLAB:
        return _validate_gitlab_credential_connectivity(credential)
    return {
        "status": "failed",
        "message_code": "credential_provider_unsupported",
        "message": "Credential provider is not supported for validation.",
    }


def _validate_github_credential_connectivity(credential):
    endpoint = (credential.endpoint_url or "https://github.com").rstrip("/")
    api_base = "https://api.github.com"
    if endpoint and endpoint != "https://github.com":
        api_base = f"{endpoint}/api/v3"
    headers = {}
    is_anonymous = (
        credential.auth_type == DataSourceCredential.AuthType.NONE
    )
    if not is_anonymous:
        headers = {"Authorization": f"Bearer {credential.get_secret()}"}
        api_url = f"{api_base}/user"
        payload, message = _credential_api_json(
            api_url,
            headers,
        )
        if payload is None:
            return {
                "status": "failed",
                "message_code": "github_credential_invalid",
                "message": message or "GitHub credential validation failed.",
            }
    scope_url = (credential.scope_config or {}).get("organization_url")
    if scope_url:
        scope_path = _credential_scope_path(scope_url)
        parts = [part for part in scope_path.split("/") if part]
        scope_api_url = ""
        if len(parts) >= 2:
            scope_api_url = f"{api_base}/repos/{parts[0]}/{parts[1]}"
        elif len(parts) == 1:
            scope_api_url = f"{api_base}/orgs/{parts[0]}/repos?per_page=1"
        if not scope_api_url:
            return {
                "status": "failed",
                "message_code": "github_scope_invalid",
                "message": "GitHub scope URL is invalid.",
            }
        scope_payload, scope_message = _credential_api_json(
            scope_api_url,
            headers,
        )
        if scope_api_url and scope_payload is None and len(parts) == 1:
            scope_payload, scope_message = _credential_api_json(
                f"{api_base}/users/{parts[0]}/repos?per_page=1",
                headers,
            )
        if scope_api_url and scope_payload is None:
            return {
                "status": "failed",
                "message_code": "github_scope_invalid",
                "message": scope_message or "GitHub scope validation failed.",
            }
    return {
        "status": "success",
        "message_code": "github_credential_valid",
        "message": "GitHub credential is valid.",
        "details": {
            "login": "" if is_anonymous else payload.get("login") or ""
        },
    }


def _validate_gitlab_credential_connectivity(credential):
    endpoint = (credential.endpoint_url or "https://gitlab.com").rstrip("/")
    headers = {}
    is_anonymous = (
        credential.auth_type == DataSourceCredential.AuthType.NONE
    )
    if not is_anonymous:
        headers = {"PRIVATE-TOKEN": credential.get_secret()}
        payload, message = _credential_api_json(
            f"{endpoint}/api/v4/user",
            headers,
        )
        if payload is None:
            return {
                "status": "failed",
                "message_code": "gitlab_credential_invalid",
                "message": message or "GitLab credential validation failed.",
            }
    scope_url = (credential.scope_config or {}).get("organization_url")
    if scope_url:
        scope_path = parse.quote(_credential_scope_path(scope_url), safe="")
        scope_payload, scope_message = _credential_api_json(
            (
                f"{endpoint}/api/v4/groups/{scope_path}/projects"
                "?include_subgroups=true&simple=true&per_page=1"
            ),
            headers,
        )
        if scope_payload is None:
            scope_payload, scope_message = _credential_api_json(
                f"{endpoint}/api/v4/projects/{scope_path}",
                headers,
            )
        if scope_payload is None:
            return {
                "status": "failed",
                "message_code": "gitlab_scope_invalid",
                "message": scope_message or "GitLab scope validation failed.",
            }
    return {
        "status": "success",
        "message_code": "gitlab_credential_valid",
        "message": "GitLab credential is valid.",
        "details": {
            "username": "" if is_anonymous else payload.get("username") or ""
        },
    }


def _validate_feishu_credential_connectivity(credential):
    app_id, _, app_secret = credential.get_secret().partition(":")
    endpoint = "https://open.feishu.cn"
    payload, message = _credential_api_json(
        f"{endpoint}/open-apis/auth/v3/tenant_access_token/internal",
        {"Content-Type": "application/json"},
        data=json.dumps(
            {"app_id": app_id, "app_secret": app_secret}
        ).encode("utf-8"),
    )
    token = (payload or {}).get("tenant_access_token")
    if not token:
        return {
            "status": "failed",
            "message_code": "feishu_credential_invalid",
            "message": message or "Feishu app credential validation failed.",
        }
    scope_config = credential.scope_config or {}
    folder_token = scope_config.get("folder_token") or _feishu_folder_token(
        scope_config.get("folder_url")
    )
    if folder_token:
        query = parse.urlencode(
            {
                "folder_token": folder_token,
                "page_size": "1",
            }
        )
        folder_payload, folder_message = _credential_api_json(
            f"{endpoint}/open-apis/drive/v1/files?{query}",
            {"Authorization": f"Bearer {token}"},
        )
        if folder_payload is None:
            return {
                "status": "failed",
                "message_code": "feishu_folder_invalid",
                "message": folder_message or "Feishu folder validation failed.",
            }
    return {
        "status": "success",
        "message_code": "feishu_credential_valid",
        "message": "Feishu credential is valid.",
    }


def _credential_api_json(url, headers, data=None, timeout=15):
    req = request.Request(url, headers=headers, data=data)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), ""
    except urlerror.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")[:500]
        except Exception:
            body = ""
        return None, f"HTTP {exc.code}: {body}"
    except urlerror.URLError as exc:
        return None, str(exc.reason)
    except (TimeoutError, json.JSONDecodeError) as exc:
        return None, str(exc)


def _feishu_folder_token(value):
    parsed = parse.urlsplit(str(value or ""))
    parts = [part for part in parsed.path.split("/") if part]
    if "folder" in parts:
        index = parts.index("folder")
        if index + 1 < len(parts):
            return parts[index + 1]
    return str(value or "").strip()


def _credential_scope_path(value):
    parsed = parse.urlsplit(str(value or "").strip())
    path = parsed.path if parsed.scheme or parsed.netloc else str(value or "")
    return path.strip("/").removesuffix(".git")


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

    def create(self, request, *args, **kwargs):
        """Onboard a node: create record, auto-approve, issue token once.

        Nodes are deployed remotely and connect back over WebSocket with
        the issued token, so the only meaningful input here is the name.
        The plaintext token is returned a single time for the compose file.
        """

        name = (request.data.get("name") or "").strip()
        if not name:
            return Response(
                {"detail": "Name is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        lensnode = LensNode.objects.create(
            name=name,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
        )
        token = issue_lensnode_token(lensnode)
        data = LensNodeSerializer(lensnode).data
        data["token"] = token
        return Response(data, status=status.HTTP_201_CREATED)

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

    @action(detail=True, methods=["post"], url_path="list-dirs")
    def list_dirs(self, request, uuid=None):
        """Ask a connected LensNode to list immediate subdirectories."""

        import time
        import uuid as uuid_mod
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        from django.core.cache import cache
        from .services import lensnode_group_name

        lensnode = self.get_object()
        if lensnode.status != LensNode.Status.ONLINE:
            return Response(
                {"error": "LensNode is offline"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        paths = request.data.get("paths") or []
        if not paths:
            return Response({"dirs": {}})

        request_id = uuid_mod.uuid4().hex
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return Response(
                {"error": "Channel layer not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        async_to_sync(channel_layer.group_send)(
            lensnode_group_name(lensnode.uuid),
            {
                "type": "lensnode_command",
                "payload": {
                    "type": "list_dirs",
                    "request_id": request_id,
                    "paths": paths,
                },
            },
        )

        cache_key = f"lens:list_dirs:{request_id}"
        for _ in range(30):
            result = cache.get(cache_key)
            if result is not None:
                cache.delete(cache_key)
                return Response({"dirs": result})
            time.sleep(0.2)

        return Response(
            {"error": "timeout"},
            status=status.HTTP_408_REQUEST_TIMEOUT,
        )

    @action(detail=True, methods=["post"], url_path="check-datasource-path")
    def check_datasource_path(self, request, uuid=None):
        """Ask a connected LensNode to inspect a datasource target path."""

        lensnode = self.get_object()
        try:
            target_path = normalize_workspace_target_path(
                request.data.get("target_path") or "",
                lensnode.workspace_path,
            )
            conflict = _datasource_target_path_conflict(
                lensnode,
                target_path,
                request.data.get("datasource_uuid") or None,
            )
            if conflict is not None:
                return Response(
                    {
                        "status": "blocked",
                        "message_code": "datasource_path_in_use",
                        "message": (
                            "Another datasource already uses this target path"
                        ),
                        "datasource_uuid": str(conflict.uuid),
                        "datasource_name": conflict.name,
                    }
                )
            result = check_datasource_path(
                lensnode,
                target_path,
                request.data.get("source_type") or DataSource.SourceType.GIT,
                config=request.data.get("config") or {},
            )
        except DataSourcePathError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DataSourceDispatchError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(result)

    @action(detail=True, methods=["post"], url_path="test-datasource-connection")
    def test_datasource_connection(self, request, uuid=None):
        """Ask a connected LensNode to test datasource connection settings."""

        lensnode = self.get_object()
        try:
            result = test_datasource_connection(
                lensnode,
                request.data.get("source_type") or DataSource.SourceType.GIT,
                config=request.data.get("config") or {},
                datasource_uuid=request.data.get("datasource_uuid") or None,
                credential_uuid=request.data.get("credential_uuid") or None,
            )
        except DataSourceDispatchError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(result)


def _datasource_target_path_conflict(lensnode, target_path, datasource_uuid):
    """Return another datasource using the same target path on this LensNode."""

    query = DataSource.objects.filter(lensnode=lensnode)
    if datasource_uuid:
        query = query.exclude(uuid=datasource_uuid)
    normalized_target = normalize_workspace_target_path(
        target_path,
        lensnode.workspace_path,
    )
    for datasource in query.only("uuid", "name", "target_path"):
        if not datasource.target_path:
            continue
        try:
            existing = normalize_workspace_target_path(
                datasource.target_path,
                lensnode.workspace_path,
            )
        except DataSourcePathError:
            continue
        if existing == normalized_target:
            return datasource
    return None


class AssistantViewSet(BaseAuthenticatedViewSet):
    """CRUD for assistants.

    Anyone authenticated may list/retrieve the assistants visible to them;
    creating, editing, and deleting assistants (including visibility and
    access grants) requires the admin console feature.
    """

    required_feature = "admin_console"
    queryset = Assistant.objects.select_related("lensnode").prefetch_related(
        "skill_bindings",
        "mcp_bindings",
        "access_grants__group",
        "access_grants__user",
    )
    serializer_class = AssistantSerializer

    def get_permissions(self):
        """Require the admin console feature for write actions."""

        if self.action in ("create", "update", "partial_update", "destroy"):
            return [permissions.IsAuthenticated(), HasRequiredFeature()]
        return super().get_permissions()

    def get_queryset(self):
        """Scope assistants to those the caller may see."""

        return super().get_queryset().visible_to(self.request.user)

    def destroy(self, request, *args, **kwargs):
        """Soft-retire assistant instead of hard delete."""

        assistant = self.get_object()
        assistant.status = Assistant.Status.DISABLED
        assistant.save(update_fields=["status", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublicAssistantView(APIView):
    """Public read-only assistant metadata for the shared chat page."""

    authentication_classes = []
    permission_classes = []

    def get(self, request, slug):
        """Return minimal metadata for an active assistant by slug."""

        assistant = Assistant.objects.filter(
            slug=slug,
            status=Assistant.Status.ACTIVE,
            visibility=Assistant.Visibility.PUBLIC,
        ).first()
        if assistant is None:
            return Response(
                {"detail": "Assistant not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {
                "name": assistant.name,
                "slug": assistant.slug,
                "status": assistant.status,
            }
        )


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
            "run__steps", "attachments"
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
        if not session.assistant.is_accessible_by(request.user):
            raise PermissionDenied(
                "You do not have access to this assistant."
            )
        serializer = RunCreateSerializer(
            data=request.data,
            context={"session": session},
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
        if not session.assistant.is_accessible_by(request.user):
            raise PermissionDenied(
                "You do not have access to this assistant."
            )
        if not session.assistant.multimodal_model_ref:
            raise ValidationError("This assistant does not accept images.")
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationError("No file provided.")
        try:
            attachment = store_message_attachment(
                session, request.user, uploaded
            )
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
        return Response(
            SharedQAMineSerializer(share).data,
            status=status.HTTP_201_CREATED,
        )


class DataSourceViewSet(BaseAdminViewSet):
    """CRUD for datasources."""

    queryset = DataSource.objects.all()
    serializer_class = DataSourceSerializer

    def get_queryset(self):
        """Return datasources filtered by optional search query."""

        queryset = super().get_queryset().select_related(
            "lensnode",
            "credential",
        )
        filters = self._datasource_search_filters(
            self.request.query_params.get("filters")
        )
        for item in filters:
            queryset = queryset.filter(
                self._datasource_search_query(
                    item.get("value", ""),
                    item.get("key", ""),
                )
            )
        if filters:
            return queryset
        search = str(self.request.query_params.get("search") or "").strip()
        if not search:
            return queryset
        search_key = str(
            self.request.query_params.get("search_key") or ""
        ).strip()
        return queryset.filter(
            self._datasource_search_query(search, search_key)
        )

    @staticmethod
    def _datasource_search_filters(value):
        """Parse datasource search filters from query params."""

        if not value:
            return []
        try:
            raw_filters = json.loads(value)
        except (TypeError, ValueError):
            return []
        if not isinstance(raw_filters, list):
            return []
        filters = []
        for item in raw_filters:
            if not isinstance(item, dict):
                continue
            keyword = str(item.get("value") or "").strip()
            if not keyword:
                continue
            filters.append(
                {
                    "key": str(item.get("key") or "").strip(),
                    "value": keyword,
                }
            )
        return filters

    @staticmethod
    def _datasource_search_query(search, search_key):
        """Build a whitelisted datasource search query."""

        sync_status_datasource_ids = ScheduledTask.objects.filter(
            task_type=ScheduledTask.TaskType.SOURCE_SYNC,
            target_type="datasource",
            last_status__icontains=search,
        ).values("target_id")
        queries = {
            "name": Q(name__icontains=search),
            "source_type": Q(source_type__icontains=search),
            "repository": (
                Q(config__repo_url__icontains=search)
                | Q(config__document_url__icontains=search)
                | Q(config__folder_url__icontains=search)
                | Q(config__app_token__icontains=search)
            ),
            "lensnode": Q(lensnode__name__icontains=search),
            "target_path": Q(target_path__icontains=search),
            "status": (
                Q(status__icontains=search)
                | Q(last_error__icontains=search)
                | Q(uuid__in=sync_status_datasource_ids)
            ),
            "sync_policy": (
                Q(sync_policy__mode__icontains=search)
                | Q(sync_policy__cron__icontains=search)
                | Q(sync_policy__timezone__icontains=search)
            ),
        }
        if search_key in queries:
            return queries[search_key]
        query = Q()
        for item in queries.values():
            query |= item
        return query

    def create(self, request, *args, **kwargs):
        """Create datasource and return the initial sync task id."""

        self._initial_sync_task_id = ""
        response = super().create(request, *args, **kwargs)
        task_id = getattr(self, "_initial_sync_task_id", "")
        if task_id and isinstance(response.data, dict):
            response.data["initial_sync_task_id"] = task_id
        return response

    def perform_create(self, serializer):
        """Create datasource, register schedule, and enqueue initial sync."""

        datasource = serializer.save()
        ensure_datasource_periodic_task(datasource)
        if datasource.status == DataSource.Status.DISABLED:
            return
        task_id = uuid_mod.uuid4().hex
        self._initial_sync_task_id = task_id
        user = self.request.user
        transaction.on_commit(
            lambda: self._enqueue_datasource_sync(
                datasource,
                task_id,
                "initial",
                user,
            )
        )

    def perform_update(self, serializer):
        """Update datasource and register its sync schedule."""

        datasource = serializer.save()
        ensure_datasource_periodic_task(datasource)

    @staticmethod
    def _enqueue_datasource_sync(datasource, task_id, trigger, user=None):
        """Register and enqueue one datasource sync task."""

        if datasource.status == DataSource.Status.DISABLED:
            raise ValueError("DATASOURCE_DISABLED")
        celery_task_id = uuid_mod.uuid4().hex
        task_execution = register_datasource_sync_task(
            datasource,
            task_id,
            trigger,
            created_by=user,
        )
        metadata = dict(task_execution.metadata or {})
        metadata["celery_task_id"] = celery_task_id
        task_execution.metadata = metadata
        task_execution.save(update_fields=["metadata"])
        source_sync_task.apply_async(
            args=[str(datasource.uuid), trigger, task_id],
            task_id=celery_task_id,
        )
        return task_execution

    @action(detail=True, methods=["post"])
    def sync(self, request, uuid=None):
        """Enqueue datasource synchronization on its LensNode."""

        datasource = self.get_object()
        if datasource.status == DataSource.Status.DISABLED:
            return Response(
                {"detail": "DATASOURCE_DISABLED"},
                status=status.HTTP_409_CONFLICT,
            )
        task_id = uuid_mod.uuid4().hex
        task_execution = self._enqueue_datasource_sync(
            datasource,
            task_id,
            "manual",
            request.user,
        )
        return Response(
            {
                "uuid": str(datasource.uuid),
                "task_id": task_id,
                "task_execution_id": task_execution.id,
                "status": datasource.status,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"], url_path="set-enabled")
    def set_enabled(self, request, uuid=None):
        """Enable or disable a datasource and sync its schedule."""

        enabled = request.data.get("enabled")
        if not isinstance(enabled, bool):
            return Response(
                {"detail": "enabled must be a boolean."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        datasource = self.get_object()
        next_status = (
            DataSource.Status.ACTIVE
            if enabled
            else DataSource.Status.DISABLED
        )
        if datasource.status != next_status:
            datasource.status = next_status
            datasource.save(update_fields=["status", "updated_at"])
        ensure_datasource_periodic_task(datasource)
        return Response(DataSourceSerializer(datasource).data)

    @action(detail=True, methods=["get"], url_path="sync-tasks")
    def sync_tasks(self, request, uuid=None):
        """List sync task executions for this datasource (paginated)."""

        from agentcore_task.adapters.django.models import TaskExecution
        from agentcore_task.adapters.django.serializers import (
            TaskExecutionListSerializer,
        )

        datasource = self.get_object()
        queryset = TaskExecution.objects.filter(
            module="lens_datasource",
            metadata__datasource_uuid=str(datasource.uuid),
        ).order_by("-created_at")
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = TaskExecutionListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = TaskExecutionListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="cancel-sync")
    def cancel_sync(self, request, uuid=None):
        """Cancel the latest running synchronization for this datasource."""

        from agentcore_task.adapters.django.models import TaskExecution
        from agentcore_task.constants import TaskStatus
        from core.celery import app

        datasource = self.get_object()
        task = (
            TaskExecution.objects.filter(
                module="lens_datasource",
                metadata__datasource_uuid=str(datasource.uuid),
                status__in=[
                    TaskStatus.PENDING,
                    *TaskStatus.get_running_statuses(),
                ],
            )
            .order_by("-created_at")
            .first()
        )
        if task is None:
            return Response(
                {"detail": "No running datasource sync task."},
                status=status.HTTP_404_NOT_FOUND,
            )

        metadata = dict(task.metadata or {})
        celery_task_id = metadata.get("celery_task_id") or task.task_id
        app.control.revoke(celery_task_id, terminate=True, signal="SIGTERM")
        cancel_datasource_sync_on_lensnode(datasource.lensnode, task.task_id)

        lock_token = metadata.get("lock_token") or task.task_id
        release_datasource_lock(datasource.uuid, token=lock_token)
        metadata["manual_revoked_at"] = timezone.now().isoformat()
        metadata["manual_revoked_by"] = request.user.pk
        task.status = TaskStatus.REVOKED
        task.finished_at = timezone.now()
        task.error = "Task manually revoked by operator."
        task.metadata = metadata
        task.save(
            update_fields=[
                "status",
                "finished_at",
                "error",
                "metadata",
            ]
        )
        return Response(
            {
                "uuid": str(datasource.uuid),
                "task_id": task.task_id,
                "task_execution_id": task.id,
                "status": task.status,
            }
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

    def perform_destroy(self, instance):
        """Delete an unbound Skill and remove its package files."""

        package_path = instance.package_path
        instance.delete()
        transaction.on_commit(
            lambda: self._remove_skill_package_path(package_path)
        )

    @action(detail=True, methods=["get"], url_path="delete-impact")
    def delete_impact(self, request, *args, **kwargs):
        """Return assistants that currently bind this Skill."""

        skill = self.get_object()
        assistants = self._bound_assistants(skill)
        return Response(
            {
                "skill": {
                    "uuid": str(skill.uuid),
                    "name": skill.name,
                    "slug": skill.slug,
                },
                "bound_count": len(assistants),
                "bound_assistants": assistants,
            }
        )

    @action(detail=True, methods=["post"], url_path="force-delete")
    def force_delete(self, request, *args, **kwargs):
        """Delete a Skill after explicit name confirmation."""

        skill = self.get_object()
        confirmation = str(request.data.get("confirmation_name") or "")
        if confirmation != skill.name:
            return Response(
                {"detail": "Skill name confirmation does not match."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        package_path = skill.package_path
        with transaction.atomic():
            AssistantSkill.objects.filter(skill=skill).delete()
            skill.delete()
            transaction.on_commit(
                lambda: self._remove_skill_package_path(package_path)
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=["post"],
        parser_classes=[MultiPartParser, FormParser],
        url_path="update-upload",
    )
    def update_upload(self, request, *args, **kwargs):
        """Replace an uploaded Skill package while preserving bindings."""

        skill = self.get_object()
        file_obj = request.FILES.get("file")
        if file_obj is None:
            return Response(
                {"detail": "Skill package file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            skill = update_skill_zip(
                skill,
                file_obj=file_obj,
                original_name=getattr(file_obj, "name", ""),
            )
        except SkillPackageError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(skill).data)

    @action(detail=True, methods=["post"], url_path="update-github")
    def update_github(self, request, *args, **kwargs):
        """Re-import a GitHub Skill while preserving bindings."""

        skill = self.get_object()
        url = str(request.data.get("url") or "").strip()
        if not url:
            return Response(
                {"detail": "GitHub URL is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            skill = update_skill_from_github(skill, url)
        except SkillPackageError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(skill).data)

    def _bound_assistants(self, skill):
        """Return compact assistant data for delete confirmation."""

        bindings = (
            AssistantSkill.objects.filter(skill=skill)
            .select_related("assistant", "assistant__lensnode")
            .order_by("assistant__name")
        )
        return [
            {
                "uuid": str(binding.assistant.uuid),
                "name": binding.assistant.name,
                "slug": binding.assistant.slug,
                "status": binding.assistant.status,
                "visibility": binding.assistant.visibility,
                "lensnode": binding.assistant.lensnode.name,
            }
            for binding in bindings
        ]

    def _remove_skill_package_path(self, package_path):
        """Remove package files for a deleted Skill."""

        if not package_path:
            return

        shutil.rmtree(package_path, ignore_errors=True)

    @action(
        detail=False,
        methods=["post"],
        parser_classes=[MultiPartParser, FormParser],
        url_path="upload",
    )
    def upload(self, request):
        """Upload and validate a Skill zip package."""

        file_obj = request.FILES.get("file")
        if file_obj is None:
            return Response(
                {"detail": "Skill package file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            skill = import_skill_zip(
                file_obj=file_obj,
                original_name=getattr(file_obj, "name", ""),
            )
        except SkillPackageError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(skill).data)

    @action(detail=False, methods=["post"], url_path="import-github")
    def import_github(self, request):
        """Import a public Skill zip package from GitHub."""

        url = str(request.data.get("url") or "").strip()
        if not url:
            return Response(
                {"detail": "GitHub URL is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            skill = import_skill_from_github(url)
        except SkillPackageError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(skill).data)

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, *args, **kwargs):
        """Download the current Skill package as a zip archive."""

        skill = self.get_object()
        archive = package_zip_bytes(skill)
        return FileResponse(
            archive,
            as_attachment=True,
            filename=f"{skill.slug}.zip",
        )

    @action(detail=False, methods=["post"])
    def beautify(self, request):
        """Polish a draft SKILL.md via the configured generator model."""

        try:
            content = beautify_skill_content(
                content=request.data.get("content", ""),
                name=request.data.get("name", ""),
                user_id=request.user.id,
            )
        except SkillGeneratorNotConfigured:
            return Response(
                {"detail": "Skill generator model is not configured."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"content": content})


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

    def partial_update(self, request, *args, **kwargs):
        """Update or create a setting addressed by key."""

        key = kwargs.get(self.lookup_field)
        instance = self.queryset.filter(key=key).first()
        data = request.data.copy()
        data["key"] = key
        serializer = self.get_serializer(
            instance,
            data=data,
            partial=instance is not None,
        )
        serializer.is_valid(raise_exception=True)
        setting = serializer.save()
        self._sync_runtime_schedule(setting)
        return Response(self.get_serializer(setting).data)

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


# While a provider call is thinking (reasoning, composing a tool call)
# the SSE stream can carry no tokens for minutes. Periodic heartbeats
# prove transport liveness to the LensNode watchdog so it only aborts
# on a genuinely dead pipe, never on a quiet-but-alive model call.
GATEWAY_STREAM_HEARTBEAT_S = 10


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
        correlation = {}
        if request.data.get("run_uuid"):
            correlation["run_uuid"] = str(request.data["run_uuid"])
            correlation["is_subagent"] = bool(
                request.data.get("is_subagent")
            )
        if correlation:
            tracker_state["metadata"] = correlation
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
        """Stream a metered LLM call as SSE chunks.

        Runs the sync LLMTracker generator in a thread and yields events via
        an async generator so Daphne (ASGI) flushes each token immediately
        instead of buffering the full response.
        """

        from agentcore_metering.adapters.django import LLMTracker
        import asyncio
        import logging as _logging

        _log = _logging.getLogger("lens.gateway_stream")
        lensnode_uuid_str = str(lensnode.uuid)

        async def event_stream():
            loop = asyncio.get_running_loop()
            queue = asyncio.Queue()

            def run_in_thread():
                try:
                    generator = LLMTracker.call_and_track(
                        messages=messages,
                        model_uuid=model_ref,
                        node_name=f"lensnode:{lensnode_uuid_str}",
                        state=tracker_state,
                        stream=True,
                        tools=payload.get("tools"),
                        tool_choice=payload.get("tool_choice"),
                        temperature=payload.get("temperature"),
                        max_tokens=payload.get("max_tokens"),
                    )
                    token_count = 0
                    while True:
                        try:
                            kind, text = next(generator)
                        except StopIteration as exc:
                            result = exc.value or {}
                            tool_calls = result.pop("_tool_calls", None) or []
                            _log.debug(
                                "gateway stream done: token_count=%d "
                                "tool_calls=%d",
                                token_count,
                                len(tool_calls),
                            )
                            loop.call_soon_threadsafe(
                                queue.put_nowait,
                                ("done", {
                                    "type": "done",
                                    "usage": result,
                                    "lensnode_uuid": lensnode_uuid_str,
                                    "tool_calls": tool_calls,
                                }),
                            )
                            return
                        except Exception as exc:
                            error_code = self._gateway_stream_error_code(exc)
                            _log.error(
                                "gateway stream exception: type=%s error=%s "
                                "token_count=%d",
                                type(exc).__name__,
                                exc,
                                token_count,
                            )
                            loop.call_soon_threadsafe(
                                queue.put_nowait,
                                (
                                    "event",
                                    {
                                        "type": "error",
                                        "error": {
                                            "code": error_code,
                                            "message": str(exc),
                                        },
                                    },
                                ),
                            )
                            return
                        token_count += 1
                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            ("event", {
                                "type": "token",
                                "kind": kind,
                                "content": text,
                            }),
                        )
                except Exception as exc:
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        (
                            "event",
                            {
                                "type": "error",
                                "error": {
                                    "code": self._gateway_stream_error_code(exc),
                                    "message": str(exc),
                                },
                            },
                        ),
                    )

            future = loop.run_in_executor(None, run_in_thread)
            try:
                while True:
                    try:
                        item = await asyncio.wait_for(
                            queue.get(), timeout=GATEWAY_STREAM_HEARTBEAT_S
                        )
                    except asyncio.TimeoutError:
                        yield self._sse({"type": "heartbeat"})
                        continue
                    if item[0] == "event":
                        yield self._sse(item[1])
                        if item[1].get("type") == "error":
                            return
                    elif item[0] == "done":
                        yield self._sse(item[1])
                        return
                    elif item[0] == "error":
                        raise item[1]
            finally:
                await future

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

    def _gateway_stream_error_code(self, exc):
        """Return a stable error code for a gateway stream exception."""

        name = type(exc).__name__.upper()
        message = str(exc).upper()
        if "TIMEOUT" in name or "TIMEOUT" in message or "TIMED OUT" in message:
            return "MODEL_TIMEOUT"
        stream_markers = [
            "CHUNKED",
            "INCOMPLETE",
            "PEER CLOSED",
            "REMOTE PROTOCOL",
            "CONNECTION RESET",
            "CONNECTION CLOSED",
        ]
        if any(marker in name or marker in message for marker in stream_markers):
            return "MODEL_STREAM_ERROR"
        return "MODEL_STREAM_ERROR"

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


class LensNodeSkillPackageView(APIView):
    """Skill package endpoint authenticated by the LensNode token."""

    authentication_classes = []
    permission_classes = []

    def get(self, request, uuid):
        """Return a packaged Skill archive for LensNode cache fill."""

        lensnode = self._authenticate_lensnode(request)
        if lensnode is None:
            return Response(
                {"detail": "Invalid LensNode token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        skill = get_object_or_404(Skill, uuid=uuid, enabled=True)
        package_hash = request.query_params.get("hash") or ""
        if package_hash and package_hash != skill.package_hash:
            return Response(
                {"detail": "Skill package hash mismatch."},
                status=status.HTTP_404_NOT_FOUND,
            )
        archive = package_zip_bytes(skill)
        response = FileResponse(
            archive,
            as_attachment=True,
            filename=f"{skill.slug or skill.uuid}.zip",
            content_type="application/zip",
        )
        response["X-Skill-Package-Hash"] = skill.package_hash
        return response

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


def _admin_safe_int(value, default, *, minimum=1, maximum=None):
    """Return a clamped positive int parsed from a query value."""

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(parsed, maximum)
    return parsed


def _admin_run_duration(run):
    """Return execution seconds (started -> finished) or None."""

    if run.started_at and run.finished_at:
        return round((run.finished_at - run.started_at).total_seconds(), 1)
    return None


def _admin_run_step_counts(run):
    """Aggregate event/subagent/LLM counts and token usage from steps."""

    counts = {
        "event_count": 0,
        "subagent_count": 0,
        "llm_calls": 0,
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }
    total_cost = 0.0
    has_cost = False
    for step in run.steps.all():
        detail = step.detail or {}
        for event in detail.get("events", []):
            counts["event_count"] += 1
            agent_event = event.get("agent_event")
            if agent_event == "tool.task.invoke":
                counts["subagent_count"] += 1
            elif agent_event == "llm.response":
                counts["llm_calls"] += 1
                counts["total_tokens"] += event.get("total_tokens") or 0
                counts["prompt_tokens"] += event.get("prompt_tokens") or 0
                counts["completion_tokens"] += (
                    event.get("completion_tokens") or 0
                )
                cost = event.get("cost")
                if cost:
                    total_cost += cost
                    has_cost = True
        # Control-plane preprocess calls (query rewrite, vision intent)
        # record their usage on the step itself, not as node events.
        usage = detail.get("usage")
        if usage:
            counts["llm_calls"] += 1
            counts["total_tokens"] += usage.get("total_tokens") or 0
            counts["prompt_tokens"] += usage.get("prompt_tokens") or 0
            counts["completion_tokens"] += usage.get("completion_tokens") or 0
            cost = usage.get("cost")
            if cost:
                total_cost += cost
                has_cost = True
    counts["total_cost"] = round(total_cost, 6) if has_cost else None
    return counts


def _admin_run_row(run):
    """Serialize one run for the observability list."""

    session = run.session
    user = session.user if session else None
    assistant = session.assistant if session else None
    question = (run.input_message.content if run.input_message else "") or ""
    counts = _admin_run_step_counts(run)
    return {
        "uuid": str(run.uuid),
        "status": run.status,
        "username": user.username if user else None,
        "assistant_name": assistant.name if assistant else None,
        "assistant_slug": assistant.slug if assistant else None,
        "question": question[:160],
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": (
            run.finished_at.isoformat() if run.finished_at else None
        ),
        "duration_seconds": _admin_run_duration(run),
        "lensnode_name": run.lensnode.name if run.lensnode else None,
        "event_count": counts["event_count"],
        "subagent_count": counts["subagent_count"],
        "llm_calls": counts["llm_calls"],
        "total_tokens": counts["total_tokens"],
        "prompt_tokens": counts["prompt_tokens"],
        "completion_tokens": counts["completion_tokens"],
        "total_cost": counts["total_cost"],
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _admin_run_detail(run):
    """Serialize a run with full Q&A, timeline and execution snapshot."""

    row = _admin_run_row(run)
    out = run.output_message
    assistant = run.session.assistant if run.session else None
    execution = run.execution if hasattr(run, "execution") else None
    steps = []
    for step in run.steps.all():
        detail = step.detail or {}
        item = {
            "step_type": step.step_type,
            "status": step.status,
            "sequence": step.sequence,
            "events": detail.get("events", []),
            "usage": detail.get("usage"),
            "updated_at": (
                step.updated_at.isoformat() if step.updated_at else None
            ),
        }
        if step.step_type == "multimodal":
            item["multimodal"] = {
                "query": detail.get("query"),
                "image_count": detail.get("image_count"),
                "rewritten": detail.get("rewritten"),
            }
        steps.append(item)
    attachments = (
        MessageAttachmentSerializer(
            run.input_message.attachments.all(), many=True
        ).data
        if run.input_message
        else []
    )
    row.update({
        "question": (
            run.input_message.content if run.input_message else ""
        ) or "",
        "attachments": attachments,
        "answer": (out.content if out else "") or "",
        "error": run.error or "",
        "agent_rounds": assistant.agent_rounds if assistant else None,
        "steps": steps,
        "execution": {
            "task": execution.task,
            "target_dirs": execution.target_dirs,
            "loaded_skills": execution.loaded_skills,
            "loaded_mcps": execution.loaded_mcps,
        } if execution else None,
    })
    return row


class AdminRunListView(APIView):
    """Admin-only cross-user list of Q&A runs for observability."""

    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        """Return a filtered, paginated list of runs."""

        params = request.query_params
        page = _admin_safe_int(params.get("page"), 1)
        page_size = _admin_safe_int(params.get("page_size"), 20, maximum=100)
        qs = (
            Run.objects.select_related(
                "session__user",
                "session__assistant",
                "input_message",
                "lensnode",
            )
            .prefetch_related("steps")
            .order_by("-created_at")
        )
        username = (params.get("username") or "").strip()
        if username:
            qs = qs.filter(session__user__username__icontains=username)
        assistant = (params.get("assistant") or "").strip()
        if assistant:
            qs = qs.filter(session__assistant__slug=assistant)
        run_status = (params.get("status") or "").strip()
        if run_status:
            qs = qs.filter(status=run_status)
        keyword = (params.get("q") or "").strip()
        if keyword:
            qs = qs.filter(input_message__content__icontains=keyword)
        start_date = parse_date((params.get("start_date") or "").strip())
        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)
        end_date = parse_date((params.get("end_date") or "").strip())
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)

        total = qs.count()
        start = (page - 1) * page_size
        rows = [_admin_run_row(run) for run in qs[start:start + page_size]]
        return Response({
            "results": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
        })


class AdminRunDetailView(APIView):
    """Admin-only full trace of a single Q&A run."""

    permission_classes = [permissions.IsAdminUser]

    def get(self, request, uuid):
        """Return the full trace for one run."""

        try:
            run = (
                Run.objects.select_related(
                    "session__user",
                    "session__assistant",
                    "input_message",
                    "output_message",
                    "lensnode",
                )
                .prefetch_related("steps")
                .get(uuid=uuid)
            )
        except Run.DoesNotExist:
            return Response(
                {"detail": "Run not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(_admin_run_detail(run))


def _unique_share_token():
    """Generate a collision-free URL-safe share token."""

    for _ in range(5):
        token = secrets.token_urlsafe(16)
        if not SharedQA.objects.filter(token=token).exists():
            return token
    return secrets.token_urlsafe(24)


def _shared_qa_default_title(question, limit=60):
    """Derive a default share title from the question text."""

    text = " ".join((question or "").split())
    return text[:limit] or "Shared Q&A"


class SharedQAViewSet(BaseAuthenticatedViewSet):
    """List, rename, and revoke the current user's own shared Q&As."""

    queryset = SharedQA.objects.all().select_related("published_by")
    serializer_class = SharedQAMineSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        """Restrict to shares published by the current user."""

        return super().get_queryset().filter(
            published_by=self.request.user
        )

    def partial_update(self, request, *args, **kwargs):
        """Let the owner edit the share title after publishing."""

        share = self.get_object()
        title = (request.data.get("title") or "").strip()
        if title:
            share.title = title[:200]
            share.save(update_fields=["title", "updated_at"])
        return Response(SharedQAMineSerializer(share).data)


class AdminSharedQAViewSet(BaseAdminViewSet):
    """Admin moderation/curation of shared Q&As."""

    queryset = SharedQA.objects.all().select_related("published_by")
    serializer_class = SharedQAAdminSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        """Filter by listed/status for the moderation queue."""

        queryset = super().get_queryset()
        params = self.request.query_params
        listed = params.get("listed")
        if listed in ("true", "false"):
            queryset = queryset.filter(is_listed=(listed == "true"))
        status_param = (params.get("status") or "").strip()
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset


class PublicSharedQAView(APIView):
    """Single shared Q&A by token with assistant visibility rules."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        """Return one published shared Q&A and bump its view count."""

        share = (
            SharedQA.objects.select_related("assistant", "published_by")
            .filter(token=token, status=SharedQA.Status.PUBLISHED)
            .first()
        )
        if share is None or not _shared_qa_visible_to_user(
            share,
            request.user,
        ):
            return Response(
                {"detail": "Shared Q&A not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        SharedQA.objects.filter(pk=share.pk).update(
            view_count=F("view_count") + 1
        )
        share.refresh_from_db(fields=["view_count"])
        return Response(SharedQAPublicSerializer(share).data)


def _shared_qa_visible_to_user(share, user):
    """Return whether a shared Q&A may be read through its token."""

    if share.is_listed:
        return True
    if not (user and user.is_authenticated):
        return False
    if user.is_staff or user.is_superuser:
        return True
    if share.published_by_id == user.id:
        return True
    publisher = share.published_by
    if publisher is None:
        return False
    return publisher.groups.filter(pk__in=user.groups.values("pk")).exists()


class PublicSharedQAListView(APIView):
    """Public list of an assistant's curated shared Q&As (anonymous)."""

    authentication_classes = []
    permission_classes = []

    def get(self, request, slug):
        """Return curated, listed shares for one active assistant."""

        assistant = Assistant.objects.filter(
            slug=slug,
            status=Assistant.Status.ACTIVE,
        ).first()
        if assistant is None:
            return Response(
                {"detail": "Assistant not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        params = request.query_params
        limit = _admin_safe_int(params.get("limit"), 20, maximum=50)
        offset = _admin_safe_int(params.get("offset"), 0, minimum=0)
        queryset = SharedQA.objects.filter(
            assistant=assistant,
            is_listed=True,
            status=SharedQA.Status.PUBLISHED,
        ).order_by("-published_at", "-created_at")
        total = queryset.count()
        rows = SharedQAListSerializer(
            queryset[offset:offset + limit],
            many=True,
        ).data
        has_more = offset + limit < total
        return Response({
            "assistant": {"name": assistant.name, "slug": assistant.slug},
            "results": rows,
            "total": total,
            "next_offset": offset + limit if has_more else None,
        })
