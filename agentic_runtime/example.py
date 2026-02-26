from __future__ import annotations

import asyncio

from .agents import AgentRegistry, CodingExpert, PlannerExpert, RetrievalExpert, VerifierExpert
from .blackboard import EventSourcedBlackboard
from .context_compiler import RuleBasedContextCompiler
from .controller import HybridAgentRuntimeV2
from .domain import ChatMessage
from .planner import SimpleTaskPlanner
from .retry import ExponentialBackoffRetryPolicy
from .synthesizer import MarkdownSynthesizer
from .validators import BlackboardValidator


async def run_example() -> None:
    registry = AgentRegistry()
    registry.register(PlannerExpert())
    registry.register(CodingExpert())
    registry.register(VerifierExpert())
    registry.register(RetrievalExpert())

    bb = EventSourcedBlackboard()
    compiler = RuleBasedContextCompiler()
    history = [
        ChatMessage("user", "I want a modular agent orchestration system.", 1),
        ChatMessage("assistant", "Okay, we can design that.", 2),
        ChatMessage("user", "Use Python, SOLID principles, and make it extensible.", 3),
        ChatMessage("user", "Include chat history.", 4),
    ]
    compiler.compile(bb, "Implement the full hybrid runtime with async execution and retries.", history)

    runtime = HybridAgentRuntimeV2(
        planner=SimpleTaskPlanner(),
        validator=BlackboardValidator(),
        synthesizer=MarkdownSynthesizer(),
        registry=registry,
        retry_policy=ExponentialBackoffRetryPolicy(max_attempts=3, base_delay_seconds=0.01),
    )
    result = await runtime.run(bb)
    print(result.state.final_response)


if __name__ == "__main__":
    asyncio.run(run_example())
