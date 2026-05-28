"""
Provider -> model list with capability tags for LLM config UI.

Capability tags (for display/filter):
- text-to-text: natural language generation / understanding
- code: code generation / understanding
- vision: image input understanding (Vision Input / Image-to-Text)
- multimodal: text + image ± other modalities
- text-to-image: image generation
- long-context: long context (e.g. 100K+ tokens)
- low-cost: low cost, lightweight
- embedding: vector embedding
- reasoning: extended reasoning / chain-of-thought (e.g. o1,
  deepseek-reasoner). When present, reasoning *effort* or *level* may be
  controlled by API params (e.g. OpenAI reasoning.effort: low/medium/high).
  Tag = capability; param = intensity.
Data is loaded from YAML under adapters/django/llm_static/
(capability_labels.yaml, mode_to_model_type.yaml, providers/*.yaml).
See llm_static/load.py.
"""
from typing import Any, Dict

from agentcore_metering.adapters.django.llm_static.load import (
    get_capability_labels,
    get_mode_to_model_type,
    get_providers_with_models as _load_providers_with_models,
)

CAPABILITY_LABELS: Dict[str, str] = get_capability_labels()
MODE_TO_MODEL_TYPE: Dict[str, str] = get_mode_to_model_type()


def get_providers_with_models() -> Dict[str, Any]:
    """
    Return provider list and per-provider model list with capability tags.
    Used by GET llm-config/models/ and for deriving model_type from model id.
    """
    return _load_providers_with_models()


def get_model_type_for_model_id(provider: str, model_id: str) -> str:
    """
    Derive LLMConfig.model_type (llm | embedding | image_generation) from
    provider and model id using curated model list. Default llm.
    """
    data = get_providers_with_models()
    prov_key = (provider or "").strip().lower()
    mid = (model_id or "").strip()
    for p in data["providers"]:
        if (p.get("id") or "").strip().lower() != prov_key:
            continue
        for m in p.get("models") or []:
            if (m.get("id") or "").strip() == mid:
                mode = m.get("mode") or "chat"
                return MODE_TO_MODEL_TYPE.get(mode, "llm")
    return "llm"


def get_model_capabilities(
    provider: str, model_id: str
) -> Dict[str, Any] | None:
    """
    Return capability info for a given provider + model_id, or None if unknown.
    """
    data = get_providers_with_models()
    prov_key = (provider or "").strip().lower()
    mid = (model_id or "").strip()
    for p in data["providers"]:
        if (p.get("id") or "").strip().lower() != prov_key:
            continue
        for m in p.get("models") or []:
            if (m.get("id") or "").strip() == mid:
                out = {
                    "capabilities": m.get("capabilities") or [],
                    "max_input_tokens": m.get("max_input_tokens"),
                    "max_output_tokens": m.get("max_output_tokens"),
                    "mode": m.get("mode", "chat"),
                }
                if m.get("reference_pricing") is not None:
                    out["reference_pricing"] = m["reference_pricing"]
                return out
    return None
