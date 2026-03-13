from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Sequence

from .blackboard import EventSourcedBlackboard
from .domain import AgentConfig, SubTask

if TYPE_CHECKING:
    from .agents import AgentRegistry, IExpertAgent


class TaskPlanningPolicy(ABC):
    @abstractmethod
    def build_plan(self, agents: Sequence[AgentConfig | "IExpertAgent"], bb: EventSourcedBlackboard) -> Sequence[SubTask]:
        raise NotImplementedError


class DefaultTaskPlanningPolicy(TaskPlanningPolicy):
    def build_plan(self, agents: Sequence[AgentConfig | "IExpertAgent"], bb: EventSourcedBlackboard) -> Sequence[SubTask]:
        if bb.state.subtasks:
            return tuple(bb.state.subtasks.values())
        query = bb.state.current_user_request or bb.state.goal
        keyword_matches = [agent for agent in agents if _matches_query(agent, query)]
        fallback_agents = [agent for agent in agents if not _selection_keywords(agent)]
        selected = keyword_matches or fallback_agents
        if not selected:
            selected = list(agents)
        subtasks = []
        for agent in selected:
            if hasattr(agent, "build_subtask") and hasattr(agent, "config"):
                base_subtask = agent.build_subtask(query)
                subtasks.append(SubTask(**{**base_subtask.__dict__, "id": _task_id()}))
            else:
                subtasks.append(
                    SubTask(
                        id=_task_id(),
                        description=f"Respond to the user query: {query}",
                        required_outputs=("response",),
                        assigned_agent=agent.name,
                    )
                )
        return tuple(subtasks)


class RoutingPolicy(ABC):
    @abstractmethod
    def choose(self, subtask: SubTask, bb: EventSourcedBlackboard, registry: "AgentRegistry") -> "IExpertAgent" | None:
        raise NotImplementedError


class DefaultRoutingPolicy(RoutingPolicy):
    def choose(self, subtask: SubTask, bb: EventSourcedBlackboard, registry: "AgentRegistry") -> "IExpertAgent" | None:
        if subtask.assigned_agent:
            return registry.get(subtask.assigned_agent)
        candidates = [a for a in registry.all() if a.can_handle(subtask, bb)]
        return max(candidates, key=lambda a: a.estimate_score(subtask, bb), default=None)


def is_enabled(agent: AgentConfig | "IExpertAgent") -> bool:
    if isinstance(agent, AgentConfig):
        return agent.enabled
    if hasattr(agent, "config"):
        return bool(agent.config.enabled)
    return True


def _matches_query(agent: AgentConfig | "IExpertAgent", query: str) -> bool:
    keywords = _selection_keywords(agent)
    if not keywords:
        return False
    query_lower = query.lower()
    return any(keyword.lower() in query_lower for keyword in keywords)


def _selection_keywords(agent: AgentConfig | "IExpertAgent") -> Sequence[str]:
    if hasattr(agent, "config"):
        return agent.config.selection_keywords
    if isinstance(agent, AgentConfig):
        return agent.selection_keywords
    return ()


def _task_id() -> str:
    return str(uuid.uuid4())[:8]
