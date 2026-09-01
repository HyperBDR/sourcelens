from threading import Event

from django.test import SimpleTestCase
from lens.plugins.providers.base import (
    DatasourceProviderError,
    PluginRequestContext,
)


class PluginRequestContextTests(SimpleTestCase):
    """Verify shared Provider concurrency and failure semantics."""

    def test_parallel_map_returns_successes_and_structured_warnings(self):
        context = PluginRequestContext(max_concurrency=2, max_retries=0)

        def operation(value):
            if value == "failed":
                raise DatasourceProviderError("GITHUB_NOT_FOUND")
            return value.upper()

        results, warnings = context.parallel_map(
            ["first", "failed", "last"],
            operation,
            "repository",
        )

        self.assertEqual(results, ["FIRST", "LAST"])
        self.assertEqual(
            warnings,
            [
                {
                    "resource": "failed",
                    "label": "repository",
                    "code": "GITHUB_NOT_FOUND",
                }
            ],
        )

    def test_retry_uses_provider_retry_after_before_succeeding(self):
        context = PluginRequestContext(
            max_retries=1,
            backoff_seconds=0,
        )
        attempts = []

        def operation():
            attempts.append(1)
            if len(attempts) == 1:
                raise DatasourceProviderError(
                    "JIRA_RATE_LIMITED",
                    retry_after=0,
                )
            return "ok"

        self.assertEqual(context.run(operation), "ok")
        self.assertEqual(len(attempts), 2)

    def test_cancelled_context_stops_before_request(self):
        event = Event()
        event.set()
        context = PluginRequestContext(cancel_event=event)

        with self.assertRaisesMessage(
            DatasourceProviderError,
            "PLUGIN_REQUEST_CANCELLED",
        ):
            context.run(lambda: "must-not-run")
