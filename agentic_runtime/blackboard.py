from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .domain import AgentResult, Constraint, DomainEvent, EventType, Fact, LifecycleState, SubTask, ValidationReport


@dataclass(frozen=True)
class BlackboardState:
    current_user_request: str = ""
    interaction_mode: str = "general"
    turn_index: int = 0
    chat_history: Tuple[Dict[str, Any], ...] = ()
    history_summary: Dict[str, Any] = field(default_factory=dict)

    goal: str = ""
    subtasks: Dict[str, SubTask] = field(default_factory=dict)
    open_questions: Tuple[str, ...] = ()
    completed_subtasks: Tuple[str, ...] = ()
    task_status: str = "new"

    constraints: Dict[str, Constraint] = field(default_factory=dict)
    facts: Tuple[Fact, ...] = ()
    artifacts: Dict[str, Any] = field(default_factory=dict)

    agents_called: Tuple[str, ...] = ()
    results_by_agent: Dict[str, Tuple[Dict[str, Any], ...]] = field(default_factory=dict)
    retry_counts: Dict[str, int] = field(default_factory=dict)
    failures: Tuple[str, ...] = ()
    selected_subtask_ids: Tuple[str, ...] = ()

    missing_items: Tuple[str, ...] = ()
    conflicts: Tuple[str, ...] = ()
    unsupported_claims: Tuple[str, ...] = ()
    ready_to_respond: bool = False

    lifecycle_state: LifecycleState = LifecycleState.INTAKE
    done: bool = False
    final_response: Optional[str] = None
    max_ticks: int = 50
    tick_count: int = 0


class BlackboardPatch(ABC):
    @abstractmethod
    def to_events(self, state: BlackboardState) -> Sequence[DomainEvent]:
        raise NotImplementedError


@dataclass(frozen=True)
class SetRequestPatch(BlackboardPatch):
    request: str
    turn_index: int

    def to_events(self, state: BlackboardState) -> Sequence[DomainEvent]:
        return [DomainEvent(EventType.USER_MESSAGE, {"content": self.request}, self.turn_index)]


@dataclass(frozen=True)
class SetModePatch(BlackboardPatch):
    mode: str
    turn_index: int

    def to_events(self, state: BlackboardState) -> Sequence[DomainEvent]:
        return [DomainEvent(EventType.MODE_SET, {"mode": self.mode}, self.turn_index)]


@dataclass(frozen=True)
class SetConstraintPatch(BlackboardPatch):
    constraint: Constraint

    def to_events(self, state: BlackboardState) -> Sequence[DomainEvent]:
        return [DomainEvent(EventType.CONSTRAINT_SET, {"constraint": self.constraint}, self.constraint.source_turn)]


@dataclass(frozen=True)
class AddFactPatch(BlackboardPatch):
    fact: Fact

    def to_events(self, state: BlackboardState) -> Sequence[DomainEvent]:
        return [DomainEvent(EventType.FACT_ADDED, {"fact": self.fact}, self.fact.turn_index)]


@dataclass(frozen=True)
class AddSubTaskPatch(BlackboardPatch):
    subtask: SubTask
    turn_index: int

    def to_events(self, state: BlackboardState) -> Sequence[DomainEvent]:
        return [DomainEvent(EventType.SUBTASK_ADDED, {"subtask": self.subtask}, self.turn_index)]


@dataclass(frozen=True)
class UpdateSubTaskPatch(BlackboardPatch):
    subtask: SubTask
    turn_index: int

    def to_events(self, state: BlackboardState) -> Sequence[DomainEvent]:
        return [DomainEvent(EventType.SUBTASK_UPDATED, {"subtask": self.subtask}, self.turn_index)]


@dataclass(frozen=True)
class RecordAgentSelectionPatch(BlackboardPatch):
    agent_name: str
    subtask_id: str
    turn_index: int

    def to_events(self, state: BlackboardState) -> Sequence[DomainEvent]:
        return [DomainEvent(EventType.AGENT_SELECTED, {"agent": self.agent_name, "subtask_id": self.subtask_id}, self.turn_index)]


