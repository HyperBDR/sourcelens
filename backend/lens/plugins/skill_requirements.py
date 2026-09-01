"""Validate declarative Skill dependencies on trusted Plugin capabilities."""

import re


PLUGIN_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")


class SkillPluginRequirementError(ValueError):
    """Raised when a Skill Plugin dependency declaration is invalid."""


def validate_required_plugins(value):
    """Return a bounded, normalized Plugin capability dependency list."""

    if value in (None, []):
        return []
    if not isinstance(value, list) or len(value) > 16:
        raise SkillPluginRequirementError(
            "required_plugins must be a list of at most 16 dependencies"
        )
    normalized = []
    seen_plugins = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "plugin",
            "capabilities",
        }:
            raise SkillPluginRequirementError(
                "required_plugins entries must declare plugin and capabilities"
            )
        plugin_key = item.get("plugin")
        capabilities = item.get("capabilities")
        if (
            not isinstance(plugin_key, str)
            or not PLUGIN_KEY_PATTERN.fullmatch(plugin_key)
            or plugin_key in seen_plugins
        ):
            raise SkillPluginRequirementError(
                "required_plugins contains an invalid or duplicate plugin"
            )
        if (
            not isinstance(capabilities, list)
            or not capabilities
            or len(capabilities) > 32
            or len(set(capabilities)) != len(capabilities)
            or any(
                not isinstance(capability, str)
                or not CAPABILITY_PATTERN.fullmatch(capability)
                for capability in capabilities
            )
        ):
            raise SkillPluginRequirementError(
                "required_plugins capabilities are invalid"
            )
        seen_plugins.add(plugin_key)
        normalized.append(
            {
                "plugin": plugin_key,
                "capabilities": list(capabilities),
            }
        )
    return normalized
