"""Host-controlled HTTP clients for trusted Plugin runtimes."""

import threading
from contextlib import contextmanager
from urllib.parse import urlsplit

import httpx


class PluginHttpClientError(ValueError):
    """Raised when a Plugin HTTP request violates the host policy."""


class PluginHttpClientPool:
    """Reuse HTTP/2 clients within one Plugin Connection and origin."""

    def __init__(
        self,
        *,
        timeout,
        verify,
        max_connections=100,
        max_keepalive_connections=20,
        keepalive_expiry=60.0,
        client_factory=httpx.Client,
    ):
        self._timeout = timeout
        self._verify = verify
        self._limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            keepalive_expiry=keepalive_expiry,
        )
        self._client_factory = client_factory
        self._clients = {}
        self._closed = False
        self._lock = threading.Lock()

    def bind(self, plugin_key, connection_uuid, origins):
        """Return a request facade restricted to declared HTTPS origins."""

        plugin_key = str(plugin_key or "").strip()
        connection_uuid = str(connection_uuid or "").strip()
        if not plugin_key or not connection_uuid:
            raise PluginHttpClientError("PLUGIN_HTTP_SCOPE_INVALID")
        normalized = frozenset(_normalize_origin(item) for item in origins)
        if not normalized:
            raise PluginHttpClientError("PLUGIN_HTTP_ORIGIN_REQUIRED")
        with self._lock:
            if self._closed:
                raise PluginHttpClientError("PLUGIN_HTTP_POOL_CLOSED")
        return PluginHttpClient(
            self,
            plugin_key,
            connection_uuid,
            normalized,
        )

    def _client_for(self, plugin_key, connection_uuid, origin):
        cache_key = (plugin_key, connection_uuid, origin)
        with self._lock:
            if self._closed:
                raise PluginHttpClientError("PLUGIN_HTTP_POOL_CLOSED")
            client = self._clients.get(cache_key)
            if client is None:
                client = self._client_factory(
                    timeout=self._timeout,
                    verify=self._verify,
                    follow_redirects=False,
                    http2=True,
                    limits=self._limits,
                )
                self._clients[cache_key] = client
            return client

    def close(self):
        """Close all pooled clients exactly once."""

        with self._lock:
            if self._closed:
                return
            self._closed = True
            clients = list(self._clients.values())
            self._clients.clear()
        for client in clients:
            client.close()

    @property
    def is_closed(self):
        """Return whether the pool has stopped accepting requests."""

        with self._lock:
            return self._closed


class PluginHttpClient:
    """Minimal streaming HTTP interface exposed to one Plugin Connection."""

    def __init__(self, pool, plugin_key, connection_uuid, origins):
        self._pool = pool
        self._plugin_key = plugin_key
        self._connection_uuid = connection_uuid
        self._origins = origins

    @contextmanager
    def stream(self, method, url, **kwargs):
        """Stream one bounded read request within the declared origins."""

        method = str(method or "").upper()
        if method not in {"GET", "HEAD"}:
            raise PluginHttpClientError("PLUGIN_HTTP_METHOD_REJECTED")
        unsupported = set(kwargs) - {
            "params",
            "headers",
            "follow_redirects",
            "timeout",
        }
        if unsupported:
            raise PluginHttpClientError("PLUGIN_HTTP_OPTIONS_REJECTED")
        if "timeout" in kwargs and (
            not isinstance(kwargs["timeout"], (int, float))
            or isinstance(kwargs["timeout"], bool)
            or kwargs["timeout"] <= 0
        ):
            raise PluginHttpClientError("PLUGIN_HTTP_TIMEOUT_INVALID")
        origin = _request_origin(url)
        if origin not in self._origins:
            raise PluginHttpClientError("PLUGIN_HTTP_ORIGIN_REJECTED")
        if kwargs.get("follow_redirects") not in {None, False}:
            raise PluginHttpClientError("PLUGIN_HTTP_REDIRECT_REJECTED")
        headers = kwargs.get("headers") or {}
        if any(str(key).lower() == "host" for key in headers):
            raise PluginHttpClientError("PLUGIN_HTTP_HOST_REJECTED")
        kwargs["follow_redirects"] = False
        client = self._pool._client_for(
            self._plugin_key,
            self._connection_uuid,
            origin,
        )
        with client.stream(method, url, **kwargs) as response:
            yield response


def _normalize_origin(value):
    """Return a canonical HTTPS origin without credentials or path."""

    parsed = _safe_split(value)
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise PluginHttpClientError("PLUGIN_HTTP_ORIGIN_INVALID")
    return _parsed_origin(parsed)


def _request_origin(value):
    """Return the canonical origin for one absolute request URL."""

    parsed = _safe_split(value)
    if parsed.fragment:
        raise PluginHttpClientError("PLUGIN_HTTP_URL_INVALID")
    return _parsed_origin(parsed)


def _safe_split(value):
    try:
        parsed = urlsplit(str(value or "").strip())
        parsed.port
    except ValueError as exc:
        raise PluginHttpClientError("PLUGIN_HTTP_URL_INVALID") from exc
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise PluginHttpClientError("PLUGIN_HTTP_URL_INVALID")
    return parsed


def _parsed_origin(parsed):
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    port_suffix = f":{port}" if port not in {None, 443} else ""
    return f"https://{host}{port_suffix}"
