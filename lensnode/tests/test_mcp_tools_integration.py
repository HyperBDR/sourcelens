import json
import socket
import threading
import time
from contextlib import contextmanager

import uvicorn
from mcp.server.fastmcp import FastMCP

from lensnode.mcp_tools import load_mcp_tools


class _RequestMethodRecorder:
    """Record HTTP methods without changing MCP protocol behavior."""

    def __init__(self, app):
        self.app = app
        self.methods = []

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            self.methods.append(scope["method"])
        await self.app(scope, receive, send)


@contextmanager
def _local_streamable_http_server():
    mcp = FastMCP(
        "SourceLens MCP integration test",
        json_response=True,
        stateless_http=False,
    )

    @mcp.tool()
    def add(left: int, right: int) -> str:
        """Add two integers and return a deterministic marker."""

        return f"sum={left + right}"

    app = _RequestMethodRecorder(mcp.streamable_http_app())
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            log_level="error",
            lifespan="on",
        )
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        raise RuntimeError("Local MCP test server did not start")

    try:
        yield f"http://127.0.0.1:{port}/mcp", app
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()


def test_streamable_http_discovers_calls_and_closes_sessions():
    events = []

    with _local_streamable_http_server() as (endpoint, recorder):
        tools = load_mcp_tools(
            [
                {
                    "name": "Local deterministic MCP",
                    "transport": "url",
                    "endpoint": endpoint,
                    "config": {},
                    "load_config": {"allow_insecure_http": True},
                }
            ],
            discovery_timeout_s=5,
            tool_timeout_s=5,
            emit_event=lambda event, detail: events.append(
                (event, detail)
            ),
        )

        assert [tool.name for tool in tools] == [
            "mcp__local_deterministic_mcp__add"
        ]
        assert recorder.methods.count("DELETE") == 1
        result = json.loads(tools[0].invoke({"left": 3, "right": 4}))

    assert result["ok"] is True
    assert "sum=7" in json.dumps(result["result"])
    assert recorder.methods.count("DELETE") == 2
    assert (
        "mcp.server.ready",
        {"server": "Local deterministic MCP", "tool_count": 1},
    ) in events
