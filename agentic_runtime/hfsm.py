from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict

from .blackboard import BlackboardState, EventSourcedBlackboard
from .domain import LifecycleState


class IState(ABC):
    @property
    @abstractmethod
    def name(self) -> LifecycleState:
        raise NotImplementedError

    async def on_enter(self, bb: EventSourcedBlackboard) -> None:
        bb._state = BlackboardState(**{**bb.state.__dict__, "lifecycle_state": self.name})

    @abstractmethod
    async def on_update(self, bb: EventSourcedBlackboard) -> LifecycleState:
        raise NotImplementedError

    async def on_exit(self, bb: EventSourcedBlackboard) -> None:
        return None


@dataclass
class HFSM:
    states: Dict[LifecycleState, IState]
    initial: LifecycleState

    def __post_init__(self) -> None:
        self._current = self.states[self.initial]

    @property
    def current(self) -> IState:
        return self._current

    async def start(self, bb: EventSourcedBlackboard) -> None:
        self._current = self.states[self.initial]
        bb.trace("hfsm_start", initial_state=self.initial.value)
        await self._current.on_enter(bb)
        bb.trace("hfsm_state_enter", state=self._current.name.value)

    async def tick(self, bb: EventSourcedBlackboard) -> None:
        bb.trace("hfsm_tick", state=self._current.name.value, tick_count=bb.state.tick_count)
        next_state = await self._current.on_update(bb)
        if next_state != self._current.name:
            bb.trace("hfsm_transition", from_state=self._current.name.value, to_state=next_state.value)
            await self._current.on_exit(bb)
            self._current = self.states[next_state]
            await self._current.on_enter(bb)
            bb.trace("hfsm_state_enter", state=self._current.name.value)
