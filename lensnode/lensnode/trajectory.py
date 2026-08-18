"""Complete, ordered trajectory events for one LensNode run."""

import json
import logging
import threading
import uuid

from .logging_utils import utc_now

LOGGER = logging.getLogger("lensnode")
TRACE_SCHEMA_VERSION = 1


def _json_value(value):
    """Return a JSON-safe copy without removing observable content."""

    try:
        return json.loads(
            json.dumps(
                value,
                allow_nan=False,
                default=str,
                ensure_ascii=False,
            )
        )
    except Exception:
        LOGGER.warning("Trajectory payload required fallback serialization")
        try:
            serialized = str(value)
        except Exception:
            serialized = f"<unserializable {type(value).__name__}>"
        return {
            "serialization_error": type(value).__name__,
            "value": serialized,
        }


class RunTrajectory:
    """Allocate run-local sequences and publish append-only event frames."""

    def __init__(
        self,
        run_uuid,
        emit_frame,
        *,
        start_sequence=0,
        attempt=1,
        trace_state=None,
        persist_state=None,
    ):
        state = trace_state if isinstance(trace_state, dict) else {}
        schema_version = state.get("trace_schema_version")
        if state and schema_version != TRACE_SCHEMA_VERSION:
            raise ValueError("Unsupported trajectory checkpoint schema")
        self.run_uuid = str(run_uuid)
        self.emit_frame = emit_frame
        self.persist_state = persist_state
        self._lock = threading.RLock()
        self._sequence = max(
            int(state.get("last_trace_seq") or start_sequence or 0),
            0,
        )
        self._attempt = max(
            int(state.get("current_attempt") or attempt or 1),
            1,
        )
        self._open_call_ids = {
            str(value) for value in state.get("open_call_ids") or []
        }
        self._open_span_ids = {
            str(value) for value in state.get("open_span_ids") or []
        }
        self._parent_call_map = {
            str(key): str(value)
            for key, value in (state.get("parent_call_map") or {}).items()
        }
        self._call_categories = {}

    def record(
        self,
        event_type,
        payload=None,
        *,
        checkpoint_id=None,
        turn=None,
        step=None,
        call_id=None,
        parent_call_id=None,
    ):
        """Publish one event and persist the resulting resume cursor."""

        with self._lock:
            self._sequence += 1
            event = {
                "event_id": str(uuid.uuid4()),
                "sequence": self._sequence,
                "attempt": self._attempt,
                "event_type": str(event_type),
                "timestamp": utc_now().isoformat().replace("+00:00", "Z"),
                "payload": _json_value(payload or {}),
            }
            for key, value in (
                ("checkpoint_id", checkpoint_id),
                ("turn", turn),
                ("step", step),
                ("call_id", call_id),
                ("parent_call_id", parent_call_id),
            ):
                if key in {"turn", "step"} and (
                    not isinstance(value, int)
                    or isinstance(value, bool)
                    or value < 1
                ):
                    continue
                if value is not None and value != "":
                    event[key] = value
            frame = {
                "type": "run_trace_events",
                "run_uuid": self.run_uuid,
                "events": [event],
            }
            snapshot = self._snapshot_unlocked()
            self.emit_frame(frame)
            if self.persist_state is not None:
                try:
                    self.persist_state(snapshot)
                except Exception:
                    LOGGER.exception("Failed to persist trajectory cursor")
            return event

    def start_call(
        self,
        category,
        name,
        payload=None,
        *,
        call_id=None,
        parent_call_id=None,
        turn=None,
        step=None,
    ):
        """Open a model, tool, or subtool call and return its stable ID."""

        call_id = str(call_id or uuid.uuid4().hex)
        category = str(category)
        with self._lock:
            if parent_call_id is None:
                parent_call_id = self._parent_call_map.get(call_id)
            self._open_call_ids.add(call_id)
            if category in {"tool", "subtool"}:
                self._open_span_ids.add(call_id)
            if parent_call_id:
                self._parent_call_map[call_id] = str(parent_call_id)
            self._call_categories[call_id] = category
            detail = dict(payload or {})
            detail.setdefault("name", str(name))
            self.record(
                f"{category}.started",
                detail,
                turn=turn,
                step=step,
                call_id=call_id,
                parent_call_id=parent_call_id,
            )
            return call_id

    def bind_parent(self, call_id, parent_call_id):
        """Associate a future tool call with the model that requested it."""

        if not call_id or not parent_call_id:
            return
        with self._lock:
            self._parent_call_map[str(call_id)] = str(parent_call_id)

    def finish_call(
        self,
        call_id,
        status,
        payload=None,
        *,
        turn=None,
        step=None,
    ):
        """Close a call with completed, failed, or interrupted status."""

        call_id = str(call_id)
        with self._lock:
            category = self._call_categories.pop(call_id, "tool")
            parent_call_id = self._parent_call_map.pop(call_id, None)
            self._open_call_ids.discard(call_id)
            self._open_span_ids.discard(call_id)
            return self.record(
                f"{category}.{status}",
                payload,
                turn=turn,
                step=step,
                call_id=call_id,
                parent_call_id=parent_call_id,
            )

    def snapshot(self):
        """Return checkpoint-safe trajectory continuation metadata."""

        with self._lock:
            return self._snapshot_unlocked()

    def merge_resume_state(self, trace_state):
        """Merge checkpoint-only open-call state without moving backwards."""

        if not isinstance(trace_state, dict):
            return
        if trace_state.get("trace_schema_version") != TRACE_SCHEMA_VERSION:
            raise ValueError("Unsupported trajectory checkpoint schema")
        with self._lock:
            self._sequence = max(
                self._sequence,
                int(trace_state.get("last_trace_seq") or 0),
            )
            self._attempt = max(
                self._attempt,
                int(trace_state.get("current_attempt") or 1),
            )
            self._open_call_ids.update(
                str(value) for value in trace_state.get("open_call_ids") or []
            )
            self._open_span_ids.update(
                str(value) for value in trace_state.get("open_span_ids") or []
            )
            self._parent_call_map.update(
                {
                    str(key): str(value)
                    for key, value in (
                        trace_state.get("parent_call_map") or {}
                    ).items()
                }
            )

    def interrupt_open_calls(self, reason):
        """Close calls left open by the previous execution attempt."""

        with self._lock:
            open_call_ids = sorted(self._open_call_ids)
        for call_id in open_call_ids:
            with self._lock:
                parent_call_id = self._parent_call_map.get(call_id)
                category = (
                    "tool" if call_id in self._open_span_ids else "model"
                )
                self._parent_call_map.pop(call_id, None)
                self._open_call_ids.discard(call_id)
                self._open_span_ids.discard(call_id)
                self._call_categories.pop(call_id, None)
                self.record(
                    "interrupted",
                    {"reason": str(reason), "category": category},
                    call_id=call_id,
                    parent_call_id=parent_call_id,
                )

    def _snapshot_unlocked(self):
        return {
            "trace_schema_version": TRACE_SCHEMA_VERSION,
            "last_trace_seq": self._sequence,
            "current_attempt": self._attempt,
            "open_call_ids": sorted(self._open_call_ids),
            "open_span_ids": sorted(self._open_span_ids),
            "parent_call_map": dict(sorted(self._parent_call_map.items())),
        }
