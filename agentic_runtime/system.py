from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence

from .agents import AgentRegistry, ConfiguredLLMAgent
from .blackboard import EventSourcedBlackboard
from .config import runtime_config_from_dict
from .context_compiler import IContextCompiler, RuleBasedContextCompiler
from .controller import HybridAgentRuntimeV2
from .domain import AgentConfig, ChatMessage, ModelSettings, RuntimeConfig
from .llm import IChatModel, LiteLLMChatModel
from .mcp import MCPToolRegistry
from .planner import ConfigurableTaskPlanner
from .synthesizer import ResponseSynthesizer
from .tools import ToolRegistry
from .validators import BlackboardValidator


ModelFactory = Dict[str, IChatModel]


@dataclass
class MultiAgentSystem:
    runtime: HybridAgentRuntimeV2
    context_compiler: IContextCompiler
    mcp_registry: Optional[MCPToolRegistry] = None

    async def respond(self, query: str, chat_history: Sequence[ChatMessage] = ()) -> str:
        bb = EventSourcedBlackboard()
        self.context_compiler.compile(bb, query, chat_history)
        result = await self.runtime.run(bb)
        return result.state.final_response or ""

    async def aclose(self) -> None:
        if self.mcp_registry is not None:
            await self.mcp_registry.aclose()


async def build_multi_agent_system(
    config: RuntimeConfig | Dict[str, object],
    *,
    tool_registry: Optional[ToolRegistry] = None,
    model_overrides: Optional[ModelFactory] = None,
    context_compiler: Optional[IContextCompiler] = None,
    mcp_registry_override: Optional[MCPToolRegistry] = None,
) -> MultiAgentSystem:
    runtime_config = runtime_config_from_dict(config) if isinstance(config, dict) else config
    local_tools = tool_registry or ToolRegistry()
    mcp_registry = mcp_registry_override or (MCPToolRegistry(runtime_config.mcp_servers) if runtime_config.mcp_servers else None)
    if mcp_registry is not None:
        await mcp_registry.load()

    registry = AgentRegistry()
    for agent_config in runtime_config.agents:
        if not agent_config.enabled:
            continue
        registry.register(
            ConfiguredLLMAgent(
                config=agent_config,
                model=_resolve_model(agent_config, model_overrides or {}),
                tool_registry=local_tools,
                mcp_registry=mcp_registry,
            )
        )

    runtime = HybridAgentRuntimeV2(
        planner=ConfigurableTaskPlanner(runtime_config.agents),
        validator=BlackboardValidator(),
        synthesizer=ResponseSynthesizer(),
        registry=registry,
        max_parallel=runtime_config.max_parallel,
    )
    return MultiAgentSystem(
        runtime=runtime,
        context_compiler=context_compiler or RuleBasedContextCompiler(),
        mcp_registry=mcp_registry,
    )


def _resolve_model(agent_config: AgentConfig, overrides: ModelFactory) -> IChatModel:
    override = overrides.get(agent_config.name)
    if override is not None:
        return override
    settings: ModelSettings = agent_config.model
    if settings.provider != "litellm":
        raise ValueError(f"Unsupported model provider '{settings.provider}' for agent '{agent_config.name}'.")
    return LiteLLMChatModel(
        model=settings.model,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        api_base=settings.api_base,
        api_key=settings.api_key,
        extra=settings.extra,
    )
