from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from .blackboard import EventSourcedBlackboard
from .domain import AgentResult, Fact, SubTask


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
