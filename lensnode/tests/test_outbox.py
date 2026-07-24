import asyncio
import json

from lensnode.main import LensNodeClient


def _make_client():
    """Build a client with a throwaway config (executor is unused here)."""

    config = type(
        "Config",
        (),
        {
            "agent_version": "test-agent",
            "name": "test-node",
            "protocol_version": "v1",
            "request_timeout_s": 240,
            "max_concurrent_runs": 1,
            "workspace_path": "/missing-test-workspace",
        },
    )()
    return LensNodeClient(config)


class FakeSendError(Exception):
    """Stand-in for a websocket send failing as the connection drops."""


class FakeWebSocket:
    """Records sent frames; optionally fails the send at a given index."""

    def __init__(self, fail_on_index=None):
        self.sent = []
        self._fail_on = fail_on_index
        self._count = 0

    async def send(self, data):
        if self._fail_on is not None and self._count == self._fail_on:
            raise FakeSendError()
        self.sent.append(data)
        self._count += 1


async def _wait_until(predicate, timeout=1.0):
    deadline = timeout
    while deadline > 0:
        if predicate():
            return
        await asyncio.sleep(0.01)
        deadline -= 0.01
    raise AssertionError("condition not met within timeout")


def test_outbox_flushes_frames_enqueued_while_disconnected():
    """Frames emitted while no send loop is active flush on the next one.

    Models a run that keeps executing across a reconnect: its frames land in
    the durable outbox with no live connection, then the next connection's
    send loop delivers them in order.
    """

    async def exercise():
        client = _make_client()
        client._enqueue({"type": "run_output", "content_delta": "a"})
        client._enqueue({"type": "run_output", "content_delta": "b"})
        client._enqueue({"type": "run_done", "status": "done"})

        ws = FakeWebSocket()
        loop_task = asyncio.create_task(client._send_loop(ws))
        await _wait_until(lambda: len(ws.sent) == 3)

        client.stopping.set()
        client._outbox_ready.set()
        await asyncio.wait_for(loop_task, timeout=1)

        frames = [json.loads(item) for item in ws.sent]
        assert [f.get("content_delta") for f in frames[:2]] == ["a", "b"]
        assert frames[2]["type"] == "run_done"
        assert not client._outbox

    asyncio.run(exercise())


def test_outbox_preserves_frame_and_order_on_send_failure():
    """A send failing mid-flush keeps that frame and the rest, in order.

    Peek-then-pop: the failing frame is never dequeued, so a drop mid-send
    loses nothing and the next connection resends from exactly where it left
    off.
    """

    async def exercise():
        client = _make_client()
        client._enqueue({"type": "run_output", "content_delta": "a"})
        client._enqueue({"type": "run_output", "content_delta": "b"})
        client._enqueue({"type": "run_output", "content_delta": "c"})

        ws = FakeWebSocket(fail_on_index=1)
        loop_task = asyncio.create_task(client._send_loop(ws))
        try:
            await asyncio.wait_for(loop_task, timeout=1)
        except FakeSendError:
            pass

        # "a" was sent and dequeued; "b" failed and stayed, "c" behind it.
        assert [json.loads(item)["content_delta"] for item in ws.sent] == ["a"]
        remaining = [frame["content_delta"] for frame in client._outbox]
        assert remaining == ["b", "c"]

    asyncio.run(exercise())


def test_completed_run_hands_terminal_frame_to_outbox():
    """A completed run enters the outbox before leaving running_tasks."""

    async def exercise():
        client = _make_client()
        run_uuid = "completed-run"

        class FakeExecutor:
            """Emit a terminal frame without yielding to the event loop."""

            async def execute(self, command, emit):
                """Complete the requested run immediately."""

                emit(
                    {
                        "type": "run_done",
                        "run_uuid": command["run_uuid"],
                        "status": "done",
                    }
                )

        client.executor = FakeExecutor()
        client.running_tasks[run_uuid] = asyncio.current_task()

        await client._execute_command(run_uuid, {"run_uuid": run_uuid})

        assert run_uuid not in client.running_tasks
        assert list(client._outbox) == [
            {
                "type": "run_done",
                "run_uuid": run_uuid,
                "status": "done",
            }
        ]

    asyncio.run(exercise())


def test_reconnect_hello_claims_buffered_terminal_run_before_flush():
    """Hello protects a completed run whose terminal frame is buffered."""

    async def exercise():
        client = _make_client()
        client.running_tasks["running-run"] = asyncio.current_task()
        client.running_tasks["datasource:sync-1"] = asyncio.current_task()
        client._enqueue(
            {
                "type": "run_output",
                "run_uuid": "incomplete-run",
                "content_delta": "partial",
            }
        )
        client._enqueue(
            {
                "type": "run_output",
                "run_uuid": "completed-run",
                "final_content": "complete answer",
            }
        )
        client._enqueue(
            {
                "type": "run_done",
                "run_uuid": "completed-run",
                "status": "done",
            }
        )

        ws = FakeWebSocket()
        client.websocket = ws
        await client._send_hello()

        loop_task = asyncio.create_task(client._send_loop(ws))
        await _wait_until(lambda: len(ws.sent) == 4)
        client.stopping.set()
        client._outbox_ready.set()
        await asyncio.wait_for(loop_task, timeout=1)

        frames = [json.loads(item) for item in ws.sent]
        assert frames[0]["type"] == "hello"
        assert frames[0]["active_runs"] == [
            "completed-run",
            "running-run",
        ]
        assert [frame["type"] for frame in frames[1:]] == [
            "run_output",
            "run_output",
            "run_done",
        ]

    asyncio.run(exercise())
