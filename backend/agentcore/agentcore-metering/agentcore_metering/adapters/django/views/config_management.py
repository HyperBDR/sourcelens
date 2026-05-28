"""
Admin API views for LLM config CRUD, test-call, and validation.

All endpoints require IsAdminUser. Used by management UI for global and
per-user LLM provider configuration.
"""
from django.apps import apps
from django.contrib.auth import get_user_model
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from agentcore_metering.adapters.django.models import LLMConfig
from agentcore_metering.adapters.django.serializers import (
    ErrorDetailSerializer,
    LLMConfigSerializer,
    LLMConfigWriteSerializer,
)
from agentcore_metering.adapters.django.services.config_source import (
    get_default_llm_config_uuid,
    set_default_llm_config,
)
from agentcore_metering.adapters.django.services.model_catalog import (
    get_model_type_for_model_id,
)

User = get_user_model()


def _preserve_masked_secret_fields(
    existing: dict, incoming: dict, keys: tuple[str, ...] = ("api_key", "key")
) -> dict:
    """
    Keep the stored secret when the client re-sends a masked value.

    The admin UI fetches configs through a read serializer that masks secret
    fields, then sends the same payload back on updates such as "set as
    default". If we do not preserve the original value here, the masked
    placeholder gets persisted and the config stops authenticating.
    """
    merged = dict(existing or {})
    for key, value in (incoming or {}).items():
        if (
            key in keys
            and isinstance(value, str)
            and "***" in value
        ):
            continue
        merged[key] = value
    return merged


