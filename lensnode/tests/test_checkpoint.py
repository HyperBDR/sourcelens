"""Tests for durable LensNode run checkpoints."""

import os
import threading

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.base import empty_checkpoint

from lensnode import checkpoint


def test_checkpoint_saver_uses_rollback_journal(tmp_path, monkeypatch):
    monkeypatch.setenv("LENSNODE_CHECKPOINT_DIR", str(tmp_path))
    checkpoint._saver = None
    saver = checkpoint.get_checkpoint_saver(str(tmp_path))

    try:
        saver.setup()
        journal_mode = saver.conn.execute(
            "PRAGMA journal_mode"
        ).fetchone()[0]
    finally:
        saver.conn.close()
        checkpoint._saver = None

    assert journal_mode == "delete"


def test_checkpoint_storage_is_private(tmp_path, monkeypatch):
    directory = tmp_path / "checkpoints"
    monkeypatch.setenv("LENSNODE_CHECKPOINT_DIR", str(directory))
    checkpoint._saver = None
    saver = checkpoint.get_checkpoint_saver(str(tmp_path))

    try:
        database = directory / "lensnode.sqlite"
        assert os.stat(directory).st_mode & 0o777 == 0o700
        assert os.stat(database).st_mode & 0o777 == 0o600
    finally:
        saver.conn.close()
        checkpoint._saver = None


def test_resume_fails_closed_without_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("LENSNODE_CHECKPOINT_DIR", str(tmp_path))
    checkpoint._saver = None

    with pytest.raises(
        checkpoint.CheckpointResumeError,
        match="checkpoint is missing",
    ):
        checkpoint.load_resume_state("missing-run", str(tmp_path))

    checkpoint._saver.conn.close()
    checkpoint._saver = None


