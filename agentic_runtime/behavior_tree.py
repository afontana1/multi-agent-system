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
        status = Status.SUCCESS if self.predicate(bb) else Status.FAILURE
        bb.trace("bt_tick", node=self.name, node_type="condition", status=status.value)
        return status


@dataclass
class ActionNode(BTNode):
    name: str
    action: Any

    async def tick(self, bb: EventSourcedBlackboard) -> Status:
        result = self.action(bb)
        status = await result if asyncio.iscoroutine(result) else result
        bb.trace("bt_tick", node=self.name, node_type="action", status=status.value)
        return status


@dataclass
class SequenceNode(BTNode):
    name: str
    children: List[BTNode]
    _index: int = 0

    async def tick(self, bb: EventSourcedBlackboard) -> Status:
        while self._index < len(self.children):
            status = await self.children[self._index].tick(bb)
            if status == Status.RUNNING:
                bb.trace("bt_tick", node=self.name, node_type="sequence", status=status.value, child_index=self._index)
                return Status.RUNNING
            if status == Status.FAILURE:
                self._index = 0
                bb.trace("bt_tick", node=self.name, node_type="sequence", status=status.value)
                return Status.FAILURE
            self._index += 1
        self._index = 0
        bb.trace("bt_tick", node=self.name, node_type="sequence", status=Status.SUCCESS.value)
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
                bb.trace("bt_tick", node=self.name, node_type="selector", status=status.value, child_index=self._index)
                return Status.RUNNING
            if status == Status.SUCCESS:
                self._index = 0
                bb.trace("bt_tick", node=self.name, node_type="selector", status=status.value)
                return Status.SUCCESS
            self._index += 1
        self._index = 0
        bb.trace("bt_tick", node=self.name, node_type="selector", status=Status.FAILURE.value)
        return Status.FAILURE


@dataclass
class CooldownDecorator(BTNode):
    name: str
    child: BTNode
    cooldown_ticks: int
    _last_success_tick: Optional[int] = None

    async def tick(self, bb: EventSourcedBlackboard) -> Status:
        if self._last_success_tick is not None and bb.state.tick_count - self._last_success_tick < self.cooldown_ticks:
            bb.trace("bt_tick", node=self.name, node_type="cooldown", status=Status.FAILURE.value, reason="cooldown_active")
            return Status.FAILURE
        status = await self.child.tick(bb)
        if status == Status.SUCCESS:
            self._last_success_tick = bb.state.tick_count
        bb.trace("bt_tick", node=self.name, node_type="cooldown", status=status.value)
        return status


@dataclass
class ParallelJoinNode(BTNode):
    name: str
    children: List[BTNode]
    require_all_success: bool = True

    async def tick(self, bb: EventSourcedBlackboard) -> Status:
        results = await asyncio.gather(*(child.tick(bb) for child in self.children))
        if self.require_all_success:
            status = Status.SUCCESS if all(r == Status.SUCCESS for r in results) else Status.FAILURE
        else:
            status = Status.SUCCESS if any(r == Status.SUCCESS for r in results) else Status.FAILURE
        bb.trace("bt_tick", node=self.name, node_type="parallel_join", status=status.value, child_results=[result.value for result in results])
        return status
