from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from .blackboard import EventSourcedBlackboard
from .domain import ValidationReport


class IValidator(ABC):
    @abstractmethod
    def validate(self, bb: EventSourcedBlackboard) -> ValidationReport:
        raise NotImplementedError


class BlackboardValidator(IValidator):
    def validate(self, bb: EventSourcedBlackboard) -> ValidationReport:
        state = bb.state
        missing: List[str] = []
        conflicts: List[str] = []
        unsupported: List[str] = []
        if not state.subtasks:
            missing.append("No subtasks created.")
        if any(s.status != "done" for s in state.subtasks.values()):
            missing.append("Some subtasks are incomplete.")
        if len(bb.active_facts()) == 0:
            unsupported.append("No facts produced by experts.")
        return ValidationReport(ready_to_respond=(not missing and not conflicts), missing_items=tuple(missing), conflicts=tuple(conflicts), unsupported_claims=tuple(unsupported), notes=("Validation completed.",))
