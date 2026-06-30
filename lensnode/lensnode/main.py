import asyncio
import json
import logging
import os
import signal
from urllib.parse import urlencode

from websockets.asyncio.client import connect

from .config import load_config
from .datasource_sync import DataSourceSyncError
from .datasource_sync import inspect_datasource_path, sync_datasource
from .datasource_sync import test_datasource_connection
from .executor import TASKS, LensNodeExecutor
from .logging_utils import (
    elapsed_since,
    format_duration,
    safe_ws_url,
    task_log,
    utc_now,
)
from .workspace import available_dirs

LOGGER = logging.getLogger("lensnode")


class LensNodeClient:
    """Async daemon that connects LensNode to the control plane."""

    def __init__(self, config):
        self.config = config
        self.executor = LensNodeExecutor(config)
        self.stopping = asyncio.Event()
        self.websocket = None
        self.connected_at = None
        self.connect_started_at = None
        self.heartbeat_count = 0
        self.last_report_signature = None
        self.running_tasks = {}

    async def run_forever(self):
        """Run the client with reconnect backoff until stopped."""

        backoff_s = 1
        while not self.stopping.is_set():
            url = self._ws_url()
            self.connect_started_at = utc_now()
            LOGGER.info(
                task_log(
                    (
                        "Starting to connect LensNode control channel "
                        f"{self.config.name}. The timeout is set to "
                        "10 secs."
                    ),
                    self.connect_started_at,
                    [
                        f"ControlPlaneWebSocket: {safe_ws_url(url)}",
                        f"WorkspacePath: {self.config.workspace_path}",
                    ],
                )
            )
            try:
                connected = await self._run_connection(url)
                if connected:
                    backoff_s = 1
            except Exception as exc:
                if self.stopping.is_set():
                    break
                self._log_connection_error(exc)

            if self.stopping.is_set():
                break
            LOGGER.info(
                task_log(
                    (
                        "Starting to reconnect LensNode control channel "
                        f"{self.config.name}. The timeout is set to "
                        f"{format_duration(backoff_s)}."
                    )
                )
            )
            await asyncio.sleep(backoff_s)
            backoff_s = min(backoff_s * 2, 30)

    async def stop(self):
        """Stop the client and close its WebSocket."""

        if self.stopping.is_set():
            return
        LOGGER.info(
            task_log(f"Stopping service LensNode {self.config.name}.")
        )
        self.stopping.set()
        if self.websocket is not None:
            await self.websocket.close()
        for task in list(self.running_tasks.values()):
            task.cancel()
        if self.running_tasks:
            await asyncio.gather(
                *self.running_tasks.values(),
                return_exceptions=True,
            )

    def _ws_url(self):
        """Return the token-authenticated WebSocket URL."""

        separator = "&" if "?" in self.config.control_ws_url else "?"
        return (
            f"{self.config.control_ws_url}"
            f"{separator}{urlencode({'token': self.config.token})}"
        )

    async def _run_connection(self, url):
        """Run one WebSocket connection until it closes."""

        send_queue = asyncio.Queue()
        connected = False
        async with connect(
            url,
            open_timeout=10,
            ping_interval=None,
        ) as websocket:
            self.websocket = websocket
            try:
                await self._on_connected(send_queue)
                connected = True
                tasks = [
                    asyncio.create_task(
                        self._send_loop(websocket, send_queue)
                    ),
                    asyncio.create_task(self._heartbeat_loop(send_queue)),
                    asyncio.create_task(
                        self._receive_loop(websocket, send_queue)
                    ),
                ]
                done, pending = await asyncio.wait(
                    tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    if task.cancelled():
                        continue
                    exception = task.exception()
                    if exception is not None:
                        raise exception
            finally:
                self.websocket = None
        return connected

    async def _on_connected(self, send_queue):
        """Record connection state and send initial report."""

        self.connected_at = utc_now()
        duration = elapsed_since(self.connect_started_at or self.connected_at)
        LOGGER.info(
            task_log(
                (
                    "Finish connecting LensNode control channel "
                    f"{self.config.name}. Actual duration: {duration}."
                ),
                self.connected_at,
            )
        )
        await self._send_hello(send_queue)

    async def _receive_loop(self, websocket, send_queue):
        """Receive and dispatch control-plane messages."""

        try:
            async for raw_message in websocket:
                await self._handle_message(raw_message, send_queue)
        finally:
            self._log_disconnected(None, None)

    async def _handle_message(self, raw_message, send_queue):
        """Dispatch one inbound control-plane message."""

        try:
            message = json.loads(raw_message)
        except json.JSONDecodeError:
            LOGGER.warning(
                task_log(
                    (
                        "Ignored control-plane message for LensNode "
                        f"{self.config.name}. Current status is invalid_json."
                    )
                )
            )
            return

        message_type = message.get("type")
        if message_type == "run_start":
            await self._start_command(message, send_queue)
        elif message_type == "list_dirs":
            await self._handle_list_dirs(message, send_queue)
        elif message_type == "datasource_check_path":
            await self._handle_datasource_check_path(message, send_queue)
        elif message_type == "datasource_test_connection":
            await self._handle_datasource_test_connection(message, send_queue)
        elif message_type == "datasource_sync":
            await self._start_datasource_sync(message, send_queue)
        elif message_type == "datasource_cancel":
            task_id = str(message.get("task_id") or "")
            task_key = f"datasource:{task_id}"
            task = self.running_tasks.get(task_key)
            if task is not None:
                task.cancel()
            LOGGER.info(
                task_log(
                    (
                        "Cancelled command datasource_sync "
                        f"{task_id} by control plane."
                    )
                )
            )
        elif message_type == "run_cancel":
            run_uuid = str(message.get("run_uuid") or "")
            task = self.running_tasks.get(run_uuid)
            if task is not None:
                task.cancel()
            LOGGER.info(
                task_log(
                    (
                        "Cancelled command run_start "
                        f"{run_uuid} by control plane."
                    )
                )
            )
        elif message_type == "connected":
            LOGGER.info(
                task_log(
                    (
                        "Connected LensNode session "
                        f"{message.get('lensnode_uuid')}. "
                        f"ProtocolVersion: {message.get('protocol_version')}."
                    )
                )
            )
        elif message_type == "hello_ack":
            LOGGER.info(
                task_log(
                    f"Confirmed LensNode capability report {self.config.name}."
                )
            )
        elif message_type == "heartbeat_ack":
            LOGGER.debug("Received control frame: %s", message_type)
        elif message_type == "error":
            LOGGER.warning(
                task_log(
                    (
                        "Checked control-plane response for LensNode "
                        f"{self.config.name}. Current status is error."
                    ),
                    details=[f"ErrorFrame: {message}"],
                )
            )
        else:
            LOGGER.debug(
                task_log(
                    (
                        "Ignored control-plane command for LensNode "
                        f"{self.config.name}. Current status is unknown."
                    ),
                    details=[f"FrameType: {message_type}"],
                )
            )

    async def _start_command(self, message, send_queue):
        """Start one LensNode command if local capacity allows it."""

        run_uuid = str(message.get("run_uuid") or "")
        if not run_uuid:
            return
        if run_uuid in self.running_tasks:
            await self._send_busy(run_uuid, send_queue, "LENSNODE_RUN_ACTIVE")
            return
        max_runs = max(1, int(getattr(self.config, "max_concurrent_runs", 1)))
        if len(self.running_tasks) >= max_runs:
            await self._send_busy(run_uuid, send_queue, "LENSNODE_BUSY")
            return

        LOGGER.info(
            task_log(
                (
                    "Starting to run command: run_start "
                    f"{run_uuid}. The timeout is set to "
                    f"{format_duration(self.config.request_timeout_s)}."
                ),
                details=[
                    f"Task: {message.get('task')}",
                    f"TargetDirs: {len(message.get('target_dirs') or [])}",
                ],
            )
        )
        task = asyncio.create_task(
            self._execute_command(run_uuid, message, send_queue)
        )
        self.running_tasks[run_uuid] = task
        task.add_done_callback(lambda item: self._consume_task_exception(item))

    async def _handle_list_dirs(self, message, send_queue):
        """List immediate subdirectories for requested paths and reply."""

        from pathlib import Path

        request_id = str(message.get("request_id") or "")
        paths = message.get("paths") or []
        result = {}
        for path in paths:
            p = Path(path)
            subdirs = []
            if p.is_dir():
                try:
                    for sub in sorted(p.iterdir(), key=lambda x: x.name):
                        if sub.is_dir() and not sub.name.startswith("."):
                            subdirs.append({"path": str(sub), "name": sub.name})
                            if len(subdirs) >= 30:
                                break
                except PermissionError:
                    pass
            result[path] = subdirs
        await send_queue.put({
            "type": "list_dirs_result",
            "request_id": request_id,
            "dirs": result,
        })

    async def _handle_datasource_check_path(self, message, send_queue):
        """Inspect a datasource path and reply to the control plane."""

        request_id = str(message.get("request_id") or "")
        try:
            result = inspect_datasource_path(
                message,
                workspace_path=self.config.workspace_path,
            )
        except DataSourceSyncError as exc:
            result = {
                "path": str(message.get("target_path") or ""),
                "source_compatible": False,
                "status": "blocked",
                "message": str(exc),
            }
        await send_queue.put(
            {
                "type": "datasource_path_result",
                "request_id": request_id,
                "result": result,
            }
        )

    async def _handle_datasource_test_connection(self, message, send_queue):
        """Test datasource connectivity and reply to the control plane."""

        request_id = str(message.get("request_id") or "")
        try:
            result = await asyncio.to_thread(
                test_datasource_connection,
                message,
            )
        except DataSourceSyncError as exc:
            result = {
                "status": "failed",
                "message_code": str(exc),
                "message": str(exc),
            }
        await send_queue.put(
            {
                "type": "datasource_connection_result",
                "request_id": request_id,
                "result": result,
            }
        )

    async def _start_datasource_sync(self, message, send_queue):
        """Start one datasource sync without blocking WebSocket receive."""

        request_id = str(message.get("request_id") or "")
        task_id = str(message.get("task_id") or request_id)
        if not task_id:
            return

        task_key = f"datasource:{task_id}"
        task = asyncio.create_task(
            self._execute_datasource_sync(message, send_queue)
        )
        self.running_tasks[task_key] = task
        task.add_done_callback(lambda item: self._consume_task_exception(item))

    async def _execute_datasource_sync(self, message, send_queue):
        """Execute a datasource sync command in a worker thread."""

        request_id = str(message.get("request_id") or "")
        task_id = str(message.get("task_id") or request_id)
        task_key = f"datasource:{task_id}"
        loop = asyncio.get_running_loop()

        def emit(event):
            payload = {
                "type": "datasource_sync_event",
                "request_id": request_id,
                "task_id": task_id,
                **event,
            }
            loop.call_soon_threadsafe(send_queue.put_nowait, payload)

        try:
            command = {
                **message,
                "ai_gateway_url": self.config.ai_gateway_url,
                "lensnode_token": self.config.token,
            }
            result = await asyncio.to_thread(
                sync_datasource,
                command,
                self.config.workspace_path,
                emit,
            )
            await send_queue.put(
                {
                    "type": "datasource_sync_done",
                    "request_id": request_id,
                    "task_id": task_id,
                    "status": result.get("status") or "success",
                    **result,
                }
            )
        except Exception as exc:
            await send_queue.put(
                {
                    "type": "datasource_sync_event",
                    "request_id": request_id,
                    "task_id": task_id,
                    "step": "failed",
                    "status": "failed",
                    "message": str(exc),
                }
            )
            await send_queue.put(
                {
                    "type": "datasource_sync_done",
                    "request_id": request_id,
                    "task_id": task_id,
                    "status": "failed",
                    "error": str(exc),
                }
            )
        finally:
            self.running_tasks.pop(task_key, None)

    async def _send_busy(self, run_uuid, send_queue, reason):
        """Report a run that cannot start because local capacity is full."""

        await send_queue.put(
            {
                "type": "run_event",
                "run_uuid": run_uuid,
                "step_type": "retrieval",
                "status": "failed",
                "detail": {
                    "message": task_log(
                        (
                            "Failed running command run_start "
                            f"{run_uuid}. Current status is busy."
                        ),
                        details=[f"Reason: {reason}"],
                    ),
                    "error": reason,
                },
            }
        )
        await send_queue.put(
            {
                "type": "run_done",
                "run_uuid": run_uuid,
                "status": "failed",
                "error": reason,
            }
        )

    async def _execute_command(self, run_uuid, message, send_queue):
        """Run one LensNode command without blocking WebSocket receive."""

        loop = asyncio.get_running_loop()

        def emit(payload):
            loop.call_soon_threadsafe(send_queue.put_nowait, payload)

        try:
            await self.executor.execute(message, emit)
        finally:
            self.running_tasks.pop(run_uuid, None)

    def _consume_task_exception(self, task):
        """Consume task exceptions so cancelled runs do not leak warnings."""

        if task.cancelled():
            return
        try:
            task.exception()
        except asyncio.CancelledError:
            return

    async def _send_hello(self, send_queue):
        """Send initial LensNode capabilities."""

        dirs = available_dirs(self.config.workspace_path)
        LOGGER.info(
            task_log(
                (
                    "Starting to report LensNode capabilities "
                    f"{self.config.name}."
                ),
                details=[
                    f"WorkspacePath: {self.config.workspace_path}",
                    f"AvailableDirs: {len(dirs)}",
                    f"Tasks: {', '.join(task['name'] for task in TASKS)}",
                ],
            )
        )
        active_runs = [
            key
            for key in self.running_tasks
            if not key.startswith("datasource:")
        ]
        await send_queue.put(
            {
                "type": "hello",
                "lensnode_name": self.config.name,
                "protocol_version": self.config.protocol_version,
                "agent_version": self.config.agent_version,
                "workspace_path": self.config.workspace_path,
                "available_dirs": dirs,
                "tasks": TASKS,
                "active_runs": active_runs,
                "labels": {
                    "mode": "local",
                },
            }
        )

    async def _heartbeat_loop(self, send_queue):
        """Periodically report workspace state while connected."""

        while not self.stopping.is_set():
            await asyncio.sleep(self.config.heartbeat_interval_s)
            dirs = available_dirs(self.config.workspace_path)
            signature = (
                tuple(item["path"] for item in dirs),
                tuple(task["name"] for task in TASKS),
            )
            self.heartbeat_count += 1
            if (
                self.heartbeat_count == 1
                or signature != self.last_report_signature
            ):
                LOGGER.info(
                    task_log(
                        (
                            "Monitoring LensNode heartbeat "
                            f"{self.config.name}. Current status is "
                            "connected. "
                            f"Elapsed time so far: "
                            f"{elapsed_since(self.connected_at or utc_now())}."
                        ),
                        details=[
                            f"AvailableDirs: {len(dirs)}",
                            f"Tasks: {len(TASKS)}",
                        ],
                    )
                )
            self.last_report_signature = signature
            await send_queue.put(
                {
                    "type": "heartbeat",
                    "available_dirs": dirs,
                    "tasks": TASKS,
                }
            )

    async def _send_loop(self, websocket, send_queue):
        """Serialize and send queued frames to the control plane."""

        while not self.stopping.is_set():
            payload = await send_queue.get()
            await websocket.send(json.dumps(payload, ensure_ascii=False))

    def _log_connection_error(self, error):
        """Log WebSocket connection errors."""

        LOGGER.warning(
            task_log(
                (
                    "Checked LensNode control channel "
                    f"{self.config.name}. Current status is error."
                ),
                details=[f"Error: {error}"],
            )
        )

    def _log_disconnected(self, status_code, message):
        """Log WebSocket close events."""

        details = [
            f"CloseStatus: {status_code}",
            f"CloseMessage: {message}",
        ]
        if self.connected_at:
            details.append(
                f"ConnectedDuration: {elapsed_since(self.connected_at)}"
            )
        LOGGER.info(
            task_log(
                (
                    "Stopped LensNode control channel "
                    f"{self.config.name}. Current status is disconnected."
                ),
                details=details,
            )
        )


async def _run_client():
    """Run LensNode and bind process signals to graceful shutdown."""

    client = LensNodeClient(load_config())
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            signum,
            lambda: asyncio.create_task(client.stop()),
        )
    await client.run_forever()


def _init_sentry():
    """Initialize Sentry error tracking if configured.

    Reuses the backend's SENTRY_* environment variables so LensNode and
    the backend report into the same Sentry project.
    """

    enabled = os.getenv("SENTRY_ENABLED", "").lower() in ("1", "true", "yes")
    dsn = os.getenv("SENTRY_DSN", "")
    if not enabled or not dsn:
        return

    try:
        import sentry_sdk
    except ImportError:
        LOGGER.warning("sentry-sdk not installed; skipping Sentry init.")
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        release=os.getenv("SENTRY_RELEASE", "") or None,
        traces_sample_rate=float(
            os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")
        ),
        send_default_pii=os.getenv(
            "SENTRY_SEND_DEFAULT_PII", "false"
        ).lower() in ("1", "true", "yes"),
    )


def main():
    """CLI entrypoint."""

    logging.basicConfig(
        level="INFO",
        format="%(message)s",
    )
    logging.getLogger("websockets").setLevel(logging.WARNING)
    _init_sentry()
    asyncio.run(_run_client())


if __name__ == "__main__":
    main()
