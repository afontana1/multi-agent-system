from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence

from .agents import AgentRegistry, BaseAgent, ConfiguredLLMAgent, IExpertAgent, UtilityRouter
from .blackboard import EventSourcedBlackboard
from .config import runtime_config_from_dict
from .context_compiler import IContextCompiler, RuleBasedContextCompiler
from .controller import HybridAgentRuntimeV2
from .coordinator import CoordinatorAgent, CoordinatorConfig, CoordinatorTaskPlanner
from .domain import AgentConfig, ChatMessage, ModelSettings, RuntimeConfig
from .llm import IChatModel, LiteLLMChatModel
from .mcp import MCPToolRegistry
from .observability import RuntimeTraceLogger, default_trace_logger
from .planner import ConfigurableTaskPlanner
from .runtime_policies import RoutingPolicy, TaskPlanningPolicy
from .synthesizer import ResponseSynthesizer
from .tools import ToolRegistry
from .validators import BlackboardValidator


ModelFactory = Dict[str, IChatModel]


@dataclass(frozen=True)
class ResponseTrace:
    response: str
    agents_called: Sequence[str]
    selected_subtask_ids: Sequence[str]
    completed_subtasks: Sequence[str]
    failures: Sequence[str]
    results_by_agent: Dict[str, Sequence[Dict[str, object]]]


@dataclass
class MultiAgentSystem:
    runtime: HybridAgentRuntimeV2
    context_compiler: IContextCompiler
    mcp_registry: Optional[MCPToolRegistry] = None
    trace_logger: Optional[RuntimeTraceLogger] = None
    _request_count: int = 0

    async def respond(self, query: str, chat_history: Sequence[ChatMessage] = ()) -> str:
        trace = await self.respond_with_trace(query, chat_history)
        return trace.response

    async def respond_with_trace(self, query: str, chat_history: Sequence[ChatMessage] = ()) -> ResponseTrace:
        self._request_count += 1
        request_index = self._request_count
        request_id = f"req-{request_index:04d}"
        bb = EventSourcedBlackboard(
            observer=self.trace_logger,
            trace_context={"request_id": request_id, "request_index": request_index},
        )
        if self.trace_logger is not None:
            self.trace_logger.log(
                "request_received",
                request_id=request_id,
                request_index=request_index,
                query=query,
                chat_history=[{"role": message.role, "content": message.content, "turn_index": message.turn_index} for message in chat_history],
            )
        self.context_compiler.compile(bb, query, chat_history)
        result = await self.runtime.run(bb)
        state = result.state
        trace = ResponseTrace(
            response=state.final_response or "",
            agents_called=state.agents_called,
            selected_subtask_ids=state.selected_subtask_ids,
            completed_subtasks=state.completed_subtasks,
            failures=state.failures,
            results_by_agent={key: value for key, value in state.results_by_agent.items()},
        )
        if self.trace_logger is not None:
            self.trace_logger.log(
                "request_completed",
                request_id=request_id,
                request_index=request_index,
                query=query,
                response=trace.response,
                agents_called=list(trace.agents_called),
                selected_subtask_ids=list(trace.selected_subtask_ids),
                completed_subtasks=list(trace.completed_subtasks),
                failures=list(trace.failures),
                results_by_agent=trace.results_by_agent,
            )
        return trace

    @property
    def session_log_path(self) -> Optional[Path]:
        if self.trace_logger is None:
            return None
        return self.trace_logger.session_file

    async def aclose(self) -> None:
        if self.mcp_registry is not None:
            await self.mcp_registry.aclose()


