import time
import uuid
from pathlib import PurePosixPath

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.utils import timezone

from .models import DataSource, DataSourceCredential, LensNode
from .services import lensnode_group_name

WORKSPACE_ROOT = "/workspace"
DATASOURCE_RESULT_TIMEOUT_S = 900
DATASOURCE_RESULT_POLL_S = 0.5


class DataSourcePathError(ValueError):
    """Raised when a datasource target path is invalid."""


class DataSourceDispatchError(RuntimeError):
    """Raised when a datasource command cannot reach a LensNode."""


def normalize_workspace_target_path(value, workspace_path=WORKSPACE_ROOT):
    """Return a safe absolute target path under a LensNode workspace."""

    raw = str(value or "").strip()
    workspace = str(workspace_path or WORKSPACE_ROOT).rstrip("/")
    if not workspace.startswith("/"):
        raise DataSourcePathError("LENS_SOURCE_WORKSPACE_PATH_INVALID")

    if not raw:
        raise DataSourcePathError("LENS_SOURCE_TARGET_PATH_REQUIRED")

    if raw == workspace:
        raise DataSourcePathError("LENS_SOURCE_TARGET_PATH_REQUIRED")

    if raw.startswith(f"{workspace}/"):
        relative = raw[len(workspace) + 1 :]
    else:
        if raw.startswith("/"):
            raise DataSourcePathError("LENS_SOURCE_TARGET_PATH_INVALID")
        relative = raw

    path = PurePosixPath(relative)
    if path.is_absolute():
        raise DataSourcePathError("LENS_SOURCE_TARGET_PATH_INVALID")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise DataSourcePathError("LENS_SOURCE_TARGET_PATH_INVALID")

    return f"{workspace}/{path.as_posix()}"


def validate_datasource_lensnode(lensnode):
    """Validate that a LensNode can execute datasource work."""

    if lensnode is None:
        raise DataSourceDispatchError("LENSNODE_REQUIRED")
    if lensnode.status != LensNode.Status.ONLINE:
        raise DataSourceDispatchError("LENSNODE_OFFLINE")
    if lensnode.enrollment_status != LensNode.EnrollmentStatus.APPROVED:
        raise DataSourceDispatchError("LENSNODE_NOT_APPROVED")
    if lensnode.token_revoked:
        raise DataSourceDispatchError("LENSNODE_TOKEN_REVOKED")


def _send_lensnode_command(lensnode, payload):
    """Send a datasource command to a connected LensNode."""

    validate_datasource_lensnode(lensnode)
    channel_layer = get_channel_layer()
    if channel_layer is None:
        raise DataSourceDispatchError("LENS_CHANNEL_LAYER_UNAVAILABLE")

    async_to_sync(channel_layer.group_send)(
        lensnode_group_name(lensnode.uuid),
        {
            "type": "lensnode.command",
            "payload": payload,
        },
    )


def _wait_cache_result(cache_key, timeout_s):
    """Wait for a LensNode result cached by the WebSocket consumer."""

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = cache.get(cache_key)
        if result is not None:
            cache.delete(cache_key)
            return result
        time.sleep(DATASOURCE_RESULT_POLL_S)
    raise DataSourceDispatchError("LENSNODE_RESULT_TIMEOUT")


def check_datasource_path(lensnode, target_path, source_type, config=None):
    """Ask a LensNode to inspect a datasource target path."""

    target_path = normalize_workspace_target_path(
        target_path,
        lensnode.workspace_path,
    )
    request_id = uuid.uuid4().hex
    _send_lensnode_command(
        lensnode,
        {
            "type": "datasource_check_path",
            "request_id": request_id,
            "target_path": target_path,
            "source_type": source_type,
            "config": config or {},
        },
    )
    return _wait_cache_result(
        f"lens:datasource_path:{request_id}",
        timeout_s=10,
    )


def test_datasource_connection(
    lensnode,
    source_type,
    config=None,
    datasource_uuid=None,
    credential_uuid=None,
):
    """Ask a LensNode to test datasource connection settings."""

    config = dict(config or {})
    _inject_existing_datasource_credential(
        config,
        credential_uuid,
    )
    request_id = uuid.uuid4().hex
    _send_lensnode_command(
        lensnode,
        {
            "type": "datasource_test_connection",
            "request_id": request_id,
            "source_type": source_type,
            "config": config,
        },
    )
    return _wait_cache_result(
        f"lens:datasource_connection:{request_id}",
        timeout_s=30,
    )


def dispatch_datasource_sync(datasource, task_id, trigger="scheduled"):
    """Dispatch one datasource synchronization to its LensNode."""

    datasource = DataSource.objects.select_related(
        "credential",
        "lensnode",
    ).get(
        pk=datasource.pk
    )
    validate_datasource_lensnode(datasource.lensnode)
    config = datasource_runtime_config(datasource)
    request_id = uuid.uuid4().hex
    _send_lensnode_command(
        datasource.lensnode,
        {
            "type": "datasource_sync",
            "request_id": request_id,
            "task_id": task_id,
            "datasource_uuid": str(datasource.uuid),
            "source_type": datasource.source_type,
            "name": datasource.name,
            "config": config,
            "target_path": datasource.target_path,
            "trigger": trigger,
        },
    )
    return _wait_cache_result(
        f"lens:datasource_sync:{request_id}",
        timeout_s=DATASOURCE_RESULT_TIMEOUT_S,
    )


def datasource_runtime_config(datasource):
    """Return datasource config with transient execution credentials."""

    config = dict(datasource.config or {})
    credential = getattr(datasource, "credential", None)
    if datasource.source_type == DataSource.SourceType.GIT and credential:
        secret = credential.get_secret()
        if secret:
            config["access_token"] = secret
            credential.last_used_at = timezone.now()
            credential.save(update_fields=["last_used_at", "updated_at"])
    if datasource.source_type == DataSource.SourceType.FEISHU and credential:
        secret = credential.get_secret()
        if secret:
            app_id, _, app_secret = secret.partition(":")
            config["app_id"] = app_id
            config["app_secret"] = app_secret
            credential.last_used_at = timezone.now()
            credential.save(update_fields=["last_used_at", "updated_at"])
    return config


def _inject_existing_datasource_credential(
    config,
    credential_uuid=None,
):
    """Add a selected encrypted credential to transient test config."""

    if not credential_uuid:
        return
    credential = DataSourceCredential.objects.filter(
        uuid=credential_uuid,
    ).first()
    if credential is None:
        return
    secret = credential.get_secret()
    if not secret:
        return
    if (
        source_type_from_credential(credential) == DataSource.SourceType.FEISHU
    ):
        app_id, _, app_secret = secret.partition(":")
        config["app_id"] = app_id
        config["app_secret"] = app_secret
    else:
        config["access_token"] = secret


def source_type_from_credential(credential):
    """Infer datasource type from a credential auth type."""

    if credential.auth_type == DataSourceCredential.AuthType.FEISHU_APP:
        return DataSource.SourceType.FEISHU
    return DataSource.SourceType.GIT
