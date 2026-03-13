from __future__ import annotations

from typing import List

from .agents import AgentRegistry, UtilityRouter
from .blackboard import EventSourcedBlackboard, RecordAgentResultPatch, RecordAgentSelectionPatch, RecordFailurePatch, UpdateSubTaskPatch
from .domain import DomainEvent, EventType, Status, SubTask
from .retry import IRetryPolicy


class ExecutionService:
    def __init__(self, registry: AgentRegistry, router: UtilityRouter, retry_policy: IRetryPolicy, max_parallel: int = 2) -> None:
        self._registry = registry
        self._router = router
        self._retry = retry_policy
        self._max_parallel = max_parallel

    async def execute_ready_subtasks(self, bb: EventSourcedBlackboard, max_parallel: int = 2) -> Status:
        ready = sorted(self._ready_subtasks(bb), key=lambda s: s.priority)[: min(max_parallel, self._max_parallel)]
        bb.trace("execution_ready_subtasks", subtask_ids=[subtask.id for subtask in ready], max_parallel=max_parallel)
        if not ready:
            bb.trace("execution_no_ready_subtasks")
            return Status.FAILURE
        results = await __import__('asyncio').gather(*(self._run_single_subtask(bb, s) for s in ready))
        bb.trace("execution_batch_complete", statuses=[result.value for result in results])
        return Status.SUCCESS if any(r == Status.SUCCESS for r in results) else Status.FAILURE

    def _ready_subtasks(self, bb: EventSourcedBlackboard) -> List[SubTask]:
        state = bb.state
        out: List[SubTask] = []
        for s in state.subtasks.values():
            if s.status == "pending" and all(state.subtasks[d].status == "done" for d in s.dependencies):
                out.append(s)
        return out

    async def _run_single_subtask(self, bb: EventSourcedBlackboard, subtask: SubTask) -> Status:
        agent = self._router.choose(subtask, bb, self._registry)
        if agent is None:
            bb.apply_patch(UpdateSubTaskPatch(SubTask(**{**subtask.__dict__, "status": "failed"}), bb.state.turn_index))
            bb.apply_patch(RecordFailurePatch(f"No agent can handle subtask {subtask.id}", bb.state.turn_index))
            bb.trace("execution_subtask_unhandled", subtask_id=subtask.id)
            return Status.FAILURE
        bb.apply_patch(RecordAgentSelectionPatch(agent.name, subtask.id, bb.state.turn_index))
        bb.apply_event(DomainEvent(EventType.AGENT_EXECUTION_STARTED, {"agent": agent.name, "subtask_id": subtask.id}, bb.state.turn_index))
        bb.trace("execution_subtask_start", subtask_id=subtask.id, agent=agent.name)

        async def op():
            return await agent.run(subtask, bb)

        try:
            result = await self._retry.run(op)
            bb.apply_patch(RecordAgentResultPatch(result, bb.state.turn_index))
            bb.trace("execution_subtask_result", subtask_id=subtask.id, agent=agent.name, success=result.success)
            return Status.SUCCESS if result.success else Status.FAILURE
        except Exception as exc:  # noqa: BLE001
            current = bb.state.subtasks.get(subtask.id, subtask)
            bb.apply_patch(UpdateSubTaskPatch(SubTask(**{**current.__dict__, "status": "failed"}), bb.state.turn_index))
            bb.apply_patch(RecordFailurePatch(f"Subtask {subtask.id} failed after retries: {exc}", bb.state.turn_index))
            bb.trace("execution_subtask_exception", subtask_id=subtask.id, agent=agent.name, error=str(exc))
            return Status.FAILURE