def test_resume_fails_closed_when_checkpointing_is_disabled(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("LENSNODE_CHECKPOINT_ENABLED", "0")

    with pytest.raises(
        checkpoint.CheckpointResumeError,
        match="checkpointing is disabled",
    ):
        checkpoint.load_resume_state("run", str(tmp_path))


def test_resume_loads_checkpoint_and_frozen_runtime_metadata(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("LENSNODE_CHECKPOINT_DIR", str(tmp_path))
    checkpoint._saver = None
    run_uuid = "00000000-0000-0000-0000-000000000013"
    saver = checkpoint.get_checkpoint_saver(str(tmp_path))
    saved = empty_checkpoint()
    saved["channel_values"] = {
        "messages": [AIMessage(content="checkpoint answer")]
    }
    checkpoint.save_resume_metadata(
        run_uuid,
        str(tmp_path),
        route_decision={"route": "plan_execute"},
        history_assistant_turns=2,
    )
    checkpoint.save_runtime_state(
        run_uuid,
        str(tmp_path),
        capability_state={"successful_capabilities": ["skill"]},
        runtime_evidence={"record_validation": {"valid": True}},
        guardrail_state={
            "run_token_usage": {"total_tokens": 42},
            "tool_call_history": ["search:one"],
        },
    )
    saver.put(
        checkpoint.thread_config(run_uuid),
        saved,
        {"source": "loop", "step": 1, "parents": {}},
        {},
    )

    try:
        state = checkpoint.load_resume_state(run_uuid, str(tmp_path))
    finally:
        saver.conn.close()
        checkpoint._saver = None

    assert state.messages[0].content == "checkpoint answer"
    assert state.route_decision == {"route": "plan_execute"}
    assert state.history_assistant_turns == 2
    assert state.capability_state == {
        "successful_capabilities": ["skill"]
    }
    assert state.runtime_evidence == {
        "record_validation": {"valid": True}
    }
    assert state.guardrail_state == {
        "run_token_usage": {"total_tokens": 42},
        "tool_call_history": ["search:one"],
    }


def test_checkpoint_and_metadata_writes_share_one_connection_lock(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("LENSNODE_CHECKPOINT_DIR", str(tmp_path))
    checkpoint._saver = None
    saver = checkpoint.get_checkpoint_saver(str(tmp_path))
    run_uuids = [f"concurrent-run-{index}" for index in range(4)]
    for run_uuid in run_uuids:
        checkpoint.save_resume_metadata(run_uuid, str(tmp_path))
    errors = []

    def write_graph(run_uuid):
        try:
            for _index in range(50):
                saver.put(
                    checkpoint.thread_config(run_uuid),
                    empty_checkpoint(),
                    {"source": "loop", "step": 1, "parents": {}},
                    {},
                )
        except Exception as exc:
            errors.append(exc)

    def write_metadata(run_uuid):
        try:
            for index in range(50):
                checkpoint.save_runtime_state(
                    run_uuid,
                    str(tmp_path),
                    capability_state={"index": index},
                )
        except Exception as exc:
            errors.append(exc)

    threads = [
        thread
        for run_uuid in run_uuids
        for thread in (
            threading.Thread(target=write_graph, args=(run_uuid,)),
            threading.Thread(target=write_metadata, args=(run_uuid,)),
        )
    ]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        saver.conn.close()
        checkpoint._saver = None

    assert errors == []


def test_expired_local_checkpoint_is_garbage_collected(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("LENSNODE_CHECKPOINT_DIR", str(tmp_path))
    monkeypatch.setenv("LENSNODE_CHECKPOINT_TTL_HOURS", "1")
    checkpoint._saver = None
    run_uuid = "00000000-0000-0000-0000-000000000015"
    saver = checkpoint.get_checkpoint_saver(str(tmp_path))
    saved = empty_checkpoint()
    checkpoint.save_resume_metadata(run_uuid, str(tmp_path))
    saver.put(
        checkpoint.thread_config(run_uuid),
        saved,
        {"source": "loop", "step": 1, "parents": {}},
        {},
    )
    saver.conn.execute(
        "UPDATE lensnode_run_metadata SET orphaned_at = 0"
    )
    saver.conn.commit()

    checkpoint.cleanup_expired_checkpoints(str(tmp_path))

    try:
        assert saver.get_tuple(checkpoint.thread_config(run_uuid)) is None
    finally:
        saver.conn.close()
        checkpoint._saver = None


def test_periodic_cleanup_preserves_active_run(tmp_path, monkeypatch):
    monkeypatch.setenv("LENSNODE_CHECKPOINT_DIR", str(tmp_path))
    monkeypatch.setenv("LENSNODE_CHECKPOINT_TTL_HOURS", "1")
    checkpoint._saver = None
    run_uuid = "00000000-0000-0000-0000-000000000016"
    saver = checkpoint.get_checkpoint_saver(str(tmp_path))
    saved = empty_checkpoint()
    checkpoint.save_resume_metadata(run_uuid, str(tmp_path))
    saver.put(
        checkpoint.thread_config(run_uuid),
        saved,
        {"source": "loop", "step": 1, "parents": {}},
        {},
    )
    saver.conn.execute(
        "UPDATE lensnode_run_metadata SET orphaned_at = 0"
    )
    saver.conn.commit()

    checkpoint.cleanup_expired_checkpoints(
        str(tmp_path),
        active_run_uuids=[run_uuid],
    )

    try:
        assert saver.get_tuple(checkpoint.thread_config(run_uuid)) is not None
        orphaned_at = saver.conn.execute(
            """
            SELECT orphaned_at
            FROM lensnode_run_metadata
            WHERE run_uuid = ?
            """,
            (run_uuid,),
        ).fetchone()[0]
        assert orphaned_at is None
    finally:
        saver.conn.close()
        checkpoint._saver = None


def test_cleanup_starts_ttl_when_checkpoint_becomes_orphaned(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("LENSNODE_CHECKPOINT_DIR", str(tmp_path))
    monkeypatch.setenv("LENSNODE_CHECKPOINT_TTL_HOURS", "1")
    checkpoint._saver = None
    run_uuid = "00000000-0000-0000-0000-000000000017"
    saver = checkpoint.get_checkpoint_saver(str(tmp_path))
    saved = empty_checkpoint()
    checkpoint.save_resume_metadata(run_uuid, str(tmp_path))
    saver.put(
        checkpoint.thread_config(run_uuid),
        saved,
        {"source": "loop", "step": 1, "parents": {}},
        {},
    )
    saver.conn.execute(
        "UPDATE lensnode_run_metadata SET updated_at = 0"
    )
    saver.conn.commit()

    checkpoint.cleanup_expired_checkpoints(str(tmp_path))
    saver.conn.close()
    checkpoint._saver = None
    restarted_saver = checkpoint.get_checkpoint_saver(str(tmp_path))

    try:
        assert (
            restarted_saver.get_tuple(checkpoint.thread_config(run_uuid))
            is not None
        )
        orphaned_at = restarted_saver.conn.execute(
            """
            SELECT orphaned_at
            FROM lensnode_run_metadata
            WHERE run_uuid = ?
            """,
            (run_uuid,),
        ).fetchone()[0]
        assert orphaned_at is not None
    finally:
        restarted_saver.conn.close()
        checkpoint._saver = None


def test_restart_preserves_existing_orphan_timestamp(tmp_path, monkeypatch):
    monkeypatch.setenv("LENSNODE_CHECKPOINT_DIR", str(tmp_path))
    checkpoint._saver = None
    saver = checkpoint.get_checkpoint_saver(str(tmp_path))
    run_uuid = "00000000-0000-0000-0000-000000000018"
    checkpoint.save_resume_metadata(run_uuid, str(tmp_path))
    saver.conn.execute(
        "UPDATE lensnode_run_metadata SET orphaned_at = ? WHERE run_uuid = ?",
        (1234.0, run_uuid),
    )
    saver.conn.commit()
    saver.conn.close()
    checkpoint._saver = None

    restarted_saver = checkpoint.get_checkpoint_saver(str(tmp_path))

    try:
        orphaned_at = restarted_saver.conn.execute(
            """
            SELECT orphaned_at
            FROM lensnode_run_metadata
            WHERE run_uuid = ?
            """,
            (run_uuid,),
        ).fetchone()[0]
        assert orphaned_at == 1234.0
    finally:
        restarted_saver.conn.close()
        checkpoint._saver = None


def test_checkpoint_ttl_hours_uses_effective_environment(monkeypatch):
    monkeypatch.setenv("LENSNODE_CHECKPOINT_TTL_HOURS", "6.5")

    assert checkpoint.checkpoint_ttl_hours() == 6.5
