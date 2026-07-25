import re
from urllib.parse import unquote, urlparse

from rest_framework import serializers


ENVIRONMENT_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
ALLOWED_SKILL_API_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def validate_environment_schema(value):
    """Return a normalized Skill environment-variable declaration."""

    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise serializers.ValidationError(
            "Environment variables must be provided as a list."
        )

    normalized = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            raise serializers.ValidationError(
                "Each environment variable must be provided as an object."
            )
        name = str(item.get("name") or "").strip()
        if not name:
            raise serializers.ValidationError(
                "Each environment variable must include a name."
            )
        if not ENVIRONMENT_KEY_RE.fullmatch(name):
            raise serializers.ValidationError(
                f'"{name}" is not a valid environment variable name. '
                "Use uppercase letters, numbers, and underscores."
            )
        if name in seen:
            raise serializers.ValidationError(
                "Environment variable names must be unique. "
                f'"{name}" appears more than once.'
            )
        seen.add(name)
        normalized.append(
            {
                "name": name,
                "description": str(item.get("description") or "").strip(),
                "required": bool(item.get("required", False)),
                "secret": bool(item.get("secret", False)),
            }
        )
    return normalized


def validate_environment_values(value):
    """Return normalized string values keyed by environment variable name."""

    if value in (None, {}, []):
        return {}
    if isinstance(value, list):
        entries = []
        for item in value:
            if not isinstance(item, dict) or "key" not in item:
                raise serializers.ValidationError(
                    "Each entry must include a variable name."
                )
            entries.append((item["key"], item.get("value", "")))
    elif isinstance(value, dict):
        entries = value.items()
    else:
        raise serializers.ValidationError(
            "Environment variable values must be provided as a list or object."
        )

    normalized = {}
    for key, item in entries:
        name = str(key or "").strip()
        if not name:
            raise serializers.ValidationError(
                "Each environment variable must include a name."
            )
        if not ENVIRONMENT_KEY_RE.fullmatch(name):
            raise serializers.ValidationError(
                f'"{name}" is not a valid environment variable name. '
                "Use uppercase letters, numbers, and underscores."
            )
        if name in normalized:
            raise serializers.ValidationError(
                "Environment variable names must be unique. "
                f'"{name}" appears more than once.'
            )
        if isinstance(item, (dict, list)):
            raise serializers.ValidationError(
                f'The value for "{name}" must be text, a number, or a boolean.'
            )
        normalized[name] = str(item if item is not None else "")
    return normalized


def validate_skill_api_policy(value, environment):
    """Return a normalized allowlist for Skill HTTP API requests."""

    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise serializers.ValidationError(
            "The Skill API policy must be an object."
        )
    base_url_env = str(value.get("base_url_env") or "").strip()
    declared_names = {item["name"] for item in environment or []}
    if base_url_env not in declared_names:
        raise serializers.ValidationError(
            "The Skill API base_url_env must name a declared environment "
            "variable."
        )
    routes = value.get("routes")
    if not isinstance(routes, list) or not routes:
        raise serializers.ValidationError(
            "The Skill API policy must declare at least one route."
        )

    normalized_routes = []
    for route in routes:
        if not isinstance(route, dict):
            raise serializers.ValidationError(
                "Each Skill API route must be an object."
            )
        path = route.get("path")
        path_prefix = route.get("path_prefix")
        if bool(path) == bool(path_prefix):
            raise serializers.ValidationError(
                "Each Skill API route must declare either path or "
                "path_prefix."
            )
        methods = route.get("methods")
        if not isinstance(methods, list) or not methods:
            raise serializers.ValidationError(
                "Each Skill API route must declare at least one method."
            )
        normalized_methods = []
        for method in methods:
            normalized_method = str(method or "").upper()
            if normalized_method not in ALLOWED_SKILL_API_METHODS:
                raise serializers.ValidationError(
                    f'"{normalized_method}" is not an allowed API method.'
                )
            if normalized_method not in normalized_methods:
                normalized_methods.append(normalized_method)
        route_key = "path" if path else "path_prefix"
        normalized_route = {
            route_key: _normalize_skill_api_path(
                path if path else path_prefix,
                prefix=route_key == "path_prefix",
            ),
            "methods": normalized_methods,
        }
        normalized_routes.append(normalized_route)
    return {
        "base_url_env": base_url_env,
        "routes": normalized_routes,
    }


def _normalize_skill_api_path(value, *, prefix=False):
    """Return a safe absolute API path or prefix."""

    text = str(value or "").strip()
    parsed = urlparse(text)
    if (
        not text.startswith("/")
        or parsed.scheme
        or parsed.netloc
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise serializers.ValidationError(
            "Skill API routes must use absolute paths without a host, "
            "query, or fragment."
        )
    decoded = parsed.path
    for _ in range(5):
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded
    if unquote(decoded) != decoded:
        raise serializers.ValidationError(
            "Skill API routes must not contain path traversal."
        )
    decoded = decoded.replace("\\", "/")
    if any(part in {".", ".."} for part in decoded.split("/")):
        raise serializers.ValidationError(
            "Skill API routes must not contain path traversal."
        )
    normalized = "/" + decoded.lstrip("/")
    if prefix:
        normalized = normalized.rstrip("/") + "/"
    return normalized


def missing_required_environment(skill, variable_set):
    """Return required Skill keys missing from an environment-variable set."""

    values = variable_set.get_values() if variable_set is not None else {}
    return missing_required_environment_values(skill, values)


def missing_required_environment_values(skill, values):
    """Return required Skill keys missing from a value mapping."""

    declarations = (skill.definition or {}).get("environment") or []
    required = {
        item["name"]
        for item in declarations
        if isinstance(item, dict) and item.get("required")
    }
    if not required:
        return []
    return sorted(name for name in required if not str(values.get(name) or ""))
