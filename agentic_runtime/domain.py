from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class Status(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    RUNNING = "RUNNING"


class LifecycleState(str, Enum):
    INTAKE = "INTAKE"
    PLAN = "PLAN"
    EXECUTE = "EXECUTE"
    VALIDATE = "VALIDATE"
    REPAIR = "REPAIR"
    RESPOND = "RESPOND"
    DONE = "DONE"
    FAILED = "FAILED"


class EventType(str, Enum):
    USER_MESSAGE = "USER_MESSAGE"
    SYSTEM_MESSAGE = "SYSTEM_MESSAGE"
    CONSTRAINT_SET = "CONSTRAINT_SET"
    FACT_ADDED = "FACT_ADDED"
    FACT_SUPERSEDED = "FACT_SUPERSEDED"
    SUBTASK_ADDED = "SUBTASK_ADDED"
    SUBTASK_UPDATED = "SUBTASK_UPDATED"
    SUBTASK_COMPLETED = "SUBTASK_COMPLETED"
    AGENT_SELECTED = "AGENT_SELECTED"
    AGENT_EXECUTION_STARTED = "AGENT_EXECUTION_STARTED"
    AGENT_RESULT_RECORDED = "AGENT_RESULT_RECORDED"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"
    OPEN_QUESTION_ADDED = "OPEN_QUESTION_ADDED"
    OPEN_QUESTION_RESOLVED = "OPEN_QUESTION_RESOLVED"
    FINAL_RESPONSE_SET = "FINAL_RESPONSE_SET"
    FAILURE_RECORDED = "FAILURE_RECORDED"
    ARTIFACT_STORED = "ARTIFACT_STORED"
    MODE_SET = "MODE_SET"


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    turn_index: int


@dataclass(frozen=True)
class Constraint:
    key: str
    value: Any
    source_turn: int
    active: bool = True
    confidence: float = 1.0


@dataclass(frozen=True)
class Fact:
    claim: str
    source: str
    confidence: float
    turn_index: int
    status: str = "active"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SubTask:
    id: str
    description: str
    required_outputs: Tuple[str, ...] = ()
    dependencies: Tuple[str, ...] = ()
    assigned_agent: Optional[str] = None
    status: str = "pending"
    attempts: int = 0
    max_attempts: int = 2
    output: Optional[Dict[str, Any]] = None
    lane: str = "default"
    priority: int = 50
    join_key: Optional[str] = None


@dataclass(frozen=True)
class AgentResult:
    agent_name: str
    success: bool
    output: Dict[str, Any]
    confidence: float = 0.5
    errors: Tuple[str, ...] = ()
    produced_facts: Tuple[Fact, ...] = ()
    completed_subtask_ids: Tuple[str, ...] = ()
    suggested_next_steps: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationReport:
    ready_to_respond: bool
    missing_items: Tuple[str, ...] = ()
    conflicts: Tuple[str, ...] = ()
    unsupported_claims: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DomainEvent:
    type: EventType
    payload: Dict[str, Any]
    turn_index: int
    ts: float = field(default_factory=time.time)
