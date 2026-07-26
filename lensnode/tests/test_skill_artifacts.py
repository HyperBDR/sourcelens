import hashlib
import io
import json
import platform
import zipfile
from pathlib import Path
from types import SimpleNamespace

from lensnode.agent_tools import build_general_chat_tools
from lensnode.runtime_resources import (
    RuntimeResources,
    _materialize_skill,
    _safe_extract_zip,
)


def _platform_values():
    """Return manifest platform values for the test host."""

    os_name = {
        "darwin": "darwin",
        "linux": "linux",
        "windows": "windows",
    }[platform.system().lower()]
    arch = {
        "aarch64": "arm64",
        "arm64": "arm64",
        "amd64": "amd64",
        "x86_64": "amd64",
    }[platform.machine().lower()]
    return os_name, arch


def _resources(root, content, sha256=None, os_name=None, arch=None):
    """Build runtime resources with one declared executable artifact."""

    current_os, current_arch = _platform_values()
    skill_dir = Path(root) / "skills" / "income-cli"
    artifact_path = skill_dir / "bin" / "current" / "income"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(content)
    artifact_path.chmod(0o644)
    artifacts = {
        "income": {
            "type": "executable",
            "entrypoints": [
                {
                    "os": os_name or current_os,
                    "arch": arch or current_arch,
                    "path": "bin/current/income",
                    "sha256": sha256 or hashlib.sha256(content).hexdigest(),
                }
            ],
        }
    }
    return RuntimeResources(
        root=Path(root),
        skill_paths=["skills/income-cli"],
        context_skill_contents=[],
        skill_environments={"income-cli": {"INCOME_TEST": "bound-value"}},
        mcp_config_path=Path(root) / "mcp.json",
        skill_artifacts={"income-cli": artifacts},
    )


def _artifact_tool(resources, command=None, emit_event=None):
    """Return the General Chat artifact tool."""

    tools = build_general_chat_tools(
        command or {},
        resources,
        emit_event=emit_event,
    )
    return next(item for item in tools if item.name == "run_skill_artifact")


def test_run_skill_artifact_selects_platform_and_restores_permission(tmp_path):
    content = (
        b"#!/bin/sh\n"
        b"printf '%s:%s:%s' \"$INCOME_TEST\" \"$1\" \"$(cat)\"\n"
    )
    resources = _resources(tmp_path, content)

    payload = json.loads(
        _artifact_tool(resources).invoke(
            {
                "skill": "income-cli",
                "artifact": "income",
                "args": ["order-1"],
                "stdin": "request-body",
            }
        )
    )

    artifact_path = tmp_path / "skills/income-cli/bin/current/income"
    assert payload["ok"] is True
    assert payload["stdout"] == "bound-value:order-1:request-body"
    assert artifact_path.stat().st_mode & 0o777 == 0o755


def test_run_skill_artifact_replaces_non_utf8_output(tmp_path):
    content = (
        b"#!/usr/bin/env python3\n"
        b"import sys\n"
        b"sys.stdout.buffer.write(bytes([255]))\n"
    )
    resources = _resources(tmp_path, content)

    payload = json.loads(
        _artifact_tool(resources).invoke(
            {"skill": "income-cli", "artifact": "income"}
        )
    )

    assert payload["ok"] is True
    assert payload["stdout"] == "\ufffd"


def test_run_skill_artifact_preserves_output_whitespace(tmp_path):
    content = (
        b"#!/bin/sh\n"
        b"printf 'row  1\\nrow  2\\n'\n"
        b"printf 'error\\nline\\n' >&2\n"
    )
    resources = _resources(tmp_path, content)

    payload = json.loads(
        _artifact_tool(resources).invoke(
            {"skill": "income-cli", "artifact": "income"}
        )
    )

    assert payload["ok"] is True
    assert payload["stdout"] == "row  1\nrow  2\n"
    assert payload["stderr"] == "error\nline\n"


