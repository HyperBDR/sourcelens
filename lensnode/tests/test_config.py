import pytest

from lensnode.config import load_config


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("0", False),
        ("invalid", False),
    ],
)
def test_load_config_parses_tls_skip_verify(monkeypatch, value, expected):
    monkeypatch.setenv("LENSNODE_TLS_SKIP_VERIFY", value)

    config = load_config()

    assert config.tls_skip_verify is expected


def test_load_config_uses_secure_tls_defaults(monkeypatch):
    monkeypatch.delenv("LENSNODE_TLS_SKIP_VERIFY", raising=False)
    monkeypatch.delenv("LENSNODE_TLS_CA_FILE", raising=False)

    config = load_config()

    assert config.tls_skip_verify is False
    assert config.tls_ca_file is None


def test_load_config_reads_tls_ca_file(monkeypatch):
    monkeypatch.setenv("LENSNODE_TLS_CA_FILE", "/etc/sourcelens/ca.crt")

    config = load_config()

    assert config.tls_ca_file == "/etc/sourcelens/ca.crt"


def test_load_config_reads_run_token_budget(monkeypatch):
    monkeypatch.setenv("LENSNODE_TOKEN_BUDGET_MAX_TOKENS", "120000")
    monkeypatch.setenv("LENSNODE_TOKEN_BUDGET_WARN_RATIO", "0.75")

    config = load_config()

    assert config.token_budget_max_tokens == 120000
    assert config.token_budget_warn_ratio == 0.75
