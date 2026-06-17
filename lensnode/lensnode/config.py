from dataclasses import dataclass
import os


@dataclass(frozen=True)
class LensNodeConfig:
    """Runtime configuration for a LensNode."""

    name: str
    token: str
    control_ws_url: str
    ai_gateway_url: str
    workspace_path: str
    protocol_version: str
    agent_version: str
    heartbeat_interval_s: int
    request_timeout_s: int
    max_concurrent_runs: int
    summary_trigger_tokens: int
    summary_keep_tokens: int


def load_config():
    """Load LensNode configuration from environment variables."""

    return LensNodeConfig(
        name=os.getenv("LENSNODE_NAME", "local-dev-lensnode"),
        token=os.getenv("LENSNODE_TOKEN", "dev-lensnode-token"),
        control_ws_url=os.getenv(
            "LENSNODE_CONTROL_WS_URL",
            "ws://backend-api:8000/ws/lens/lensnodes/",
        ),
        ai_gateway_url=os.getenv(
            "LENSNODE_AI_GATEWAY_URL",
            "http://backend-api:8000/api/lens/lensnode/ai-gateway/",
        ),
        workspace_path=os.getenv("LENSNODE_WORKSPACE_PATH", "/workspace"),
        protocol_version=os.getenv("LENSNODE_PROTOCOL_VERSION", "v1"),
        agent_version=os.getenv("LENSNODE_AGENT_VERSION", "0.1.0"),
        heartbeat_interval_s=int(
            os.getenv("LENSNODE_HEARTBEAT_INTERVAL_S", "15")
        ),
        request_timeout_s=int(os.getenv("LENSNODE_REQUEST_TIMEOUT_S", "120")),
        max_concurrent_runs=int(os.getenv("LENSNODE_MAX_CONCURRENT_RUNS", "1")),
        summary_trigger_tokens=int(
            os.getenv("LENSNODE_SUMMARY_TRIGGER_TOKENS", "80000")
        ),
        summary_keep_tokens=int(
            os.getenv("LENSNODE_SUMMARY_KEEP_TOKENS", "16000")
        ),
    )