def test_run_skill_artifact_preserves_large_output_by_reference(tmp_path):
    content = b"#!/bin/sh\nprintf 'abcdefghijklmnopqrstuvwxyz'\n"
    resources = _resources(tmp_path, content)
    command = {
        "settings": {"tool_policy": {"skill_script_stdout_limit": 10}}
    }
    events = []

    payload = json.loads(
        _artifact_tool(
            resources,
            command,
            lambda name, detail: events.append((name, detail)),
        ).invoke(
            {"skill": "income-cli", "artifact": "income"}
        )
    )

    output_path = resources.root / payload["stdout_ref"].lstrip("/")
    assert payload["stdout"] == "abcdefghij…"
    assert payload["stdout_truncated"] is True
    assert payload["stdout_bytes"] == 26
    assert "Read stdout_ref" in payload["instruction"]
    saved_output = output_path.read_text(encoding="utf-8")
    assert saved_output == "abcdefghijklmnopqrstuvwxyz"
    assert events[0][0] == "tool.run_skill_artifact.start"
    assert events[-1][0] == "tool.run_skill_artifact.done"
    assert events[0][1]["invocation_id"] == events[-1][1]["invocation_id"]
    assert events[-1][1]["stdout_ref"] == payload["stdout_ref"]
    assert events[-1][1]["stdout_truncated"] is True


