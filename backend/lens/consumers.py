import json
import logging
from urllib.parse import parse_qs
import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from .lensnode_auth import hash_lensnode_token
from .models import LensNode, Run
from .services import (
    append_lensnode_output,
    fail_active_runs_for_lensnode,
    finish_lensnode_run,
    lensnode_group_name,
    record_lensnode_run_event,
)

LOGGER = logging.getLogger(__name__)


class LensNodeConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket endpoint used by LensNode execution workers."""

    async def connect(self):
        """Authenticate a LensNode by token and add it to its command group."""

        token = self._query_token()
        self.lensnode = await self._authenticate_lensnode(token)
        if self.lensnode is None:
            await self.close(code=4401)
            return

        self.group_name = lensnode_group_name(self.lensnode.uuid)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(
            {
                "type": "connected",
                "lensnode_uuid": str(self.lensnode.uuid),
                "protocol_version": self.lensnode.protocol_version,
            }
        )

    async def disconnect(self, code):
        """Mark the LensNode offline when its connection closes."""

        del code
        if getattr(self, "lensnode", None) is None:
            return
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        await self._mark_disconnected(self.lensnode.uuid, self.channel_name)
        await database_sync_to_async(fail_active_runs_for_lensnode)(
            self.lensnode.uuid
        )

    async def receive_json(self, content, **kwargs):
        """Route inbound LensNode protocol frames."""

        del kwargs
        frame_type = content.get("type")
        if frame_type == "hello":
            await self._handle_hello(content)
        elif frame_type == "heartbeat":
            await self._handle_heartbeat(content)
        elif frame_type == "run_event":
            await self._handle_run_event(content)
        elif frame_type == "run_output":
            await self._handle_run_output(content)
        elif frame_type == "run_done":
            await self._handle_run_done(content)
        elif frame_type == "list_dirs_result":
            await self._handle_list_dirs_result(content)
        else:
            await self.send_json(
                {
                    "type": "error",
                    "code": "LENSNODE_FRAME_UNKNOWN",
                    "frame_type": frame_type,
                }
            )

    async def lensnode_command(self, event):
        """Forward a control-plane command to the connected LensNode."""

        await self.send_json(event["payload"])

    def _query_token(self):
        """Return the token from the WebSocket query string."""

        raw = self.scope.get("query_string", b"").decode("utf-8")
        values = parse_qs(raw)
        return (values.get("token") or [""])[0]

    @database_sync_to_async
    def _authenticate_lensnode(self, token):
        """Authenticate a LensNode and mark it online."""

        if not token:
            return None
        lensnode = (
            LensNode.objects.filter(auth_token_hash=hash_lensnode_token(token))
            .exclude(auth_token_hash="")
            .first()
        )
        if lensnode is None:
            return None
        if lensnode.enrollment_status != LensNode.EnrollmentStatus.APPROVED:
            return None
        if lensnode.token_revoked:
            return None

        now = timezone.now()
        lensnode.status = LensNode.Status.ONLINE
        lensnode.connection_id = self.channel_name
        lensnode.last_authenticated_at = now
        lensnode.last_heartbeat_at = now
        lensnode.save(
            update_fields=[
                "status",
                "connection_id",
                "last_authenticated_at",
                "last_heartbeat_at",
                "updated_at",
            ]
        )
        return lensnode

    @database_sync_to_async
    def _mark_disconnected(self, lensnode_uuid, connection_id):
        """Mark a LensNode offline if the current connection owns it."""

        LensNode.objects.filter(
            uuid=lensnode_uuid,
            connection_id=connection_id,
        ).update(
            status=LensNode.Status.OFFLINE,
            connection_id="",
            updated_at=timezone.now(),
        )

    async def _handle_hello(self, content):
        await self._update_lensnode_report(content, require_versions=True)
        await self.send_json({"type": "hello_ack"})

    async def _handle_heartbeat(self, content):
        await self._update_lensnode_report(content, require_versions=False)
        await self.send_json(
            {
                "type": "heartbeat_ack",
                "ts": timezone.now().isoformat(),
            }
        )

    @database_sync_to_async
    def _update_lensnode_report(self, content, require_versions):
        """Persist LensNode-reported workspace, task, and version metadata."""

        lensnode = LensNode.objects.get(pk=self.lensnode.pk)
        lensnode.status = LensNode.Status.ONLINE
        lensnode.connection_id = self.channel_name
        lensnode.last_heartbeat_at = timezone.now()
        if content.get("workspace_path") is not None:
            lensnode.workspace_path = content.get("workspace_path", "")
        if content.get("available_dirs") is not None:
            lensnode.available_dirs = content.get("available_dirs") or []
        if content.get("tasks") is not None:
            lensnode.tasks = content.get("tasks") or []
        if content.get("labels") is not None:
            lensnode.labels = content.get("labels") or {}
        if require_versions or content.get("protocol_version") is not None:
            lensnode.protocol_version = content.get("protocol_version", "")
        if require_versions or content.get("agent_version") is not None:
            lensnode.agent_version = content.get("agent_version", "")
        lensnode.save()
        self.lensnode = lensnode

    async def _handle_run_event(self, content):
        run_uuid = self._parse_uuid(content.get("run_uuid"))
        if run_uuid is None:
            await self._send_bad_frame("run_uuid is invalid")
            return
        await database_sync_to_async(record_lensnode_run_event)(
            run_uuid,
            content.get("step_type") or "retrieval",
            content.get("status") or "running",
            content.get("detail") or {},
        )
        LOGGER.info(
            "Recorded LensNode run event run_uuid=%s step_type=%s status=%s",
            run_uuid,
            content.get("step_type") or "retrieval",
            content.get("status") or "running",
        )

    async def _handle_run_output(self, content):
        run_uuid = self._parse_uuid(content.get("run_uuid"))
        if run_uuid is None:
            await self._send_bad_frame("run_uuid is invalid")
            return
        run = await database_sync_to_async(append_lensnode_output)(
            run_uuid,
            content_delta=content.get("content_delta") or "",
            final_content=content.get("final_content"),
            reset=bool(content.get("reset")),
        )
        delta_chars = len(content.get("content_delta") or "")
        final_chars = len(content.get("final_content") or "")
        content_length = 0
        if run.output_message is not None:
            content_length = len(run.output_message.content)
        if final_chars or content_length == delta_chars:
            LOGGER.info(
                "Recorded LensNode run output run_uuid=%s delta_chars=%s "
                "final_chars=%s content_chars=%s",
                run_uuid,
                delta_chars,
                final_chars,
                content_length,
            )
        else:
            LOGGER.debug(
                "Recorded LensNode run output run_uuid=%s delta_chars=%s "
                "content_chars=%s",
                run_uuid,
                delta_chars,
                content_length,
            )

    async def _handle_run_done(self, content):
        run_uuid = self._parse_uuid(content.get("run_uuid"))
        if run_uuid is None:
            await self._send_bad_frame("run_uuid is invalid")
            return
        status = content.get("status") or Run.Status.DONE
        if status not in [Run.Status.DONE, Run.Status.FAILED]:
            status = Run.Status.FAILED
        await database_sync_to_async(finish_lensnode_run)(
            run_uuid,
            status,
            error=content.get("error") or "",
        )
        LOGGER.info(
            "Finished LensNode run run_uuid=%s status=%s error=%s",
            run_uuid,
            status,
            content.get("error") or "",
        )

    def _parse_uuid(self, value):
        """Parse a UUID value or return None."""

        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError):
            return None

    async def _handle_list_dirs_result(self, content):
        """Store list_dirs response in cache for the waiting HTTP handler."""

        request_id = content.get("request_id") or ""
        dirs = content.get("dirs") or {}
        if request_id:
            await database_sync_to_async(self._cache_list_dirs_result)(
                request_id, dirs
            )

    @staticmethod
    def _cache_list_dirs_result(request_id, dirs):
        from django.core.cache import cache
        cache.set(f"lens:list_dirs:{request_id}", dirs, timeout=30)

    async def _send_bad_frame(self, message):
        await self.send_json(
            {
                "type": "error",
                "code": "LENSNODE_FRAME_INVALID",
                "message": message,
            }
        )

    async def decode_json(self, text_data):
        """Decode JSON frames with a stable error shape."""

        try:
            return json.loads(text_data)
        except json.JSONDecodeError:
            return {"type": "__invalid_json__"}
