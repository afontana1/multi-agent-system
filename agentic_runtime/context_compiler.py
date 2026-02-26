from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from .blackboard import EventSourcedBlackboard, SetConstraintPatch, SetModePatch, SetRequestPatch
from .domain import ChatMessage, Constraint, DomainEvent, EventType


class IContextCompiler(ABC):
    @abstractmethod
    def compile(self, bb: EventSourcedBlackboard, current_question: str, chat_history: Sequence[ChatMessage]) -> None:
        raise NotImplementedError


class RuleBasedContextCompiler(IContextCompiler):
    def compile(self, bb: EventSourcedBlackboard, current_question: str, chat_history: Sequence[ChatMessage]) -> None:
        for msg in chat_history:
            ev_type = EventType.USER_MESSAGE if msg.role == "user" else EventType.SYSTEM_MESSAGE
            bb.apply_event(DomainEvent(ev_type, {"content": msg.content, "role": msg.role}, msg.turn_index))
            self._extract_constraints(bb, msg)
        bb.apply_patch(SetRequestPatch(current_question, chat_history[-1].turn_index if chat_history else 0))
        bb.apply_patch(SetModePatch(self._infer_mode(current_question, chat_history), bb.state.turn_index))

    def _extract_constraints(self, bb: EventSourcedBlackboard, msg: ChatMessage) -> None:
        if msg.role != "user":
            return
        lower = msg.content.lower()
        if "python" in lower:
            bb.apply_patch(SetConstraintPatch(Constraint("preferred_language", "python", msg.turn_index)))
        if "solid" in lower:
            bb.apply_patch(SetConstraintPatch(Constraint("design_principles", "SOLID", msg.turn_index)))
        if "extensible" in lower or "modular" in lower:
            bb.apply_patch(SetConstraintPatch(Constraint("architecture_quality", "extensible", msg.turn_index)))
        if "chat history" in lower:
            bb.apply_patch(SetConstraintPatch(Constraint("include_chat_history", True, msg.turn_index)))

    def _infer_mode(self, current_question: str, chat_history: Sequence[ChatMessage]) -> str:
        text = (current_question + " " + " ".join(m.content for m in chat_history[-6:])).lower()
        if any(k in text for k in ("implement", "code", "architecture", "runtime")):
            return "building"
        if any(k in text for k in ("debug", "error", "traceback")):
            return "debugging"
        return "general"
