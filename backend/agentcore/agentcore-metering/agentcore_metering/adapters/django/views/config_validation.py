import json

from django.http import StreamingHttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from agentcore_metering.adapters.django.serializers import (
    ConfigTestResponseSerializer,
    LLMConfigWriteSerializer,
    TestCallRequestSerializer,
    TestCallResponseSerializer,
)
from agentcore_metering.adapters.django.services.runtime_config import (
    VALIDATION_MESSAGE_IDS,
    get_validation_message,
    run_test_call,
    run_test_call_stream,
    validate_llm_config,
)


class AdminLLMConfigTestView(APIView):
    """
    POST: Validate provider + config without saving. Body: provider, config.
    Runs minimal completion to verify api_key and endpoint.
    Returns {"ok": true} or {"ok": false, "detail": "error message"}.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["llm-metering"],
        summary="Test LLM config",
        description=(
            "Validate provider and config without saving. Runs minimal "
            "completion to verify api_key and endpoint. Returns 200 with "
            "ok=true on success, ok=false and detail on failure."
        ),
        request=LLMConfigWriteSerializer,
        responses={
            200: ConfigTestResponseSerializer,
            400: ConfigTestResponseSerializer,
        },
    )
    def post(self, request):
        ser = LLMConfigWriteSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {"ok": False, "detail": ser.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        provider = (data.get("provider") or "openai").strip().lower()
        config = data.get("config") or {}
        ok, message = validate_llm_config(provider, config, user=request.user)
        if ok:
            return Response({"ok": True})
        if message in VALIDATION_MESSAGE_IDS:
            detail = get_validation_message(message, request.LANGUAGE_CODE)
        else:
            detail = message
        return Response(
            {"ok": False, "detail": detail}, status=status.HTTP_200_OK
        )


class AdminLLMConfigTestCallView(APIView):
    """
    POST: Run one completion with a saved LLMConfig and record to LLMUsage.

    Body: config_uuid, prompt; optional max_tokens (default 512, max 4096).
    Returns { ok, content?, detail?, usage? }. Call is synchronous and
    recorded in admin_test_call usage.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["llm-metering"],
        summary="Test call with config",
        description=(
            "Run one completion using the given LLMConfig uuid and prompt. "
            "Synchronous; records the call to LLM usage. Returns content "
            "and usage when ok is true."
        ),
        request=TestCallRequestSerializer,
        responses={200: TestCallResponseSerializer},
    )
    def post(self, request):
        ser = TestCallRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {"ok": False, "detail": ser.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        config_uuid = data.get("config_uuid")
        config_id = data.get("config_id")
        prompt = (data.get("prompt") or "").strip()
        max_tokens = data.get("max_tokens") or 512
        stream = data.get("stream", False)

        if not stream:
            ok, content_or_detail, usage_dict = run_test_call(
                config_uuid=str(config_uuid) if config_uuid else None,
                config_id=config_id,
                prompt=prompt,
                user=request.user,
                max_tokens=max_tokens,
            )
            if ok:
                return Response({
                    "ok": True,
                    "content": content_or_detail,
                    "usage": usage_dict,
                })
            return Response({
                "ok": False,
                "detail": content_or_detail,
            }, status=status.HTTP_200_OK)

        try:
            gen = run_test_call_stream(
                config_uuid=str(config_uuid) if config_uuid else None,
                config_id=config_id,
                prompt=prompt,
                user=request.user,
                max_tokens=max_tokens,
            )
        except ValueError as e:
            return Response({
                "ok": False,
                "detail": str(e),
            }, status=status.HTTP_200_OK)

        def sse_stream():
            usage_dict = None
            try:
                while True:
                    chunk = next(gen)
                    if isinstance(chunk, (list, tuple)) and len(chunk) >= 2:
                        kind, text = chunk[0], chunk[1]
                        payload = json.dumps({"type": kind, "content": text})
                    else:
                        payload = json.dumps(
                            {"type": "chunk", "content": chunk}
                        )
                    yield f"data: {payload}\n\n"
            except StopIteration as e:
                usage_dict = e.value
            except Exception as e:
                payload = json.dumps(
                    {"type": "done", "ok": False, "detail": str(e)}
                )
                yield f"data: {payload}\n\n"
                return
            payload = json.dumps({
                "type": "done",
                "ok": True,
                "usage": usage_dict or {},
            })
            yield f"data: {payload}\n\n"

        response = StreamingHttpResponse(
            sse_stream(),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
