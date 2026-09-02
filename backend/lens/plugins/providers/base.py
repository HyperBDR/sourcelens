"""Stable contracts for Plugin datasource implementations."""

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from math import isfinite
from threading import Event
from time import monotonic, sleep


class DatasourceProviderError(ValueError):
    """Raised when datasource configuration violates a provider contract."""

    def __init__(self, code, retry_after=None):
        super().__init__(code)
        self.code = str(code)
        self.retry_after = retry_after


def retry_after_seconds(value, maximum=60.0):
    """Parse a bounded numeric Retry-After header for Provider backoff."""

    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(seconds) or seconds < 0:
        return None
    return min(seconds, maximum)


@dataclass
class PluginRequestContext:
    """Bound one Provider operation by concurrency and cancellation limits."""

    max_concurrency: int = 5
    timeout_seconds: float = 15.0
    deadline_seconds: float | None = None
    max_retries: int = 2
    backoff_seconds: float = 0.25
    cancel_event: Event | None = None

    def __post_init__(self):
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.deadline_seconds is not None and self.deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.cancel_event = self.cancel_event or Event()
        self._deadline = (
            monotonic() + self.deadline_seconds
            if self.deadline_seconds is not None
            else None
        )

    def check(self):
        """Raise a stable error when this operation cannot continue."""

        if self.cancel_event.is_set():
            raise DatasourceProviderError("PLUGIN_REQUEST_CANCELLED")
        if self._deadline is not None and monotonic() >= self._deadline:
            raise DatasourceProviderError("PLUGIN_REQUEST_DEADLINE_EXCEEDED")

    def run(self, operation):
        """Run one operation with bounded retries and interruptible backoff."""

        for attempt in range(self.max_retries + 1):
            self.check()
            try:
                return operation()
            except DatasourceProviderError as exc:
                retryable = exc.code.endswith(
                    ("_RATE_LIMITED", "_REQUEST_FAILED")
                )
                if not retryable or attempt >= self.max_retries:
                    raise
                delay = exc.retry_after
                if not isinstance(delay, (int, float)) or delay < 0:
                    delay = self.backoff_seconds * (2**attempt)
                self._sleep(delay)

        raise DatasourceProviderError("PLUGIN_REQUEST_FAILED")

    def parallel_map(self, values, operation, resource_label):
        """Run requests concurrently and retain partial failures."""

        values = list(values)
        if not values:
            return [], []
        worker_count = min(self.max_concurrency, len(values))
        results = []
        warnings = []
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(self.run, lambda value=value: operation(value))
                for value in values
            ]
            for value, future in zip(values, futures):
                try:
                    results.append(future.result())
                except DatasourceProviderError as exc:
                    warnings.append(
                        {
                            "resource": str(value),
                            "label": resource_label,
                            "code": exc.code,
                        }
                    )
        return results, warnings

    def _sleep(self, delay):
        """Sleep without making cancellation or deadline unresponsive."""

        end = monotonic() + max(0.0, float(delay))
        while True:
            self.check()
            remaining = end - monotonic()
            if remaining <= 0:
                return
            sleep(min(remaining, 0.05))


class DatasourceProvider(ABC):
    """Validate and normalize datasource-specific resource configuration."""

    key = ""

    def validate_connection(self, endpoint, connection_config):
        """Return a normalized endpoint accepted by this provider."""

        del connection_config
        value = str(endpoint or "").strip().rstrip("/")
        if not value:
            raise DatasourceProviderError("connection endpoint is required")
        return value

    def validate_connection_scope(self, connection_scope):
        """Return a normalized reusable authorization scope."""

        if not isinstance(connection_scope, dict):
            raise DatasourceProviderError("connection scope must be an object")
        return connection_scope

    def validate_live_connection(
        self,
        secret,
        endpoint="",
        connection_config=None,
        client=None,
        request_context=None,
    ):
        """Validate stored authentication against the remote provider."""

        del secret, endpoint, connection_config, client, request_context
        raise DatasourceProviderError("PROVIDER_VALIDATION_UNSUPPORTED")

    def discover_resources(
        self,
        connection_scope,
        secret,
        endpoint="",
        connection_config=None,
        client=None,
        request_context=None,
    ):
        """Return resources visible inside an approved connection scope."""

        del (
            connection_scope,
            secret,
            endpoint,
            connection_config,
            client,
            request_context,
        )
        raise DatasourceProviderError("PROVIDER_DISCOVERY_UNSUPPORTED")

    def discover_connection_resources(
        self,
        secret,
        endpoint="",
        connection_config=None,
        query="",
        cursor="",
        limit=50,
        client=None,
        request_context=None,
    ):
        """Return bounded resources before a Connection is saved."""

        del (
            secret,
            endpoint,
            connection_config,
            query,
            cursor,
            limit,
            client,
            request_context,
        )
        raise DatasourceProviderError(
            "PROVIDER_CONNECTION_DISCOVERY_UNSUPPORTED"
        )

    def validate_datasource_source_type(self, source_type):
        """Reject datasource kinds unsupported by this provider."""

        value = str(source_type or "").strip()
        if not value:
            raise DatasourceProviderError("datasource source type is required")
        return value

    @abstractmethod
    def validate_datasource_config(self, connection_scope, datasource_config):
        """Return normalized config that remains within connection scope."""
