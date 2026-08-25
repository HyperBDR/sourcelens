import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

from lensnode.agent_tools import build_general_chat_tools
from lensnode.runtime_resources import (
    RuntimeResources,
    _materialize_skill,
    _safe_extract_zip,
)


def _resources(root, content, path="scripts/run.sh", executable=True):
    """Build runtime resources with one bundled executable under the
    Skill root."""

    skill_dir = Path(root) / "skills" / "income-cli"
    script_path = skill_dir / path
    script_path.parent.mkdir(parents=True)
    script_path.write_bytes(content)
    if executable:
        script_path.chmod(0o755)
    else:
        script_path.chmod(0o644)
    return RuntimeResources(
        root=Path(root),
        skill_paths=["skills/income-cli"],
        context_skill_contents=[],
        skill_environments={"income-cli": {"INCOME_TEST": "bound-value"}},
        mcp_config_path=Path(root) / "mcp.json",
    )


def _script_tool(resources, command=None, emit_event=None, config=None):
    """Return the General Chat script tool."""

    tools = build_general_chat_tools(
        command or {},
        resources,
        config=config,
        emit_event=emit_event,
    )
    return next(item for item in tools if item.name == "run_skill_script")


def test_run_skill_script_runs_executable_under_skill_root(tmp_path):
    content = (
        b"#!/bin/sh\n"
        b"printf '%s:%s:%s' \"$INCOME_TEST\" \"$1\" \"$(cat)\"\n"
    )
    resources = _resources(tmp_path, content)

    payload = json.loads(
        _script_tool(resources).invoke(
            {
                "skill": "income-cli",
                "script": "scripts/run.sh",
                "args": ["order-1"],
                "stdin": "request-body",
            }
        )
    )

    assert payload["ok"] is True
    assert payload["stdout"] == "bound-value:order-1:request-body"


def test_run_skill_script_runs_native_binary_under_bin(tmp_path):
    content = (
        b"#!/bin/sh\n"
        b"printf '%s:%s' \"$INCOME_TEST\" \"$1\"\n"
    )
    resources = _resources(
        tmp_path,
        content,
        path="bin/linux-amd64/income",
    )

    payload = json.loads(
        _script_tool(resources).invoke(
            {
                "skill": "income-cli",
                "script": "bin/linux-amd64/income",
                "args": ["order-1"],
            }
        )
    )

    assert payload["ok"] is True
    assert payload["stdout"] == "bound-value:order-1"


def test_run_skill_script_replaces_non_utf8_output(tmp_path):
    content = (
        b"#!/usr/bin/env python3\n"
        b"import sys\n"
        b"sys.stdout.buffer.write(bytes([255]))\n"
    )
    resources = _resources(tmp_path, content)

    payload = json.loads(
        _script_tool(resources).invoke(
            {"skill": "income-cli", "script": "scripts/run.sh"}
        )
    )

    assert payload["ok"] is True
    assert payload["stdout"] == "\ufffd"


def test_run_skill_script_preserves_output_whitespace(tmp_path):
    content = (
        b"#!/bin/sh\n"
        b"printf 'row  1\\nrow  2\\n'\n"
        b"printf 'error\\nline\\n' >&2\n"
    )
    resources = _resources(tmp_path, content)

    payload = json.loads(
        _script_tool(resources).invoke(
            {"skill": "income-cli", "script": "scripts/run.sh"}
        )
    )

    assert payload["ok"] is True
    assert payload["stdout"] == "row  1\nrow  2\n"
    assert payload["stderr"] == "error\nline\n"


def test_run_skill_script_preserves_large_output_by_reference(tmp_path):
    content = b"#!/bin/sh\nprintf 'abcdefghijklmnopqrstuvwxyz'\n"
    resources = _resources(tmp_path, content)
    command = {
        "settings": {"tool_policy": {"skill_script_stdout_limit": 10}}
    }
    events = []

    payload = json.loads(
        _script_tool(
            resources,
            command,
            lambda name, detail: events.append((name, detail)),
        ).invoke(
            {"skill": "income-cli", "script": "scripts/run.sh"}
        )
    )

    output_path = resources.root / payload["stdout_ref"].lstrip("/")
    assert payload["stdout"] == "abcdefghij…"
    assert payload["stdout_truncated"] is True
    assert payload["stdout_bytes"] == 26
    assert "Read stdout_ref" in payload["instruction"]
    saved_output = output_path.read_text(encoding="utf-8")
    assert saved_output == "abcdefghijklmnopqrstuvwxyz"
    assert events[0][0] == "tool.run_skill_script.start"
    assert events[-1][0] == "tool.run_skill_script.done"
    assert events[-1][1]["stdout_ref"] == payload["stdout_ref"]
    assert events[-1][1]["stdout_truncated"] is True


