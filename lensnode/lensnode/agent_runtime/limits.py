"""Budget policy for individual LensNode agent runs."""


def resolve_token_budget(config, command):
    """Return the LensNode safety ceiling, independent of run settings."""

    del command
    fallback_max = max(
        int(getattr(config, "token_budget_max_tokens", 200000) or 0),
        0,
    )
    hard_max = max(
        int(getattr(config, "token_budget_hard_max_tokens", 500000) or 0),
        0,
    )
    fallback_reserve = max(
        int(
            getattr(config, "token_budget_final_reserve_tokens", 40000) or 0
        ),
        0,
    )
    max_tokens = hard_max or fallback_max

    return {
        "profile": "system",
        "max_tokens": max_tokens,
        "final_reserve_tokens": min(fallback_reserve, max_tokens),
    }
