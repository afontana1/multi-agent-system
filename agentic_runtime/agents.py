from __future__ import annotations

import asyncio
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .agent_policies import (
    ContextStrategy,
    DefaultContextStrategy,
    DefaultFinalizationStrategy,
    DefaultToolExecutionStrategy,
    FinalizationStrategy,
    MemoryStrategy,
    ToolExecutionStrategy,
    WindowedMemoryStrategy,
)
from .blackboard import EventSourcedBlackboard
from .domain import AgentConfig, AgentResult, MemoryEntry, SubTask, ToolResult
from .llm import IChatModel, openai_tool_result_message, to_openai_assistant_message
from .mcp import MCPToolRegistry
from .runtime_policies import DefaultRoutingPolicy, RoutingPolicy
from .tools import ITool, ToolRegistry, serialize_tool_result


class IExpertAgent(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def can_handle(self, subtask: SubTask, bb: EventSourcedBlackboard) -> bool:
        raise NotImplementedError

    @abstractmethod
    def estimate_score(self, subtask: SubTask, bb: EventSourcedBlackboard) -> float:
        raise NotImplementedError

    @abstractmethod
    async def run(self, subtask: SubTask, bb: EventSourcedBlackboard) -> AgentResult:
        raise NotImplementedError


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: Dict[str, IExpertAgent] = {}

    def register(self, agent: IExpertAgent) -> None:
        self._agents[agent.name] = agent

    def all(self) -> List[IExpertAgent]:
        return list(self._agents.values())

    def get(self, name: str) -> Optional[IExpertAgent]:
        return self._agents.get(name)


class UtilityRouter:
    def __init__(self, routing_policy: RoutingPolicy | None = None) -> None:
        self._routing_policy = routing_policy or DefaultRoutingPolicy()

    def choose(self, subtask: SubTask, bb: EventSourcedBlackboard, registry: AgentRegistry) -> Optional[IExpertAgent]:
        return self._routing_policy.choose(subtask, bb, registry)


class BaseAgent(IExpertAgent):
    def __init__(self, config: AgentConfig, *, memory_strategy: Optional[MemoryStrategy] = None) -> None:
        self._config = config
        self._memory: List[MemoryEntry] = []
        self._memory_strategy = memory_strategy or WindowedMemoryStrategy()

    @property
    def config(self) -> AgentConfig:
        return self._config

    @property
    def capabilities(self) -> Sequence[str]:
        return self._config.capabilities

    @property
    def name(self) -> str:
        return self._config.name

    def can_handle(self, subtask: SubTask, bb: EventSourcedBlackboard) -> bool:
        if subtask.assigned_agent == self.name:
            return True
        if not self._config.selection_keywords:
            return True
        text = f"{subtask.description} {bb.state.current_user_request}".lower()
        return any(keyword.lower() in text for keyword in self._config.selection_keywords)

    def estimate_score(self, subtask: SubTask, bb: EventSourcedBlackboard) -> float:
        if subtask.assigned_agent == self.name:
            return 1.0
        text = f"{subtask.description} {bb.state.current_user_request}".lower()
        hits = sum(1 for keyword in self._config.selection_keywords if keyword.lower() in text)
        return min(self._config.score_bias + (0.1 * hits), 0.99)

    def append_memory(self, role: str, content: str) -> None:
        self._memory_strategy.append(self._memory, role, content, self._config.memory_window)

    def recent_memory(self) -> Sequence[MemoryEntry]:
        return self._memory_strategy.recent(self._memory, self._config.memory_window)

    def estimate_window_size(self) -> int:
        return self._config.memory_window

    def build_subtask(self, query: str, priority: Optional[int] = None) -> SubTask:
        return SubTask(
            id="",
            description=self._config.task_template.format(query=query),
            required_outputs=("response",),
            assigned_agent=self.name,
            lane=self._config.lane,
            priority=self._config.priority if priority is None else priority,
        )


class BaseLLMAgent(BaseAgent):
    def __init__(
        self,
        config: AgentConfig,
        *,
        model: IChatModel,
        tool_registry: Optional[ToolRegistry] = None,
        mcp_registry: Optional[MCPToolRegistry] = None,
        memory_strategy: Optional[MemoryStrategy] = None,
        context_strategy: Optional[ContextStrategy] = None,
        tool_execution_strategy: Optional[ToolExecutionStrategy] = None,
        finalization_strategy: Optional[FinalizationStrategy] = None,
    ) -> None:
        super().__init__(config, memory_strategy=memory_strategy)
        self._model = model
        self._tool_registry = tool_registry or ToolRegistry()
        self._mcp_registry = mcp_registry
        self._context_strategy = context_strategy or DefaultContextStrategy()
        self._tool_execution_strategy = tool_execution_strategy or DefaultToolExecutionStrategy()
        self._finalization_strategy = finalization_strategy or DefaultFinalizationStrategy()

    async def invoke_model(self, messages: Sequence[Dict[str, object]], tools: Sequence[ITool]):
        return await self._model.complete(messages, [tool.definition for tool in tools])

    async def run(self, subtask: SubTask, bb: EventSourcedBlackboard) -> AgentResult:
        tools = await self.resolve_tools()
        messages = self.build_messages(subtask, bb)
        tool_results: List[ToolResult] = []
        final_text = ""

        for _ in range(self.config.max_tool_rounds + 1):
            response = await self.invoke_model(messages, tools)
            messages.append(to_openai_assistant_message(response.message))
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    result = await self.execute_tool_call(tool_call.name, tool_call.id, tool_call.arguments, tools)
                    tool_results.append(result)
                    messages.append(openai_tool_result_message(tool_call.id, tool_call.name, serialize_tool_result(result)))
                continue
            final_text = response.content.strip()
            break

        # Some models finish tool use without producing a natural-language answer.
        # In that case, ask once more with the existing conversation but no tools.
        if not final_text:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Respond to the user with a direct plain-text answer now. "
                        "Do not call tools. If tool results were gathered, use them."
                    ),
                }
            )
            follow_up = await self.invoke_model(messages, ())
            messages.append(to_openai_assistant_message(follow_up.message))
            final_text = (follow_up.content or "").strip()

        if not final_text and tool_results:
            final_text = "\n".join(result.content for result in tool_results if result.content)

        if not final_text:
            _log_empty_agent_response(self.config.name, bb, messages, tool_results)

        self.append_memory("user", bb.state.current_user_request)
        if final_text:
            self.append_memory("assistant", final_text)

        return self.build_agent_result(subtask, bb, final_text, tool_results)

    def build_messages(self, subtask: SubTask, bb: EventSourcedBlackboard) -> List[Dict[str, object]]:
        return self._context_strategy.build_messages(
            self.config,
            self.recent_memory(),
            subtask,
            bb,
        )

    async def resolve_tools(self) -> Sequence[ITool]:
        return await self._tool_execution_strategy.resolve_tools(self.config, self._tool_registry, self._mcp_registry)

    async def execute_tool_call(self, tool_name: str, tool_call_id: str, arguments: Dict[str, object], tools: Sequence[ITool]) -> ToolResult:
        return await self._tool_execution_strategy.execute_tool_call(tool_name, arguments, tools)

    def build_agent_result(
        self,
        subtask: SubTask,
        bb: EventSourcedBlackboard,
        final_text: str,
        tool_results: Sequence[ToolResult],
    ) -> AgentResult:
        return self._finalization_strategy.build_agent_result(self.config, subtask, bb, final_text, tool_results)


