from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, List, Optional

from .blackboard import EventSourcedBlackboard
from .domain import Status


class BTNode(ABC):
    @abstractmethod
    async def tick(self, bb: EventSourcedBlackboard) -> Status:
        raise NotImplementedError


@dataclass
class ConditionNode(BTNode):
    name: str
    predicate: Any

    async def tick(self, bb: EventSourcedBlackboard) -> Status:
        return Status.SUCCESS if self.predicate(bb) else Status.FAILURE


@dataclass
class ActionNode(BTNode):
    name: str
    action: Any

    async def tick(self, bb: EventSourcedBlackboard) -> Status:
        result = self.action(bb)
        return await result if asyncio.iscoroutine(result) else result


@dataclass
class SequenceNode(BTNode):
    name: str
    children: List[BTNode]
    _index: int = 0

    async def tick(self, bb: EventSourcedBlackboard) -> Status:
        while self._index < len(self.children):
            status = await self.children[self._index].tick(bb)
            if status == Status.RUNNING:
                return Status.RUNNING
            if status == Status.FAILURE:
                self._index = 0
                return Status.FAILURE
            self._index += 1
        self._index = 0
        return Status.SUCCESS


@dataclass
class SelectorNode(BTNode):
    name: str
    children: List[BTNode]
    _index: int = 0

    async def tick(self, bb: EventSourcedBlackboard) -> Status:
        while self._index < len(self.children):
            status = await self.children[self._index].tick(bb)
            if status == Status.RUNNING:
                return Status.RUNNING
            if status == Status.SUCCESS:
                self._index = 0
                return Status.SUCCESS
            self._index += 1
        self._index = 0
        return Status.FAILURE


@dataclass
class CooldownDecorator(BTNode):
    name: str
    child: BTNode
    cooldown_ticks: int
    _last_success_tick: Optional[int] = None

    async def tick(self, bb: EventSourcedBlackboard) -> Status:
        if self._last_success_tick is not None and bb.state.tick_count - self._last_success_tick < self.cooldown_ticks:
            return Status.FAILURE
        status = await self.child.tick(bb)
        if status == Status.SUCCESS:
            self._last_success_tick = bb.state.tick_count
        return status


@dataclass
class ParallelJoinNode(BTNode):
    name: str
    children: List[BTNode]
    require_all_success: bool = True

    async def tick(self, bb: EventSourcedBlackboard) -> Status:
        results = await asyncio.gather(*(child.tick(bb) for child in self.children))
        if self.require_all_success:
            return Status.SUCCESS if all(r == Status.SUCCESS for r in results) else Status.FAILURE
        return Status.SUCCESS if any(r == Status.SUCCESS for r in results) else Status.FAILURE
