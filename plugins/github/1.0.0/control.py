"""GitHub implementation of the generic datasource provider contract."""

import json
import re
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

import httpx

from lens.plugins.contracts import ToolProviderError
from lens.plugins.providers.base import (
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
ALLOWED_CONFIG_KEYS = frozenset({"repository", "branch", "directory"})
ALLOWED_SCOPE_KEYS = frozenset({"repositories"})
GITHUB_API_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
GITHUB_MAX_RESPONSE_BYTES = 500_000
GITHUB_MAX_REPOSITORIES = 50
GITHUB_MAX_BRANCHES = 100
GITHUB_DISCOVERY_WORKERS = 5
GITHUB_TIMEOUT_SECONDS = 15
GITHUB_MAX_BRANCH_LENGTH = 255
GITHUB_MAX_DIRECTORY_LENGTH = 1000
SEARCH_SCOPE_PATTERN = re.compile(r"(?:repo|org|user):", re.IGNORECASE)

PLUGIN_API_VERSION = 1
PLUGIN_KEY = "github"
PLUGIN_VERSION = "1.0.0"


class GitHubDatasourceProvider(DatasourceProvider):
    """Validate read-only GitHub repository datasource selections."""

    key = "github"

    def validate_datasource_source_type(self, source_type):
        """Bind the GitHub Provider to the existing Git datasource runtime."""

        if source_type != "git":
            raise DatasourceProviderError(
                "GitHub datasource source type must be git"
            )
        return source_type

    def validate_connection(self, endpoint, connection_config):
        """Allow only the public GitHub HTTPS endpoint in V1."""

        if connection_config not in ({}, None):
            raise DatasourceProviderError(
                "GitHub connection config contains unsupported fields"
            )
        parsed = urlsplit(str(endpoint or "").strip())
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise DatasourceProviderError(
                "GitHub connection endpoint must be https://github.com"
            )
        return "https://github.com"

    def validate_connection_scope(self, connection_scope):
        """Normalize the explicit repository allowlist for one Connection."""

        if not isinstance(connection_scope, dict):
            raise DatasourceProviderError("connection scope must be an object")
        if set(connection_scope).difference(ALLOWED_SCOPE_KEYS):
            raise DatasourceProviderError(
                "connection scope contains unsupported fields"
            )
        repositories = connection_scope.get("repositories")
        if not isinstance(repositories, list) or not repositories:
            raise DatasourceProviderError(
                "connection scope requires repositories"
            )
        if len(repositories) > GITHUB_MAX_REPOSITORIES:
            raise DatasourceProviderError(
                "connection scope contains too many repositories"
            )
        normalized = []
        identities = set()
        for value in repositories:
            repository = _repository_name(value)
            identity = repository.casefold()
            if identity not in identities:
                identities.add(identity)
                normalized.append(repository)
        return {"repositories": normalized}

    def validate_live_connection(
        self,
        secret,
        endpoint="",
        connection_config=None,
        client=None,
        request_context=None,
    ):
        """Validate one PAT and return bounded, non-sensitive account data."""

        if endpoint or connection_config:
            self.validate_connection(endpoint, connection_config)
        token = _secret_value(secret)
        context = request_context or PluginRequestContext(
            timeout_seconds=GITHUB_TIMEOUT_SECONDS,
        )
        with _GitHubClient(client) as github_client:
            payload = context.run(
                lambda: _github_json(github_client, "/user", token)
            )
        if not isinstance(payload, dict):
            raise DatasourceProviderError("GITHUB_RESPONSE_INVALID")
        login = payload.get("login")
        if not isinstance(login, str) or not login:
            raise DatasourceProviderError("GITHUB_RESPONSE_INVALID")
        name = payload.get("name")
        return {
            "account": {
                "login": login[:160],
                "name": name[:160] if isinstance(name, str) else "",
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
        """Discover bounded metadata for explicitly approved repositories."""

        if endpoint or connection_config:
            self.validate_connection(endpoint, connection_config)
        scope = self.validate_connection_scope(connection_scope)
        token = _secret_value(secret)
        context = request_context or PluginRequestContext(
            max_concurrency=GITHUB_DISCOVERY_WORKERS,
            timeout_seconds=GITHUB_TIMEOUT_SECONDS,
        )
        with _GitHubClient(client) as github_client:
            repositories = scope["repositories"]
            resources, warnings = context.parallel_map(
                repositories,
                lambda repository: _github_repository_resource(
                    github_client,
                    repository,
                    token,
                ),
                "repository",
            )
        result = {
            "resources": {
                "repositories": {
                    "items": resources,
                }
            }
        }
        if warnings:
            result["warnings"] = warnings
        return result

    def validate_datasource_config(self, connection_scope, datasource_config):
        """Return a normalized repository selection within configured scope."""

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
        repository = _repository_name(datasource_config.get("repository"))
        allowed_repositories = _allowed_repositories(connection_scope)
        if repository.casefold() not in allowed_repositories:
            raise DatasourceProviderError(
                "repository is outside connection scope"
            )
        normalized = {"repository": repository}
        branch = _optional_nonempty_string(
            datasource_config.get("branch"), "branch"
        )
        if branch:
            normalized["branch"] = branch
        directory = _directory_path(datasource_config.get("directory"))
        if directory:
            normalized["directory"] = directory
        return normalized


def _allowed_repositories(connection_scope):
    """Return explicitly allowed V1 repositories from one Connection scope."""

    normalized = GitHubDatasourceProvider().validate_connection_scope(
        connection_scope
    )
    return {repository.casefold() for repository in normalized["repositories"]}


def _repository_name(value):
    """Validate and normalize an owner/repository identifier."""

    if not isinstance(value, str):
        raise DatasourceProviderError("repository is required")
    repository = value.strip().strip("/")
    parts = repository.split("/")
    if (
        len(parts) != 2
        or not all(parts)
        or any(len(part) > 100 for part in parts)
        or any(part in {".", ".."} for part in parts)
        or any(
            not all(
                character.isalnum() or character in {"-", "_", "."}
                for character in part
            )
            for part in parts
        )
    ):
        raise DatasourceProviderError("repository must use owner/repository")
    return repository


def _optional_nonempty_string(value, field_name):
    """Return a trimmed optional string field."""

    if value is None:
        return ""
    if not isinstance(value, str):
        raise DatasourceProviderError(
            f"{field_name} must be a non-empty string"
        )
    text = value.strip()
    if (
        not text
        or len(text) > GITHUB_MAX_BRANCH_LENGTH
        or any(ord(character) < 32 for character in text)
    ):
        raise DatasourceProviderError(f"{field_name} is invalid")
    return text


def _directory_path(value):
    """Return a safe repository-relative directory path."""

    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        raise DatasourceProviderError("directory must be a string")
    text = value.strip()
    if len(text) > GITHUB_MAX_DIRECTORY_LENGTH or any(
        ord(character) < 32 for character in text
    ):
        raise DatasourceProviderError("directory is invalid")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or ".." in path.parts
        or any(len(part) > 255 for part in path.parts)
    ):
        raise DatasourceProviderError("directory must be repository-relative")
    normalized = path.as_posix()
    return "" if normalized == "." else normalized


class _GitHubClient:
    """Manage an optional injected HTTPX client without closing it."""

    def __init__(self, client):
        self.client = client
        self.owned = client is None

    def __enter__(self):
        if self.client is None:
            self.client = httpx.Client(
                timeout=GITHUB_TIMEOUT_SECONDS,
                follow_redirects=False,
            )
        return self.client

    def __exit__(self, exc_type, exc_value, traceback):
        if self.owned:
            self.client.close()


def _secret_value(value):
    """Return a non-empty secret without persisting or returning it."""

    if not isinstance(value, str) or not value:
        raise DatasourceProviderError("GITHUB_SECRET_UNAVAILABLE")
    return value


def _github_repository_resource(client, repository, token):
    """Return safe repository and branch metadata for one allowed resource."""

    path = quote(repository, safe="/")
    metadata = _github_json(client, f"/repos/{path}", token)
    branches = _github_json(
        client,
        f"/repos/{path}/branches",
        token,
        params={"per_page": GITHUB_MAX_BRANCHES, "page": 1},
    )
    if not isinstance(metadata, dict) or not isinstance(branches, list):
        raise DatasourceProviderError("GITHUB_RESPONSE_INVALID")
    full_name = metadata.get("full_name")
    default_branch = metadata.get("default_branch")
    private = metadata.get("private")
    if (
        not isinstance(full_name, str)
        or full_name.casefold() != repository.casefold()
        or not isinstance(default_branch, str)
        or not isinstance(private, bool)
    ):
        raise DatasourceProviderError("GITHUB_RESPONSE_INVALID")
    branch_names = []
    for item in branches[:GITHUB_MAX_BRANCHES]:
        name = item.get("name") if isinstance(item, dict) else None
        if isinstance(name, str) and name:
            branch_names.append(name[:255])
    repository_name = full_name[:201]
    return {
        "value": repository_name,
        "label": repository_name,
        "metadata": {
            "default_branch": default_branch[:255],
            "private": private,
        },
        "options": {
            "branches": [
                {"value": name, "label": name}
                for name in branch_names
            ]
        },
    }


def _github_json(client, path, token, params=None):
    """Read bounded JSON from the fixed GitHub API host."""

    try:
        with client.stream(
            "GET",
            f"{GITHUB_API_URL}{path}",
            params=params,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
                "User-Agent": "SourceLens-Control-Plane",
            },
            follow_redirects=False,
        ) as response:
            if response.is_redirect:
                raise DatasourceProviderError("GITHUB_REDIRECT_REJECTED")
            if response.status_code >= 400:
                retry_after = (
                    retry_after_seconds(response.headers.get("Retry-After"))
                    if response.status_code == 429
                    else None
                )
                raise DatasourceProviderError(
                    _github_error(response.status_code),
                    retry_after=retry_after,
                )
            body = bytearray()
            for chunk in response.iter_bytes():
                if len(body) + len(chunk) > GITHUB_MAX_RESPONSE_BYTES:
                    raise DatasourceProviderError("GITHUB_RESPONSE_TOO_LARGE")
                body.extend(chunk)
    except DatasourceProviderError:
        raise
    except httpx.HTTPError as exc:
        raise DatasourceProviderError("GITHUB_REQUEST_FAILED") from exc
    try:
        return json.loads(body)
    except (UnicodeDecodeError, ValueError) as exc:
        raise DatasourceProviderError("GITHUB_RESPONSE_INVALID") from exc


def _github_error(status_code):
    """Map provider failures without exposing remote response content."""

    if status_code == 404:
        return "GITHUB_NOT_FOUND"
    if status_code in {401, 403}:
        return "GITHUB_ACCESS_DENIED"
    if status_code == 429:
        return "GITHUB_RATE_LIMITED"
    return "GITHUB_REQUEST_FAILED"


class GitHubToolProvider:
    """Validate bounded read-only GitHub Tool requests."""

    key = "github"

    def validate_request(self, endpoint, allowed_scope, tool_key, arguments):
        """Return canonical endpoint and authorized arguments."""

        try:
            endpoint = GitHubDatasourceProvider().validate_connection(
                endpoint,
                {},
            )
            repository = _repository_name(
                arguments.get("repository")
                if isinstance(arguments, dict)
                else None
            )
            allowed = _allowed_repositories(allowed_scope)
        except DatasourceProviderError as exc:
            raise ToolProviderError(str(exc)) from exc
        if repository.casefold() not in allowed:
            raise ToolProviderError("repository is outside connection scope")
        if tool_key == "github_read_file":
            normalized = {
                "repository": repository,
                "path": _tool_path(arguments.get("path"), required=True),
            }
            ref = _tool_text(arguments.get("ref"), "ref", 255)
            if ref:
                normalized["ref"] = ref
            return endpoint, normalized
        if tool_key == "github_search_code":
            query = _tool_text(
                arguments.get("query"),
                "query",
                1024,
                required=True,
            )
            if SEARCH_SCOPE_PATTERN.search(query):
                raise ToolProviderError(
                    "query scope qualifiers are not allowed"
                )
            normalized = {
                "repository": repository,
                "query": query,
                "max_results": _tool_max_results(
                    arguments.get("max_results")
                ),
            }
            path = _tool_path(arguments.get("path"), required=False)
            if path and (
                any(character.isspace() for character in path) or '"' in path
            ):
                raise ToolProviderError("search path is invalid")
            if path:
                normalized["path"] = path
            return endpoint, normalized
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


def _tool_path(value, required):
    """Return a bounded repository-relative Tool path."""

    text = _tool_text(value, "path", 4096, required=required)
    if not text:
        return ""
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        raise ToolProviderError("path must be repository-relative")
    normalized = path.as_posix()
    if normalized in {"", "."} and required:
        raise ToolProviderError("path is required")
    return "" if normalized == "." else normalized


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


DATASOURCE_PROVIDER = GitHubDatasourceProvider()
TOOL_PROVIDER = GitHubToolProvider()
