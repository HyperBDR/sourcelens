"""
Resolve LLM configuration from DB (global or per-user).

When model_uuid is provided, the config with that uuid is used (must be
active and model_type=llm). Otherwise the earliest enabled LLM config
by created_at (then id) is used: user scope first, then global.
"""
from typing import Any, Dict, List, Optional, Union

from agentcore_metering.adapters.django.models import LLMConfig


def _get_earliest_active_configs(
    scope: str, user_id: Optional[int]
) -> List[LLMConfig]:
    """
    Active LLM configs for scope. Global: is_default first, then created_at.
    User: created_at, id (earliest first).
    """
    qs = LLMConfig.objects.filter(
        scope=scope,
        model_type=LLMConfig.MODEL_TYPE_LLM,
        is_active=True,
    )
    if scope == LLMConfig.Scope.USER and user_id is not None:
        qs = qs.filter(user_id=user_id).order_by("created_at", "id")
    elif scope == LLMConfig.Scope.GLOBAL:
        qs = qs.filter(user__isnull=True).order_by(
            "-is_default", "created_at", "id"
        )
    else:
        qs = qs.order_by("created_at", "id")
    return list(qs)


def _config_to_dict(row: LLMConfig) -> Dict[str, Any]:
    return {
        "provider": (row.provider or "openai").strip().lower(),
        "config": row.config or {},
    }


def get_config_from_db(
    user_id: Optional[int] = None,
    model_uuid: Optional[Union[str, bytes]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Load one LLM config from DB.

    If model_uuid is provided, returns that config (must be active,
    model_type=llm). Otherwise returns the earliest enabled LLM config
    by created_at: user scope first (when user_id given), then global.

    Returns:
        Dict with keys: provider (str), config (dict).
        None if no matching config in DB.
    """
    if model_uuid is not None:
        try:
            row = LLMConfig.objects.get(
                uuid=model_uuid,
                model_type=LLMConfig.MODEL_TYPE_LLM,
                is_active=True,
            )
            return _config_to_dict(row)
        except (LLMConfig.DoesNotExist, ValueError, TypeError):
            return None

    configs: List[LLMConfig] = []
    if user_id is not None:
        configs = _get_earliest_active_configs(LLMConfig.Scope.USER, user_id)
    if not configs:
        configs = _get_earliest_active_configs(LLMConfig.Scope.GLOBAL, None)
    if not configs:
        return None
    return _config_to_dict(configs[0])


def set_default_llm_config(config: LLMConfig) -> None:
    """
    Set this config as the default (is_default=True) and clear others.
    Only global LLM configs can be default; no-op for user scope.
    """
    if config.scope != LLMConfig.Scope.GLOBAL:
        return
    config.is_default = True
    config.save(update_fields=["is_default", "updated_at"])
    LLMConfig.objects.filter(
        scope=LLMConfig.Scope.GLOBAL,
        model_type=LLMConfig.MODEL_TYPE_LLM,
    ).exclude(pk=config.pk).update(is_default=False)


def get_default_llm_config_uuid() -> Optional[str]:
    """
    Return the uuid of the single default LLM config (used when no model_uuid).

    Prefers global config with is_default=True; else earliest by created_at.
    Returns None if there is no active global LLM config.
    """
    row = (
        LLMConfig.objects.filter(
            scope=LLMConfig.Scope.GLOBAL,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            is_active=True,
        )
        .order_by("-is_default", "created_at", "id")
        .first()
    )
    return str(row.uuid) if row else None


def get_config_list_from_db(
    scope: str,
    user_id: Optional[int] = None,
    model_type: str = LLMConfig.MODEL_TYPE_LLM,
) -> List[Dict[str, Any]]:
    """
    List all configs for a scope (and optionally user), for API list response.
    Does not filter by is_active so UI can show all.
    Ordered by created_at, id for consistency with default resolution.
    """
    qs = (
        LLMConfig.objects.filter(scope=scope, model_type=model_type)
        .order_by("created_at", "id")
    )
    if scope == LLMConfig.Scope.USER:
        if user_id is None:
            return []
        qs = qs.filter(user_id=user_id)
    else:
        qs = qs.filter(user__isnull=True)
    return [
        {
            "id": row.id,
            "uuid": str(row.uuid),
            "scope": row.scope,
            "user_id": row.user_id,
            "model_type": row.model_type,
            "provider": row.provider,
            "config": row.config,
            "is_active": row.is_active,
            "created_at": (
                row.created_at.isoformat() if row.created_at else None
            ),
            "updated_at": (
                row.updated_at.isoformat() if row.updated_at else None
            ),
        }
        for row in qs
    ]
