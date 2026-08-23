from types import SimpleNamespace

from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.local_shell import LocalShellBackend

from lensnode.agent_runtime.runtime import _build_execution_backend


def test_trusted_container_backend_executes_commands_in_workspace(tmp_path):
    backend = _build_execution_backend(
        SimpleNamespace(execution_backend="trusted_container"),
        tmp_path,
    )

    assert isinstance(backend, LocalShellBackend)
    result = backend.execute("printf 'hello'; printf ' error' >&2")

    assert result.exit_code == 0
    assert "hello" in result.output
    assert "error" in result.output


def test_filesystem_backend_remains_available_as_explicit_fallback(tmp_path):
    backend = _build_execution_backend(
        SimpleNamespace(execution_backend="filesystem"),
        tmp_path,
    )

    assert isinstance(backend, FilesystemBackend)
    assert not isinstance(backend, LocalShellBackend)


def test_execution_backend_rejects_unknown_mode(tmp_path):
    try:
        _build_execution_backend(
            SimpleNamespace(execution_backend="unknown"),
            tmp_path,
        )
    except ValueError as exc:
        assert "LENSNODE_EXECUTION_BACKEND" in str(exc)
    else:
        raise AssertionError("Unknown execution backend should fail fast")
