from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Sequence

from .blackboard import EventSourcedBlackboard
from .domain import AgentConfig, AgentResult, Fact, SubTask, ToolResult
from .llm import IChatModel, openai_tool_result_message, to_openai_assistant_message
from .mcp import MCPToolRegistry
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
    def choose(self, subtask: SubTask, bb: EventSourcedBlackboard, registry: AgentRegistry) -> Optional[IExpertAgent]:
        if subtask.assigned_agent:
            return registry.get(subtask.assigned_agent)
        candidates = [a for a in registry.all() if a.can_handle(subtask, bb)]
        return max(candidates, key=lambda a: a.estimate_score(subtask, bb), default=None)


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


class ConfiguredLLMAgent(IExpertAgent):
    def __init__(
        self,
        *,
        config: AgentConfig,
        model: IChatModel,
        tool_registry: Optional[ToolRegistry] = None,
        mcp_registry: Optional[MCPToolRegistry] = None,
    ) -> None:
        self._config = config
        self._model = model
        self._tool_registry = tool_registry or ToolRegistry()
        self._mcp_registry = mcp_registry

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

    async def run(self, subtask: SubTask, bb: EventSourcedBlackboard) -> AgentResult:
        tools = await self._resolve_tools()
        messages = self._build_messages(subtask, bb)
        tool_results: List[ToolResult] = []
        final_text = ""

        for _ in range(self._config.max_tool_rounds + 1):
            response = await self._model.complete(messages, [tool.definition for tool in tools])
            messages.append(to_openai_assistant_message(response.message))
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    tool = next((item for item in tools if item.definition.name == tool_call.name), None)
                    if tool is None:
                        result = ToolResult(tool_name=tool_call.name, content=f"Tool '{tool_call.name}' is not available.", is_error=True)
                    else:
                        result = await tool.invoke(tool_call.arguments)
                    tool_results.append(result)
                    messages.append(openai_tool_result_message(tool_call.id, tool_call.name, serialize_tool_result(result)))
                continue
            final_text = response.content.strip()
            break

        if not final_text and tool_results:
            final_text = "\n".join(result.content for result in tool_results if result.content)

        fact = Fact(
            claim=f"{self.name} produced a response for '{bb.state.current_user_request}'.",
            source=f"agent:{self.name}",
            confidence=0.7,
            turn_index=bb.state.turn_index,
            metadata={"response": final_text},
        )
        return AgentResult(
            agent_name=self.name,
            success=bool(final_text),
            output={
                "response": final_text,
                "tool_results": [self._tool_result_payload(result) for result in tool_results],
                "agent_description": self._config.description,
            },
            confidence=0.7,
            produced_facts=(fact,),
            completed_subtask_ids=(subtask.id,),
            errors=() if final_text else ("The model returned an empty response.",),
        )

    def _build_messages(self, subtask: SubTask, bb: EventSourcedBlackboard) -> List[Dict[str, object]]:
        context = {
            "request": bb.state.current_user_request,
            "mode": bb.state.interaction_mode,
            "constraints": {key: value.value for key, value in bb.state.constraints.items()},
            "facts": [fact.claim for fact in bb.active_facts()[-5:]],
        }
        return [
            {"role": "system", "content": self._config.system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": subtask.description,
                        "context": context,
                    }
                ),
            },
        ]

    async def _resolve_tools(self) -> Sequence[ITool]:
        local_tools = list(self._tool_registry.resolve(self._config.tools)) if self._config.tools else []
        if self._mcp_registry is None:
            return tuple(local_tools)
        mcp_tools = await self._mcp_registry.load(self._config.mcp_servers or None)
        if self._config.mcp_servers:
            selected = set(self._config.mcp_servers)
            mcp_tools = [tool for tool in mcp_tools if tool.definition.metadata.get("server") in selected]
        return tuple(local_tools) + tuple(mcp_tools)

    def _tool_result_payload(self, result: ToolResult) -> Dict[str, object]:
        return {
            "tool_name": result.tool_name,
            "content": result.content,
            "is_error": result.is_error,
            "metadata": dict(result.metadata),
        }
