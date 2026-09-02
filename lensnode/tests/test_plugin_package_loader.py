from pathlib import Path

import pytest

from lensnode.plugin_package_loader import (
    PluginPackageLoadError,
    load_runtime_contract,
)


RUNTIME_SOURCE = '''
PLUGIN_API_VERSION = 1
PLUGIN_KEY = "example"
PLUGIN_VERSION = "1.2.3"

def build_tool(definition, executor):
    return definition, executor

def execute_tool(tool_key, client, arguments, secret, endpoint, config):
    return {"ok": True}

def build_datasource_command(snapshot, material, trigger):
    return {"source_type": "git"}
'''


def _package(tmp_path, source=RUNTIME_SOURCE):
    package = tmp_path / "example" / "1.2.3"
    package.mkdir(parents=True)
    (package / "runtime.py").write_text(source, encoding="utf-8")
    return package


def test_loads_exact_runtime_contract_from_configured_root(tmp_path):
    _package(tmp_path)

    contract = load_runtime_contract(
        "example",
        "1.2.3",
        roots=[tmp_path],
    )

    assert contract.plugin_key == "example"
    assert contract.plugin_version == "1.2.3"
    assert callable(contract.build_tool)
    assert callable(contract.execute_tool)
    assert callable(contract.build_datasource_command)


def test_rejects_runtime_identity_mismatch(tmp_path):
    _package(tmp_path, RUNTIME_SOURCE.replace('"example"', '"other"'))

    with pytest.raises(PluginPackageLoadError):
        load_runtime_contract("example", "1.2.3", roots=[tmp_path])


def test_rejects_symlinked_runtime_entrypoint(tmp_path):
    package = _package(tmp_path)
    external = tmp_path / "external.py"
    external.write_text(RUNTIME_SOURCE, encoding="utf-8")
    (package / "runtime.py").unlink()
    (package / "runtime.py").symlink_to(external)

    with pytest.raises(PluginPackageLoadError):
        load_runtime_contract("example", "1.2.3", roots=[tmp_path])


def test_rejects_path_like_plugin_identity(tmp_path):
    with pytest.raises(PluginPackageLoadError):
        load_runtime_contract("../example", "1.2.3", roots=[tmp_path])


def test_requires_complete_runtime_contract(tmp_path):
    _package(tmp_path, RUNTIME_SOURCE.replace("def execute_tool", "def missing"))

    with pytest.raises(PluginPackageLoadError):
        load_runtime_contract("example", "1.2.3", roots=[tmp_path])
