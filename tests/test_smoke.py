import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agentic_runtime import (
    ChatCompletionResult,
    ChatMessage,
    FunctionTool,
    ToolCall,
    ToolDefinition,
    ToolRegistry,
    ToolResult,
    build_multi_agent_system,
)
from agentic_runtime.tools import tool_to_openai_schema


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
