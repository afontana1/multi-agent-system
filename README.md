# agentic-runtime

A modular multi-agent runtime with:
- HFSM lifecycle control
- behavior trees for execution and repair
- event-sourced blackboard with typed patches
- configurable LiteLLM-backed agents
- coordinator-driven replanning across multiple execution rounds
- local tool execution and MCP server tools
- pluggable memory, context, tool execution, finalization, planning, and routing policies
- config-driven agent registration

There is also a minimal HTTP FastMCP server at [mcp/README.md](C:\Users\ajfon\Documents\Classes\projects\multi-agent-system\mcp\README.md) for local or network MCP integration testing.
For a terminal chat example, see [examples/README.md](C:\Users\ajfon\Documents\Classes\projects\multi-agent-system\examples\README.md).
Architecture diagrams live in [docs/README.md](C:\Users\ajfon\Documents\Classes\projects\multi-agent-system\docs\README.md).

## Quick start

```python
import asyncio

from agentic_runtime import FunctionTool, ToolDefinition, ToolRegistry, ToolResult, build_multi_agent_system


async def lookup_docs(arguments):
    return ToolResult(tool_name="lookup_docs", content=f"Docs for {arguments['topic']}")


async def main():
    system = await build_multi_agent_system(
        {
            "agents": [
                {
                    "name": "assistant",
                    "system_prompt": "You answer user questions with tools when useful.",
                    "capabilities": ["general_qa", "tool_usage"],
                    "tools": ["lookup_docs"],
                    "model": {"provider": "litellm", "model": "openai/gpt-4o-mini"},
                }
            ]
        },
        coordinator_spec={
            "name": "coordinator",
            "system_prompt": "Plan the next subtasks as JSON using agent capabilities and task status.",
            "model": {"provider": "litellm", "model": "openai/gpt-4o-mini"},
        },
        tool_registry=ToolRegistry(
            [
                FunctionTool(
                    ToolDefinition(
                        name="lookup_docs",
                        description="Lookup project documentation.",
                        parameters={"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]},
                    ),
                    lookup_docs,
                )
            ]
        ),
    )
    try:
        print(await system.respond("How do I add a new agent?"))
    finally:
        await system.aclose()


asyncio.run(main())
```
