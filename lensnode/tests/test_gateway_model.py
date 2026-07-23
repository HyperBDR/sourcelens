import ssl
import threading
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import HumanMessage

from lensnode.agent_runtime import _build_summarization_middleware
from lensnode.gateway_model import (
    LensGatewayChatModel,
    RunCancelledError,
    describe_image_result,
)


SSE_BODY = (
    'data: {"type": "heartbeat"}\n\n'
    'data: {"type": "token", "kind": "reasoning", "content": "thinking"}\n\n'
    'data: {"type": "token", "kind": "content", "content": "Hello"}\n\n'
    'data: {"type": "done", "usage": {"total_tokens": 5}, '
    '"tool_calls": []}\n\n'
)


def _install_transport(monkeypatch, handler, client_options=None):
    """Route the module's httpx.Client through a mock transport."""

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def fake_client(*args, **kwargs):
        if client_options is not None:
            client_options.update(kwargs)
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(
        "lensnode.gateway_model.httpx.Client", fake_client
    )


def test_streaming_touches_activity_on_every_event(monkeypatch):
    captured = {}
    client_options = {}

    def handler(request):
        captured["payload"] = request.read()
        return httpx.Response(200, content=SSE_BODY.encode("utf-8"))

    _install_transport(monkeypatch, handler, client_options)
    outputs = []
    activity = {"count": 0}

    def on_activity():
        activity["count"] += 1

    model = LensGatewayChatModel(
        model_ref="model-ref",
        ai_gateway_url="http://gateway/ai/",
        token="token",
        emit_output=outputs.append,
        on_activity=on_activity,
        run_uuid="00000000-0000-0000-0000-000000000009",
    )

    result = model._generate([HumanMessage(content="hi")])

    message = result.generations[0].message
    assert message.content == "Hello"
    # heartbeat + reasoning + content + done all count as activity,
    # while only the content token reaches the user-facing stream.
    assert activity["count"] == 4
    assert outputs == ["Hello"]
    assert b'"run_uuid"' in captured["payload"]
    assert b'"is_subagent"' in captured["payload"]
    assert client_options["verify"].verify_mode == ssl.CERT_REQUIRED


def test_cancelled_run_aborts_before_model_call(monkeypatch):
    def handler(request):
        raise AssertionError("cancelled run must not call the gateway")

    _install_transport(monkeypatch, handler)
    cancel_event = threading.Event()
    cancel_event.set()

    model = LensGatewayChatModel(
        model_ref="model-ref",
        ai_gateway_url="http://gateway/ai/",
        token="token",
        emit_output=lambda *_args, **_kwargs: None,
        cancel_event=cancel_event,
    )

    with pytest.raises(RunCancelledError):
        model._generate([HumanMessage(content="hi")])


def test_https_gateway_request_uses_configured_tls_context(monkeypatch):
    client_options = {}

    def handler(request):
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "ok"}},
        )

    _install_transport(monkeypatch, handler, client_options)
    model = LensGatewayChatModel(
        model_ref="model-ref",
        ai_gateway_url="https://gateway.example/ai/",
        token="token",
        tls_skip_verify=True,
    )

    result = model._generate([HumanMessage(content="hi")])

    assert result.generations[0].message.content == "ok"
    context = client_options["verify"]
    assert context.verify_mode == ssl.CERT_NONE
    assert context.check_hostname is False


def test_image_gateway_request_uses_configured_tls_context(monkeypatch):
    client_options = {}

    def handler(request):
        return httpx.Response(
            200,
            json={"message": {"content": "described"}},
        )

    _install_transport(monkeypatch, handler, client_options)

    result = describe_image_result(
        b"image",
        "Describe this image.",
        "image/png",
        model_ref="vision-model",
        ai_gateway_url="https://gateway.example/ai/",
        token="token",
        tls_skip_verify=True,
    )

    assert result["content"] == "described"
    assert client_options["verify"].verify_mode == ssl.CERT_NONE


def test_summarization_model_receives_tls_configuration():
    config = SimpleNamespace(
        summary_trigger_tokens=1000,
        summary_keep_tokens=500,
        ai_gateway_url="https://gateway.example/ai/",
        token="token",
        request_timeout_s=30,
        tls_skip_verify=True,
        tls_ca_file="/ignored/ca.crt",
    )

    middleware = _build_summarization_middleware(
        config,
        "summary-model",
        lambda *args: None,
    )

    assert middleware.model.tls_skip_verify is True
    assert middleware.model.tls_ca_file == "/ignored/ca.crt"
