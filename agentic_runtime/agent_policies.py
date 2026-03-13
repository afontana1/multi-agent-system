from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Sequence

from .blackboard import EventSourcedBlackboard
from .domain import AgentConfig, AgentResult, Fact, MemoryEntry, SubTask, ToolResult
from .mcp import MCPToolRegistry
from .tools import ITool, ToolRegistry


class MemoryStrategy(ABC):
    @abstractmethod
    def append(self, memory: List[MemoryEntry], role: str, content: str, window_size: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def recent(self, memory: Sequence[MemoryEntry], window_size: int) -> Sequence[MemoryEntry]:
        raise NotImplementedError


class WindowedMemoryStrategy(MemoryStrategy):
    def append(self, memory: List[MemoryEntry], role: str, content: str, window_size: int) -> None:
        memory.append(MemoryEntry(role=role, content=content))
        overflow = len(memory) - window_size
        if overflow > 0:
            del memory[:overflow]

    def recent(self, memory: Sequence[MemoryEntry], window_size: int) -> Sequence[MemoryEntry]:
        return tuple(memory[-window_size:])


class ContextStrategy(ABC):
    @abstractmethod
    def build_messages(
        self,
        config: AgentConfig,
        memory: Sequence[MemoryEntry],
        subtask: SubTask,
        bb: EventSourcedBlackboard,
    ) -> List[Dict[str, object]]:
        raise NotImplementedError


class DefaultContextStrategy(ContextStrategy):
    def build_messages(
        self,
        config: AgentConfig,
        memory: Sequence[MemoryEntry],
        subtask: SubTask,
        bb: EventSourcedBlackboard,
    ) -> List[Dict[str, object]]:
        messages: List[Dict[str, object]] = [{"role": "system", "content": config.system_prompt}]
        for entry in memory:
            messages.append({"role": entry.role, "content": entry.content})
        constraints = {key: value.value for key, value in bb.state.constraints.items()}
        facts = [fact.claim for fact in bb.active_facts()[-5:]]
        constraint_lines = "\n".join(f"- {key}: {value}" for key, value in constraints.items()) or "- none"
        fact_lines = "\n".join(f"- {fact}" for fact in facts) or "- none"
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Task:\n{subtask.description}\n\n"
                    f"Current user request:\n{bb.state.current_user_request}\n\n"
                    f"Interaction mode:\n{bb.state.interaction_mode}\n\n"
                    f"Constraints:\n{constraint_lines}\n\n"
                    f"Relevant facts:\n{fact_lines}\n\n"
                    "Answer the user directly. Use tools only if they are actually needed."
                ),
            }
        )
        return messages


class ToolExecutionStrategy(ABC):
    @abstractmethod
    async def resolve_tools(
        self,
        config: AgentConfig,
        tool_registry: ToolRegistry,
        mcp_registry: Optional[MCPToolRegistry],
    ) -> Sequence[ITool]:
        raise NotImplementedError

    @abstractmethod
    async def execute_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, object],
        tools: Sequence[ITool],
    ) -> ToolResult:
        raise NotImplementedError


class DefaultToolExecutionStrategy(ToolExecutionStrategy):
    async def resolve_tools(
        self,
        config: AgentConfig,
        tool_registry: ToolRegistry,
        mcp_registry: Optional[MCPToolRegistry],
    ) -> Sequence[ITool]:
        local_tools = list(tool_registry.resolve(config.tools)) if config.tools else []
        if mcp_registry is None or not config.mcp_servers:
            return tuple(local_tools)
        selected = set(config.mcp_servers)
        mcp_tools = await mcp_registry.load(config.mcp_servers)
        mcp_tools = [tool for tool in mcp_tools if tool.definition.metadata.get("server") in selected]
        return tuple(local_tools) + tuple(mcp_tools)

    async def execute_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, object],
        tools: Sequence[ITool],
    ) -> ToolResult:
        tool = next((item for item in tools if item.definition.name == tool_name), None)
        if tool is None:
            return ToolResult(tool_name=tool_name, content=f"Tool '{tool_name}' is not available.", is_error=True)
        return await tool.invoke(arguments)


class FinalizationStrategy(ABC):
    @abstractmethod
    def build_agent_result(
        self,
        config: AgentConfig,
        subtask: SubTask,
        bb: EventSourcedBlackboard,
        final_text: str,
        tool_results: Sequence[ToolResult],
    ) -> AgentResult:
        raise NotImplementedError


class DefaultFinalizationStrategy(FinalizationStrategy):
    def build_agent_result(
        self,
        config: AgentConfig,
        subtask: SubTask,
        bb: EventSourcedBlackboard,
        final_text: str,
        tool_results: Sequence[ToolResult],
    ) -> AgentResult:
        fact = Fact(
            claim=f"{config.name} produced a response for '{bb.state.current_user_request}'.",
            source=f"agent:{config.name}",
            confidence=0.7,
            turn_index=bb.state.turn_index,
            metadata={"response": final_text},
        )
        return AgentResult(
            agent_name=config.name,
            success=bool(final_text),
            output={
                "response": final_text,
                "tool_results": [self._tool_result_payload(result) for result in tool_results],
                "agent_description": config.description,
            },
            confidence=0.7,
            produced_facts=(fact,),
            completed_subtask_ids=(subtask.id,),
            errors=() if final_text else ("The model returned an empty response.",),
        )

    def _tool_result_payload(self, result: ToolResult) -> Dict[str, object]:
        return {
            "tool_name": result.tool_name,
            "content": result.content,
            "is_error": result.is_error,
            "metadata": dict(result.metadata),
        }
