from contextlib import contextmanager

import pytest

from lens.plugins.http import PluginHttpClientError, PluginHttpClientPool


class FakeHttpClient:
    """Record requests made through one host-managed HTTP client."""

    def __init__(self, **options):
        self.options = options
        self.requests = []
        self.is_closed = False

    @contextmanager
    def stream(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        yield object()

    def close(self):
        self.is_closed = True


def test_pool_reuses_negotiated_http2_client_for_one_connection():
    clients = []

    def factory(**options):
        client = FakeHttpClient(**options)
        clients.append(client)
        return client

    pool = PluginHttpClientPool(client_factory=factory)
    first = pool.bind("github", "connection-1", ["https://api.github.com"])
    second = pool.bind("github", "connection-1", ["https://api.github.com"])

    with first.stream("GET", "https://api.github.com/user"):
        pass
    with second.stream("GET", "https://api.github.com/repos"):
        pass

    assert len(clients) == 1
    assert clients[0].options["http2"] is True
    assert clients[0].options["follow_redirects"] is False
    assert len(clients[0].requests) == 2


def test_pool_isolates_connection_clients_on_the_same_origin():
    clients = []

    def factory(**options):
        client = FakeHttpClient(**options)
        clients.append(client)
        return client

    pool = PluginHttpClientPool(client_factory=factory)
    first = pool.bind("github", "connection-1", ["https://api.github.com"])
    second = pool.bind("github", "connection-2", ["https://api.github.com"])

    with first.stream("GET", "https://api.github.com/user"):
        pass
    with second.stream("GET", "https://api.github.com/user"):
        pass

    assert len(clients) == 2


def test_temporary_client_is_closed_without_entering_the_pool():
    clients = []

    def factory(**options):
        client = FakeHttpClient(**options)
        clients.append(client)
        return client

    pool = PluginHttpClientPool(client_factory=factory)

    with pool.temporary("github", ["https://api.github.com"]) as client:
        with client.stream("GET", "https://api.github.com/user"):
            pass
        assert clients[0].is_closed is False

    assert clients[0].is_closed is True
    assert pool.client_count == 0


@pytest.mark.parametrize(
    ("method", "url", "kwargs"),
    [
        ("POST", "https://api.github.com/user", {}),
        ("GET", "http://api.github.com/user", {}),
        ("GET", "https://other.example/user", {}),
        ("GET", "https://user:pass@api.github.com/user", {}),
        ("GET", "https://api.github.com/user", {"follow_redirects": True}),
        ("GET", "https://api.github.com/user", {"cookies": {}}),
        (
            "GET",
            "https://api.github.com/user",
            {"headers": {"Host": "other.example"}},
        ),
    ],
)
def test_bound_client_rejects_requests_outside_host_policy(
    method,
    url,
    kwargs,
):
    pool = PluginHttpClientPool()
    client = pool.bind(
        "github",
        "connection-1",
        ["https://api.github.com"],
    )

    with pytest.raises(PluginHttpClientError):
        with client.stream(method, url, **kwargs):
            pass


def test_pool_closes_created_clients_and_rejects_new_bindings():
    clients = []

    def factory(**options):
        client = FakeHttpClient(**options)
        clients.append(client)
        return client

    pool = PluginHttpClientPool(client_factory=factory)
    client = pool.bind("github", "connection-1", ["https://api.github.com"])
    with client.stream("GET", "https://api.github.com/user"):
        pass

    pool.close()

    assert clients[0].is_closed is True
    with pytest.raises(PluginHttpClientError):
        pool.bind("github", "connection-1", ["https://api.github.com"])
