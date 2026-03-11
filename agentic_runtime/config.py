from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .domain import AgentConfig, MCPServerConfig, ModelSettings, RuntimeConfig


def runtime_config_from_dict(data: Mapping[str, Any]) -> RuntimeConfig:
    return RuntimeConfig(
        agents=tuple(_agent_config_from_dict(item) for item in data.get("agents", [])),
        mcp_servers=tuple(_mcp_server_from_dict(item) for item in data.get("mcp_servers", [])),
        max_parallel=int(data.get("max_parallel", 3)),
        interaction_mode=str(data.get("interaction_mode", "general")),
    )


def load_runtime_config(path: str | Path) -> RuntimeConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return runtime_config_from_dict(payload)


def _agent_config_from_dict(data: Mapping[str, Any]) -> AgentConfig:
    return AgentConfig(
        name=str(data["name"]),
        model=_model_settings_from_dict(data["model"]),
        system_prompt=str(data["system_prompt"]),
        description=str(data.get("description", "")),
        selection_keywords=tuple(_to_strs(data.get("selection_keywords", ()))),
        task_template=str(data.get("task_template", "Respond to the user query: {query}")),
        tools=tuple(_to_strs(data.get("tools", ()))),
        mcp_servers=tuple(_to_strs(data.get("mcp_servers", ()))),
        score_bias=float(data.get("score_bias", 0.5)),
        priority=int(data.get("priority", 50)),
        lane=str(data.get("lane", "default")),
        max_tool_rounds=int(data.get("max_tool_rounds", 4)),
        enabled=bool(data.get("enabled", True)),
    )


def _model_settings_from_dict(data: Mapping[str, Any]) -> ModelSettings:
    extra = {key: value for key, value in data.items() if key not in {"provider", "model", "temperature", "max_tokens", "api_base", "api_key"}}
    return ModelSettings(
        provider=str(data.get("provider", "litellm")),
        model=str(data["model"]),
        temperature=float(data.get("temperature", 0.2)),
        max_tokens=data.get("max_tokens"),
        api_base=data.get("api_base"),
        api_key=data.get("api_key"),
        extra=extra,
    )


def _mcp_server_from_dict(data: Mapping[str, Any]) -> MCPServerConfig:
    return MCPServerConfig(
        name=str(data["name"]),
        url=str(data["url"]),
        headers={str(key): str(value) for key, value in dict(data.get("headers", {})).items()},
        enabled=bool(data.get("enabled", True)),
    )


def _to_strs(values: Iterable[Any]) -> Iterable[str]:
    for value in values:
        yield str(value)
