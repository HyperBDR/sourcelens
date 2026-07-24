import re

from rest_framework import serializers


ENVIRONMENT_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


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


def missing_required_environment(skill, variable_set):
    """Return required Skill keys missing from an environment-variable set."""

    declarations = (skill.definition or {}).get("environment") or []
    required = {
        item["name"]
        for item in declarations
        if isinstance(item, dict) and item.get("required")
    }
    if not required:
        return []
    values = variable_set.get_values() if variable_set is not None else {}
    return sorted(name for name in required if not str(values.get(name) or ""))
