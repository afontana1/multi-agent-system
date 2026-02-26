from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from .blackboard import EventSourcedBlackboard


class ISynthesizer(ABC):
    @abstractmethod
    def synthesize(self, bb: EventSourcedBlackboard) -> str:
        raise NotImplementedError


class MarkdownSynthesizer(ISynthesizer):
    def synthesize(self, bb: EventSourcedBlackboard) -> str:
        s = bb.state
        lines: List[str] = ["## Runtime Summary", f"- Goal: {s.goal}", f"- Mode: {s.interaction_mode}", f"- Lifecycle: {s.lifecycle_state.value}", "", "### Subtasks"]
        for task in s.subtasks.values():
            lines.append(f"- {task.id} [{task.status}] {task.description} via {task.assigned_agent}")
        if bb.active_facts():
            lines += ["", "### Facts"]
            for fact in bb.active_facts():
                lines.append(f"- {fact.claim} (source={fact.source}, confidence={fact.confidence:.2f})")
        if s.missing_items or s.conflicts or s.unsupported_claims:
            lines += ["", "### Validation"]
            for item in s.missing_items:
                lines.append(f"- Missing: {item}")
            for item in s.conflicts:
                lines.append(f"- Conflict: {item}")
            for item in s.unsupported_claims:
                lines.append(f"- Unsupported: {item}")
        lines += ["", "### Event Count", f"- {len(bb.events)}"]
        return "\n".join(lines)
