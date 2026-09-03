"""Atlassian Jira Cloud datasource Provider implementation."""

import base64
import json
import re
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from lens.plugins.contracts import ToolProviderError
from lens.plugins.providers.base import (
    DatasourceProvider,
    DatasourceProviderError,
    PluginRequestContext,
    retry_after_seconds,
)

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PROJECT_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,19}$")
ALLOWED_CONFIG_KEYS = frozenset({"project", "max_issues"})
ALLOWED_SCOPE_KEYS = frozenset({"projects"})
JIRA_MAX_PROJECTS = 50
JIRA_MAX_ISSUES = 100
JIRA_DISCOVERY_WORKERS = 5
JIRA_TIMEOUT_SECONDS = 15
JIRA_MAX_RESPONSE_BYTES = 500_000

PLUGIN_API_VERSION = 1
PLUGIN_KEY = "jira"
PLUGIN_VERSION = "1.0.0"


class JiraDatasourceProvider(DatasourceProvider):
    """Validate read-only Jira Cloud project datasource selections."""

    key = "jira"

    def validate_datasource_source_type(self, source_type):
        """Bind Jira to its bounded Issue export runtime."""

        if source_type != "jira":
            raise DatasourceProviderError(
                "Jira datasource source type must be jira"
            )
        return source_type

    def validate_connection(self, endpoint, connection_config):
        """Accept an Atlassian Cloud site and non-secret account email."""

        _email(connection_config)
        return _endpoint(endpoint)

    def validate_connection_scope(self, connection_scope):
        """Normalize explicit Jira project keys for one Connection."""

        if not isinstance(connection_scope, dict):
            raise DatasourceProviderError("connection scope must be an object")
        if set(connection_scope).difference(ALLOWED_SCOPE_KEYS):
            raise DatasourceProviderError(
                "connection scope contains unsupported fields"
            )
        projects = connection_scope.get("projects")
        if not isinstance(projects, list) or not projects:
            raise DatasourceProviderError("connection scope requires projects")
        if len(projects) > JIRA_MAX_PROJECTS:
            raise DatasourceProviderError(
                "connection scope contains too many projects"
            )
        normalized = []
        identities = set()
        for value in projects:
            project = _project_key(value)
            if project not in identities:
                identities.add(project)
                normalized.append(project)
        return {"projects": normalized}

    def validate_live_connection(
        self,
        secret,
        endpoint="",
        connection_config=None,
        client=None,
        request_context=None,
    ):
        """Validate Jira Cloud API Token authentication."""

        base_url = self.validate_connection(endpoint, connection_config)
        headers = _headers(connection_config, secret)
        context = request_context or PluginRequestContext(
            timeout_seconds=JIRA_TIMEOUT_SECONDS,
        )
        with _JiraClient(client) as jira_client:
            payload = context.run(
                lambda: _jira_json(
                    jira_client,
                    base_url,
                    "/rest/api/3/myself",
                    headers,
                )
            )
        if not isinstance(payload, dict):
            raise DatasourceProviderError("JIRA_RESPONSE_INVALID")
        account_id = payload.get("accountId")
        display_name = payload.get("displayName")
        if not isinstance(account_id, str) or not account_id:
            raise DatasourceProviderError("JIRA_RESPONSE_INVALID")
        return {
            "account": {
                "account_id": account_id[:160],
                "display_name": (
                    display_name[:160]
                    if isinstance(display_name, str)
                    else ""
                ),
            }
        }

    def discover_resources(
        self,
        connection_scope,
        secret,
        endpoint="",
        connection_config=None,
        client=None,
        request_context=None,
    ):
        """Discover metadata only for explicitly approved Jira projects."""

        base_url = self.validate_connection(endpoint, connection_config)
        scope = self.validate_connection_scope(connection_scope)
        headers = _headers(connection_config, secret)
        context = request_context or PluginRequestContext(
            max_concurrency=JIRA_DISCOVERY_WORKERS,
            timeout_seconds=JIRA_TIMEOUT_SECONDS,
        )
        with _JiraClient(client) as jira_client:
            projects = scope["projects"]
            items, warnings = context.parallel_map(
                projects,
                lambda project: _project_resource(
                    jira_client,
                    base_url,
                    project,
                    headers,
                ),
                "project",
            )
        result = {"resources": {"projects": {"items": items}}}
        if warnings:
            result["warnings"] = warnings
        return result

    def validate_datasource_config(
        self,
        connection_scope,
        datasource_config,
    ):
        """Return one bounded project Issue export selection."""

        if not isinstance(datasource_config, dict):
            raise DatasourceProviderError(
                "datasource config must be an object"
            )
        if set(datasource_config).difference(ALLOWED_CONFIG_KEYS):
            raise DatasourceProviderError(
                "datasource config contains unsupported fields"
            )
        project = _project_key(datasource_config.get("project"))
        allowed = set(
            self.validate_connection_scope(connection_scope)["projects"]
        )
        if project not in allowed:
            raise DatasourceProviderError("project is outside connection scope")
        max_issues = datasource_config.get("max_issues", JIRA_MAX_ISSUES)
        if (
            isinstance(max_issues, bool)
            or not isinstance(max_issues, int)
            or max_issues < 1
            or max_issues > JIRA_MAX_ISSUES
        ):
            raise DatasourceProviderError("max_issues is invalid")
        return {"project": project, "max_issues": max_issues}


