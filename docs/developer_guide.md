# Developer Guide

## Purpose

This guide is for developers extending the runtime.

It focuses on:

- adding new agents
- adding or changing policies
- adding tools
- adding MCP servers
- enabling coordinator-driven orchestration
- testing changes safely

For a broader architecture explanation, see [system_overview.md](C:\Users\ajfon\Documents\Classes\projects\multi-agent-system\docs\system_overview.md).

## Core Mental Model

The runtime is built from a few layers:

1. `MultiAgentSystem` is the public entry point.
2. The context compiler seeds the blackboard.
3. The runtime lifecycle controls planning, execution, validation, repair, and response.
4. Agents perform work.
5. Policies customize agent behavior and runtime behavior.
6. LiteLLM provides model access.
7. Local tools and HTTP MCP tools extend the model with external actions.
8. An optional coordinator can dynamically create new subtasks over multiple rounds.

When modifying the system, try to preserve that separation.

## Adding a New Agent

There are two supported paths.

### Option 1: Add a config-driven agent

Use this when the default `ConfiguredLLMAgent` behavior is sufficient.

Example:

```python
config = {
    "agents": [
        {
            "name": "researcher",
            "system_prompt": "You perform targeted research.",
            "description": "Finds relevant information and summarizes it.",
            "capabilities": ["research", "summarization"],
            "selection_keywords": ["research", "find", "look up"],
            "tools": ["lookup_docs"],
            "mcp_servers": ["demo-tools"],
            "model": {"provider": "litellm", "model": "openai/gpt-4o-mini"},
        }
    ]
}
```

Important config fields:

- `name`
- `system_prompt`
- `description`
- `capabilities`
- `selection_keywords`
- `tools`
- `mcp_servers`
- `task_template`
- `memory_window`
- `model`

This path is the fastest way to add a normal worker agent.

### Option 2: Add a concrete agent class

Use this when the agent needs custom runtime behavior.

Usually you should subclass `BaseLLMAgent`.

Example:

```python
from agentic_runtime import AgentConfig, BaseLLMAgent, ModelSettings


class ReviewerAgent(BaseLLMAgent):
    pass


agent = ReviewerAgent(
    AgentConfig(
        name="reviewer",
        system_prompt="You review outputs for correctness and risk.",
        capabilities=("review", "verification"),
        model=ModelSettings(provider="litellm", model="openai/gpt-4o-mini"),
    ),
    model=my_model,
)
```

Then pass it directly:

```python
system = await build_multi_agent_system(agents=[agent])
```

Use this path when you need:

- nonstandard memory behavior
- nonstandard context building
- nonstandard tool behavior
- nonstandard finalization
- any custom logic beyond what config alone can describe

## Choosing Between Config and Concrete Agents

Use config-driven agents when:

- behavior is mostly declarative
- prompts, tools, and capabilities are the main differences
- you want simple setup

Use concrete agent classes when:

- behavior is custom
- policy composition is not enough by itself
- you want explicit Python control over the agent

In general:

- start with config
- move to a concrete agent only when behavior actually differs

## Adding a New Agent Policy

The agent behavior seams live in agent_policies.py

The current policy families are:

- `MemoryStrategy`
- `ContextStrategy`
- `ToolExecutionStrategy`
- `FinalizationStrategy`

### Adding a memory policy

Implement `MemoryStrategy` when you want custom memory retention.

Example use cases:

- assistant-only memory
- summarizing memory
- retrieval-backed memory
- role-specific filtering

### Adding a context policy

Implement `ContextStrategy` when you want to control how prompts are built.

Example use cases:

- inserting additional system instructions
- formatting task state differently
- attaching structured context
- limiting blackboard content per task

### Adding a tool execution policy

Implement `ToolExecutionStrategy` when you want to control tool behavior.

Example use cases:

- retrying tool calls
- allow/deny rules
- usage quotas
- tool prioritization
- fallback behavior when a tool fails

### Adding a finalization policy

Implement `FinalizationStrategy` when you want to control how `AgentResult` is built.

Example use cases:

- stricter success criteria
- richer produced facts
- confidence scoring
- custom output payloads
- post-processing model output

### Wiring policies into an agent

Example:

```python
agent = CustomAgent(
    config,
    model=my_model,
    memory_strategy=my_memory_strategy,
    context_strategy=my_context_strategy,
    tool_execution_strategy=my_tool_policy,
    finalization_strategy=my_finalization_policy,
)
```

## Adding a New Runtime Policy

Runtime policies live in runtime_policies.py

The current runtime policy families are:

- `TaskPlanningPolicy`
- `RoutingPolicy`

### Adding a planning policy

Implement `TaskPlanningPolicy` when you want deterministic or rule-based changes to task decomposition.

Use cases:

- one-subtask-per-agent planning
- lane-aware planning
- priority rules
- static decompositions for known request types

### Adding a routing policy

Implement `RoutingPolicy` when you want to change how agents are selected for tasks.

Use cases:

- capability-first routing
- cost-aware routing
- confidence-aware routing
- strict assignment rules

### Wiring runtime policies into the system

Example:

```python
system = await build_multi_agent_system(
    config=config,
    planning_policy=my_planning_policy,
    routing_policy=my_routing_policy,
)
```

## Adding a Coordinator

Coordinator logic lives in coordinator.py

