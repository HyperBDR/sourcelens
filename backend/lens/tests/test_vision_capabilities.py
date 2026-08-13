from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase

from agentcore_metering.adapters.django.models import LLMConfig
from lens.models import Assistant, LensNode
from lens.serializers import AssistantSerializer
from lens.vision_capabilities import resolve_model_capability

User = get_user_model()


class VisionCapabilityTests(TestCase):
    def setUp(self):
        self.node = LensNode.objects.create(
            name="Vision test node",
            tasks=[{"name": "knowledge_qa"}],
            available_dirs=["/workspace"],
        )

    def config(self, *, provider="openai_compatible", vision=None):
        data = {"model": "custom-model", "api_key": "test-key"}
        if vision is not None:
            data["vision"] = vision
        return LLMConfig.objects.create(
            scope=LLMConfig.Scope.GLOBAL,
            model_type=LLMConfig.MODEL_TYPE_LLM,
            provider=provider,
            config=data,
            is_active=True,
        )

    @patch(
        "agentcore_metering.adapters.django.services.runtime_config.get_litellm_params"
    )
    @patch("litellm.utils.supports_vision", return_value=False)
    def test_explicit_custom_vision_is_supported(
        self, mock_catalog, mock_params
    ):
        config = self.config(vision=True)
        mock_params.return_value = {"model": "custom-model"}

        result = resolve_model_capability(config.uuid)

        self.assertTrue(result["supports_vision"])
        self.assertEqual(result["vision_capability"], "supported")
        self.assertEqual(result["vision_capability_source"], "explicit")
        mock_catalog.assert_not_called()

    @patch(
        "agentcore_metering.adapters.django.services.runtime_config.get_litellm_params"
    )
    @patch("litellm.utils.supports_vision", return_value=False)
    def test_unknown_custom_model_is_not_assignable(
        self, mock_catalog, mock_params
    ):
        config = self.config()
        mock_params.return_value = {"model": "custom-model"}
        assistant = Assistant(
            name="Vision assistant",
            slug=f"vision-{uuid4().hex[:8]}",
            lensnode=self.node,
            selected_task="knowledge_qa",
            selected_dirs=[{"path": "/workspace"}],
            multimodal_model_ref=config.uuid,
        )
        serializer = AssistantSerializer(assistant, data={
            "multimodal_model_ref": str(config.uuid),
        }, partial=True)

        self.assertFalse(serializer.is_valid())
        self.assertEqual(
            serializer.errors["multimodal_model_ref"]["code"],
            "MODEL_NOT_VISION_CAPABLE",
        )
        mock_catalog.assert_called_once()

    def test_disabled_model_is_not_assignable(self):
        config = self.config(vision=True)
        config.is_active = False
        config.save(update_fields=["is_active"])
        assistant = Assistant(
            name="Disabled vision assistant",
            slug=f"disabled-{uuid4().hex[:8]}",
            lensnode=self.node,
            selected_task="knowledge_qa",
            selected_dirs=[{"path": "/workspace"}],
        )
        serializer = AssistantSerializer(assistant, data={
            "multimodal_model_ref": str(config.uuid),
        }, partial=True)

        self.assertFalse(serializer.is_valid())
        self.assertEqual(
            serializer.errors["multimodal_model_ref"]["code"],
            "VISION_MODEL_DISABLED",
        )
