from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional, Sequence

from .domain import ToolResult


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    source: str = "local"
    metadata: Dict[str, Any] = field(default_factory=dict)


class ITool(ABC):
    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        raise NotImplementedError

    @abstractmethod
    async def invoke(self, arguments: Dict[str, Any]) -> ToolResult:
        raise NotImplementedError


ToolHandler = Callable[[Dict[str, Any]], Awaitable[ToolResult]]


class FunctionTool(ITool):
    def __init__(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        self._definition = definition
        self._handler = handler

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def invoke(self, arguments: Dict[str, Any]) -> ToolResult:
        return await self._handler(arguments)


class ToolRegistry:
    def __init__(self, tools: Optional[Iterable[ITool]] = None) -> None:
        self._tools: Dict[str, ITool] = {}
        for tool in tools or ():
            self.register(tool)

    def register(self, tool: ITool) -> None:
        self._tools[tool.definition.name] = tool

    def get(self, name: str) -> Optional[ITool]:
        return self._tools.get(name)

    def require(self, name: str) -> ITool:
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' is not registered.")
        return tool

    def definitions(self, names: Optional[Sequence[str]] = None) -> Sequence[ToolDefinition]:
        if names is None:
            return tuple(tool.definition for tool in self._tools.values())
        return tuple(self.require(name).definition for name in names)

    def resolve(self, names: Sequence[str]) -> Sequence[ITool]:
        return tuple(self.require(name) for name in names)


def tool_to_openai_schema(definition: ToolDefinition) -> Dict[str, Any]:
    parameters = dict(definition.parameters)
    properties = parameters.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    required = parameters.get("required")
    if not isinstance(required, list):
        required = list(required or [])
    return {
        "type": "function",
        "function": {
            "name": definition.name,
            "description": definition.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": bool(parameters.get("additionalProperties", False)),
            },
        },
    }


def serialize_tool_result(result: ToolResult) -> str:
    if result.metadata:
        payload = {
            "tool_name": result.tool_name,
            "content": result.content,
            "is_error": result.is_error,
            "metadata": result.metadata,
        }
        return json.dumps(payload)
    return result.content
