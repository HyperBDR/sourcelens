"""Durable agent-run checkpoints for in-flight resume after a node restart.

Checkpoints are written to a SQLite file under the workspace (a host
persistent volume), so a node process crash or container recreate keeps
them as long as the volume survives. Each run is one LangGraph thread keyed
by its run_uuid; on a terminal state the thread is deleted so checkpoints
never accumulate.

The saver is a process-wide singleton: SqliteSaver 3.x serializes its own
access across threads, and checkpointing happens at agent node boundaries
so the local writes are cheap.
"""

import json
import logging
import math
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field

from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.sqlite import SqliteSaver

LOGGER = logging.getLogger("lensnode")

_CHECKPOINT_FILE = "lensnode.sqlite"
_saver = None
_saver_lock = threading.Lock()
_database_lock = threading.RLock()


class CheckpointResumeError(RuntimeError):
    """A resume command cannot be proven safe from durable state."""

    code = "CHECKPOINT_UNAVAILABLE"


@dataclass(frozen=True)
class ResumeState:
    """Checkpoint and immutable runtime metadata needed for a resume."""

    messages: tuple
    route_decision: dict
    history_assistant_turns: int
    capability_state: dict = field(default_factory=dict)
    runtime_evidence: dict = field(default_factory=dict)
    guardrail_state: dict = field(default_factory=dict)


def checkpoint_enabled() -> bool:
    """Return whether run checkpoints are enabled for this node."""

    raw = os.getenv("LENSNODE_CHECKPOINT_ENABLED", "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def checkpoint_ttl_hours() -> float:
    """Return the effective local retention window for orphan checkpoints."""

    raw = os.getenv("LENSNODE_CHECKPOINT_TTL_HOURS", "24")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 24.0
    return max(value, 1.0) if math.isfinite(value) else 24.0


def checkpoint_dir(workspace_path) -> str:
    """Return the directory holding the checkpoint SQLite file."""

    configured = os.getenv("LENSNODE_CHECKPOINT_DIR", "").strip()
    if configured:
        return configured
    return os.path.join(workspace_path, ".checkpoints")


def get_checkpoint_saver(workspace_path) -> SqliteSaver:
    """Return the process-wide SqliteSaver, creating it on first use."""

    global _saver
    if _saver is None:
        with _saver_lock:
            if _saver is None:
                directory = checkpoint_dir(workspace_path)
                os.makedirs(directory, mode=0o700, exist_ok=True)
                os.chmod(directory, 0o700)
                path = os.path.join(directory, _CHECKPOINT_FILE)
                connection = sqlite3.connect(
                    path, check_same_thread=False
                )
                os.chmod(path, 0o600)
                # Rollback journal, not WAL: WAL coordination across the
                # Docker Desktop bind mount can leave commits invisible to
                # other connections, which makes terminal cleanup appear to
                # not run. The checkpoint writes are small and local, so
                # rollback journal is plenty.
                saver = SqliteSaver(connection)
                # Metadata and LangGraph checkpoints share one connection,
                # so every transaction must also share one re-entrant lock.
                saver.lock = _database_lock
                saver.setup()
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS lensnode_run_metadata (
                        run_uuid TEXT PRIMARY KEY,
                        route_decision TEXT NOT NULL,
                        history_assistant_turns INTEGER NOT NULL,
                        runtime_state TEXT NOT NULL DEFAULT '{}',
                        updated_at REAL NOT NULL,
                        orphaned_at REAL
                    )
                    """
                )
                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(lensnode_run_metadata)"
                    ).fetchall()
                }
                if "runtime_state" not in columns:
                    connection.execute(
                        "ALTER TABLE lensnode_run_metadata "
                        "ADD COLUMN runtime_state TEXT NOT NULL DEFAULT '{}'"
                    )
                if "orphaned_at" not in columns:
                    connection.execute(
                        "ALTER TABLE lensnode_run_metadata "
                        "ADD COLUMN orphaned_at REAL"
                    )
                # A fresh process means every retained thread may have just
                # become orphaned. Start a full local retention window now so
                # it cannot expire before the control plane's advertised
                # resume deadline.
                connection.execute(
                    """
                    UPDATE lensnode_run_metadata
                    SET orphaned_at = ?
                    WHERE orphaned_at IS NULL
                    """,
                    (time.time(),),
                )
                connection.commit()
                _saver = saver
                LOGGER.info("Agent run checkpoints enabled: %s", path)
    return _saver


def thread_config(run_uuid):
    """Return the LangGraph invoke config that pins a run to its thread."""

    return {
        "configurable": {
            "thread_id": str(run_uuid),
            "checkpoint_ns": "",
        },
    }


def save_resume_metadata(
    run_uuid,
    workspace_path,
    *,
    route_decision=None,
    history_assistant_turns=0,
):
    """Persist the runtime decisions that must not change on resume."""

    saver = get_checkpoint_saver(workspace_path)
    with _database_lock:
        saver.conn.execute(
            """
            INSERT OR REPLACE INTO lensnode_run_metadata (
                run_uuid,
                route_decision,
                history_assistant_turns,
                runtime_state,
                updated_at,
                orphaned_at
            ) VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (
                str(run_uuid),
                json.dumps(route_decision or {}, sort_keys=True),
                max(int(history_assistant_turns or 0), 0),
                "{}",
                time.time(),
            ),
        )
        saver.conn.commit()


def save_initial_checkpoint(run_uuid, workspace_path, messages):
    """Persist a resumable state before a non-graph model call starts."""

    saver = get_checkpoint_saver(workspace_path)
    saved = empty_checkpoint()
    saved["channel_values"] = {"messages": list(messages or [])}
    saver.put(
        thread_config(run_uuid),
        saved,
        {"source": "input", "step": -1, "parents": {}},
        {},
    )