The coordinator is different from the planning policy.

Planning policy:

- deterministic
- infrastructure-oriented
- no model required

Coordinator:

- model-driven
- uses blackboard task status
- uses agent capabilities
- can replan after execution rounds complete

### Add a coordinator by config

```python
system = await build_multi_agent_system(
    config=config,
    coordinator_spec={
        "name": "coordinator",
        "system_prompt": "Plan subtasks as JSON using task status and agent capabilities.",
        "model": {"provider": "litellm", "model": "openai/gpt-4o-mini"},
    },
)
```

### Add a coordinator instance directly

```python
from agentic_runtime import CoordinatorAgent, CoordinatorConfig

coordinator = CoordinatorAgent(
    CoordinatorConfig(
        name="coordinator",
        system_prompt="Plan subtasks as JSON.",
        model=my_model_settings,
    ),
    model=my_model,
)

system = await build_multi_agent_system(config=config, coordinator=coordinator)
```

### What the coordinator sees

The coordinator prompt includes:

- the current user request
- structured task status:
  - pending
  - running
  - completed
  - failed
- an agent catalog with:
  - name
  - description
  - capabilities
  - selection keywords
  - lane

### Coordinator output contract

The coordinator currently returns JSON like:

```json
{
  "subtasks": [
    {
      "description": "Research the relevant design choices",
      "assigned_agent": "researcher",
      "priority": 10
    }
  ]
}
```

If you change this contract, you must update:

- coordinator.py
- tests that cover coordinator behavior

## Adding a Local Tool

Local tools are defined through tools.py

Example:

```python
from agentic_runtime import FunctionTool, ToolDefinition, ToolRegistry, ToolResult


async def lookup_docs(arguments):
    return ToolResult(tool_name="lookup_docs", content=f"Docs for {arguments['topic']}")


tool_registry = ToolRegistry(
    [
        FunctionTool(
            ToolDefinition(
                name="lookup_docs",
                description="Lookup project docs.",
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
```

Then pass the tool registry into `build_multi_agent_system()`.

Important:

- tool schemas are normalized into OpenAI-compatible function-tool format before being sent to models
- tool results are sent back to the model as OpenAI-style tool messages

## Adding an MCP Server

MCP support is HTTP-only and lives in mcp.py

Server config shape:

```json
{
  "name": "demo-tools",
  "url": "http://localhost:8000/mcp"
}
```

Agent config references MCP servers by name:

```json
{
  "name": "assistant",
  "mcp_servers": ["demo-tools"]
}
```

The demo server is:

- mcp/simple_server.py

## Adding a New Model Provider Behavior

Model access is abstracted through `IChatModel` in llm.py

The default is `LiteLLMChatModel`.

If you want custom behavior, you can:

- implement `IChatModel`
- inject the model directly into a custom agent
- or provide a test/double via `model_overrides`

This is the preferred extension point instead of editing the agent runtime directly.

## How to Use `build_multi_agent_system()`

This is the main assembly API.

It supports:

- `config=...`
- `agent_specs=...`
- `agents=[...]`
- `coordinator=...`
- `coordinator_spec=...`
- `planning_policy=...`
- `routing_policy=...`
- `tool_registry=...`
- `model_overrides=...`
- `mcp_registry_override=...`

Typical usage patterns:

### Simple

```python
system = await build_multi_agent_system(config=config)
```

### Config agents plus coordinator

```python
system = await build_multi_agent_system(
    config=config,
    coordinator_spec=coordinator_spec,
)
```

### Concrete agents with custom policies

```python
system = await build_multi_agent_system(
    agents=[custom_agent],
    routing_policy=my_routing_policy,
)
```

## Testing Strategy

The canonical smoke tests are in:

- tests/test_smoke.py

Current test coverage includes:

- config-driven agents
- concrete agent instances
- custom memory/context/tool/finalization policies
- custom planning/routing policies
- coordinator-driven replanning
- OpenAI tool schema formatting
- MCP-backed tool execution via a loopback HTTP test server

When changing architecture, add tests that prove the new seam is actually exercised.

For example, if you add a new policy:

- make it record whether it was called
- assert it actually changes behavior

That is better than only testing that construction succeeds.

## Recommended Development Workflow

When adding a new extension point:

1. Decide whether it belongs in:
   - agent policies
   - runtime policies
   - coordinator logic
   - model abstraction
   - tool abstraction
2. Add the abstraction first.
3. Add a default implementation.
4. Thread it through the builder or agent constructor.
5. Add at least one test proving the new abstraction is actually used.
6. Update docs and diagrams if the architecture changed.

## Common Mistakes to Avoid

### 1. Putting behavior into config that should be code

If the behavior is procedural or conditional, it probably belongs in a policy or a concrete agent class, not more config keys.

### 2. Subclassing when a policy is enough

If you only want to change memory, context, tool execution, finalization, planning, or routing, prefer a policy object over a new subclass.

### 3. Mixing coordinator logic into static planning

Keep the distinction:

- static planning policy
- dynamic coordinator behavior

If you blur those together, the orchestration model becomes harder to reason about.

### 4. Changing tool message formats casually

The tool-call path is intentionally normalized for OpenAI-compatible models.

If you change:

- tool schema formatting
- assistant tool call formatting
- tool result message formatting

you may break model interoperability.