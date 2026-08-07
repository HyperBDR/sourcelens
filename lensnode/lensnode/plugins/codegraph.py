"""Built-in CodeGraph MCP plugin.

Contributes a stdio MCP server that exposes a CodeGraph knowledge graph
of the lensnode workspace to the agent, indexing the workspace once on
first use.
"""

import fcntl
import shutil
import subprocess
from pathlib import Path

from . import LensNodePlugin

CODEGRAPH_SERVER_NAME = "codegraph"
CODEGRAPH_INDEX_DIR = ".codegraph"
CODEGRAPH_INIT_LOCK = "codegraph-init.lock"
CODEGRAPH_CODE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
}


class CodeGraphPlugin(LensNodePlugin):
    """Contribute the CodeGraph MCP server for the current workspace."""

    name = CODEGRAPH_SERVER_NAME

    def enabled(self, config):
        """Require the toggle, an allowlisted binary on PATH."""

        command = str(getattr(config, "codegraph_command", "") or "")
        allowlist = getattr(config, "mcp_stdio_allowlist", ()) or ()
        return bool(
            getattr(config, "mcp_enable_codegraph", False)
            and command
            and Path(command).name in allowlist
            and shutil.which(command)
        )

    def contribute_mcp_servers(self, config, emit_event=None):
        """Return the CodeGraph stdio server once the index is usable."""

        workspace = Path(config.workspace_path)
        if not _ensure_codegraph_index(
            config,
            workspace,
            emit_event=emit_event,
        ):
            return []
        return [
            {
                "name": CODEGRAPH_SERVER_NAME,
                "transport": "stdio",
                "endpoint": "",
                "config": {
                    "command": config.codegraph_command,
                    "args": ["serve", "--mcp", "--path", str(workspace)],
                },
                "load_config": {},
            }
        ]


def _ensure_codegraph_index(config, workspace, emit_event=None):
    """Build the workspace CodeGraph index once, guarded by a lock."""

    index_dir = workspace / CODEGRAPH_INDEX_DIR
    if index_dir.is_dir():
        return True
    if not _has_indexable_code(workspace):
        return False
    lock_dir = workspace / ".sourcelens"
    lock_path = lock_dir / CODEGRAPH_INIT_LOCK
    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
        timeout_s = int(getattr(config, "codegraph_init_timeout_s", 300))
        with open(lock_path, "a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                if index_dir.is_dir():
                    return True
                subprocess.run(
                    [
                        str(config.codegraph_command),
                        "init",
                        str(workspace),
                    ],
                    timeout=timeout_s,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except Exception as exc:
        if emit_event is not None:
            emit_event(
                "codegraph.init.failed",
                {"reason": type(exc).__name__},
            )
        return False
    return index_dir.is_dir()


def _has_indexable_code(workspace):
    """Return whether the workspace has source files CodeGraph indexes."""

    if not workspace.is_dir():
        return False
    try:
        for path in workspace.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower() in CODEGRAPH_CODE_EXTENSIONS
            ):
                return True
    except OSError:
        return False
    return False
