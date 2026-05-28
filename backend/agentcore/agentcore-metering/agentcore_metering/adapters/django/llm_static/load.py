"""
Load capability labels, mode->model_type mapping, and provider/model data
from YAML. Data is under this package (llm_static/*.yaml,
llm_static/providers/*.yaml). Paths are resolved relative to this file
so it works when the package is installed.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import yaml

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

_capability_labels: Optional[Dict[str, str]] = None
_mode_to_model_type: Optional[Dict[str, str]] = None
_providers_with_models: Optional[Dict[str, Any]] = None
_provider_defaults: Optional[Dict[str, Dict[str, Any]]] = None


def _path(*parts: str) -> str:
    return os.path.join(_THIS_DIR, *parts)


def _load_yaml(filename: str) -> Any:
    with open(_path(filename), encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_capability_labels() -> Dict[str, str]:
    """
    Load capability tag id -> short label for UI. Cached after first load.
    """
    global _capability_labels
    if _capability_labels is None:
        _capability_labels = _load_yaml("capability_labels.yaml") or {}
    return _capability_labels


def get_mode_to_model_type() -> Dict[str, str]:
    """Load mode -> model_type for resolver. Cached after first load."""
    global _mode_to_model_type
    if _mode_to_model_type is None:
        _mode_to_model_type = _load_yaml("mode_to_model_type.yaml") or {}
    return _mode_to_model_type


def _normalize_model(m: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure each model dict has id, label, capabilities, mode;
    optional max_input/max_output, reference_pricing.
    """
    out: Dict[str, Any] = {
        "id": str(m.get("id", "")),
        "label": str(m.get("label", "")),
        "capabilities": list(m.get("capabilities") or []),
        "max_input_tokens": m.get("max_input_tokens"),
        "max_output_tokens": m.get("max_output_tokens"),
        "mode": str(m.get("mode", "chat")),
    }
    rp = m.get("reference_pricing")
    if not isinstance(rp, dict):
        return out
    has_input = rp.get("input_usd_per_1m") is not None
    has_output = rp.get("output_usd_per_1m") is not None
    if has_input or has_output:
        out["reference_pricing"] = {
            "input_usd_per_1m": rp.get("input_usd_per_1m"),
            "output_usd_per_1m": rp.get("output_usd_per_1m"),
            "source": rp.get("source"),
            "updated": rp.get("updated"),
        }
    return out


def get_providers_with_models() -> Dict[str, Any]:
    """
    Load providers list (in index order) with models and capability_labels.
    Same shape as before: { "providers": [...], "capability_labels": {...} }.
    Cached.
    """
    global _providers_with_models
    if _providers_with_models is not None:
        return _providers_with_models
    index = _load_yaml("providers/index.yaml") or {}
    provider_ids = index.get("provider_ids") or []
    providers = []
    for pid in provider_ids:
        path = os.path.join("providers", f"{pid}.yaml")
        if not os.path.isfile(_path(path)):
            continue
        data = _load_yaml(path) or {}
        models = [_normalize_model(m) for m in (data.get("models") or [])]
        providers.append({
            "id": str(data.get("id", pid)),
            "label": str(data.get("label", pid)),
            "models": models,
        })
    _providers_with_models = {
        "providers": providers,
        "capability_labels": get_capability_labels(),
    }
    return _providers_with_models


def get_provider_defaults() -> Dict[str, Dict[str, Any]]:
    """
    Load per-provider defaults: default_api_base, default_model,
    default_temperature, default_top_p, default_max_tokens, settings_key,
    requires_api_base. Keys are provider ids. Cached. Only includes providers
    that have a YAML file in providers/.
    """
    global _provider_defaults
    if _provider_defaults is not None:
        return _provider_defaults
    index = _load_yaml("providers/index.yaml") or {}
    provider_ids = index.get("provider_ids") or []
    out: Dict[str, Dict[str, Any]] = {}
    for pid in provider_ids:
        path = os.path.join("providers", f"{pid}.yaml")
        if not os.path.isfile(_path(path)):
            continue
        data = _load_yaml(path) or {}
        out[pid] = {
            "default_api_base": data.get("default_api_base"),
            "default_model": data.get("default_model"),
            "default_temperature": data.get("default_temperature"),
            "default_top_p": data.get("default_top_p"),
            "default_max_tokens": data.get("default_max_tokens"),
            "settings_key": data.get("settings_key"),
            "requires_api_base": bool(data.get("requires_api_base", False)),
        }
    _provider_defaults = out
    return _provider_defaults