class AdminLLMConfigAllListView(APIView):
    """
    GET: List all LLM configs (global + user) in one list.
    Query param scope: all (default) | global | user.
    Optional user_id when scope=user.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["llm-metering"],
        summary="List all LLM configs",
        description=(
            "List all LLM configs (global + user). scope=all returns both; "
            "scope=global or user filters. When scope=user, use user_id."
        ),
        parameters=[
            OpenApiParameter(
                "scope",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                description="Filter: all (default), global, or user",
                enum=["all", "global", "user"],
                default="all",
            ),
            OpenApiParameter(
                "user_id",
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                description="Filter by user id when scope=user",
            ),
        ],
        responses={200: LLMConfigSerializer(many=True)},
    )
    def get(self, request):
        scope_param = (
            request.query_params.get("scope") or "all"
        ).strip().lower()
        user_id_param = request.query_params.get("user_id")
        qs = (
            LLMConfig.objects.filter(model_type=LLMConfig.MODEL_TYPE_LLM)
            .select_related("user")
            .order_by("scope", "created_at", "id")
        )
        if scope_param == "global":
            qs = qs.filter(scope=LLMConfig.Scope.GLOBAL)
        elif scope_param == "user":
            qs = qs.filter(scope=LLMConfig.Scope.USER)
            if user_id_param is not None and str(user_id_param).strip():
                qs = qs.filter(user_id=user_id_param)
        ctx = {"default_config_uuid": get_default_llm_config_uuid()}
        return Response(
            LLMConfigSerializer(qs, many=True, context=ctx).data
        )


class AdminLLMConfigGlobalView(APIView):
    """
    GET: List global LLM configs (model_type=llm, ordered).
    POST: Add one config. Body may include scope (global|user) and
    user_id for user config.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["llm-metering"],
        summary="List global LLM configs",
        description=(
            "List global LLM configs (model_type=llm, ordered by "
            "created_at, id)."
        ),
        responses={200: LLMConfigSerializer(many=True)},
    )
    def get(self, request):
        qs = (
            LLMConfig.objects.filter(
                scope=LLMConfig.Scope.GLOBAL,
                model_type=LLMConfig.MODEL_TYPE_LLM,
            )
            .order_by("created_at", "id")
        )
        ctx = {"default_config_uuid": get_default_llm_config_uuid()}
        return Response(
            LLMConfigSerializer(qs, many=True, context=ctx).data
        )

    @extend_schema(
        tags=["llm-metering"],
        summary="Create LLM config",
        description=(
            "Add one global or user config. Body: provider, config; optional "
            "scope (global|user), user_id, is_active."
        ),
        request=LLMConfigWriteSerializer,
        responses={201: LLMConfigSerializer, 400: ErrorDetailSerializer},
    )
    def post(self, request):
        ser = LLMConfigWriteSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        scope_raw = (request.data.get("scope") or "global").strip().lower()
        user_id_raw = request.data.get("user_id")
        provider = (data.get("provider") or "openai").strip().lower()
        config = data.get("config") or {}
        model_id = (config.get("model") or "").strip()
        model_type_raw = (
            (request.data.get("model_type") or "").strip()
            or get_model_type_for_model_id(provider, model_id or None)
            or LLMConfig.MODEL_TYPE_LLM
        )
        if model_type_raw not in LLMConfig.MODEL_TYPES:
            model_type_raw = LLMConfig.MODEL_TYPE_LLM
        if scope_raw == "user" and user_id_raw is not None:
            user = None
            try:
                user = User.objects.get(pk=user_id_raw)
            except (User.DoesNotExist, ValueError, TypeError):
                return Response(
                    {"detail": "User not found."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            obj = LLMConfig.objects.create(
                scope=LLMConfig.Scope.USER,
                user=user,
                model_type=model_type_raw,
                provider=(data.get("provider") or "openai").strip().lower(),
                config=data.get("config") or {},
                is_active=data.get("is_active", True),
            )
        else:
            obj = LLMConfig.objects.create(
                scope=LLMConfig.Scope.GLOBAL,
                user=None,
                model_type=model_type_raw,
                provider=(data.get("provider") or "openai").strip().lower(),
                config=data.get("config") or {},
                is_active=data.get("is_active", True),
                is_default=data.get("is_default", False),
            )
            if data.get("is_default"):
                set_default_llm_config(obj)
        ctx = {"default_config_uuid": get_default_llm_config_uuid()}
        return Response(
            LLMConfigSerializer(obj, context=ctx).data,
            status=status.HTTP_201_CREATED,
        )


class AdminLLMConfigDetailView(APIView):
    """GET/PUT/DELETE one LLM config by uuid."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["llm-metering"],
        summary="Get LLM config",
        description="Get one LLM config by uuid.",
        responses={200: LLMConfigSerializer, 404: ErrorDetailSerializer},
    )
    def get(self, request, config_ref):
        obj = self._get_obj(config_ref)
        if obj is None:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        ctx = {"default_config_uuid": get_default_llm_config_uuid()}
        return Response(LLMConfigSerializer(obj, context=ctx).data)

    @extend_schema(
        tags=["llm-metering"],
        summary="Update LLM config",
        description=(
            "Update one LLM config by uuid. Body: optional provider, config, "
            "is_active, is_default (global only)."
        ),
        request=LLMConfigWriteSerializer,
        responses={
            200: LLMConfigSerializer,
            400: ErrorDetailSerializer,
            404: ErrorDetailSerializer,
        },
    )
    def put(self, request, config_ref):
        obj = self._get_obj(config_ref)
        if obj is None:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        ser = LLMConfigWriteSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        if "provider" in data:
            obj.provider = (data["provider"] or "openai").strip().lower()
        if "config" in data:
            obj.config = _preserve_masked_secret_fields(
                obj.config or {}, data["config"] or {}
            )
        if "is_active" in data:
            obj.is_active = data["is_active"]
        if "is_default" in data and obj.scope == LLMConfig.Scope.GLOBAL:
            obj.is_default = data["is_default"]
            if obj.is_default:
                set_default_llm_config(obj)
        model_type_raw = request.data.get("model_type")
        mt_ok = (
            model_type_raw is not None
            and str(model_type_raw).strip() in LLMConfig.MODEL_TYPES
        )
        if mt_ok:
            obj.model_type = str(model_type_raw).strip()
        else:
            provider = (
                data.get("provider") or obj.provider or "openai"
            ).strip().lower()
            config = data.get("config") if "config" in data else obj.config
            model_id = ((config or {}).get("model") or "").strip()
            if model_id:
                derived = get_model_type_for_model_id(provider, model_id)
                if derived:
                    obj.model_type = derived
        obj.save()
        ctx = {"default_config_uuid": get_default_llm_config_uuid()}
        return Response(LLMConfigSerializer(obj, context=ctx).data)

    @extend_schema(
        tags=["llm-metering"],
        summary="Delete LLM config",
        description="Delete one LLM config by uuid.",
        responses={204: None, 404: ErrorDetailSerializer},
    )
    def delete(self, request, config_ref):
        obj = self._get_obj(config_ref)
        if obj is None:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        route_model = apps.get_model(
            "ai_query",
            "AiQueryProjectModelRoute",
            require_ready=False,
        )
        if route_model.objects.filter(llm_config=obj).exists():
            return Response(
                {"code": "llm_config_in_use"},
                status=status.HTTP_409_CONFLICT,
            )
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _get_obj(self, config_ref):
        qs = LLMConfig.objects.select_related("user")
        try:
            return qs.get(uuid=config_ref)
        except (LLMConfig.DoesNotExist, ValueError, TypeError):
            if str(config_ref).isdigit():
                try:
                    return qs.get(pk=int(config_ref))
                except (LLMConfig.DoesNotExist, ValueError, TypeError):
                    return None
            return None


class AdminLLMConfigUserListView(APIView):
    """
    GET: List per-user LLM configs. Optional query param user_id to filter
    by one user.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["llm-metering"],
        summary="List per-user LLM configs",
        description=(
            "List per-user LLM configs. Optional user_id to filter."
        ),
        parameters=[
            OpenApiParameter(
                "user_id",
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                description="Filter by user id (optional)",
            ),
        ],
        responses={200: LLMConfigSerializer(many=True)},
    )
    def get(self, request):
        user_id = request.query_params.get("user_id")
        qs = (
            LLMConfig.objects.filter(scope=LLMConfig.Scope.USER)
            .select_related("user")
        )
        if user_id is not None and str(user_id).strip():
            qs = qs.filter(user_id=user_id)
        qs = qs.order_by("created_at", "id")
        ctx = {"default_config_uuid": get_default_llm_config_uuid()}
        return Response(
            LLMConfigSerializer(qs, many=True, context=ctx).data
        )


class AdminLLMConfigUserDetailView(APIView):
    """
    GET: Return one user's LLM config (404 if not set).
    PUT: Create or update that user's LLM config.
    DELETE: Remove user config so they fall back to global default.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["llm-metering"],
        summary="Get user LLM config",
        description="Get one user's LLM config. 404 if not set.",
        responses={200: LLMConfigSerializer, 404: ErrorDetailSerializer},
    )
    def get(self, request, user_id):
        user = self._get_user(user_id)
        if user is None:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        qs = LLMConfig.objects.filter(
            scope=LLMConfig.Scope.USER,
            user_id=user.pk,
            model_type=LLMConfig.MODEL_TYPE_LLM,
        ).select_related("user")
        if qs.count() > 1:
            return Response(
                {
                    "detail": (
                        "Multiple user LLM configs exist for this user. "
                        "Clean up duplicates before reading."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        obj = qs.first()
        if obj is None:
            return Response(
                {"detail": "No LLM config for this user. Use PUT to create."},
                status=status.HTTP_404_NOT_FOUND,
            )
        ctx = {"default_config_uuid": get_default_llm_config_uuid()}
        return Response(LLMConfigSerializer(obj, context=ctx).data)

    @extend_schema(
        tags=["llm-metering"],
        summary="Create or update user LLM config",
        description=(
            "Create or update that user's LLM config. Body: provider, config."
        ),
        request=LLMConfigWriteSerializer,
        responses={
            200: LLMConfigSerializer,
            400: ErrorDetailSerializer,
            404: ErrorDetailSerializer,
        },
    )
    def put(self, request, user_id):
        user = self._get_user(user_id)
        if user is None:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        ser = LLMConfigWriteSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        qs = LLMConfig.objects.filter(
            scope=LLMConfig.Scope.USER,
            user=user,
            model_type=LLMConfig.MODEL_TYPE_LLM,
        )
        if qs.count() > 1:
            return Response(
                {
                    "detail": (
                        "Multiple user LLM configs exist for this user. "
                        "Clean up duplicates before updating."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        obj = qs.first()
        if obj is None:
            obj = LLMConfig.objects.create(
                scope=LLMConfig.Scope.USER,
                user=user,
                model_type=LLMConfig.MODEL_TYPE_LLM,
                provider=(data.get("provider") or "openai").strip().lower(),
                config=_preserve_masked_secret_fields(
                    {}, data.get("config") or {}
                ),
                is_active=data.get("is_active", True),
            )
        else:
            obj.provider = (data.get("provider") or "openai").strip().lower()
            obj.config = _preserve_masked_secret_fields(
                obj.config or {}, data.get("config") or {}
            )
            if "is_active" in data:
                obj.is_active = data["is_active"]
            obj.save()
        ctx = {"default_config_uuid": get_default_llm_config_uuid()}
        return Response(LLMConfigSerializer(obj, context=ctx).data)

    @extend_schema(
        tags=["llm-metering"],
        summary="Delete user LLM config",
        description="Remove user config so they fall back to global default.",
        responses={204: None, 404: ErrorDetailSerializer},
    )
    def delete(self, request, user_id):
        user = self._get_user(user_id)
        if user is None:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        deleted, _ = LLMConfig.objects.filter(
            scope=LLMConfig.Scope.USER, user=user
        ).delete()
        if deleted:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            {"detail": "No user config to delete."},
            status=status.HTTP_404_NOT_FOUND,
        )

    def _get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return None
