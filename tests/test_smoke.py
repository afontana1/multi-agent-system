import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agentic_runtime import (
    AgentConfig,
    BaseLLMAgent,
    ChatCompletionResult,
    ChatMessage,
    CoordinatorConfig,
    DefaultRoutingPolicy,
    DefaultTaskPlanningPolicy,
    DefaultContextStrategy,
    DefaultFinalizationStrategy,
    DefaultToolExecutionStrategy,
    FinalizationStrategy,
    FunctionTool,
    MemoryEntry,
    MemoryStrategy,
    ModelSettings,
    ToolCall,
    ToolDefinition,
    ToolExecutionStrategy,
    ToolRegistry,
    ToolResult,
    RoutingPolicy,
    TaskPlanningPolicy,
    WindowedMemoryStrategy,
    build_multi_agent_system,
)
from agentic_runtime.tools import tool_to_openai_schema
from agentic_runtime.runtime_policies import DefaultTaskPlanningPolicy
from agentic_runtime.blackboard import EventSourcedBlackboard, SetRequestPatch


class FakeChatModel:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, tools=()):
        self.calls += 1
        if self.calls == 1:
            return ChatCompletionResult(
                message={
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-local",
                            "type": "function",
                            "function": {"name": "lookup_docs", "arguments": "{\"topic\": \"litellm\"}"},
                        },
                        {
                            "id": "call-mcp",
                            "type": "function",
                            "function": {"name": "mcp_echo", "arguments": "{\"text\": \"server ok\"}"},
                        },
                    ],
                },
                content="",
                tool_calls=(
                    ToolCall(id="call-local", name="lookup_docs", arguments={"topic": "litellm"}),
                    ToolCall(id="call-mcp", name="mcp_echo", arguments={"text": "server ok"}),
                ),
            )
        assistant_message = next(msg for msg in messages if msg.get("role") == "assistant" and msg.get("tool_calls"))
        assert assistant_message["content"] is None
        assert assistant_message["tool_calls"][0]["type"] == "function"
        assert isinstance(assistant_message["tool_calls"][0]["function"]["arguments"], str)
        tool_messages = [msg for msg in messages if msg.get("role") == "tool"]
        assert tool_messages[0]["name"] == "lookup_docs"
        assert isinstance(tool_messages[0]["content"], str)
        return ChatCompletionResult(
            message={"role": "assistant", "content": f"Final answer using {len(tool_messages)} tools."},
            content=f"Final answer using {len(tool_messages)} tools.",
        )


class FakeWorkerModel:
    def __init__(self):
        self.calls = 0

    async def complete(self, messages, tools=()):
        self.calls += 1
        return ChatCompletionResult(
            message={"role": "assistant", "content": f"worker answer {self.calls}"},
            content=f"worker answer {self.calls}",
        )


class FakeCoordinatorModel:
    def __init__(self):
        self.calls = 0

    async def complete(self, messages, tools=()):
        self.calls += 1
        payload = json.loads(messages[-1]["content"])
        assert "agent_catalog" in payload
        assert "task_status" in payload
        assert "completed_subtasks" not in payload
        assert "capabilities" in payload["agent_catalog"][0]
        assert "pending" in payload["task_status"]
        assert "completed" in payload["task_status"]
        if self.calls == 1:
            content = json.dumps(
                {"subtasks": [{"description": "First coordinated task", "assigned_agent": "general_assistant", "priority": 10}]}
            )
        elif self.calls == 2:
            content = json.dumps(
                {"subtasks": [{"description": "Second coordinated task", "assigned_agent": "general_assistant", "priority": 20}]}
            )
        else:
            content = json.dumps({"subtasks": []})
        return ChatCompletionResult(message={"role": "assistant", "content": content}, content=content)