def test_run_skill_script_prefers_named_preview_limit(tmp_path):
    content = b"#!/bin/sh\nprintf 'abcdefghijklmnopqrstuvwxyz'\n"
    resources = _resources(tmp_path, content)
    command = {
        "settings": {
            "tool_policy": {
                "skill_script_stdout_preview_chars": 6,
                "skill_script_stdout_limit": 10,
            }
        }
    }

    payload = json.loads(
        _script_tool(resources, command).invoke(
            {"skill": "income-cli", "script": "scripts/run.sh"}
        )
    )

    assert payload["stdout"] == "abcdef…"
    assert payload["stdout_truncated"] is True


def test_run_skill_script_summarizes_large_csv_output(tmp_path):
    content = (
        b"#!/bin/sh\n"
        b"printf 'id,status\\n1,paid\\n2,pending\\n'\n"
    )
    resources = _resources(tmp_path, content)
    command = {
        "settings": {"tool_policy": {"skill_script_stdout_limit": 8}}
    }

    payload = json.loads(
        _script_tool(resources, command).invoke(
            {"skill": "income-cli", "script": "scripts/run.sh"}
        )
    )

    assert payload["stdout_format"] == "csv"
    assert payload["stdout_synopsis"]["columns"] == ["id", "status"]
    assert payload["stdout_synopsis"]["row_count"] == 2
    assert "inspect_saved_output" in payload["instruction"]


