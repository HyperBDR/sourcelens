"""Tests for optional Langfuse observability initialization."""

import logging
import os
import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from core.apps import configure_langfuse


class ConfigureLangfuseTests(TestCase):
    """Verify runtime opt-in behavior for the LiteLLM integration."""

    def test_runtime_dependencies_support_langfuse_otel(self):
        """Keep the installed OpenTelemetry API compatible with LiteLLM."""

        from litellm.integrations.langfuse.langfuse_otel import (
            LangfuseOtelLogger,
        )

        self.assertIsNotNone(LangfuseOtelLogger)

    @patch.dict(
        os.environ,
        {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""},
    )
    def test_disabled_without_credentials(self):
        """Leave LiteLLM unloaded when Langfuse credentials are absent."""

        with patch.dict(sys.modules, {"litellm": None}):
            self.assertFalse(configure_langfuse())

    @patch.dict(
        os.environ,
        {
            "LANGFUSE_PUBLIC_KEY": "public-key",
            "LANGFUSE_SECRET_KEY": "secret-key",
        },
    )
    def test_preserves_existing_callbacks(self):
        """Append Langfuse without replacing existing callbacks."""

        existing_callback = object()
        litellm = SimpleNamespace(callbacks=[existing_callback])

        with patch.dict(sys.modules, {"litellm": litellm}):
            self.assertTrue(configure_langfuse())

        self.assertEqual(
            litellm.callbacks,
            [existing_callback, "langfuse_otel"],
        )

    @patch.dict(
        os.environ,
        {
            "LANGFUSE_PUBLIC_KEY": "public-key",
            "LANGFUSE_SECRET_KEY": "secret-key",
        },
    )
    def test_does_not_duplicate_callback(self):
        """Keep repeated Django initialization idempotent."""

        litellm = SimpleNamespace(callbacks=["langfuse_otel"])

        with patch.dict(sys.modules, {"litellm": litellm}):
            self.assertTrue(configure_langfuse())
            self.assertTrue(configure_langfuse())

        self.assertEqual(litellm.callbacks, ["langfuse_otel"])

    @patch.dict(
        os.environ,
        {"LANGFUSE_PUBLIC_KEY": "public-key", "LANGFUSE_SECRET_KEY": ""},
    )
    def test_warns_for_partial_credentials(self):
        """Disable Langfuse and warn for an incomplete configuration."""

        litellm = SimpleNamespace(callbacks=[])

        with patch.dict(sys.modules, {"litellm": litellm}):
            with self.assertLogs("core.apps", logging.WARNING) as logs:
                self.assertFalse(configure_langfuse())

        self.assertEqual(litellm.callbacks, [])
        self.assertIn("incomplete", " ".join(logs.output).lower())
        self.assertNotIn("public-key", " ".join(logs.output))