class EmptyAfterToolFakeModel:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, tools=()):
        self.calls += 1
        if self.calls == 1:
            return ChatCompletionResult(
                message={
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-local",
                            "type": "function",
                            "function": {"name": "lookup_docs", "arguments": "{\"topic\": \"math\"}"},
                        }
                    ],
                },
                content="",
                tool_calls=(ToolCall(id="call-local", name="lookup_docs", arguments={"topic": "math"}),),
            )
        if self.calls == 2:
            return ChatCompletionResult(message={"role": "assistant", "content": ""}, content="")
        return ChatCompletionResult(message={"role": "assistant", "content": "The answer is 4."}, content="The answer is 4.")


class EmptyUntilExplicitRetryModel:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, tools=()):
        self.calls += 1
        if self.calls == 1:
            return ChatCompletionResult(message={"role": "assistant", "content": ""}, content="")
        assert messages[-1]["role"] == "user"
        assert "Respond to the user with a direct plain-text answer now." in messages[-1]["content"]
        return ChatCompletionResult(message={"role": "assistant", "content": "I am doing well."}, content="I am doing well.")


class StrategyAwareFakeChatModel(FakeChatModel):
    async def complete(self, messages, tools=()):
        if self.calls == 0:
            assert any(msg.get("content") == "context-strategy:tagged" for msg in messages if msg.get("role") == "system")
        return await super().complete(messages, tools)


class AssistantOnlyMemoryStrategy(MemoryStrategy):
    def append(self, memory, role, content, window_size):
        if role == "assistant":
            memory.append(MemoryEntry("assistant", content))
        overflow = len(memory) - window_size
        if overflow > 0:
            del memory[:overflow]

    def recent(self, memory, window_size):
        return tuple(memory[-window_size:])


class TaggedContextStrategy(DefaultContextStrategy):
    def build_messages(self, config, memory, subtask, bb):
        messages = super().build_messages(config, memory, subtask, bb)
        messages.insert(1, {"role": "system", "content": "context-strategy:tagged"})
        return messages


class RecordingToolExecutionStrategy(ToolExecutionStrategy):
    def __init__(self):
        self.resolved = False
        self.executed = []
        self._default = DefaultToolExecutionStrategy()

    async def resolve_tools(self, config, tool_registry, mcp_registry):
        self.resolved = True
        return await self._default.resolve_tools(config, tool_registry, mcp_registry)

    async def execute_tool_call(self, tool_name, arguments, tools):
        self.executed.append(tool_name)
        return await self._default.execute_tool_call(tool_name, arguments, tools)


class TaggedFinalizationStrategy(FinalizationStrategy):
    def __init__(self):
        self.called = False
        self._default = DefaultFinalizationStrategy()

    def build_agent_result(self, config, subtask, bb, final_text, tool_results):
        self.called = True
        result = self._default.build_agent_result(config, subtask, bb, f"[finalized] {final_text}", tool_results)
        return result


class RecordingPlanningPolicy(TaskPlanningPolicy):
    def __init__(self):
        self.called = False
        self._default = DefaultTaskPlanningPolicy()

    def build_plan(self, agents, bb):
        self.called = True
        subtasks = list(self._default.build_plan(agents, bb))
        if subtasks:
            first = subtasks[0]
            subtasks[0] = type(first)(**{**first.__dict__, "description": f"[planned] {first.description}"})
        return tuple(subtasks)


class RecordingRoutingPolicy(RoutingPolicy):
    def __init__(self):
        self.called = False
        self._default = DefaultRoutingPolicy()

    def choose(self, subtask, bb, registry):
        self.called = True
        return self._default.choose(subtask, bb, registry)


class CustomAssistantAgent(BaseLLMAgent):
    def __init__(self, model, tool_registry, mcp_registry=None, memory_strategy=None, context_strategy=None, tool_execution_strategy=None, finalization_strategy=None):
        super().__init__(
            AgentConfig(
                name="custom_assistant",
                model=ModelSettings(provider="litellm", model="fake"),
                system_prompt="You are a custom assistant.",
                tools=("lookup_docs",),
                mcp_servers=("echo",),
                selection_keywords=("custom", "mcp"),
                memory_window=4,
            ),
            model=model,
            tool_registry=tool_registry,
            mcp_registry=mcp_registry,
            memory_strategy=memory_strategy,
            context_strategy=context_strategy,
            tool_execution_strategy=tool_execution_strategy,
            finalization_strategy=finalization_strategy,
        )


class MCPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        method = payload.get("method")

        if method == "notifications/initialized":
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if method == "initialize":
            result = {"capabilities": {"tools": {}}}
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "mcp_echo",
                        "description": "Echo text from MCP.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"],
                        },
                    }
                ]
            }
        elif method == "tools/call":
            result = {
                "content": [{"type": "text", "text": f"MCP:{payload['params']['arguments']['text']}"}],
                "isError": False,
            }
        else:
            self._write_json({"jsonrpc": "2.0", "id": payload.get("id"), "error": {"message": f"Unknown method: {method}"}}, status=400)
            return

        self._write_json({"jsonrpc": "2.0", "id": payload.get("id"), "result": result})

    def log_message(self, format, *args):
        return

    def _write_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_runtime_smoke():
    async def _run():
        async def lookup_docs(arguments):
            return ToolResult(tool_name="lookup_docs", content=f"Docs for {arguments['topic']}")

        tool_registry = ToolRegistry(
            [
                FunctionTool(
                    ToolDefinition(
                        name="lookup_docs",
                        description="Lookup local docs.",
                        parameters={
                            "type": "object",
                            "properties": {"topic": {"type": "string"}},
                            "required": ["topic"],
                        },
                    ),
                    lookup_docs,
                )
            ]
        )

        server = ThreadingHTTPServer(("127.0.0.1", 0), MCPHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = {
                "max_parallel": 2,
                "agents": [
                    {
                        "name": "general_assistant",
                        "system_prompt": "You are a helpful assistant.",
                        "selection_keywords": ["litellm", "tool", "mcp"],
                        "tools": ["lookup_docs"],
                        "mcp_servers": ["echo"],
                        "model": {"provider": "litellm", "model": "fake"},
                    }
                ],
                "mcp_servers": [{"name": "echo", "url": f"http://127.0.0.1:{server.server_port}/mcp"}],
            }

            system = await build_multi_agent_system(
                config,
                tool_registry=tool_registry,
                model_overrides={"general_assistant": FakeChatModel()},
            )
            try:
                response = await system.respond(
                    "Use LiteLLM, tools, and MCP to answer this.",
                    [ChatMessage("user", "Please use tools when needed.", 1)],
                )
            finally:
                await system.aclose()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        assert "Final answer using 2 tools." in response

    asyncio.run(_run())


def test_runtime_accepts_agent_instances():
    async def _run():
        async def lookup_docs(arguments):
            return ToolResult(tool_name="lookup_docs", content=f"Docs for {arguments['topic']}")

        tool_registry = ToolRegistry(
            [
                FunctionTool(
                    ToolDefinition(
                        name="lookup_docs",
                        description="Lookup local docs.",
                        parameters={
                            "type": "object",
                            "properties": {"topic": {"type": "string"}},
                            "required": ["topic"],
                        },
                    ),
                    lookup_docs,
                )
            ]
        )

        server = ThreadingHTTPServer(("127.0.0.1", 0), MCPHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            from agentic_runtime.mcp import MCPToolRegistry
            from agentic_runtime.domain import MCPServerConfig

            mcp_registry = MCPToolRegistry((MCPServerConfig(name="echo", url=f"http://127.0.0.1:{server.server_port}/mcp"),))
            await mcp_registry.load()
            tool_strategy = RecordingToolExecutionStrategy()
            finalization_strategy = TaggedFinalizationStrategy()
            agent = CustomAssistantAgent(
                StrategyAwareFakeChatModel(),
                tool_registry,
                mcp_registry,
                memory_strategy=AssistantOnlyMemoryStrategy(),
                context_strategy=TaggedContextStrategy(),
                tool_execution_strategy=tool_strategy,
                finalization_strategy=finalization_strategy,
            )
            system = await build_multi_agent_system(agents=[agent], mcp_registry_override=mcp_registry)
            try:
                response = await system.respond("custom mcp question", [ChatMessage("user", "Use memory and tools", 1)])
            finally:
                await system.aclose()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        assert "[finalized] Final answer using 2 tools." in response
        assert agent.estimate_window_size() == 4
        assert len(agent.recent_memory()) == 1
        assert agent.recent_memory()[0].role == "assistant"
        assert tool_strategy.resolved is True
        assert tool_strategy.executed == ["lookup_docs", "mcp_echo"]
        assert finalization_strategy.called is True

    asyncio.run(_run())


def test_runtime_accepts_planning_and_routing_policies():
    async def _run():
        async def lookup_docs(arguments):
            return ToolResult(tool_name="lookup_docs", content=f"Docs for {arguments['topic']}")

        tool_registry = ToolRegistry(
            [
                FunctionTool(
                    ToolDefinition(
                        name="lookup_docs",
                        description="Lookup local docs.",
                        parameters={
                            "type": "object",
                            "properties": {"topic": {"type": "string"}},
                            "required": ["topic"],
                        },
                    ),
                    lookup_docs,
                )
            ]
        )

        planning_policy = RecordingPlanningPolicy()
        routing_policy = RecordingRoutingPolicy()

        server = ThreadingHTTPServer(("127.0.0.1", 0), MCPHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = {
                "agents": [
                    {
                        "name": "general_assistant",
                        "system_prompt": "You are a helpful assistant.",
                        "selection_keywords": ["planned"],
                        "tools": ["lookup_docs"],
                        "mcp_servers": ["echo"],
                        "model": {"provider": "litellm", "model": "fake"},
                    }
                ],
                "mcp_servers": [{"name": "echo", "url": f"http://127.0.0.1:{server.server_port}/mcp"}],
            }
            system = await build_multi_agent_system(
                config,
                tool_registry=tool_registry,
                model_overrides={"general_assistant": FakeChatModel()},
                planning_policy=planning_policy,
                routing_policy=routing_policy,
            )
            try:
                response = await system.respond("planned test")
            finally:
                await system.aclose()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        assert "Final answer using 2 tools." in response
        assert planning_policy.called is True
        assert routing_policy.called is True

    asyncio.run(_run())


def test_openai_tool_schema_formatter():
    schema = tool_to_openai_schema(
        ToolDefinition(
            name="lookup_docs",
            description="Lookup local docs.",
            parameters={"properties": {"topic": {"type": "string"}}, "required": ("topic",)},
        )
    )

    assert schema["type"] == "function"
    assert schema["function"]["parameters"]["type"] == "object"
    assert schema["function"]["parameters"]["required"] == ["topic"]
    assert schema["function"]["parameters"]["additionalProperties"] is False


def test_coordinator_agent_can_replan():
    async def _run():
        coordinator_model = FakeCoordinatorModel()
        worker_model = FakeWorkerModel()
        system = await build_multi_agent_system(
            config={
                "agents": [
                    {
                        "name": "general_assistant",
                        "system_prompt": "You are a worker agent.",
                        "capabilities": ["answer_questions", "follow_coordinator_tasks"],
                        "model": {"provider": "litellm", "model": "fake-worker"},
                    }
                ]
            },
            coordinator_spec={
                "name": "coordinator",
                "system_prompt": "Plan subtasks as JSON.",
                "model": {"provider": "litellm", "model": "fake-coordinator"},
            },
            model_overrides={
                "general_assistant": worker_model,
                "coordinator": coordinator_model,
            },
        )
        try:
            response = await system.respond("Do the coordinated workflow")
        finally:
            await system.aclose()

        assert "worker answer 1" in response
        assert "worker answer 2" in response
        assert coordinator_model.calls >= 2

    asyncio.run(_run())


def test_agent_recovers_from_empty_post_tool_response():
    async def _run():
        async def lookup_docs(arguments):
            return ToolResult(tool_name="lookup_docs", content="2 + 2 = 4")

        tool_registry = ToolRegistry(
            [
                FunctionTool(
                    ToolDefinition(
                        name="lookup_docs",
                        description="Lookup local docs.",
                        parameters={
                            "type": "object",
                            "properties": {"topic": {"type": "string"}},
                            "required": ["topic"],
                        },
                    ),
                    lookup_docs,
                )
            ]
        )

        system = await build_multi_agent_system(
            config={
                "agents": [
                    {
                        "name": "assistant",
                        "system_prompt": "You answer questions.",
                        "tools": ["lookup_docs"],
                        "model": {"provider": "litellm", "model": "fake"},
                    }
                ]
            },
            tool_registry=tool_registry,
            model_overrides={"assistant": EmptyAfterToolFakeModel()},
        )
        try:
            response = await system.respond("What is 2+2?")
        finally:
            await system.aclose()

        assert "The answer is 4." in response

    asyncio.run(_run())


def test_agent_recovers_from_empty_model_response_with_explicit_retry():
    async def _run():
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
            model_overrides={"assistant": EmptyUntilExplicitRetryModel()},
        )
        try:
            response = await system.respond("How are you?")
        finally:
            await system.aclose()

        assert "I am doing well." in response

    asyncio.run(_run())


def test_litellm_content_blocks_are_normalized():
    from agentic_runtime.llm import _as_dict, _extract_response_content

    message = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Two plus two is four."},
        ],
    }
    normalized = _as_dict(message)

    assert normalized["content"] == "Two plus two is four."
    assert _extract_response_content({}, {}, normalized) == "Two plus two is four."


