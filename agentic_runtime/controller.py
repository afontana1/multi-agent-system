from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .agents import AgentRegistry, UtilityRouter
from .behavior_tree import ActionNode, BTNode, ConditionNode, CooldownDecorator, SelectorNode, SequenceNode
from .blackboard import BlackboardState, EventSourcedBlackboard, AddSubTaskPatch, SetFinalResponsePatch, SetValidationPatch, UpdateSubTaskPatch
from .domain import LifecycleState, Status, SubTask
from .execution import ExecutionService
from .hfsm import HFSM, IState
from .planner import ITaskPlanner
from .retry import ExponentialBackoffRetryPolicy, IRetryPolicy
from .synthesizer import ISynthesizer
from .validators import IValidator


def build_execute_bt(execution_service: ExecutionService) -> BTNode:
    return SelectorNode(
        name="execute_root",
        children=[
            SequenceNode(
                name="all_done",
                children=[
                    ConditionNode("all_subtasks_done", lambda bb: bool(bb.state.subtasks) and all(s.status == "done" for s in bb.state.subtasks.values())),
                    ActionNode("done", lambda bb: Status.SUCCESS),
                ],
            ),
            ActionNode("parallel_execute", lambda bb: execution_service.execute_ready_subtasks(bb, max_parallel=2)),
        ],
    )


def build_repair_bt() -> BTNode:
    async def retry_failed(bb: EventSourcedBlackboard) -> Status:
        failed = bb.failed_subtasks()
        if not failed:
            return Status.FAILURE
        repaired = False
        for subtask in failed:
            if subtask.attempts < subtask.max_attempts:
                bb.apply_patch(UpdateSubTaskPatch(SubTask(**{**subtask.__dict__, "status": "pending"}), bb.state.turn_index))
                repaired = True
        return Status.SUCCESS if repaired else Status.FAILURE

    return SelectorNode(name="repair_root", children=[CooldownDecorator("retry_cooldown", ActionNode("retry_failed", retry_failed), cooldown_ticks=1)])


@dataclass
class IntakeState(IState):
    @property
    def name(self) -> LifecycleState:
        return LifecycleState.INTAKE

    async def on_update(self, bb: EventSourcedBlackboard) -> LifecycleState:
        return LifecycleState.PLAN


@dataclass
class PlanState(IState):
    planner: ITaskPlanner

    @property
    def name(self) -> LifecycleState:
        return LifecycleState.PLAN

    async def on_update(self, bb: EventSourcedBlackboard) -> LifecycleState:
        for subtask in self.planner.build_plan(bb):
            if subtask.id not in bb.state.subtasks:
                bb.apply_patch(AddSubTaskPatch(subtask, bb.state.turn_index))
        return LifecycleState.EXECUTE


@dataclass
class ExecuteState(IState):
    execution_bt: BTNode

    @property
    def name(self) -> LifecycleState:
        return LifecycleState.EXECUTE

    async def on_update(self, bb: EventSourcedBlackboard) -> LifecycleState:
        status = await self.execution_bt.tick(bb)
        if bb.state.subtasks and all(s.status == "done" for s in bb.state.subtasks.values()):
            return LifecycleState.VALIDATE
        if status == Status.FAILURE and bb.failed_subtasks():
            return LifecycleState.REPAIR
        return LifecycleState.EXECUTE


@dataclass
class ValidateState(IState):
    validator: IValidator

    @property
    def name(self) -> LifecycleState:
        return LifecycleState.VALIDATE

    async def on_update(self, bb: EventSourcedBlackboard) -> LifecycleState:
        report = self.validator.validate(bb)
        bb.apply_patch(SetValidationPatch(report, bb.state.turn_index))
        return LifecycleState.RESPOND if report.ready_to_respond else LifecycleState.REPAIR


@dataclass
class RepairState(IState):
    repair_bt: BTNode

    @property
    def name(self) -> LifecycleState:
        return LifecycleState.REPAIR

    async def on_update(self, bb: EventSourcedBlackboard) -> LifecycleState:
        status = await self.repair_bt.tick(bb)
        if status == Status.SUCCESS:
            return LifecycleState.EXECUTE
        if bb.active_facts() or any(s.status == "done" for s in bb.state.subtasks.values()):
            return LifecycleState.RESPOND
        return LifecycleState.FAILED


@dataclass
class RespondState(IState):
    synthesizer: ISynthesizer

    @property
    def name(self) -> LifecycleState:
        return LifecycleState.RESPOND

    async def on_update(self, bb: EventSourcedBlackboard) -> LifecycleState:
        bb.apply_patch(SetFinalResponsePatch(self.synthesizer.synthesize(bb), bb.state.turn_index))
        return LifecycleState.DONE


@dataclass
class DoneState(IState):
    @property
    def name(self) -> LifecycleState:
        return LifecycleState.DONE

    async def on_update(self, bb: EventSourcedBlackboard) -> LifecycleState:
        bb._state = BlackboardState(**{**bb.state.__dict__, "done": True})
        return LifecycleState.DONE


@dataclass
class FailedState(IState):
    @property
    def name(self) -> LifecycleState:
        return LifecycleState.FAILED

    async def on_update(self, bb: EventSourcedBlackboard) -> LifecycleState:
        if not bb.state.final_response:
            bb.apply_patch(SetFinalResponsePatch("Failed to complete task with available experts.", bb.state.turn_index))
        bb._state = BlackboardState(**{**bb.state.__dict__, "done": True})
        return LifecycleState.FAILED


class HybridAgentRuntimeV2:
    def __init__(
        self,
        planner: ITaskPlanner,
        validator: IValidator,
        synthesizer: ISynthesizer,
        registry: AgentRegistry,
        router: Optional[UtilityRouter] = None,
        retry_policy: Optional[IRetryPolicy] = None,
        max_parallel: int = 2,
    ) -> None:
        self._router = router or UtilityRouter()
        self._retry = retry_policy or ExponentialBackoffRetryPolicy()
        execution_service = ExecutionService(registry, self._router, self._retry, max_parallel=max_parallel)
        self._hfsm = HFSM(
            states={
                LifecycleState.INTAKE: IntakeState(),
                LifecycleState.PLAN: PlanState(planner),
                LifecycleState.EXECUTE: ExecuteState(build_execute_bt(execution_service)),
                LifecycleState.VALIDATE: ValidateState(validator),
                LifecycleState.REPAIR: RepairState(build_repair_bt()),
                LifecycleState.RESPOND: RespondState(synthesizer),
                LifecycleState.DONE: DoneState(),
                LifecycleState.FAILED: FailedState(),
            },
            initial=LifecycleState.INTAKE,
        )

    async def run(self, bb: EventSourcedBlackboard) -> EventSourcedBlackboard:
        await self._hfsm.start(bb)
        while not bb.state.done and bb.state.tick_count < bb.state.max_ticks:
            bb._state = BlackboardState(**{**bb.state.__dict__, "tick_count": bb.state.tick_count + 1})
            await self._hfsm.tick(bb)
        if bb.state.tick_count >= bb.state.max_ticks and not bb.state.done:
            bb.apply_patch(SetFinalResponsePatch("Stopped due to max tick limit.", bb.state.turn_index))
            bb._state = BlackboardState(**{**bb.state.__dict__, "done": True})
        return bb
