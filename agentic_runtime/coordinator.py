from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

from .blackboard import EventSourcedBlackboard
from .domain import AgentConfig, ModelSettings, SubTask
from .llm import IChatModel
from .planner import ITaskPlanner


@dataclass(frozen=True)
class CoordinatorConfig:
    name: str
    system_prompt: str
    model: ModelSettings
    max_subtasks_per_round: int = 4


class CoordinatorAgent:
    def __init__(self, config: CoordinatorConfig, model: IChatModel) -> None:
        self._config = config
        self._model = model

    @property
    def name(self) -> str:
        return self._config.name

    async def plan(self, bb: EventSourcedBlackboard, agents: Sequence[AgentConfig | object]) -> Sequence[Dict[str, object]]:
        task_snapshot = bb.task_status_snapshot()
        messages = [
            {"role": "system", "content": self._config.system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "request": bb.state.current_user_request,
                        "task_status": task_snapshot,
                        "agent_catalog": [_agent_descriptor(agent) for agent in agents],
                        "instructions": {
                            "return_json": True,
                            "format": {
                                "subtasks": [
                                    {
                                        "description": "string",
                                        "assigned_agent": "agent_name",
                                        "priority": 50,
                                    }
                                ]
                            },
                        },
                    }
                ),
            },
        ]
        response = await self._model.complete(messages)
        try:
            payload = json.loads(response.content or "{}")
        except json.JSONDecodeError:
            return ()
        subtasks = payload.get("subtasks", [])
        if not isinstance(subtasks, list):
            return ()
        return tuple(subtasks[: self._config.max_subtasks_per_round])


class CoordinatorTaskPlanner(ITaskPlanner):
    def __init__(self, coordinator: CoordinatorAgent, agents: Sequence[AgentConfig | object], fallback_planner: ITaskPlanner) -> None:
        self._coordinator = coordinator
        self._agents = tuple(agents)
        self._fallback_planner = fallback_planner
        self._counter = 0

    def build_plan(self, bb: EventSourcedBlackboard) -> Sequence[SubTask]:
        raise RuntimeError("CoordinatorTaskPlanner requires async_build_plan().")

    async def async_build_plan(self, bb: EventSourcedBlackboard) -> Sequence[SubTask]:
        active = [task for task in bb.state.subtasks.values() if task.status in {"pending", "running"}]
        if active:
            return tuple(active)

        planned = await self._coordinator.plan(bb, self._agents)
        novel = self._novel_subtasks(planned, bb)
        if novel:
            return novel
        return self._fallback_planner.build_plan(bb)

    def _novel_subtasks(self, planned: Iterable[Dict[str, object]], bb: EventSourcedBlackboard) -> Sequence[SubTask]:
        existing = {(task.description, task.assigned_agent) for task in bb.state.subtasks.values()}
        out: List[SubTask] = []
        for item in planned:
            description = str(item.get("description", "")).strip()
            assigned_agent = item.get("assigned_agent")
            if not description:
                continue
            key = (description, assigned_agent)
            if key in existing:
                continue
            out.append(
                SubTask(
                    id=self._id(),
                    description=description,
                    required_outputs=("response",),
                    assigned_agent=str(assigned_agent) if assigned_agent else None,
                    priority=int(item.get("priority", 50)),
                )
            )
        return tuple(out)

    def _id(self) -> str:
        self._counter += 1
        return f"coord-{self._counter:04d}"


def _agent_descriptor(agent: AgentConfig | object) -> Dict[str, object]:
    if isinstance(agent, AgentConfig):
        return {
            "name": agent.name,
            "description": agent.description,
            "capabilities": list(agent.capabilities),
            "keywords": list(agent.selection_keywords),
            "lane": agent.lane,
        }
    config = getattr(agent, "config", None)
    if config is not None:
        return {
            "name": config.name,
            "description": config.description,
            "capabilities": list(config.capabilities),
            "keywords": list(config.selection_keywords),
            "lane": config.lane,
        }
    return {"name": getattr(agent, "name", "unknown"), "description": "", "capabilities": [], "keywords": [], "lane": "default"}
