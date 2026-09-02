"""Stable exceptions shared with trusted Plugin control packages."""


class ToolProviderError(ValueError):
    """Raised when a Tool request violates its Plugin contract."""