def save_runtime_state(
    run_uuid,
    workspace_path,
    *,
    capability_state=None,
    runtime_evidence=None,
    guardrail_state=None,
):
    """Persist execution-gate state that must survive a process restart."""

    saver = get_checkpoint_saver(workspace_path)
    payload = {
        "capability_state": capability_state or {},
        "runtime_evidence": runtime_evidence or {},
        "guardrail_state": guardrail_state or {},
    }
    with _database_lock:
        cursor = saver.conn.execute(
            """
            UPDATE lensnode_run_metadata
            SET runtime_state = ?, updated_at = ?
            WHERE run_uuid = ?
            """,
            (json.dumps(payload, sort_keys=True), time.time(), str(run_uuid)),
        )
        if cursor.rowcount != 1:
            raise CheckpointResumeError(
                "Cannot persist runtime state without checkpoint metadata."
            )
        saver.conn.commit()


def load_resume_state(run_uuid, workspace_path) -> ResumeState:
    """Load a complete checkpoint or reject the resume without executing."""

    if not checkpoint_enabled():
        raise CheckpointResumeError(
            "Cannot resume run because checkpointing is disabled."
        )
    try:
        saver = get_checkpoint_saver(workspace_path)
        with _database_lock:
            snapshot = saver.get_tuple(thread_config(run_uuid))
            row = saver.conn.execute(
                """
                SELECT route_decision, history_assistant_turns, runtime_state
                FROM lensnode_run_metadata
                WHERE run_uuid = ?
                """,
                (str(run_uuid),),
            ).fetchone()
    except CheckpointResumeError:
        raise
    except Exception as exc:
        raise CheckpointResumeError(
            "Cannot resume run because its checkpoint could not be read."
        ) from exc
    if snapshot is None:
        raise CheckpointResumeError(
            "Cannot resume run because its checkpoint is missing."
        )
    if row is None:
        raise CheckpointResumeError(
            "Cannot resume run because its checkpoint metadata is missing."
        )
    try:
        route_decision = json.loads(row[0])
        runtime_state = json.loads(row[2])
    except (TypeError, ValueError) as exc:
        raise CheckpointResumeError(
            "Cannot resume run because its checkpoint metadata is invalid."
        ) from exc
    if not isinstance(runtime_state, dict):
        raise CheckpointResumeError(
            "Cannot resume run because its runtime state is invalid."
        )
    channel_values = snapshot.checkpoint.get("channel_values") or {}
    return ResumeState(
        messages=tuple(channel_values.get("messages") or ()),
        route_decision=route_decision,
        history_assistant_turns=max(int(row[1] or 0), 0),
        capability_state=runtime_state.get("capability_state") or {},
        runtime_evidence=runtime_state.get("runtime_evidence") or {},
        guardrail_state=runtime_state.get("guardrail_state") or {},
    )


def _cleanup_expired_checkpoints(saver, active_run_uuids=()):
    """Remove locally orphaned checkpoints after the bounded resume TTL."""

    now = time.time()
    cutoff = now - checkpoint_ttl_hours() * 3600
    active = {str(run_uuid) for run_uuid in active_run_uuids}
    with _database_lock:
        rows = saver.conn.execute(
            """
            SELECT run_uuid, orphaned_at
            FROM lensnode_run_metadata
            """
        ).fetchall()
        for run_uuid, orphaned_at in rows:
            if run_uuid in active:
                if orphaned_at is not None:
                    saver.conn.execute(
                        """
                        UPDATE lensnode_run_metadata
                        SET orphaned_at = NULL
                        WHERE run_uuid = ?
                        """,
                        (run_uuid,),
                    )
            elif orphaned_at is None:
                saver.conn.execute(
                    """
                    UPDATE lensnode_run_metadata
                    SET orphaned_at = ?
                    WHERE run_uuid = ?
                    """,
                    (now, run_uuid),
                )
        run_uuids = [
            run_uuid
            for run_uuid, orphaned_at in rows
            if run_uuid not in active
            and orphaned_at is not None
            and orphaned_at < cutoff
        ]
        for run_uuid in run_uuids:
            saver.delete_thread(run_uuid)
        if run_uuids:
            saver.conn.executemany(
                "DELETE FROM lensnode_run_metadata WHERE run_uuid = ?",
                [(run_uuid,) for run_uuid in run_uuids],
            )
        saver.conn.commit()
    return len(run_uuids)


def cleanup_expired_checkpoints(workspace_path, active_run_uuids=()):
    """Periodically remove expired checkpoints not active in this process."""

    if not checkpoint_enabled() or not workspace_path:
        return 0
    try:
        saver = get_checkpoint_saver(workspace_path)
        return _cleanup_expired_checkpoints(saver, active_run_uuids)
    except Exception:
        LOGGER.exception("Failed to clean up expired run checkpoints")
        return 0


def cleanup_run_checkpoint(run_uuid, workspace_path=None):
    """Delete the checkpoint thread for a terminal run, if any."""

    if not checkpoint_enabled():
        return
    if workspace_path is None:
        LOGGER.debug(
            "Skipping checkpoint cleanup for %s: no workspace path",
            run_uuid,
        )
        return
    try:
        saver = get_checkpoint_saver(workspace_path)
        with _database_lock:
            saver.delete_thread(str(run_uuid))
            saver.conn.execute(
                "DELETE FROM lensnode_run_metadata WHERE run_uuid = ?",
                (str(run_uuid),),
            )
            saver.conn.commit()
        LOGGER.info("Cleaned up checkpoint for run %s", run_uuid)
    except Exception:
        LOGGER.exception(
            "Failed to clean up checkpoint for run %s", run_uuid
        )
