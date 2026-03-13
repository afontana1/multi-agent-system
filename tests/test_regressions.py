import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from agentic_runtime import ChatCompletionResult, ChatMessage, RuntimeTraceLogger, build_multi_agent_system


class CapturingChatModel:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = []

    async def complete(self, messages, tools=()):
        self.calls.append({"messages": list(messages), "tools": list(tools)})
        return ChatCompletionResult(
            message={"role": "assistant", "content": self.content},
            content=self.content,
        )


class InvalidCoordinatorModel:
    async def complete(self, messages, tools=()):
        return ChatCompletionResult(
            message={"role": "assistant", "content": "{not valid json"},
            content="{not valid json",
        )


def test_system_returns_failure_message_when_no_agents_exist():
    async def _run():
        system = await build_multi_agent_system(config={"agents": []})
        try:
            response = await system.respond("hello")
        finally:
            await system.aclose()

        assert response == "Failed to complete task with available experts."

    asyncio.run(_run())


def test_coordinator_invalid_json_falls_back_to_base_planner():
    async def _run():
        worker = CapturingChatModel("fallback worker response")
        system = await build_multi_agent_system(
            config={
                "agents": [
                    {
                        "name": "assistant",
                        "system_prompt": "You answer questions.",
                        "model": {"provider": "litellm", "model": "fake-worker"},
                    }
                ]
            },
            coordinator_spec={
                "name": "coordinator",
                "system_prompt": "Return JSON subtasks.",
                "model": {"provider": "litellm", "model": "fake-coordinator"},
            },
            model_overrides={
                "assistant": worker,
                "coordinator": InvalidCoordinatorModel(),
            },
        )
        try:
            response = await system.respond("hello")
        finally:
            await system.aclose()

        assert response == "fallback worker response"
        assert len(worker.calls) == 1

    asyncio.run(_run())


def test_chat_agent_does_not_receive_tools_for_normal_query():
    async def _run():
        chat_model = CapturingChatModel("chat response")
        tool_model = CapturingChatModel("tool response")
        class StubMCPRegistry:
            async def load(self, selected_servers=None):
                return ()

            async def aclose(self):
                return None

        system = await build_multi_agent_system(
            config={
                "agents": [
                    {
                        "name": "chat_assistant",
                        "system_prompt": "You are a chat assistant.",
                        "model": {"provider": "litellm", "model": "fake-chat"},
                    },
                    {
                        "name": "tool_assistant",
                        "system_prompt": "You are a tool assistant.",
                        "selection_keywords": ["tool", "calculate", "sum"],
                        "mcp_servers": ["demo-tools"],
                        "model": {"provider": "litellm", "model": "fake-tool"},
                    },
                ],
                "mcp_servers": [{"name": "demo-tools", "url": "http://example.invalid/mcp"}],
            },
            model_overrides={
                "chat_assistant": chat_model,
                "tool_assistant": tool_model,
            },
            mcp_registry_override=StubMCPRegistry(),
        )
        try:
            response = await system.respond("hello")
        finally:
            await system.aclose()

        assert response == "chat response"
        assert len(chat_model.calls) == 1
        assert chat_model.calls[0]["tools"] == []
        assert len(tool_model.calls) == 0

    asyncio.run(_run())


def test_tool_agent_receives_tools_for_tool_query_without_calling_real_mcp():
    async def _run():
        chat_model = CapturingChatModel("chat response")
        tool_model = CapturingChatModel("tool response")

        class StubMCPRegistry:
            async def load(self, selected_servers=None):
                return ()

            async def aclose(self):
                return None

        system = await build_multi_agent_system(
            config={
                "agents": [
                    {
                        "name": "chat_assistant",
                        "system_prompt": "You are a chat assistant.",
                        "model": {"provider": "litellm", "model": "fake-chat"},
                    },
                    {
                        "name": "tool_assistant",
                        "system_prompt": "You are a tool assistant.",
                        "selection_keywords": ["tool", "calculate", "sum"],
                        "mcp_servers": ["demo-tools"],
                        "model": {"provider": "litellm", "model": "fake-tool"},
                    },
                ],
                "mcp_servers": [{"name": "demo-tools", "url": "http://example.invalid/mcp"}],
            },
            model_overrides={
                "chat_assistant": chat_model,
                "tool_assistant": tool_model,
            },
            mcp_registry_override=StubMCPRegistry(),
        )
        try:
            response = await system.respond("use the tool to calculate 1+2")
        finally:
            await system.aclose()

        assert response == "tool response"
        assert len(chat_model.calls) == 0
        assert len(tool_model.calls) == 1

    asyncio.run(_run())


