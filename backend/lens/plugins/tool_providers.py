"""Trusted control-plane validation for built-in Plugin Tool Providers."""

import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from .providers.gitlab import _endpoint as _gitlab_endpoint
from .providers.gitlab import _project_name
from .providers.jira import _endpoint as _jira_endpoint
from .providers.jira import _project_key

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
        if repository.casefold() not in _allowed_repositories(allowed_scope):
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
                any(character.isspace() for character in path) or '"' in path
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


class GitLabToolProvider:
    """Validate bounded read-only GitLab Tool requests."""

    key = "gitlab"

    def validate_request(self, endpoint, allowed_scope, tool_key, arguments):
        """Return canonical endpoint and normalized authorized arguments."""

        endpoint = _gitlab_endpoint(endpoint)
        if not isinstance(arguments, dict):
            raise ToolProviderError("tool arguments must be an object")
        project = _project_name(arguments.get("project"))
        if project.casefold() not in _allowed_projects(allowed_scope):
            raise ToolProviderError("project is outside connection scope")
        if tool_key == "gitlab_read_file":
            normalized = {
                "project": project,
                "path": _repository_path(arguments.get("path"), required=True),
            }
            ref = _bounded_text(arguments.get("ref"), "ref", 255)
            if ref:
                normalized["ref"] = ref
            return endpoint, normalized
        if tool_key == "gitlab_search_code":
            normalized = {
                "project": project,
                "query": _bounded_text(
                    arguments.get("query"),
                    "query",
                    1024,
                    required=True,
                ),
                "max_results": _max_results(arguments.get("max_results")),
            }
            path = _repository_path(arguments.get("path"), required=False)
            if path:
                normalized["path"] = path
            ref = _bounded_text(arguments.get("ref"), "ref", 255)
            if ref:
                normalized["ref"] = ref
            return endpoint, normalized
        raise ToolProviderError("tool is unsupported")


class JiraToolProvider:
    """Validate bounded read-only Jira Cloud Tool requests."""

    key = "jira"

    def validate_request(self, endpoint, allowed_scope, tool_key, arguments):
        """Return canonical endpoint and normalized authorized arguments."""

        endpoint = _jira_endpoint(endpoint)
        if not isinstance(arguments, dict):
            raise ToolProviderError("tool arguments must be an object")
        allowed_projects = _allowed_jira_projects(allowed_scope)
        if tool_key == "jira_get_issue":
            issue_key = _jira_issue_key(arguments.get("issue_key"))
            if issue_key.rsplit("-", 1)[0] not in allowed_projects:
                raise ToolProviderError("issue is outside connection scope")
            return endpoint, {"issue_key": issue_key}
        if tool_key == "jira_search_issues":
            try:
                project = _project_key(arguments.get("project"))
            except ValueError as exc:
                raise ToolProviderError(str(exc)) from exc
            if project not in allowed_projects:
                raise ToolProviderError("project is outside connection scope")
            return endpoint, {
                "project": project,
                "query": _bounded_text(
                    arguments.get("query"),
                    "query",
                    500,
                    required=True,
                ),
                "max_results": _max_results(arguments.get("max_results")),
            }
        raise ToolProviderError("tool is unsupported")


PROVIDERS = {
    "github": GitHubToolProvider(),
    "gitlab": GitLabToolProvider(),
    "jira": JiraToolProvider(),
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
    return {
        _repository_name(repository).casefold() for repository in repositories
    }


def _allowed_projects(value):
    """Return canonical GitLab project identities from Connection scope."""

    if not isinstance(value, dict):
        raise ToolProviderError("connection scope must be an object")
    projects = value.get("projects")
    if not isinstance(projects, list) or not projects:
        raise ToolProviderError("connection scope requires projects")
    try:
        return {_project_name(project).casefold() for project in projects}
    except ValueError as exc:
        raise ToolProviderError(str(exc)) from exc


def _allowed_jira_projects(value):
    """Return canonical Jira project keys from Connection scope."""

    if not isinstance(value, dict):
        raise ToolProviderError("connection scope must be an object")
    projects = value.get("projects")
    if not isinstance(projects, list) or not projects:
        raise ToolProviderError("connection scope requires projects")
    try:
        return {_project_key(project) for project in projects}
    except ValueError as exc:
        raise ToolProviderError(str(exc)) from exc


def _jira_issue_key(value):
    """Return one bounded canonical Jira Issue key."""

    text = _bounded_text(value, "issue_key", 40, required=True).upper()
    parts = text.rsplit("-", 1)
    if len(parts) != 2 or not parts[1].isdigit() or int(parts[1]) < 1:
        raise ToolProviderError("issue_key is invalid")
    try:
        _project_key(parts[0])
    except ValueError as exc:
        raise ToolProviderError("issue_key is invalid") from exc
    return text


def _repository_name(value):
    """Return one canonical owner/repository identifier."""

    if not isinstance(value, str):
        raise ToolProviderError("repository is required")
    repository = value.strip().strip("/")
    parts = repository.split("/")
    if len(parts) != 2 or not all(
        REPOSITORY_PART_PATTERN.fullmatch(part) for part in parts
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