def test_run_skill_artifact_stops_after_configured_call_budget(tmp_path):
    resources = _resources(tmp_path, b"#!/bin/sh\nprintf 'ok'\n")
    command = {
        "settings": {"tool_policy": {"skill_artifact_max_calls": 2}}
    }
    events = []
    artifact = _artifact_tool(
        resources,
        command,
        lambda name, detail: events.append((name, detail)),
    )

    first = json.loads(
        artifact.invoke({"skill": "income-cli", "artifact": "income"})
    )
    second = json.loads(
        artifact.invoke({"skill": "income-cli", "artifact": "income"})
    )
    third = json.loads(
        artifact.invoke({"skill": "income-cli", "artifact": "income"})
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert third["ok"] is False
    assert third["error"] == "ARTIFACT_CALL_LIMIT"
    assert third["max_calls"] == 2
    assert "Stop requesting" in third["instruction"]
    assert events[-1][0] == "tool.run_skill_artifact.budget_exceeded"
    assert events[-1][1]["call_count"] == 3
    assert events[-1][1]["max_calls"] == 2


def test_run_skill_artifact_redacts_sensitive_args_in_history(tmp_path):
    resources = _resources(tmp_path, b"#!/bin/sh\nexit 0\n")
    events = []

    _artifact_tool(
        resources,
        emit_event=lambda name, detail: events.append((name, detail)),
    ).invoke(
        {
            "skill": "income-cli",
            "artifact": "income",
            "args": ["auth", "login", "--token", "secret", "--limit", "20"],
        }
    )

    start = events[0][1]
    assert start["args_redacted"] == [
        "auth",
        "login",
        "--token",
        "[REDACTED]",
        "--limit",
        "20",
    ]


def test_run_skill_artifact_timeout_preserves_output_whitespace(tmp_path):
    content = b"#!/bin/sh\nprintf 'row  1\\nrow  2\\n'\nsleep 2\n"
    resources = _resources(tmp_path, content)
    command = {
        "settings": {"tool_policy": {"skill_script_timeout_s": 1}}
    }

    payload = json.loads(
        _artifact_tool(resources, command).invoke(
            {"skill": "income-cli", "artifact": "income"}
        )
    )

    assert payload["ok"] is False
    assert payload["error"] == "ARTIFACT_TIMEOUT"
    assert payload["stdout"] == "row  1\nrow  2\n"


def test_run_skill_artifact_timeout_preserves_large_output_by_reference(
    tmp_path,
):
    content = b"#!/bin/sh\nprintf 'abcdefghij'\nsleep 2\n"
    resources = _resources(tmp_path, content)
    command = {
        "settings": {
            "tool_policy": {
                "skill_script_timeout_s": 1,
                "skill_script_stdout_limit": 5,
            }
        }
    }

    payload = json.loads(
        _artifact_tool(resources, command).invoke(
            {"skill": "income-cli", "artifact": "income"}
        )
    )

    output_path = resources.root / payload["stdout_ref"].lstrip("/")
    assert payload["stdout"] == "abcde…"
    assert payload["stdout_truncated"] is True
    assert output_path.read_text(encoding="utf-8") == "abcdefghij"


def test_run_skill_artifact_rejects_undeclared_binary(tmp_path):
    resources = _resources(tmp_path, b"#!/bin/sh\nexit 0\n")

    payload = json.loads(
        _artifact_tool(resources).invoke(
            {"skill": "income-cli", "artifact": "other"}
        )
    )

    assert payload == {"ok": False, "error": "ARTIFACT_NOT_DECLARED"}


def test_run_skill_artifact_rejects_wrong_platform(tmp_path):
    current_os, _current_arch = _platform_values()
    unavailable_os = "windows" if current_os != "windows" else "linux"
    resources = _resources(
        tmp_path,
        b"#!/bin/sh\nexit 0\n",
        os_name=unavailable_os,
    )

    payload = json.loads(
        _artifact_tool(resources).invoke(
            {"skill": "income-cli", "artifact": "income"}
        )
    )

    assert payload == {
        "ok": False,
        "error": "ARTIFACT_PLATFORM_UNAVAILABLE",
    }


def test_run_skill_artifact_rejects_hash_mismatch(tmp_path):
    resources = _resources(
        tmp_path,
        b"#!/bin/sh\nexit 0\n",
        sha256="0" * 64,
    )

    payload = json.loads(
        _artifact_tool(resources).invoke(
            {"skill": "income-cli", "artifact": "income"}
        )
    )

    assert payload == {"ok": False, "error": "ARTIFACT_HASH_MISMATCH"}


def test_run_skill_artifact_rejects_symlink(tmp_path):
    resources = _resources(tmp_path, b"#!/bin/sh\nexit 0\n")
    artifact_path = tmp_path / "skills/income-cli/bin/current/income"
    real_path = tmp_path / "outside"
    real_path.write_bytes(b"#!/bin/sh\nexit 0\n")
    artifact_path.unlink()
    artifact_path.symlink_to(real_path)

    payload = json.loads(
        _artifact_tool(resources).invoke(
            {"skill": "income-cli", "artifact": "income"}
        )
    )

    assert payload == {"ok": False, "error": "ARTIFACT_PATH_INVALID"}


def test_runtime_zip_restores_modes_and_recursively_enables_scripts(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        script_info = zipfile.ZipInfo("skill/scripts/nested/run")
        script_info.external_attr = 0o100644 << 16
        archive.writestr(script_info, b"#!/bin/sh\n")
        binary_info = zipfile.ZipInfo("skill/bin/linux-arm64/income")
        binary_info.external_attr = 0o100755 << 16
        archive.writestr(binary_info, b"binary")

    _safe_extract_zip(buffer.getvalue(), tmp_path)

    assert (tmp_path / "scripts/nested/run").stat().st_mode & 0o777 == 0o755
    assert (
        (tmp_path / "bin/linux-arm64/income").stat().st_mode & 0o777
        == 0o755
    )


def test_materialize_skill_repairs_scripts_from_existing_cache(tmp_path):
    cache_root = tmp_path / "cache"
    skills_root = tmp_path / "runtime" / "skills"
    skill = {
        "skill_uuid": "skill-uuid",
        "skill_slug": "cached-skill",
        "content_hash": "sha256:cached",
    }
    cache_dir = cache_root / "skills/skill-uuid/sha256-cached"
    script_path = cache_dir / "scripts/nested/run"
    script_path.parent.mkdir(parents=True)
    script_path.write_bytes(b"#!/bin/sh\n")
    script_path.chmod(0o644)
    (cache_dir / ".complete").write_text("ok\n", encoding="utf-8")

    relative_path = _materialize_skill(
        SimpleNamespace(),
        cache_root,
        skills_root,
        skill,
    )

    runtime_script = tmp_path / "runtime" / relative_path / "scripts/nested/run"
    assert runtime_script.stat().st_mode & 0o777 == 0o755