@dataclass(frozen=True)
class RecordAgentResultPatch(BlackboardPatch):
    result: AgentResult
    turn_index: int

    def to_events(self, state: BlackboardState) -> Sequence[DomainEvent]:
        events: List[DomainEvent] = [DomainEvent(EventType.AGENT_RESULT_RECORDED, {"result": self.result}, self.turn_index)]
        for fact in self.result.produced_facts:
            events.append(DomainEvent(EventType.FACT_ADDED, {"fact": fact}, fact.turn_index))
        for subtask_id in self.result.completed_subtask_ids:
            events.append(DomainEvent(EventType.SUBTASK_COMPLETED, {"subtask_id": subtask_id}, self.turn_index))
        return events


@dataclass(frozen=True)
class RecordFailurePatch(BlackboardPatch):
    message: str
    turn_index: int

    def to_events(self, state: BlackboardState) -> Sequence[DomainEvent]:
        return [DomainEvent(EventType.FAILURE_RECORDED, {"message": self.message}, self.turn_index)]


@dataclass(frozen=True)
class SetValidationPatch(BlackboardPatch):
    report: ValidationReport
    turn_index: int

    def to_events(self, state: BlackboardState) -> Sequence[DomainEvent]:
        event_type = EventType.VALIDATION_PASSED if self.report.ready_to_respond else EventType.VALIDATION_FAILED
        return [DomainEvent(event_type, {"report": self.report}, self.turn_index)]


@dataclass(frozen=True)
class SetFinalResponsePatch(BlackboardPatch):
    response: str
    turn_index: int

    def to_events(self, state: BlackboardState) -> Sequence[DomainEvent]:
        return [DomainEvent(EventType.FINAL_RESPONSE_SET, {"response": self.response}, self.turn_index)]