def _endpoint(value):
    """Return a safe Atlassian Cloud site endpoint."""

    parsed = urlsplit(str(value or "").strip())
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname.endswith(".atlassian.net")
        or hostname == "atlassian.net"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise DatasourceProviderError("Jira Cloud endpoint is invalid")
    return urlunsplit(("https", parsed.netloc, "", "", ""))


def _email(connection_config):
    """Return the bounded non-secret Jira account email."""

    if not isinstance(connection_config, dict) or set(
        connection_config
    ) != {"email"}:
        raise DatasourceProviderError(
            "Jira connection config requires only email"
        )
    email = connection_config.get("email")
    if (
        not isinstance(email, str)
        or len(email) > 254
        or not EMAIL_PATTERN.fullmatch(email.strip())
    ):
        raise DatasourceProviderError("Jira account email is invalid")
    return email.strip()


def _project_key(value):
    """Return one canonical Jira project key."""

    if not isinstance(value, str):
        raise DatasourceProviderError("project is required")
    project = value.strip().upper()
    if not PROJECT_PATTERN.fullmatch(project):
        raise DatasourceProviderError("Jira project key is invalid")
    return project


def _headers(connection_config, secret):
    """Build Jira Cloud Basic authentication without exposing raw values."""

    email = _email(connection_config)
    if not isinstance(secret, str) or not secret:
        raise DatasourceProviderError("JIRA_SECRET_UNAVAILABLE")
    credential = base64.b64encode(
        f"{email}:{secret}".encode("utf-8")
    ).decode("ascii")
    return {
        "Accept": "application/json",
        "Authorization": f"Basic {credential}",
        "User-Agent": "SourceLens-Control-Plane",
    }


class _JiraClient:
    """Require the HTTP client injected by the SourceLens host."""

    def __init__(self, client):
        self.client = client

    def __enter__(self):
        if self.client is None:
            raise DatasourceProviderError(
                "PLUGIN_HTTP_CLIENT_REQUIRED"
            )
        return self.client

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def _project_resource(client, endpoint, project, headers):
    """Return bounded display metadata for one approved Jira project."""

    payload = _jira_json(
        client,
        endpoint,
        f"/rest/api/3/project/{quote(project, safe='')}",
        headers,
    )
    if not isinstance(payload, dict):
        raise DatasourceProviderError("JIRA_RESPONSE_INVALID")
    key = payload.get("key")
    name = payload.get("name")
    if (
        not isinstance(key, str)
        or key.upper() != project
        or not isinstance(name, str)
        or not name
    ):
        raise DatasourceProviderError("JIRA_RESPONSE_INVALID")
    return {
        "value": project,
        "label": f"{project} · {name[:160]}",
        "metadata": {"name": name[:160]},
    }


