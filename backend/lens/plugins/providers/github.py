"""GitHub implementation of the generic datasource provider contract."""

from pathlib import PurePosixPath
from urllib.parse import urlsplit

from .base import DatasourceProvider, DatasourceProviderError


SENSITIVE_CONFIG_KEYS = frozenset({
    "access_token",
    "api_key",
    "authorization",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
})
ALLOWED_CONFIG_KEYS = frozenset({"repository", "branch", "directory"})


class GitHubDatasourceProvider(DatasourceProvider):
    """Validate read-only GitHub repository datasource selections."""

    key = "github"

    def validate_connection(self, endpoint, connection_config):
        """Allow only the public GitHub HTTPS endpoint in V1."""

        del connection_config
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

    def validate_datasource_config(self, connection_scope, datasource_config):
        """Return a normalized repository selection within configured scope."""

        if not isinstance(datasource_config, dict):
            raise DatasourceProviderError("datasource config must be an object")
        unknown_keys = set(datasource_config).difference(ALLOWED_CONFIG_KEYS)
        if unknown_keys.intersection(SENSITIVE_CONFIG_KEYS):
            raise DatasourceProviderError("datasource config cannot contain credentials")
        if unknown_keys:
            raise DatasourceProviderError("datasource config contains unsupported fields")
        repository = _repository_name(datasource_config.get("repository"))
        allowed_repositories = _allowed_repositories(connection_scope)
        if repository not in allowed_repositories:
            raise DatasourceProviderError("repository is outside connection scope")
        normalized = {"repository": repository}
        branch = _optional_nonempty_string(datasource_config.get("branch"), "branch")
        if branch:
            normalized["branch"] = branch
        directory = _directory_path(datasource_config.get("directory"))
        if directory:
            normalized["directory"] = directory
        return normalized


def _allowed_repositories(connection_scope):
    """Return explicitly allowed V1 repositories from one Connection scope."""

    if not isinstance(connection_scope, dict):
        raise DatasourceProviderError("connection scope must be an object")
    repositories = connection_scope.get("repositories")
    if not isinstance(repositories, list) or not repositories:
        raise DatasourceProviderError("connection scope requires repositories")
    return {_repository_name(repository) for repository in repositories}


def _repository_name(value):
    """Validate and normalize an owner/repository identifier."""

    if not isinstance(value, str):
        raise DatasourceProviderError("repository is required")
    repository = value.strip().strip("/")
    parts = repository.split("/")
    if len(parts) != 2 or not all(parts):
        raise DatasourceProviderError("repository must use owner/repository")
    return repository


def _optional_nonempty_string(value, field_name):
    """Return a trimmed optional string field."""

    if value is None:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise DatasourceProviderError(f"{field_name} must be a non-empty string")
    return value.strip()


def _directory_path(value):
    """Return a safe repository-relative directory path."""

    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        raise DatasourceProviderError("directory must be a string")
    path = PurePosixPath(value.strip())
    if path.is_absolute() or ".." in path.parts:
        raise DatasourceProviderError("directory must be repository-relative")
    normalized = path.as_posix()
    return "" if normalized == "." else normalized