class BlackboardReducer:
    def apply(self, state: BlackboardState, event: DomainEvent) -> BlackboardState:
        t = event.type
        p = event.payload

        if t == EventType.USER_MESSAGE:
            history = state.chat_history + ({"role": "user", "content": p["content"], "turn_index": event.turn_index},)
            return BlackboardState(**{**state.__dict__, "current_user_request": p["content"], "goal": p["content"], "turn_index": event.turn_index, "chat_history": history})
        if t == EventType.SYSTEM_MESSAGE:
            history = state.chat_history + ({"role": p.get("role", "system"), "content": p["content"], "turn_index": event.turn_index},)
            return BlackboardState(**{**state.__dict__, "chat_history": history})
        if t == EventType.MODE_SET:
            return BlackboardState(**{**state.__dict__, "interaction_mode": p["mode"]})
        if t == EventType.CONSTRAINT_SET:
            c: Constraint = p["constraint"]
            constraints = dict(state.constraints)
            constraints[c.key] = c
            return BlackboardState(**{**state.__dict__, "constraints": constraints})
        if t == EventType.FACT_ADDED:
            fact: Fact = p["fact"]
            return BlackboardState(**{**state.__dict__, "facts": state.facts + (fact,)})
        if t == EventType.SUBTASK_ADDED:
            st: SubTask = p["subtask"]
            subtasks = dict(state.subtasks)
            subtasks[st.id] = st
            return BlackboardState(**{**state.__dict__, "subtasks": subtasks, "task_status": "planned"})
        if t == EventType.SUBTASK_UPDATED:
            st: SubTask = p["subtask"]
            subtasks = dict(state.subtasks)
            subtasks[st.id] = st
            return BlackboardState(**{**state.__dict__, "subtasks": subtasks})
        if t == EventType.SUBTASK_COMPLETED:
            subtask_id = p["subtask_id"]
            subtasks = dict(state.subtasks)
            if subtask_id in subtasks:
                old = subtasks[subtask_id]
                subtasks[subtask_id] = SubTask(**{**old.__dict__, "status": "done"})
            completed = state.completed_subtasks if subtask_id in state.completed_subtasks else state.completed_subtasks + (subtask_id,)
            return BlackboardState(**{**state.__dict__, "subtasks": subtasks, "completed_subtasks": completed})
        if t == EventType.AGENT_SELECTED:
            agent_name = p["agent"]
            subtask_id = p["subtask_id"]
            subtasks = dict(state.subtasks)
            if subtask_id in subtasks:
                old = subtasks[subtask_id]
                subtasks[subtask_id] = SubTask(**{**old.__dict__, "assigned_agent": agent_name, "status": "running", "attempts": old.attempts + 1})
            return BlackboardState(**{**state.__dict__, "subtasks": subtasks, "agents_called": state.agents_called + (agent_name,), "selected_subtask_ids": state.selected_subtask_ids + (subtask_id,)})
        if t == EventType.AGENT_RESULT_RECORDED:
            result: AgentResult = p["result"]
            results = dict(state.results_by_agent)
            results[result.agent_name] = results.get(result.agent_name, ()) + (result.output,)
            failures = state.failures if result.success else state.failures + tuple(result.errors or (f"Agent {result.agent_name} failed.",))
            subtasks = dict(state.subtasks)
            for sid in result.completed_subtask_ids:
                if sid in subtasks:
                    old = subtasks[sid]
                    subtasks[sid] = SubTask(**{**old.__dict__, "status": "done", "output": result.output})
            return BlackboardState(**{**state.__dict__, "results_by_agent": results, "failures": failures, "subtasks": subtasks})
        if t == EventType.FAILURE_RECORDED:
            return BlackboardState(**{**state.__dict__, "failures": state.failures + (p['message'],)})
        if t in (EventType.VALIDATION_FAILED, EventType.VALIDATION_PASSED):
            report: ValidationReport = p["report"]
            return BlackboardState(**{**state.__dict__, "missing_items": report.missing_items, "conflicts": report.conflicts, "unsupported_claims": report.unsupported_claims, "ready_to_respond": report.ready_to_respond})
        if t == EventType.FINAL_RESPONSE_SET:
            return BlackboardState(**{**state.__dict__, "final_response": p["response"]})
        return state


class EventStore:
    def __init__(self) -> None:
        self._events: List[DomainEvent] = []

    @property
    def events(self) -> Tuple[DomainEvent, ...]:
        return tuple(self._events)

    def append(self, events: Iterable[DomainEvent]) -> None:
        self._events.extend(events)


class EventSourcedBlackboard:
    def __init__(self, initial: Optional[BlackboardState] = None) -> None:
        self._state = initial or BlackboardState()
        self._store = EventStore()
        self._reducer = BlackboardReducer()

    @property
    def state(self) -> BlackboardState:
        return self._state

    @property
    def events(self) -> Tuple[DomainEvent, ...]:
        return self._store.events

    def apply_patch(self, patch: BlackboardPatch) -> None:
        events = list(patch.to_events(self._state))
        self._store.append(events)
        for event in events:
            self._state = self._reducer.apply(self._state, event)

    def apply_event(self, event: DomainEvent) -> None:
        self._store.append([event])
        self._state = self._reducer.apply(self._state, event)

    def active_facts(self) -> Tuple[Fact, ...]:
        return tuple(f for f in self._state.facts if f.status == "active")

    def get_constraint(self, key: str, default: Any = None) -> Any:
        c = self._state.constraints.get(key)
        return c.value if c and c.active else default

    def pending_subtasks(self) -> List[SubTask]:
        return [s for s in self._state.subtasks.values() if s.status == "pending"]

    def running_subtasks(self) -> List[SubTask]:
        return [s for s in self._state.subtasks.values() if s.status == "running"]

    def failed_subtasks(self) -> List[SubTask]:
        return [s for s in self._state.subtasks.values() if s.status == "failed"]
