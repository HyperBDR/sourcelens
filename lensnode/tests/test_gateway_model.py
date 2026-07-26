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
    _message_from_gateway,
    describe_image_result,
)


SSE_BODY = (
    'data: {"type": "heartbeat"}\n\n'
    'data: {"type": "token", "kind": "reasoning", "content": "thinking"}\n\n'
    'data: {"type": "token", "kind": "content", "content": "Hello"}\n\n'
    'data: {"type": "done", "usage": {"total_tokens": 5}, '
    '"tool_calls": [], "finish_reason": "length"}\n\n'
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
    assert message.content.startswith("Hello")
    assert "incomplete" in message.content.lower()
    assert message.response_metadata["finish_reason"] == "length"
    assert message.response_metadata["model_length_capped"] is True
    assert model.stop_reason == "model_length_capped"
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
            json={
                "message": {
                    "role": "assistant",
                    "content": "ok",
                    "finish_reason": "stop",
                }
            },
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
    assert (
        result.generations[0].message.response_metadata["finish_reason"]
        == "stop"
    )
    context = client_options["verify"]
    assert context.verify_mode == ssl.CERT_NONE
    assert context.check_hostname is False


def test_malformed_tool_arguments_are_not_executable():
    message = _message_from_gateway(
        {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "search_workspace",
                        "arguments": '{"query":',
                    },
                }
            ],
        }
    )

    assert message.tool_calls == []
    assert len(message.invalid_tool_calls) == 1
    assert message.invalid_tool_calls[0]["id"] == "call_1"
    assert "tool_calls" not in message.additional_kwargs


def test_safety_finish_reason_suppresses_tool_calls():
    message = _message_from_gateway(
        {
            "content": "partial",
            "finish_reason": "content_filter",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "run_skill_script",
                        "arguments": '{"path":"scripts/run.py"}',
                    },
                }
            ],
        }
    )

    assert message.tool_calls == []
    assert "safety" in message.content.lower()
    assert message.response_metadata["safety_terminated"] is True
    assert message.response_metadata["suppressed_tool_call_count"] == 1
    assert "tool_calls" not in message.additional_kwargs


def test_length_finish_reason_marks_visible_content_incomplete():
    message = _message_from_gateway(
        {
            "content": "partial answer",
            "finish_reason": "MAX_TOKENS",
            "tool_calls": [],
        }
    )

    assert "partial answer" in message.content
    assert "incomplete" in message.content.lower()
    assert message.response_metadata["model_length_capped"] is True


def test_run_token_budget_warns_then_suppresses_new_tool_calls(monkeypatch):
    requests = []
    responses = [
        {
            "message": {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "search_workspace",
                            "arguments": '{"query":"first"}',
                        },
                    }
                ],
            },
            "usage": {
                "prompt_tokens": 70,
                "completion_tokens": 10,
                "total_tokens": 80,
            },
        },
        {
            "message": {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "search_workspace",
                            "arguments": '{"query":"second"}',
                        },
                    }
                ],
            },
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
            },
        },
    ]

    def handler(request):
        requests.append(request.read().decode("utf-8"))
        return httpx.Response(200, json=responses[len(requests) - 1])

    _install_transport(monkeypatch, handler)
    model = LensGatewayChatModel(
        model_ref="model-ref",
        ai_gateway_url="http://gateway/ai/",
        token="token",
        token_budget_max_tokens=100,
        token_budget_warn_ratio=0.8,
    )

    first = model._generate([HumanMessage(content="hi")])
    second = model._generate([HumanMessage(content="continue")])

    assert len(first.generations[0].message.tool_calls) == 1
    assert "TOKEN BUDGET WARNING" in requests[1]
    capped = second.generations[0].message
    assert capped.tool_calls == []
    assert capped.response_metadata["token_capped"] is True
    assert "token budget" in capped.content.lower()
    assert model.stop_reason == "token_capped"
    assert model.token_usage == {
        "prompt_tokens": 90,
        "completion_tokens": 20,
        "total_tokens": 110,
    }


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
