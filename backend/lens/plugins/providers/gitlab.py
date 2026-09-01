"""GitLab implementation of the generic datasource Provider contract."""

import json
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from .base import (
    DatasourceProvider,
    DatasourceProviderError,
    PluginRequestContext,
    retry_after_seconds,
)

SENSITIVE_CONFIG_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "credential",
        "credentials",
        "password",
        "secret",
        "token",
    }
)
ALLOWED_CONFIG_KEYS = frozenset({"project", "branch", "directory"})
ALLOWED_SCOPE_KEYS = frozenset({"projects"})
GITLAB_MAX_PROJECTS = 50
GITLAB_MAX_BRANCHES = 100
GITLAB_DISCOVERY_WORKERS = 5
GITLAB_TIMEOUT_SECONDS = 15
GITLAB_MAX_RESPONSE_BYTES = 500_000
GITLAB_MAX_BRANCH_LENGTH = 255
GITLAB_MAX_DIRECTORY_LENGTH = 1000


class GitLabDatasourceProvider(DatasourceProvider):
    """Validate read-only GitLab project datasource selections."""

    key = "gitlab"

    def validate_datasource_source_type(self, source_type):
        """Bind the GitLab Provider to the existing Git datasource runtime."""

        if source_type != "git":
            raise DatasourceProviderError(
                "GitLab datasource source type must be git"
            )
        return source_type

    def validate_connection(self, endpoint, connection_config):
        """Accept a root HTTPS GitLab endpoint without embedded authority."""

        if connection_config not in ({}, None):
            raise DatasourceProviderError(
                "GitLab connection config contains unsupported fields"
            )
        return _endpoint(endpoint)

    def validate_connection_scope(self, connection_scope):
        """Normalize the explicit project allowlist for one Connection."""

        if not isinstance(connection_scope, dict):
            raise DatasourceProviderError("connection scope must be an object")
        if set(connection_scope).difference(ALLOWED_SCOPE_KEYS):
            raise DatasourceProviderError(
                "connection scope contains unsupported fields"
            )
        projects = connection_scope.get("projects")
        if not isinstance(projects, list) or not projects:
            raise DatasourceProviderError("connection scope requires projects")
        if len(projects) > GITLAB_MAX_PROJECTS:
            raise DatasourceProviderError(
                "connection scope contains too many projects"
            )
        normalized = []
        identities = set()
        for value in projects:
            project = _project_name(value)
            identity = project.casefold()
            if identity not in identities:
                identities.add(identity)
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
        """Validate one access token against the selected GitLab host."""

        self.validate_connection(endpoint, connection_config)
        base_url = _endpoint(endpoint)
        token = _secret_value(secret)
        context = request_context or PluginRequestContext(
            timeout_seconds=GITLAB_TIMEOUT_SECONDS,
        )
        with _GitLabClient(client) as gitlab_client:
            payload = context.run(
                lambda: _gitlab_json(
                    gitlab_client,
                    base_url,
                    "/api/v4/user",
                    token,
                )
            )
        if not isinstance(payload, dict):
            raise DatasourceProviderError("GITLAB_RESPONSE_INVALID")
        username = payload.get("username")
        account_id = payload.get("id")
        if not isinstance(username, str) or not username:
            raise DatasourceProviderError("GITLAB_RESPONSE_INVALID")
        return {
            "account": {
                "id": account_id if isinstance(account_id, int) else None,
                "username": username[:160],
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
        """Discover bounded metadata for explicitly approved projects."""

        self.validate_connection(endpoint, connection_config)
        base_url = _endpoint(endpoint)
        scope = self.validate_connection_scope(connection_scope)
        token = _secret_value(secret)
        context = request_context or PluginRequestContext(
            max_concurrency=GITLAB_DISCOVERY_WORKERS,
            timeout_seconds=GITLAB_TIMEOUT_SECONDS,
        )
        with _GitLabClient(client) as gitlab_client:
            projects = scope["projects"]
            resources, warnings = context.parallel_map(
                projects,
                lambda project: _gitlab_project_resource(
                    gitlab_client,
                    base_url,
                    project,
                    token,
                ),
                "project",
            )
        result = {"resources": {"projects": {"items": resources}}}
        if warnings:
            result["warnings"] = warnings
        return result

    def validate_datasource_config(
        self,
        connection_scope,
        datasource_config,
    ):
        """Return a normalized project selection within configured scope."""

        if not isinstance(datasource_config, dict):
            raise DatasourceProviderError(
                "datasource config must be an object"
            )
        unknown_keys = set(datasource_config).difference(ALLOWED_CONFIG_KEYS)
        if unknown_keys.intersection(SENSITIVE_CONFIG_KEYS):
            raise DatasourceProviderError(
                "datasource config cannot contain credentials"
            )
        if unknown_keys:
            raise DatasourceProviderError(
                "datasource config contains unsupported fields"
            )
        project = _project_name(datasource_config.get("project"))
        allowed = {
            item.casefold()
            for item in self.validate_connection_scope(
                connection_scope
            )["projects"]
        }
        if project.casefold() not in allowed:
            raise DatasourceProviderError("project is outside connection scope")
        normalized = {"project": project}
        branch = _optional_text(
            datasource_config.get("branch"),
            "branch",
            GITLAB_MAX_BRANCH_LENGTH,
        )
        if branch:
            normalized["branch"] = branch
        directory = _directory_path(datasource_config.get("directory"))
        if directory:
            normalized["directory"] = directory
        return normalized


def _endpoint(value):
    """Return a safe root HTTPS GitLab endpoint."""

    parsed = urlsplit(str(value or "").strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise DatasourceProviderError("GitLab connection endpoint is invalid")
    return urlunsplit(("https", parsed.netloc, "", "", ""))


def _project_name(value):
    """Return a canonical GitLab namespace/project identity."""

    if not isinstance(value, str):
        raise DatasourceProviderError("project is required")
    project = value.strip().strip("/")
    parts = project.split("/")
    if (
        len(parts) < 2
        or len(parts) > 20
        or len(project) > 255
        or any(
            not part
            or len(part) > 100
            or part in {".", ".."}
            or not all(
                character.isalnum() or character in {"-", "_", "."}
                for character in part
            )
            for part in parts
        )
    ):
        raise DatasourceProviderError(
            "project must use namespace/project form"
        )
    return project


def _optional_text(value, field, limit):
    """Return bounded optional text without control characters."""

    if value is None:
        return ""
    if not isinstance(value, str):
        raise DatasourceProviderError(f"{field} must be a string")
    text = value.strip()
    if not text or len(text) > limit or any(ord(char) < 32 for char in text):
        raise DatasourceProviderError(f"{field} is invalid")
    return text


def _directory_path(value):
    """Return a safe project-relative directory path."""

    if value is None or value == "":
        return ""
    text = _optional_text(value, "directory", GITLAB_MAX_DIRECTORY_LENGTH)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        raise DatasourceProviderError("directory must be project-relative")
    normalized = path.as_posix()
    return "" if normalized == "." else normalized


class _GitLabClient:
    """Manage an optional injected HTTPX client without closing it."""

    def __init__(self, client):
        self.client = client
        self.owned = client is None

    def __enter__(self):
        if self.client is None:
            self.client = httpx.Client(
                timeout=GITLAB_TIMEOUT_SECONDS,
                follow_redirects=False,
            )
        return self.client

    def __exit__(self, exc_type, exc_value, traceback):
        if self.owned:
            self.client.close()


def _secret_value(value):
    """Return a non-empty secret without persisting or returning it."""

    if not isinstance(value, str) or not value:
        raise DatasourceProviderError("GITLAB_SECRET_UNAVAILABLE")
    return value


def _gitlab_project_resource(client, endpoint, project, token):
    """Return safe project and branch metadata for one allowed resource."""

    encoded = quote(project, safe="")
    metadata = _gitlab_json(
        client,
        endpoint,
        f"/api/v4/projects/{encoded}",
        token,
    )
    branches = _gitlab_json(
        client,
        endpoint,
        f"/api/v4/projects/{encoded}/repository/branches",
        token,
        params={"per_page": GITLAB_MAX_BRANCHES, "page": 1},
    )
    if not isinstance(metadata, dict) or not isinstance(branches, list):
        raise DatasourceProviderError("GITLAB_RESPONSE_INVALID")
    full_name = metadata.get("path_with_namespace")
    default_branch = metadata.get("default_branch")
    visibility = metadata.get("visibility")
    if (
        not isinstance(full_name, str)
        or full_name.casefold() != project.casefold()
        or not isinstance(default_branch, str)
        or not isinstance(visibility, str)
    ):
        raise DatasourceProviderError("GITLAB_RESPONSE_INVALID")
    branch_names = []
    for item in branches[:GITLAB_MAX_BRANCHES]:
        name = item.get("name") if isinstance(item, dict) else None
        if isinstance(name, str) and name:
            branch_names.append(name[:255])
    return {
        "value": full_name[:255],
        "label": full_name[:255],
        "metadata": {
            "default_branch": default_branch[:255],
            "visibility": visibility[:32],
        },
        "options": {
            "branches": [
                {"value": name, "label": name} for name in branch_names
            ]
        },
    }


def _gitlab_json(client, endpoint, path, token, params=None):
    """Read bounded JSON from the validated GitLab endpoint."""

    try:
        with client.stream(
            "GET",
            f"{endpoint}{path}",
            params=params,
            headers={
                "Accept": "application/json",
                "PRIVATE-TOKEN": token,
                "User-Agent": "SourceLens-Control-Plane",
            },
            follow_redirects=False,
        ) as response:
            if response.is_redirect:
                raise DatasourceProviderError("GITLAB_REDIRECT_REJECTED")
            if response.status_code >= 400:
                retry_after = (
                    retry_after_seconds(response.headers.get("Retry-After"))
                    if response.status_code == 429
                    else None
                )
                raise DatasourceProviderError(
                    _gitlab_error(response.status_code),
                    retry_after=retry_after,
                )
            body = bytearray()
            for chunk in response.iter_bytes():
                if len(body) + len(chunk) > GITLAB_MAX_RESPONSE_BYTES:
                    raise DatasourceProviderError(
                        "GITLAB_RESPONSE_TOO_LARGE"
                    )
                body.extend(chunk)
    except DatasourceProviderError:
        raise
    except httpx.HTTPError as exc:
        raise DatasourceProviderError("GITLAB_REQUEST_FAILED") from exc
    try:
        return json.loads(body)
    except (UnicodeDecodeError, ValueError) as exc:
        raise DatasourceProviderError("GITLAB_RESPONSE_INVALID") from exc


def _gitlab_error(status_code):
    """Map GitLab statuses without exposing third-party response bodies."""

    if status_code == 404:
        return "GITLAB_NOT_FOUND"
    if status_code in {401, 403}:
        return "GITLAB_ACCESS_DENIED"
    if status_code == 429:
        return "GITLAB_RATE_LIMITED"
    return "GITLAB_REQUEST_FAILED"
