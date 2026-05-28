from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from agentcore_metering.adapters.django.serializers import (
    ModelsResponseSerializer,
    ProvidersResponseSerializer,
)
from agentcore_metering.adapters.django.services.model_catalog import (
    get_providers_with_models,
)
from agentcore_metering.adapters.django.services.runtime_config import (
    get_provider_params_schema,
)


class AdminLLMConfigProvidersView(APIView):
    """
    GET: Per-provider param schema (required/optional, default model/api_base).
    Use in UI to build provider-specific config forms. api_base is first in
    optional list so UI can show it at top.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["llm-metering"],
        summary="Provider params schema",
        description=(
            "Per-provider param schema (required/optional/editable_params, "
            "default_model, default_api_base). Use in UI to build "
            "provider-specific config forms. Keys are provider ids."
        ),
        responses={200: ProvidersResponseSerializer},
    )
    def get(self, request):
        return Response(get_provider_params_schema())


class AdminLLMConfigModelsView(APIView):
    """
    GET: Provider list and per-provider model list with capability tags.
    Each provider includes default_api_base (official URL) for UI default.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["llm-metering"],
        summary="Models and capabilities",
        description=(
            "Provider list and per-provider model list with capability tags "
            "(e.g. text-to-text, vision, code, reasoning). Each provider "
            "includes default_api_base for UI defaults."
        ),
        responses={200: ModelsResponseSerializer},
    )
    def get(self, request):
        data = get_providers_with_models()
        schema = get_provider_params_schema()
        for prov in data.get("providers") or []:
            pid = prov.get("id")
            if pid:
                prov["default_api_base"] = (
                    schema.get("providers") or {}
                ).get(pid, {}).get("default_api_base")
        return Response(data)
