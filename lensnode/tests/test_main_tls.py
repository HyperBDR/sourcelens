import asyncio
import ssl

import pytest

from lensnode.main import LensNodeClient


class FakeWebSocketContext:
    """Minimal asynchronous WebSocket connection context."""

    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def _make_client():
    """Build a LensNode client for transport option tests."""

    config = type(
        "Config",
        (),
        {
            "name": "test-node",
            "request_timeout_s": 30,
            "max_concurrent_runs": 1,
            "tls_skip_verify": True,
            "tls_ca_file": None,
        },
    )()
    return LensNodeClient(config)


@pytest.mark.parametrize(
    "url,uses_tls",
    [
        ("wss://server.example/ws/lens/lensnodes/", True),
        ("ws://server.example/ws/lens/lensnodes/", False),
    ],
)
def test_websocket_connection_uses_tls_context_only_for_wss(
    monkeypatch,
    url,
    uses_tls,
):
    captured = {}

    def fake_connect(target, **options):
        captured["target"] = target
        captured["options"] = options
        return FakeWebSocketContext()

    async def connected():
        return None

    async def loop(*args):
        return None

    client = _make_client()
    monkeypatch.setattr("lensnode.main.connect", fake_connect)
    monkeypatch.setattr(client, "_on_connected", connected)
    monkeypatch.setattr(client, "_send_loop", loop)
    monkeypatch.setattr(client, "_heartbeat_loop", loop)
    monkeypatch.setattr(client, "_receive_loop", loop)

    assert asyncio.run(client._run_connection(url)) is True
    assert captured["target"] == url
    if uses_tls:
        context = captured["options"]["ssl"]
        assert context.verify_mode == ssl.CERT_NONE
        assert context.check_hostname is False
    else:
        assert "ssl" not in captured["options"]
