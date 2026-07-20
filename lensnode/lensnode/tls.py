import logging
import ssl


def create_ssl_context(skip_verify=False, ca_file=None):
    """Create the TLS context used for SourceLens connections."""

    if skip_verify:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    return ssl.create_default_context(cafile=ca_file or None)


def create_config_ssl_context(config):
    """Create a SourceLens TLS context from LensNode configuration."""

    return create_ssl_context(
        skip_verify=getattr(config, "tls_skip_verify", False),
        ca_file=getattr(config, "tls_ca_file", None),
    )


def warn_if_verification_disabled(config, logger=None):
    """Warn once at startup when SourceLens TLS verification is disabled."""

    if not getattr(config, "tls_skip_verify", False):
        return
    target_logger = logger or logging.getLogger("lensnode")
    message = (
        "LensNode TLS certificate and hostname verification is disabled. "
        "LENSNODE_TLS_SKIP_VERIFY is intended for development only."
    )
    if getattr(config, "tls_ca_file", None):
        message += " LENSNODE_TLS_CA_FILE is ignored."
    target_logger.warning(message)
