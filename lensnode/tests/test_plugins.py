from types import SimpleNamespace

from lensnode.plugins import collect_mcp_servers
from lensnode.plugins.codegraph import (
    CODEGRAPH_SERVER_NAME,
    CodeGraphPlugin,
)
from lensnode.runtime_resources import _apply_feature_flags


def _config(**overrides):
    values = {
        "workspace_path": "/workspace",
        "mcp_enable_codegraph": True,
        "codegraph_command": "codegraph",
        "mcp_stdio_allowlist": ("codegraph",),
        "codegraph_init_timeout_s": 30,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_codegraph_plugin_contributes_stdio_server(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("print('hi')")
    monkeypatch.setattr(
        "lensnode.plugins.codegraph._ensure_codegraph_index",
        lambda *_args, **_kwargs: True,
    )

    servers = collect_mcp_servers(
        _config(workspace_path=str(tmp_path)),
        [],
    )

    assert [server["name"] for server in servers] == [
        CODEGRAPH_SERVER_NAME
    ]
    assert servers[0]["transport"] == "stdio"
    assert servers[0]["config"]["command"] == "codegraph"
    assert servers[0]["config"]["args"] == [
        "serve",
        "--mcp",
        "--path",
        str(tmp_path),
    ]


def test_codegraph_plugin_disabled_when_toggle_off():
    config = _config(mcp_enable_codegraph=False)
    assert not CodeGraphPlugin().enabled(config)


def test_codegraph_plugin_disabled_when_not_allowlisted():
    config = _config(mcp_stdio_allowlist=("other",))
    assert not CodeGraphPlugin().enabled(config)


def test_codegraph_plugin_disabled_when_binary_missing(monkeypatch):
    monkeypatch.setattr(
        "lensnode.plugins.codegraph.shutil.which",
        lambda _command: None,
    )
    assert not CodeGraphPlugin().enabled(_config())


def test_codegraph_plugin_config_wins_over_contribution(monkeypatch):
    configured = {
        "name": "codegraph",
        "transport": "url",
        "endpoint": "https://mcp.example.com/api",
        "config": {},
        "load_config": {},
    }
    monkeypatch.setattr(
        "lensnode.plugins.codegraph._ensure_codegraph_index",
        lambda *_args, **_kwargs: True,
    )

    servers = collect_mcp_servers(_config(), [configured])

    assert servers == [configured]


def test_codegraph_index_skipped_without_indexable_code(tmp_path):
    (tmp_path / "notes.txt").write_text("no code here")

    result = collect_mcp_servers(
        _config(workspace_path=str(tmp_path)),
        [],
    )

    assert result == []
    assert not (tmp_path / ".codegraph").exists()


def test_feature_flags_override_codegraph_off():
    config = _config(mcp_enable_codegraph=True)

    applied = _apply_feature_flags(config, {"codegraph": False})

    assert applied is config
    assert applied.mcp_enable_codegraph is False


def test_feature_flags_override_codegraph_on():
    config = _config(mcp_enable_codegraph=False)

    applied = _apply_feature_flags(config, {"codegraph": True})

    assert applied is config
    assert applied.mcp_enable_codegraph is True


def test_feature_flags_missing_or_unknown_are_noop():
    config = _config(mcp_enable_codegraph=True)

    assert _apply_feature_flags(config, None) is config
    assert _apply_feature_flags(config, {}) is config
    assert _apply_feature_flags(config, {"unlisted_feature": True}) is config