class ConfiguredLLMAgent(BaseLLMAgent):
    pass


class PlannerExpert(IExpertAgent):
    @property
    def name(self) -> str:
        return "planner_expert"

    def can_handle(self, subtask: SubTask, bb: EventSourcedBlackboard) -> bool:
        return any(k in subtask.description.lower() for k in ("plan", "decompose", "design"))

    def estimate_score(self, subtask: SubTask, bb: EventSourcedBlackboard) -> float:
        return 0.95

    async def run(self, subtask: SubTask, bb: EventSourcedBlackboard) -> AgentResult:
        await asyncio.sleep(0.01)
        fact = Fact(claim=f"A plan for '{subtask.description}' was produced.", source=f"agent:{self.name}", confidence=0.9, turn_index=bb.state.turn_index)
        return AgentResult(agent_name=self.name, success=True, output={"plan": ["decompose", "implement", "validate"]}, confidence=0.9, produced_facts=(fact,), completed_subtask_ids=(subtask.id,))


class CodingExpert(IExpertAgent):
    @property
    def name(self) -> str:
        return "coding_expert"

    def can_handle(self, subtask: SubTask, bb: EventSourcedBlackboard) -> bool:
        return any(k in subtask.description.lower() for k in ("implement", "code", "class", "runtime", "schema"))

    def estimate_score(self, subtask: SubTask, bb: EventSourcedBlackboard) -> float:
        score = 0.8
        if bb.get_constraint("preferred_language") == "python":
            score += 0.15
        return min(score, 1.0)

    async def run(self, subtask: SubTask, bb: EventSourcedBlackboard) -> AgentResult:
        await asyncio.sleep(0.01)
        fact = Fact(claim=f"Implementation draft for '{subtask.description}' created.", source=f"agent:{self.name}", confidence=0.8, turn_index=bb.state.turn_index)
        return AgentResult(agent_name=self.name, success=True, output={"code_fragment": f"# code for: {subtask.description}"}, confidence=0.8, produced_facts=(fact,), completed_subtask_ids=(subtask.id,))


