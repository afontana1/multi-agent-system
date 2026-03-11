from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Sequence

from .blackboard import EventSourcedBlackboard
from .domain import AgentConfig, SubTask


class ITaskPlanner(ABC):
    @abstractmethod
    def build_plan(self, bb: EventSourcedBlackboard) -> Sequence[SubTask]:
        raise NotImplementedError


class SimpleTaskPlanner(ITaskPlanner):
    def build_plan(self, bb: EventSourcedBlackboard) -> Sequence[SubTask]:
        if bb.state.subtasks:
            return tuple(bb.state.subtasks.values())
        t1 = SubTask(id=self._id(), description="Design runtime decomposition", lane="analysis", priority=10)
        t2 = SubTask(id=self._id(), description="Implement event-sourced blackboard schema", dependencies=(t1.id,), lane="code", priority=20, join_key="build-core")
        t3 = SubTask(id=self._id(), description="Implement async execution runtime", dependencies=(t1.id,), lane="code", priority=20, join_key="build-core")
        t4 = SubTask(id=self._id(), description="Validate extensibility and SOLID structure", dependencies=(t2.id, t3.id), lane="verify", priority=30)
        return (t1, t2, t3, t4)

    def _id(self) -> str:
        return str(uuid.uuid4())[:8]


class ConfigurableTaskPlanner(ITaskPlanner):
    def __init__(self, agents: Sequence[AgentConfig]) -> None:
        self._agents = tuple(agent for agent in agents if agent.enabled)

    def build_plan(self, bb: EventSourcedBlackboard) -> Sequence[SubTask]:
        if bb.state.subtasks:
            return tuple(bb.state.subtasks.values())
        query = bb.state.current_user_request or bb.state.goal
        selected = [agent for agent in self._agents if _matches_query(agent, query)]
        if not selected:
            selected = list(self._agents)
        return tuple(
            SubTask(
                id=self._id(),
                description=agent.task_template.format(query=query),
                required_outputs=("response",),
                assigned_agent=agent.name,
                lane=agent.lane,
                priority=agent.priority,
            )
            for agent in selected
        )

    def _id(self) -> str:
        return str(uuid.uuid4())[:8]


def _matches_query(agent: AgentConfig, query: str) -> bool:
    if not agent.selection_keywords:
        return True
    query_lower = query.lower()
    return any(keyword.lower() in query_lower for keyword in agent.selection_keywords)