def _jira_json(client, endpoint, path, headers, params=None):
    """Read bounded JSON from one validated Atlassian Cloud site."""

    try:
        with client.stream(
            "GET",
            f"{endpoint}{path}",
            params=params,
            headers=headers,
            follow_redirects=False,
        ) as response:
            if response.is_redirect:
                raise DatasourceProviderError("JIRA_REDIRECT_REJECTED")
            if response.status_code >= 400:
                retry_after = (
                    retry_after_seconds(response.headers.get("Retry-After"))
                    if response.status_code == 429
                    else None
                )
                raise DatasourceProviderError(
                    _jira_error(response.status_code),
                    retry_after=retry_after,
                )
            body = bytearray()
            for chunk in response.iter_bytes():
                if len(body) + len(chunk) > JIRA_MAX_RESPONSE_BYTES:
                    raise DatasourceProviderError("JIRA_RESPONSE_TOO_LARGE")
                body.extend(chunk)
    except DatasourceProviderError:
        raise
    except httpx.HTTPError as exc:
        raise DatasourceProviderError("JIRA_REQUEST_FAILED") from exc
    try:
        return json.loads(body)
    except (UnicodeDecodeError, ValueError) as exc:
        raise DatasourceProviderError("JIRA_RESPONSE_INVALID") from exc


def _jira_error(status_code):
    """Map Jira statuses without exposing response bodies."""

    if status_code == 404:
        return "JIRA_NOT_FOUND"
    if status_code in {401, 403}:
        return "JIRA_ACCESS_DENIED"
    if status_code == 429:
        return "JIRA_RATE_LIMITED"
    return "JIRA_REQUEST_FAILED"


class JiraToolProvider:
    """Validate bounded read-only Jira Cloud Tool requests."""

    key = "jira"

    def validate_request(self, endpoint, allowed_scope, tool_key, arguments):
        """Return canonical endpoint and authorized arguments."""

        try:
            endpoint = _endpoint(endpoint)
            allowed = set(
                JiraDatasourceProvider()
                .validate_connection_scope(allowed_scope)["projects"]
            )
        except DatasourceProviderError as exc:
            raise ToolProviderError(str(exc)) from exc
        if not isinstance(arguments, dict):
            raise ToolProviderError("tool arguments must be an object")
        if tool_key == "jira_get_issue":
            issue_key = _issue_key(arguments.get("issue_key"))
            if issue_key.rsplit("-", 1)[0] not in allowed:
                raise ToolProviderError("issue is outside connection scope")
            return endpoint, {"issue_key": issue_key}
        if tool_key == "jira_search_issues":
            try:
                project = _project_key(arguments.get("project"))
            except DatasourceProviderError as exc:
                raise ToolProviderError(str(exc)) from exc
            if project not in allowed:
                raise ToolProviderError("project is outside connection scope")
            return endpoint, {
                "project": project,
                "query": _tool_text(
                    arguments.get("query"),
                    "query",
                    500,
                    required=True,
                ),
                "max_results": _tool_max_results(
                    arguments.get("max_results")
                ),
            }
        raise ToolProviderError("tool is unsupported")


def _tool_text(value, field, limit, required=False):
    """Return bounded Tool text without control characters."""

    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ToolProviderError(f"{field} must be a string")
    text = value.strip()
    if (required and not text) or len(text) > limit or any(
        ord(character) < 32 for character in text
    ):
        raise ToolProviderError(f"{field} is invalid")
    return text


def _issue_key(value):
    """Return one bounded canonical Jira Issue key."""

    text = _tool_text(value, "issue_key", 40, required=True).upper()
    parts = text.rsplit("-", 1)
    if len(parts) != 2 or not parts[1].isdigit() or int(parts[1]) < 1:
        raise ToolProviderError("issue_key is invalid")
    try:
        _project_key(parts[0])
    except DatasourceProviderError as exc:
        raise ToolProviderError("issue_key is invalid") from exc
    return text


def _tool_max_results(value):
    """Return one bounded search result count."""

    if value is None:
        return 10
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 1
        or value > 20
    ):
        raise ToolProviderError("max_results must be between 1 and 20")
    return value


DATASOURCE_PROVIDER = JiraDatasourceProvider()
TOOL_PROVIDER = JiraToolProvider()
