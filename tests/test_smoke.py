import asyncio

from agentic_runtime.agents import AgentRegistry, CodingExpert, PlannerExpert, RetrievalExpert, VerifierExpert
from agentic_runtime.blackboard import EventSourcedBlackboard
from agentic_runtime.context_compiler import RuleBasedContextCompiler
from agentic_runtime.controller import HybridAgentRuntimeV2
from agentic_runtime.domain import ChatMessage
from agentic_runtime.planner import SimpleTaskPlanner
from agentic_runtime.synthesizer import MarkdownSynthesizer
from agentic_runtime.validators import BlackboardValidator


def test_runtime_smoke():
    async def _run():
        registry = AgentRegistry()
        registry.register(PlannerExpert())
        registry.register(CodingExpert())
        registry.register(VerifierExpert())
        registry.register(RetrievalExpert())

        bb = EventSourcedBlackboard()
        RuleBasedContextCompiler().compile(
            bb,
            "Implement runtime",
            [ChatMessage("user", "Use Python and SOLID.", 1)],
        )

        runtime = HybridAgentRuntimeV2(
            planner=SimpleTaskPlanner(),
            validator=BlackboardValidator(),
            synthesizer=MarkdownSynthesizer(),
            registry=registry,
        )
        result = await runtime.run(bb)
        assert result.state.final_response
        assert "Runtime Summary" in result.state.final_response

    asyncio.run(_run())
