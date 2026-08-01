import sys
import threading
import types

import pytest

from lensnode.datasource_sync import convert_managed_workspace
from lensnode.gateway_model import RunCancelledError


def install_fake_markitdown(monkeypatch, failing_name=""):
    """Install a deterministic MarkItDown test double."""

    class FakeMarkItDown:
        """Return text unless the configured filename must fail."""

        def convert(self, path):
            if failing_name and str(path).endswith(failing_name):
                raise RuntimeError("PASSWORD_PROTECTED")
            return types.SimpleNamespace(text_content="Converted document.")

    monkeypatch.setitem(
        sys.modules,
        "markitdown",
        types.SimpleNamespace(
            MarkItDown=FakeMarkItDown,
            __version__="test",
        ),
    )


def conversion_command(target, cancel_event=None):
    """Return a managed workspace conversion command."""

    return {
        "datasource_uuid": "managed-1",
        "name": "Managed documents",
        "source_type": "managed_workspace",
        "target_path": str(target),
        "conversion": {"document": True},
        "cancel_event": cancel_event,
    }


def test_managed_conversion_writes_sidecars_and_skips_unchanged(
    tmp_path,
    monkeypatch,
):
    """Managed conversion preserves originals and reuses fingerprints."""

    install_fake_markitdown(monkeypatch)
    document = tmp_path / "report.docx"
    original = b"external document bytes"
    document.write_bytes(original)
    (tmp_path / "notes.txt").write_text("Not a supported document.")

    first = convert_managed_workspace(
        conversion_command(tmp_path),
        workspace_path=tmp_path.parent,
    )
    second = convert_managed_workspace(
        conversion_command(tmp_path),
        workspace_path=tmp_path.parent,
    )

    assert first["status"] == "success"
    assert first["conversion_summary"]["success"] == 1
    assert first["conversion_summary"]["unsupported"] == 1
    assert document.read_bytes() == original
    assert (tmp_path / "report.docx.sourcelens/content.md").is_file()
    assert (tmp_path / "report.docx.sourcelens/meta.json").is_file()
    assert second["conversion_summary"]["skipped"] == 1
    reasons = {
        item["reason"] for item in second["conversion_summary"]["items"]
    }
    assert reasons == {"UNCHANGED", "UNSUPPORTED_TYPE"}


def test_managed_conversion_continues_after_one_file_failure(
    tmp_path,
    monkeypatch,
):
    """A per-file failure does not fail the managed conversion batch."""

    install_fake_markitdown(monkeypatch, failing_name="protected.docx")
    (tmp_path / "ok.docx").write_bytes(b"ok")
    (tmp_path / "protected.docx").write_bytes(b"protected")

    result = convert_managed_workspace(
        conversion_command(tmp_path),
        workspace_path=tmp_path.parent,
    )

    summary = result["conversion_summary"]
    assert result["status"] == "success"
    assert summary["success"] == 1
    assert summary["failed"] == 1
    assert "CONVERSION_PARTIAL_FAILED" in summary["warnings"]
    failed = next(item for item in summary["items"] if item["status"] == "failed")
    assert failed["reason"] == "PASSWORD_PROTECTED"


def test_managed_conversion_stops_at_safe_boundary_when_cancelled(
    tmp_path,
    monkeypatch,
):
    """Cancellation prevents new sidecars from being written."""

    install_fake_markitdown(monkeypatch)
    document = tmp_path / "cancelled.docx"
    document.write_bytes(b"cancelled")
    cancel_event = threading.Event()
    cancel_event.set()

    with pytest.raises(RunCancelledError):
        convert_managed_workspace(
            conversion_command(tmp_path, cancel_event=cancel_event),
            workspace_path=tmp_path.parent,
        )

    assert not (tmp_path / "cancelled.docx.sourcelens").exists()
