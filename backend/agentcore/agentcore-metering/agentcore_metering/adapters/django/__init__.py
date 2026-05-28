# Django adapter: full Django app for LLM metering.
# Public API: import LLMTracker from here or from
# agentcore_metering.adapters.django.trackers / .trackers.llm.
# Lazy import so that importing this package does not load Django models before
# django.setup() / apps are ready (avoids AppRegistryNotReady).

__all__ = ["LLMTracker"]


def __getattr__(name):
    if name == "LLMTracker":
        from agentcore_metering.adapters.django.trackers import LLMTracker
        return LLMTracker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
