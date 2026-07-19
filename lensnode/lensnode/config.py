from dataclasses import dataclass
import os


@dataclass(frozen=True)
class LensNodeConfig:
    """Runtime configuration for a LensNode."""

    name: str
    token: str
    control_ws_url: str
    ai_gateway_url: str
    deliverable_upload_url: str
    deliverable_max_bytes: int
    workspace_path: str
    protocol_version: str
    agent_version: str
    heartbeat_interval_s: int
    request_timeout_s: int
    run_idle_timeout_s: int
    drain_timeout_s: int
    max_concurrent_runs: int
    summary_trigger_tokens: int
    summary_keep_tokens: int
    offload_tool_tokens: int
    offload_human_tokens: int | None


def _optional_int(value):
    """Return int(value), or None when the env var is unset or empty."""

    return int(value) if value not in (None, "") else None


def _derive_ws_url(server_url):
    """Derive the control WebSocket URL from the base server URL."""

    base = server_url.rstrip("/")
    if base.startswith("https://"):
        return "wss://" + base[len("https://") :] + "/ws/lens/lensnodes/"
    if base.startswith("http://"):
        return "ws://" + base[len("http://") :] + "/ws/lens/lensnodes/"
    return base + "/ws/lens/lensnodes/"


def load_config():
    """Load LensNode configuration from environment variables.

    Only LENSNODE_SERVER_URL (the base address) is required for connectivity;
    the control WebSocket and AI gateway URLs are derived from it unless
    overridden explicitly.
    """

    server_url = os.getenv(
        "LENSNODE_SERVER_URL", "http://backend-api:8000"
    ).rstrip("/")
    return LensNodeConfig(
        name=os.getenv("LENSNODE_NAME", "local-dev-lensnode"),
        token=os.getenv("LENSNODE_TOKEN", "dev-lensnode-token"),
        control_ws_url=os.getenv("LENSNODE_CONTROL_WS_URL")
        or _derive_ws_url(server_url),
        ai_gateway_url=os.getenv("LENSNODE_AI_GATEWAY_URL")
        or f"{server_url}/api/lens/lensnode/ai-gateway/",
        deliverable_upload_url=os.getenv("LENSNODE_DELIVERABLE_UPLOAD_URL")
        or f"{server_url}/api/lens/lensnode/deliverables/",
        deliverable_max_bytes=int(
            os.getenv("LENSNODE_DELIVERABLE_MAX_BYTES", str(50 * 1024 * 1024))
        ),
        workspace_path=os.getenv("LENSNODE_WORKSPACE_PATH", "/workspace"),
        protocol_version=os.getenv("LENSNODE_PROTOCOL_VERSION", "v1"),
        agent_version=os.getenv("LENSNODE_AGENT_VERSION", "0.1.0"),
        heartbeat_interval_s=int(
            os.getenv("LENSNODE_HEARTBEAT_INTERVAL_S", "15")
        ),
        request_timeout_s=int(os.getenv("LENSNODE_REQUEST_TIMEOUT_S", "240")),
        run_idle_timeout_s=int(
            os.getenv("LENSNODE_RUN_IDLE_TIMEOUT_S", "180")
        ),
        drain_timeout_s=int(
            os.getenv("LENSNODE_DRAIN_TIMEOUT_S", "240")
        ),
        max_concurrent_runs=int(os.getenv("LENSNODE_MAX_CONCURRENT_RUNS", "1")),
        summary_trigger_tokens=int(
            os.getenv("LENSNODE_SUMMARY_TRIGGER_TOKENS", "48000")
        ),
        summary_keep_tokens=int(
            os.getenv("LENSNODE_SUMMARY_KEEP_TOKENS", "16000")
        ),
        offload_tool_tokens=int(
            os.getenv("LENSNODE_OFFLOAD_TOOL_TOKENS") or "5000"
        ),
        offload_human_tokens=_optional_int(
            os.getenv("LENSNODE_OFFLOAD_HUMAN_TOKENS")
        ),
    )