async def build_multi_agent_system(
    config: RuntimeConfig | Dict[str, object] | None = None,
    *,
    agent_specs: Optional[Sequence[AgentConfig | Dict[str, object]]] = None,
    agents: Optional[Sequence[IExpertAgent]] = None,
    coordinator: Optional[CoordinatorAgent] = None,
    coordinator_spec: Optional[CoordinatorConfig | Dict[str, object]] = None,
    tool_registry: Optional[ToolRegistry] = None,
    model_overrides: Optional[ModelFactory] = None,
    context_compiler: Optional[IContextCompiler] = None,
    mcp_registry_override: Optional[MCPToolRegistry] = None,
    planning_policy: Optional[TaskPlanningPolicy] = None,
    routing_policy: Optional[RoutingPolicy] = None,
    trace_logger: Optional[RuntimeTraceLogger] = None,
) -> MultiAgentSystem:
    runtime_config = _normalize_runtime_config(config, agent_specs)
    local_tools = tool_registry or ToolRegistry()
    mcp_registry = mcp_registry_override or (MCPToolRegistry(runtime_config.mcp_servers) if runtime_config.mcp_servers else None)
    if mcp_registry is not None:
        await mcp_registry.load()

    registry = AgentRegistry()
    resolved_agents = list(agents or ())
    if not resolved_agents:
        resolved_agents.extend(
            _build_agents_from_specs(runtime_config.agents, local_tools, mcp_registry, model_overrides or {})
        )
    for agent in resolved_agents:
        registry.register(agent)

    base_planner = ConfigurableTaskPlanner(resolved_agents or runtime_config.agents, planning_policy=planning_policy)
    resolved_coordinator = coordinator or _build_coordinator(coordinator_spec, model_overrides or {})
    planner = CoordinatorTaskPlanner(resolved_coordinator, resolved_agents or runtime_config.agents, base_planner) if resolved_coordinator else base_planner

    runtime = HybridAgentRuntimeV2(
        planner=planner,
        validator=BlackboardValidator(),
        synthesizer=ResponseSynthesizer(),
        registry=registry,
        router=UtilityRouter(routing_policy) if routing_policy is not None else None,
        max_parallel=runtime_config.max_parallel,
    )
    return MultiAgentSystem(
        runtime=runtime,
        context_compiler=context_compiler or RuleBasedContextCompiler(),
        mcp_registry=mcp_registry,
        trace_logger=trace_logger or default_trace_logger(),
    )


def _normalize_runtime_config(
    config: RuntimeConfig | Dict[str, object] | None,
    agent_specs: Optional[Sequence[AgentConfig | Dict[str, object]]],
) -> RuntimeConfig:
    if config is None:
        if agent_specs is None:
            return RuntimeConfig(agents=())
        return RuntimeConfig(agents=tuple(_normalize_agent_spec(item) for item in agent_specs))
    runtime_config = runtime_config_from_dict(config) if isinstance(config, dict) else config
    if agent_specs is None:
        return runtime_config
    return RuntimeConfig(
        agents=tuple(_normalize_agent_spec(item) for item in agent_specs),
        mcp_servers=runtime_config.mcp_servers,
        max_parallel=runtime_config.max_parallel,
        interaction_mode=runtime_config.interaction_mode,
    )


def _normalize_agent_spec(spec: AgentConfig | Dict[str, object]) -> AgentConfig:
    if isinstance(spec, AgentConfig):
        return spec
    return runtime_config_from_dict({"agents": [spec]}).agents[0]


def _build_agents_from_specs(
    specs: Iterable[AgentConfig],
    tool_registry: ToolRegistry,
    mcp_registry: Optional[MCPToolRegistry],
    model_overrides: ModelFactory,
) -> Sequence[IExpertAgent]:
    out = []
    for agent_config in specs:
        if not agent_config.enabled:
            continue
        out.append(
            ConfiguredLLMAgent(
                agent_config,
                model=_resolve_model(agent_config, model_overrides),
                tool_registry=tool_registry,
                mcp_registry=mcp_registry,
            )
        )
    return tuple(out)


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


def _build_coordinator(
    coordinator_spec: CoordinatorConfig | Dict[str, object] | None,
    overrides: ModelFactory,
) -> CoordinatorAgent | None:
    if coordinator_spec is None:
        return None
    config = _normalize_coordinator_spec(coordinator_spec)
    override = overrides.get(config.name)
    model = override or LiteLLMChatModel(
        model=config.model.model,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens,
        api_base=config.model.api_base,
        api_key=config.model.api_key,
        extra=config.model.extra,
    )
    return CoordinatorAgent(config, model)


def _normalize_coordinator_spec(spec: CoordinatorConfig | Dict[str, object]) -> CoordinatorConfig:
    if isinstance(spec, CoordinatorConfig):
        return spec
    model_spec = spec["model"]
    model = ModelSettings(
        provider=str(model_spec.get("provider", "litellm")),
        model=str(model_spec["model"]),
        temperature=float(model_spec.get("temperature", 0.2)),
        max_tokens=model_spec.get("max_tokens"),
        api_base=model_spec.get("api_base"),
        api_key=model_spec.get("api_key"),
        extra={key: value for key, value in model_spec.items() if key not in {"provider", "model", "temperature", "max_tokens", "api_base", "api_key"}},
    )
    return CoordinatorConfig(
        name=str(spec.get("name", "coordinator")),
        system_prompt=str(spec["system_prompt"]),
        model=model,
        max_subtasks_per_round=int(spec.get("max_subtasks_per_round", 4)),
    )
