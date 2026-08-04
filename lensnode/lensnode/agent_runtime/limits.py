"""Budget policy for individual LensNode agent runs."""


def resolve_token_budget(config, command):
    """Return a validated per-run budget capped by the LensNode ceiling."""

    requested = command.get("token_budget") or {}
    profile = str(requested.get("profile") or "standard")
    if profile not in {"standard", "deep", "unlimited"}:
        profile = "standard"
    if profile == "unlimited":
        return {
            "profile": profile,
            "max_tokens": 0,
            "final_reserve_tokens": 0,
        }

    fallback_max = max(
        int(getattr(config, "token_budget_max_tokens", 200000) or 0),
        0,
    )
    hard_max = max(
        int(getattr(config, "token_budget_hard_max_tokens", 500000) or 0),
        0,
    )
    try:
        requested_max = max(int(requested.get("max_tokens")), 0)
    except (TypeError, ValueError):
        requested_max = fallback_max
    max_tokens = min(requested_max, hard_max) if hard_max else requested_max

    fallback_reserve = max(
        int(
            getattr(config, "token_budget_final_reserve_tokens", 40000) or 0
        ),
        0,
    )
    try:
        reserve = max(int(requested.get("final_reserve_tokens")), 0)
    except (TypeError, ValueError):
        reserve = fallback_reserve

    return {
        "profile": profile,
        "max_tokens": max_tokens,
        "final_reserve_tokens": min(reserve, max_tokens),
    }
