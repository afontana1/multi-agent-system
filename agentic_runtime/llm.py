from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

from .domain import ToolCall
from .tools import ToolDefinition, tool_to_openai_schema


@dataclass(frozen=True)
class ChatCompletionResult:
    message: Dict[str, Any]
    content: str
    tool_calls: Tuple[ToolCall, ...] = ()
    finish_reason: Optional[str] = None


class IChatModel(ABC):
    @abstractmethod
    async def complete(self, messages: Sequence[Dict[str, Any]], tools: Sequence[ToolDefinition] = ()) -> ChatCompletionResult:
        raise NotImplementedError


class LiteLLMChatModel(IChatModel):
    def __init__(
        self,
        model: str,
        *,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._api_base = api_base
        self._api_key = api_key
        self._extra = dict(extra or {})

    async def complete(self, messages: Sequence[Dict[str, Any]], tools: Sequence[ToolDefinition] = ()) -> ChatCompletionResult:
        try:
            from litellm import acompletion
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("LiteLLM is not installed. Add the 'litellm' package to use LiteLLMChatModel.") from exc

        request: Dict[str, Any] = {
            "model": self._model,
            "messages": list(messages),
            "temperature": self._temperature,
            **self._extra,
        }
        if self._max_tokens is not None:
            request["max_tokens"] = self._max_tokens
        if self._api_base:
            request["api_base"] = self._api_base
        if self._api_key:
            request["api_key"] = self._api_key
        if tools:
            request["tools"] = [tool_to_openai_schema(tool) for tool in tools]
            request["tool_choice"] = "auto"

        response = await acompletion(**request)
        choice = _get_value(_get_value(response, "choices"), 0)
        message = to_openai_assistant_message(_as_dict(_get_value(choice, "message")))
        tool_calls = tuple(_parse_tool_call(item) for item in message.get("tool_calls", []) or ())
        return ChatCompletionResult(
            message=message,
            content=message.get("content") or "",
            tool_calls=tool_calls,
            finish_reason=_get_value(choice, "finish_reason"),
        )


def _get_value(container: Any, key: Any) -> Any:
    if container is None:
        return None
    if isinstance(container, dict):
        return container.get(key)
    if isinstance(key, int):
        return container[key]
    return getattr(container, key, None)


def _as_dict(message: Any) -> Dict[str, Any]:
    if message is None:
        return {"role": "assistant", "content": ""}
    if isinstance(message, dict):
        return dict(message)
    out: Dict[str, Any] = {
        "role": getattr(message, "role", "assistant"),
        "content": getattr(message, "content", "") or "",
    }
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        out["tool_calls"] = [_as_tool_call_dict(item) for item in tool_calls]
    return out


def _as_tool_call_dict(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return item
    function = getattr(item, "function", None)
    return {
        "id": getattr(item, "id", None),
        "type": getattr(item, "type", "function"),
        "function": {
            "name": getattr(function, "name", None),
            "arguments": getattr(function, "arguments", "{}"),
        },
    }


def _parse_tool_call(item: Any) -> ToolCall:
    data = _as_tool_call_dict(item)
    function = data.get("function", {})
    raw_arguments = function.get("arguments", "{}")
    if isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError:
            arguments = {"raw": raw_arguments}
    elif isinstance(raw_arguments, dict):
        arguments = raw_arguments
    else:
        arguments = {"value": raw_arguments}
    return ToolCall(
        id=data.get("id") or function.get("name", "tool-call"),
        name=function.get("name", ""),
        arguments=arguments,
    )


def to_openai_assistant_message(message: Dict[str, Any]) -> Dict[str, Any]:
    tool_calls = [openai_tool_call_dict(_parse_tool_call(item)) for item in message.get("tool_calls", []) or ()]
    content = message.get("content")
    if tool_calls:
        return {
            "role": "assistant",
            "content": content if content not in ("", []) else None,
            "tool_calls": tool_calls,
        }
    return {
        "role": message.get("role", "assistant"),
        "content": content if content is not None else "",
    }


def openai_tool_call_dict(tool_call: ToolCall) -> Dict[str, Any]:
    return {
        "id": tool_call.id,
        "type": "function",
        "function": {
            "name": tool_call.name,
            "arguments": json.dumps(tool_call.arguments),
        },
    }


def openai_tool_result_message(tool_call_id: str, tool_name: str, content: str) -> Dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": content,
    }
