import asyncio
import json

from lensnode.main import LensNodeClient


def _make_client(drain_timeout_s=5):
    """Build a client with a throwaway config (executor is unused here)."""

    config = type(
        "Config",
        (),
        {
            "name": "test-node",
            "request_timeout_s": 240,
            "drain_timeout_s": drain_timeout_s,
            "max_concurrent_runs": 1,
        },
    )()
    return LensNodeClient(config)


class FakeWebSocket:
    """Records sent frames and supports close()."""

    def __init__(self):
        self.sent = []
        self.closed = False

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        self.closed = True


def _sent_types(ws):
    return [json.loads(item).get("type") for item in ws.sent]


def test_drain_lets_in_flight_run_finish_then_stops():
    """A run finishing within the drain window completes, is not cancelled."""

    async def exercise():
        client = _make_client(drain_timeout_s=5)
        ws = FakeWebSocket()
        client.websocket = ws
        send_task = asyncio.create_task(client._send_loop(ws))

        finished = asyncio.Event()

        async def fake_run():
            await asyncio.sleep(0.1)
            finished.set()

        run = asyncio.create_task(fake_run())
        client.running_tasks["run-1"] = run
        run.add_done_callback(
            lambda item: client.running_tasks.pop("run-1", None)
        )

        await client.stop()

        assert finished.is_set()
        assert not run.cancelled()
        assert client.draining.is_set()
        assert client.stopping.is_set()
        assert ws.closed
        assert client.gateway_http_client.is_closed
        # Draining was announced so the control plane stops routing here.
        assert "node_draining" in _sent_types(ws)

        send_task.cancel()

    asyncio.run(exercise())


def test_drain_rejects_new_runs():
    """While draining, a new run_start is rejected with LENSNODE_DRAINING."""

    async def exercise():
        client = _make_client()
        client.draining.set()

        await client._start_command(
            {"run_uuid": "new-run", "task": "knowledge_qa"}
        )

        # No task was started; the node replied busy/draining instead.
        assert "new-run" not in client.running_tasks
        frames = [dict(item) for item in client._outbox]
        errors = [f.get("error") for f in frames]
        assert "LENSNODE_DRAINING" in errors
        assert any(f.get("type") == "run_done" for f in frames)

    asyncio.run(exercise())


def test_drain_cancels_runs_past_deadline():
    """A run still active past the drain deadline is cancelled."""

    async def exercise():
        client = _make_client(drain_timeout_s=0)
        ws = FakeWebSocket()
        client.websocket = ws
        send_task = asyncio.create_task(client._send_loop(ws))

        async def long_run():
            await asyncio.sleep(30)

        run = asyncio.create_task(long_run())
        client.running_tasks["run-1"] = run

        await client.stop()

        assert run.cancelled()
        assert client.stopping.is_set()

        send_task.cancel()

    asyncio.run(exercise())