class VerifierExpert(IExpertAgent):
    @property
    def name(self) -> str:
        return "verifier_expert"

    def can_handle(self, subtask: SubTask, bb: EventSourcedBlackboard) -> bool:
        return any(k in subtask.description.lower() for k in ("validate", "verify", "check"))

    def estimate_score(self, subtask: SubTask, bb: EventSourcedBlackboard) -> float:
        return 0.92

    async def run(self, subtask: SubTask, bb: EventSourcedBlackboard) -> AgentResult:
        await asyncio.sleep(0.01)
        return AgentResult(agent_name=self.name, success=True, output={"verification": "Passed structural checks."}, confidence=0.88, completed_subtask_ids=(subtask.id,))


class RetrievalExpert(IExpertAgent):
    @property
    def name(self) -> str:
        return "retrieval_expert"

    def can_handle(self, subtask: SubTask, bb: EventSourcedBlackboard) -> bool:
        return any(k in subtask.description.lower() for k in ("retrieve", "research", "gather"))

    def estimate_score(self, subtask: SubTask, bb: EventSourcedBlackboard) -> float:
        return 0.87

    async def run(self, subtask: SubTask, bb: EventSourcedBlackboard) -> AgentResult:
        await asyncio.sleep(0.01)
        return AgentResult(agent_name=self.name, success=True, output={"documents": ["doc-a", "doc-b"]}, confidence=0.78, completed_subtask_ids=(subtask.id,))


def _log_empty_agent_response(
    agent_name: str,
    bb: EventSourcedBlackboard,
    messages: Sequence[Dict[str, object]],
    tool_results: Sequence[ToolResult],
) -> None:
    if os.getenv("DEBUG_EMPTY_RESPONSES", "1").strip().lower() not in {"1", "true", "yes", "on"}:
        return

    payload = {
        "agent": agent_name,
        "request": bb.state.current_user_request,
        "interaction_mode": bb.state.interaction_mode,
        "messages": [_json_safe_message(message) for message in messages],
        "tool_results": [
            {
                "tool_name": result.tool_name,
                "content": result.content,
                "is_error": result.is_error,
                "metadata": dict(result.metadata),
            }
            for result in tool_results
        ],
    }
    path = Path(os.getenv("DEBUG_EMPTY_RESPONSE_LOG_PATH", "logs/empty_agent_responses.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True, default=str) + "\n")


def _json_safe_message(message: Dict[str, object]) -> Dict[str, object]:
    payload: Dict[str, object] = {}
    for key, value in message.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            payload[key] = value
        else:
            payload[key] = json.loads(json.dumps(value, ensure_ascii=True, default=str))
    return payload
