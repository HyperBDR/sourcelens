import json
from typing import Any, Sequence

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool


class LensGatewayChatModel(BaseChatModel):
    """LangChain chat model that delegates calls to the control plane."""

    model_ref: str
    ai_gateway_url: str
    token: str
    request_timeout_s: int = 120

    @property
    def _llm_type(self):
        """Return LangChain model type identifier."""

        return "lens_gateway_chat_model"

    @property
    def _identifying_params(self):
        """Return identifying params for tracing."""

        return {
            "model_ref": self.model_ref,
            "ai_gateway_url": self.ai_gateway_url,
        }

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs,
    ):
        """Bind OpenAI-compatible tools to the model."""

        formatted = [convert_to_openai_tool(tool) for tool in tools]
        return self.bind(
            tools=formatted,
            tool_choice=tool_choice,
            **kwargs,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop=None,
        run_manager=None,
        **kwargs,
    ):
        """Generate a response through the LensNode AI gateway."""

        del stop, run_manager
        payload = {
            "model_ref": self.model_ref,
            "messages": [_message_to_gateway(message) for message in messages],
            "return_message": True,
        }
        if kwargs.get("tools") is not None:
            payload["tools"] = kwargs["tools"]
        if kwargs.get("tool_choice") is not None:
            payload["tool_choice"] = kwargs["tool_choice"]
        if kwargs.get("temperature") is not None:
            payload["temperature"] = kwargs["temperature"]
        if kwargs.get("max_tokens") is not None:
            payload["max_tokens"] = kwargs["max_tokens"]

        with httpx.Client(timeout=self.request_timeout_s) as client:
            response = client.post(
                self.ai_gateway_url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        message = _message_from_gateway(data.get("message") or {})
        message.response_metadata["usage"] = data.get("usage") or {}
        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output={"usage": data.get("usage") or {}},
        )


def _message_to_gateway(message):
    """Convert a LangChain message to OpenAI-compatible payload."""

    if message.type == "system":
        return {"role": "system", "content": _content_to_text(message.content)}
    if message.type == "human":
        return {"role": "user", "content": _content_to_text(message.content)}
    if message.type == "tool":
        return {
            "role": "tool",
            "content": _content_to_text(message.content),
            "tool_call_id": getattr(message, "tool_call_id", ""),
        }
    if message.type == "ai":
        payload = {
            "role": "assistant",
            "content": _content_to_text(message.content),
        }
        tool_calls = _tool_calls_to_gateway(getattr(message, "tool_calls", []))
        if tool_calls:
            payload["tool_calls"] = tool_calls
        return payload
    return {
        "role": message.type,
        "content": _content_to_text(message.content),
    }


def _tool_calls_to_gateway(tool_calls):
    """Convert LangChain tool calls to OpenAI-compatible tool calls."""

    output = []
    for call in tool_calls or []:
        name = call.get("name")
        if not name:
            continue
        output.append(
            {
                "id": call.get("id"),
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(
                        call.get("args") or {},
                        ensure_ascii=False,
                    ),
                },
            }
        )
    return output


def _message_from_gateway(payload):
    """Convert gateway assistant payload to AIMessage."""

    tool_calls = []
    for raw_call in payload.get("tool_calls") or []:
        function = raw_call.get("function") or {}
        arguments = function.get("arguments") or "{}"
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            args = {}
        tool_calls.append(
            {
                "name": function.get("name", ""),
                "args": args,
                "id": raw_call.get("id"),
            }
        )
    return AIMessage(
        content=payload.get("content") or "",
        tool_calls=tool_calls,
        additional_kwargs={
            "tool_calls": payload.get("tool_calls") or [],
        },
    )


def _content_to_text(content):
    """Return string content for gateway calls."""

    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)