def test_default_planner_prefers_keyword_matches_over_fallback_agents():
    planner = DefaultTaskPlanningPolicy()
    bb = EventSourcedBlackboard()
    bb.apply_patch(SetRequestPatch("use the tool to calculate 2+2", 1))

    general = AgentConfig(
        name="chat_assistant",
        model=ModelSettings(provider="litellm", model="fake"),
        system_prompt="Chat agent.",
    )
    tool_agent = AgentConfig(
        name="tool_assistant",
        model=ModelSettings(provider="litellm", model="fake"),
        system_prompt="Tool agent.",
        selection_keywords=("tool", "calculate"),
    )

    plan = planner.build_plan((general, tool_agent), bb)

    assert len(plan) == 1
    assert plan[0].assigned_agent == "tool_assistant"


def test_agents_without_mcp_servers_do_not_receive_global_mcp_tools():
    class FailingMCPRegistry:
        async def load(self, selected_servers=None):
            raise AssertionError("MCP tools should not be loaded for agents without configured MCP servers.")

    strategy = DefaultToolExecutionStrategy()
    config = AgentConfig(
        name="chat_assistant",
        model=ModelSettings(provider="litellm", model="fake"),
        system_prompt="Chat agent.",
        mcp_servers=(),
    )

    tools = asyncio.run(strategy.resolve_tools(config, ToolRegistry(), FailingMCPRegistry()))

    assert tools == ()


def test_system_can_respond_across_multiple_turns():
    async def _run():
        class SequenceModel:
            def __init__(self):
                self.calls = 0

            async def complete(self, messages, tools=()):
                self.calls += 1
                text = "Hello there." if self.calls == 1 else "Still here."
                return ChatCompletionResult(message={"role": "assistant", "content": text}, content=text)

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
            model_overrides={"assistant": SequenceModel()},
        )
        try:
            first = await system.respond("hello")
            second = await system.respond(
                "hi again",
                [ChatMessage("user", "hello", 1), ChatMessage("assistant", first, 2)],
            )
        finally:
            await system.aclose()

        assert first == "Hello there."
        assert second == "Still here."

    asyncio.run(_run())
