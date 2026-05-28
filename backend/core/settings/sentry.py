"""
Sentry error tracking configuration.

Doc: https://docs.sentry.io/platforms/python/
"""

import os

# ============================
# Sentry Configuration
# ============================

# Enable Sentry error tracking
# Default: disabled (empty string or "false" disables it)
SENTRY_ENABLED = os.getenv("SENTRY_ENABLED", "").lower() in ("1", "true", "yes")

# Sentry DSN (Data Source Name)
# Get from: https://sentry.oneprocloud.com/settings/<org>/projects/<project>/keys/
SENTRY_DSN = os.getenv("SENTRY_DSN", "")

# Environment name (production, staging, development)
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "production")

# Release version (typically git commit hash or version number)
SENTRY_RELEASE = os.getenv("SENTRY_RELEASE", "")

# Sample rate for error capturing (0.0 to 1.0)
# 1.0 = capture all errors
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

# Enable performance monitoring
SENTRY_PROFILING_SAMPLE_RATE = float(os.getenv("SENTRY_PROFILING_SAMPLE_RATE", "0.05"))

# Include personal identifiable information
SENTRY_SEND_DEFAULT_PII = os.getenv("SENTRY_SEND_DEFAULT_PII", "false").lower() in (
    "1",
    "true",
    "yes",
)
