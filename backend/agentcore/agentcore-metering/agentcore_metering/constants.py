"""
Shared constants for agentcore_metering.

Default currency, LLM completion defaults, and test limits.
"""
# Default currency for cost when not specified (e.g. LiteLLM returns USD).
DEFAULT_COST_CURRENCY = "USD"

# Default LLM completion params when not set in config or call.
# Override via config (api) or call_and_track(...) args.
DEFAULT_MAX_TOKENS = 4096

# Max tokens for connection test only. Some models reject max_tokens=1.
TEST_MAX_TOKENS = 64
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TOP_P = 1.0

# LiteLLM global retry and timeout (applied at adapter module load).
# RateLimitError and transient failures are retried by LiteLLM up to this.
LITELLM_NUM_RETRIES = 3
LITELLM_REQUEST_TIMEOUT = 60