def test_run_skill_script_redacts_sensitive_args_in_history(tmp_path):
    resources = _resources(tmp_path, b"#!/bin/sh\nexit 0\n")
    events = []

    _script_tool(
        resources,
        emit_event=lambda name, detail: events.append((name, detail)),
    ).invoke(
        {
            "skill": "income-cli",
            "script": "scripts/run.sh",
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


def test_run_skill_script_timeout_preserves_output_whitespace(tmp_path):
    content = b"#!/bin/sh\nprintf 'row  1\\nrow  2\\n'\nsleep 2\n"
    resources = _resources(tmp_path, content)
    command = {
        "settings": {"tool_policy": {"skill_script_timeout_s": 1}}
    }

    payload = json.loads(
        _script_tool(resources, command).invoke(
            {"skill": "income-cli", "script": "scripts/run.sh"}
        )
    )

    assert payload["ok"] is False
    assert payload["error"] == "SCRIPT_TIMEOUT"
    assert payload["stdout"] == "row  1\nrow  2\n"


def test_run_skill_script_timeout_preserves_large_output_by_reference(
    tmp_path,
):
    content = b"#!/bin/sh\nprintf 'abcdefghij'\nsleep 5\n"
    resources = _resources(tmp_path, content)
    command = {
        "settings": {
            "tool_policy": {
                "skill_script_timeout_s": 2,
                "skill_script_stdout_limit": 5,
            }
        }
    }

    payload = json.loads(
        _script_tool(resources, command).invoke(
            {"skill": "income-cli", "script": "scripts/run.sh"}
        )
    )

    assert payload["ok"] is False
    assert payload["error"] == "SCRIPT_TIMEOUT"
    assert payload["stdout_ref"]
    output_path = resources.root / payload["stdout_ref"].lstrip("/")
    assert payload["stdout"] == "abcde…"
    assert payload["stdout_truncated"] is True
    assert output_path.read_text(encoding="utf-8") == "abcdefghij"


def test_run_skill_script_rejects_path_escape(tmp_path):
    resources = _resources(tmp_path, b"#!/bin/sh\nexit 0\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "run.sh"
    outside_file.write_bytes(b"#!/bin/sh\nexit 0\n")

    payload = json.loads(
        _script_tool(resources).invoke(
            {
                "skill": "income-cli",
                "script": "../outside/run.sh",
            }
        )
    )

    assert payload == {"ok": False, "error": "SCRIPT_NOT_ALLOWED"}


def test_run_skill_script_rejects_symlink(tmp_path):
    resources = _resources(tmp_path, b"#!/bin/sh\nexit 0\n")
    script_path = tmp_path / "skills/income-cli/scripts/run.sh"
    real_path = tmp_path / "outside"
    real_path.write_bytes(b"#!/bin/sh\nexit 0\n")
    script_path.unlink()
    script_path.symlink_to(real_path)

    payload = json.loads(
        _script_tool(resources).invoke(
            {"skill": "income-cli", "script": "scripts/run.sh"}
        )
    )

    assert payload == {"ok": False, "error": "SCRIPT_NOT_ALLOWED"}


def test_run_skill_script_rejects_non_executable(tmp_path):
    resources = _resources(
        tmp_path,
        b"not a script\n",
        path="data.txt",
        executable=False,
    )

    payload = json.loads(
        _script_tool(resources).invoke(
            {"skill": "income-cli", "script": "data.txt"}
        )
    )

    assert payload == {"ok": False, "error": "SCRIPT_NOT_EXECUTABLE"}


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
        "skill_package_name": "cached-skill",
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


def test_run_skill_script_ignores_legacy_fixed_call_budget(tmp_path):
    content = b"#!/bin/sh\nprintf 'ok'\n"
    resources = _resources(tmp_path, content)
    command = {
        "settings": {"tool_policy": {"skill_script_max_calls": 1}}
    }
    tool = _script_tool(
        resources,
        command,
        lambda _name, _detail: None,
    )

    first = json.loads(
        tool.invoke({"skill": "income-cli", "script": "scripts/run.sh"})
    )
    second = json.loads(
        tool.invoke({"skill": "income-cli", "script": "scripts/run.sh"})
    )

    assert first["ok"] is True
    assert second["ok"] is True


def test_run_skill_script_enforces_per_call_output_byte_quota(tmp_path):
    content = (
        b"#!/bin/sh\n"
        b"printf 'abcdefghij'\n"
        b"sleep 1\n"
        b"touch should-not-exist\n"
    )
    resources = _resources(tmp_path, content)
    command = {
        "settings": {
            "tool_policy": {
                "skill_script_max_output_bytes_per_call": 6,
                "skill_script_max_output_bytes_per_run": 20,
            }
        }
    }
    events = []

    payload = json.loads(
        _script_tool(
            resources,
            command,
            lambda name, detail: events.append((name, detail)),
        ).invoke(
            {"skill": "income-cli", "script": "scripts/run.sh"}
        )
    )

    assert payload["ok"] is False
    assert payload["error"] == "SKILL_SCRIPT_OUTPUT_QUOTA_EXCEEDED"
    assert payload["quota_scope"] == "per_call"
    assert payload["output_bytes_this_call"] == 6
    assert payload["output_bytes_this_run"] == 6
    assert payload["stdout"] == "abcdef"
    assert payload["stdout_ref"]
    output_path = resources.root / payload["stdout_ref"].lstrip("/")
    assert output_path.read_text(encoding="utf-8") == "abcdef"
    assert not (
        resources.root / "skills/income-cli/should-not-exist"
    ).exists()
    assert events[-1][0] == "tool.run_skill_script.output_quota_exceeded"


def test_run_skill_script_enforces_per_run_output_byte_quota(tmp_path):
    content = b"#!/bin/sh\nprintf 'abcd'\n"
    resources = _resources(tmp_path, content)
    command = {
        "settings": {
            "tool_policy": {
                "skill_script_max_output_bytes_per_call": 10,
                "skill_script_max_output_bytes_per_run": 6,
            }
        }
    }
    tool = _script_tool(resources, command)

    first = json.loads(
        tool.invoke({"skill": "income-cli", "script": "scripts/run.sh"})
    )
    second = json.loads(
        tool.invoke({"skill": "income-cli", "script": "scripts/run.sh"})
    )

    assert first["ok"] is True
    assert first["stdout"] == "abcd"
    assert second["ok"] is False
    assert second["error"] == "SKILL_SCRIPT_OUTPUT_QUOTA_EXCEEDED"
    assert second["quota_scope"] == "per_run"
    assert second["output_bytes_this_call"] == 2
    assert second["output_bytes_this_run"] == 6
    assert second["stdout"] == "ab"


def test_run_skill_script_done_reports_call_counts(tmp_path):
    content = b"#!/bin/sh\nprintf 'abc'\n"
    resources = _resources(tmp_path, content)
    command = {
        "settings": {"tool_policy": {"skill_script_max_calls": 3}}
    }
    events = []
    tool = _script_tool(
        resources,
        command,
        lambda name, detail: events.append((name, detail)),
    )

    json.loads(
        tool.invoke({"skill": "income-cli", "script": "scripts/run.sh"})
    )
    json.loads(
        tool.invoke({"skill": "income-cli", "script": "scripts/run.sh"})
    )

    done_events = [
        detail
        for name, detail in events
        if name == "tool.run_skill_script.done"
    ]
    assert done_events[0]["call_count"] == 1
    assert done_events[1]["call_count"] == 2


def test_run_skill_script_refs_medium_json_output(tmp_path):
    content = (
        b"#!/bin/sh\n"
        b"printf '%s' \"[{\\\"key\\\": \\\"$(printf 'x%.0s' "
        b"$(seq 1 900))\\\"}]\"\n"
    )
    resources = _resources(tmp_path, content)

    payload = json.loads(
        _script_tool(resources).invoke(
            {"skill": "income-cli", "script": "scripts/run.sh"}
        )
    )

    assert payload["ok"] is True
    assert payload["stdout_truncated"] is True
    assert payload["stdout_format"] == "json"
    assert payload["stdout_ref"]
    assert "analyze_structured_output" in payload["instruction"]
    output_path = resources.root / payload["stdout_ref"].lstrip("/")
    saved = output_path.read_text(encoding="utf-8")
    assert saved.startswith('[{"key": "xx')
    assert len(saved) > 900


def test_run_skill_script_keeps_small_json_output_inline(tmp_path):
    content = (
        b"#!/bin/sh\n"
        b"printf '%s' '[{\"key\": \"value\"}]'\n"
    )
    resources = _resources(tmp_path, content)

    payload = json.loads(
        _script_tool(resources).invoke(
            {"skill": "income-cli", "script": "scripts/run.sh"}
        )
    )

    assert payload["ok"] is True
    assert payload["stdout_format"] == "json"
    assert payload["stdout_truncated"] is False
    assert payload["stdout_ref"] is None
