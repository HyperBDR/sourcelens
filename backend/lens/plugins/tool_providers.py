"""Trusted control-plane validation for built-in Plugin Tool Providers."""

import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit


REPOSITORY_PART_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
SEARCH_SCOPE_PATTERN = re.compile(r"(?:repo|org|user):", re.IGNORECASE)


class ToolProviderError(ValueError):
    """Raised when a Tool request violates its Provider contract."""


class GitHubToolProvider:
    """Validate bounded read-only GitHub Tool requests."""

    key = "github"

    def validate_request(self, endpoint, allowed_scope, tool_key, arguments):
        """Return canonical endpoint and normalized authorized arguments."""

        endpoint = self._validate_endpoint(endpoint)
        if not isinstance(arguments, dict):
            raise ToolProviderError("tool arguments must be an object")
        repository = _repository_name(arguments.get("repository"))
        if repository not in _allowed_repositories(allowed_scope):
            raise ToolProviderError("repository is outside connection scope")
        if tool_key == "github_read_file":
            normalized = {
                "repository": repository,
                "path": _repository_path(arguments.get("path"), required=True),
            }
            ref = _bounded_text(arguments.get("ref"), "ref", 255)
            if ref:
                normalized["ref"] = ref
            return endpoint, normalized
        if tool_key == "github_search_code":
            normalized = {
                "repository": repository,
                "query": _search_query(arguments.get("query")),
                "max_results": _max_results(arguments.get("max_results")),
            }
            path = _repository_path(arguments.get("path"), required=False)
            if path and (
                any(character.isspace() for character in path)
                or '"' in path
            ):
                raise ToolProviderError("search path is invalid")
            if path:
                normalized["path"] = path
            return endpoint, normalized
        raise ToolProviderError("tool is unsupported")

    def _validate_endpoint(self, endpoint):
        """Allow only the public GitHub HTTPS endpoint in V1."""

        parsed = urlsplit(str(endpoint or "").strip())
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ToolProviderError(
                "GitHub connection endpoint must be https://github.com"
            )
        return "https://github.com"


PROVIDERS = {
    "github": GitHubToolProvider(),
}


def get_tool_provider(plugin_key):
    """Return one trusted built-in Tool Provider implementation."""

    try:
        return PROVIDERS[plugin_key]
    except KeyError as exc:
        raise ToolProviderError("tool provider is unsupported") from exc


def _allowed_repositories(value):
    """Return canonical repository identities from Connection scope."""

    if not isinstance(value, dict):
        raise ToolProviderError("connection scope must be an object")
    repositories = value.get("repositories")
    if not isinstance(repositories, list) or not repositories:
        raise ToolProviderError("connection scope requires repositories")
    return {_repository_name(repository) for repository in repositories}


def _repository_name(value):
    """Return one canonical owner/repository identifier."""

    if not isinstance(value, str):
        raise ToolProviderError("repository is required")
    repository = value.strip().strip("/")
    parts = repository.split("/")
    if (
        len(parts) != 2
        or not all(REPOSITORY_PART_PATTERN.fullmatch(part) for part in parts)
    ):
        raise ToolProviderError("repository must use owner/repository")
    return repository


def _repository_path(value, required):
    """Return a bounded repository-relative path."""

    text = _bounded_text(value, "path", 4096, required=required)
    if not text:
        return ""
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        raise ToolProviderError("path must be repository-relative")
    normalized = path.as_posix()
    if normalized in {"", "."} and required:
        raise ToolProviderError("path is required")
    return "" if normalized == "." else normalized


def _bounded_text(value, field, limit, required=False):
    """Return bounded text without control characters."""

    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ToolProviderError(f"{field} must be a string")
    text = value.strip()
    if (required and not text) or len(text) > limit:
        raise ToolProviderError(f"{field} is invalid")
    if any(ord(character) < 32 for character in text):
        raise ToolProviderError(f"{field} is invalid")
    return text


def _max_results(value):
    """Return the bounded GitHub search result count."""

    if value is None:
        return 10
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolProviderError("max_results must be an integer")
    if value < 1 or value > 20:
        raise ToolProviderError("max_results must be between 1 and 20")
    return value


def _search_query(value):
    """Return bounded code terms without provider scope qualifiers."""

    query = _bounded_text(value, "query", 1024, required=True)
    if SEARCH_SCOPE_PATTERN.search(query):
        raise ToolProviderError("query scope qualifiers are not allowed")
    return query