def test_system_handles_multiple_turns_with_mixed_routing():
    async def _run():
        chat_model = CapturingChatModel("chat reply")
        tool_model = CapturingChatModel("tool reply")

        class StubMCPRegistry:
            async def load(self, selected_servers=None):
                return ()

            async def aclose(self):
                return None

        system = await build_multi_agent_system(
            config={
                "agents": [
                    {
                        "name": "chat_assistant",
                        "system_prompt": "You are a chat assistant.",
                        "model": {"provider": "litellm", "model": "fake-chat"},
                    },
                    {
                        "name": "tool_assistant",
                        "system_prompt": "You are a tool assistant.",
                        "selection_keywords": ["tool", "calculate", "sum"],
                        "mcp_servers": ["demo-tools"],
                        "model": {"provider": "litellm", "model": "fake-tool"},
                    },
                ],
                "mcp_servers": [{"name": "demo-tools", "url": "http://example.invalid/mcp"}],
            },
            model_overrides={
                "chat_assistant": chat_model,
                "tool_assistant": tool_model,
            },
            mcp_registry_override=StubMCPRegistry(),
        )
        try:
            first = await system.respond("hello")
            second = await system.respond(
                "use the tool to calculate 1+2",
                [ChatMessage("user", "hello", 1), ChatMessage("assistant", first, 2)],
            )
            third = await system.respond(
                "thanks",
                [
                    ChatMessage("user", "hello", 1),
                    ChatMessage("assistant", first, 2),
                    ChatMessage("user", "use the tool to calculate 1+2", 3),
                    ChatMessage("assistant", second, 4),
                ],
            )
        finally:
            await system.aclose()

        assert first == "chat reply"
        assert second == "tool reply"
        assert third == "chat reply"
        assert len(chat_model.calls) == 2
        assert len(tool_model.calls) == 1

    asyncio.run(_run())


def test_respond_with_trace_reports_called_agents():
    async def _run():
        chat_model = CapturingChatModel("chat trace response")
        system = await build_multi_agent_system(
            config={
                "agents": [
                    {
                        "name": "chat_assistant",
                        "system_prompt": "You are a chat assistant.",
                        "model": {"provider": "litellm", "model": "fake-chat"},
                    }
                ]
            },
            model_overrides={"chat_assistant": chat_model},
        )
        try:
            trace = await system.respond_with_trace("hello")
        finally:
            await system.aclose()

        assert trace.response == "chat trace response"
        assert list(trace.agents_called) == ["chat_assistant"]
        assert list(trace.completed_subtasks)

    asyncio.run(_run())


def test_default_planner_prefers_default_conversational_agent_for_unmatched_queries():
    from agentic_runtime.blackboard import EventSourcedBlackboard, SetRequestPatch
    from agentic_runtime.domain import AgentConfig, ModelSettings
    from agentic_runtime.runtime_policies import DefaultTaskPlanningPolicy

    planner = DefaultTaskPlanningPolicy()
    bb = EventSourcedBlackboard()
    bb.apply_patch(SetRequestPatch("whats up", 1))

    researcher = AgentConfig(
        name="researcher",
        model=ModelSettings(provider="litellm", model="fake"),
        system_prompt="Research specialist.",
        selection_keywords=("research", "investigate", "find"),
    )
    writer = AgentConfig(
        name="writer",
        model=ModelSettings(provider="litellm", model="fake"),
        system_prompt="Primary conversational assistant.",
    )

    plan = planner.build_plan((researcher, writer), bb)

    assert len(plan) == 1
    assert plan[0].assigned_agent == "writer"


def test_session_trace_logger_writes_request_and_runtime_events():
    async def _run():
        with TemporaryDirectory() as tmp_dir:
            trace_logger = RuntimeTraceLogger(Path(tmp_dir))
            model = CapturingChatModel("hello from trace")
            system = await build_multi_agent_system(
                config={
                    "agents": [
                        {
                            "name": "assistant",
                            "system_prompt": "You answer questions.",
                            "model": {"provider": "litellm", "model": "fake"},
                        }
                    ]
                },
                model_overrides={"assistant": model},
                trace_logger=trace_logger,
            )
            try:
                response = await system.respond("hello")
            finally:
                await system.aclose()

            assert response == "hello from trace"
            assert system.session_log_path == trace_logger.session_file
            log_lines = trace_logger.session_file.read_text(encoding="utf-8").splitlines()
            events = [json.loads(line) for line in log_lines]
            event_types = {event["event_type"] for event in events}
            request_ids = {event["payload"].get("request_id") for event in events if "request_id" in event["payload"]}

            assert "request_received" in event_types
            assert "request_completed" in event_types
            assert "hfsm_start" in event_types
            assert "blackboard_event" in event_types
            assert "bt_tick" in event_types
            assert request_ids == {"req-0001"}

    asyncio.run(_run())
