import logging
import ssl
from types import SimpleNamespace

from lensnode.tls import create_ssl_context
from lensnode.tls import warn_if_verification_disabled


def test_default_context_verifies_certificate_and_hostname():
    context = create_ssl_context()

    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_custom_ca_is_loaded_with_verification_enabled(monkeypatch):
    expected = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    calls = []

    def fake_create_default_context(*, cafile=None):
        calls.append(cafile)
        return expected

    monkeypatch.setattr(
        ssl,
        "create_default_context",
        fake_create_default_context,
    )

    context = create_ssl_context(ca_file="/etc/sourcelens/ca.crt")

    assert context is expected
    assert calls == ["/etc/sourcelens/ca.crt"]


def test_skip_verify_disables_certificate_and_hostname_checks():
    context = create_ssl_context(
        skip_verify=True,
        ca_file="/ignored/ca.crt",
    )

    assert context.verify_mode == ssl.CERT_NONE
    assert context.check_hostname is False


def test_skip_verify_logs_one_startup_warning(caplog):
    config = SimpleNamespace(
        tls_skip_verify=True,
        tls_ca_file="/ignored/ca.crt",
    )

    with caplog.at_level(logging.WARNING, logger="lensnode"):
        warn_if_verification_disabled(config)

    assert len(caplog.records) == 1
    assert "development only" in caplog.text
    assert "LENSNODE_TLS_CA_FILE is ignored" in caplog.text


def test_secure_tls_configuration_does_not_warn(caplog):
    config = SimpleNamespace(
        tls_skip_verify=False,
        tls_ca_file="/etc/sourcelens/ca.crt",
    )

    with caplog.at_level(logging.WARNING, logger="lensnode"):
        warn_if_verification_disabled(config)

    assert caplog.records == []
