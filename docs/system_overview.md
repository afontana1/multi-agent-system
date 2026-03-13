# System Overview

## What This System Is

This project is a modular multi-agent LLM runtime built around a few core ideas:

- a central event-sourced blackboard stores task state, facts, constraints, and results
- a hybrid runtime manages lifecycle transitions such as planning, execution, repair, validation, and response
- agents are real runtime objects, not just config blobs
- agent behavior is split into swappable policies for memory, context building, tool execution, finalization, planning, and routing
- an optional coordinator agent can dynamically replan work across multiple rounds
- model calls are made through LiteLLM
- tools can be local Python functions or MCP tools exposed over HTTP

The result is a system that can start simple with config-defined agents, but can also grow into a more dynamic orchestration runtime with custom agent classes and coordinator-driven workflows.

## High-Level Architecture

At a high level, the system looks like this:

1. A caller sends a user query into `MultiAgentSystem`.
2. The context compiler seeds a blackboard with the request, history, and inferred constraints.
3. The runtime enters its lifecycle loop.
4. A planner decides what subtasks should exist.
5. The execution service selects agents and runs ready subtasks.
6. Each LLM agent builds messages, resolves tools, calls the model, executes tool calls, and finalizes an `AgentResult`.
7. Results are written back to the blackboard.
8. The runtime may replan, validate, repair, or synthesize a final response.
9. The caller receives the final answer.

If a coordinator is enabled, planning is not just a one-time static step. The coordinator can inspect the current task status and agent capabilities, then emit additional subtasks for later rounds.

## Main Modules

### `agentic_runtime/system.py`

This is the main entry point.

It exposes:

- `MultiAgentSystem`
- `build_multi_agent_system()`

`build_multi_agent_system()` assembles the runtime from:

- config-defined agent specs
- concrete prebuilt agent instances
- optional coordinator config or coordinator instance
- optional custom planning and routing policies
- optional MCP registry override
- optional model overrides for testing or custom providers

### `agentic_runtime/controller.py`

This contains `HybridAgentRuntimeV2`, the lifecycle controller.

It uses:

- HFSM states for the major lifecycle phases
- behavior-tree style execution and repair loops
- a planner to create subtasks
- an execution service to run ready work
- a validator and synthesizer to produce the final result

The lifecycle is roughly:

- `INTAKE`
- `PLAN`
- `EXECUTE`
- `REPAIR`
- `VALIDATE`
- `RESPOND`
- `DONE` or `FAILED`

One important design point is that the runtime can now re-enter `PLAN` after execution. That allows multi-round coordination instead of forcing all subtasks to be defined up front.

### `agentic_runtime/blackboard.py`

This is the central state container.

The blackboard stores:

- current request and chat history
- constraints
- facts
- subtasks and their status
- results by agent
- failures
- final response

It is event-sourced:

- patches emit typed domain events
- a reducer applies events back into state

This makes the runtime easier to reason about, inspect, and extend.

The coordinator also relies on a structured task snapshot from the blackboard so it can see:

- pending tasks
- running tasks
- completed tasks
- failed tasks

### `agentic_runtime/agents.py`

This module contains the runtime agent abstractions.

The important layers are:

- `IExpertAgent`: runtime agent interface
- `BaseAgent`: shared agent identity, routing metadata, planning metadata, and memory hooks
- `BaseLLMAgent`: shared LLM-agent behavior
- `ConfiguredLLMAgent`: default config-driven LLM agent

`BaseLLMAgent` handles:

- prompt/message assembly
- model invocation
- OpenAI-compatible tool call formatting
- tool-call loop
- memory updates
- final `AgentResult` production

But it does not hardcode all of that logic internally anymore. Most of that behavior is delegated to policy objects.

### `agentic_runtime/agent_policies.py`

This module is the main extension seam for agent behavior.

It currently contains policies for:

- memory
- context building
- tool execution
- finalization

Concrete defaults include:

- `WindowedMemoryStrategy`
- `DefaultContextStrategy`
- `DefaultToolExecutionStrategy`
- `DefaultFinalizationStrategy`

This means you can keep the same agent class but swap out how it:

- stores memory
- builds prompts
- resolves and executes tools
- decides success/failure and builds facts/results

### `agentic_runtime/runtime_policies.py`

This module contains runtime-level policies:

- `TaskPlanningPolicy`
- `RoutingPolicy`

Concrete defaults include:

- `DefaultTaskPlanningPolicy`
- `DefaultRoutingPolicy`

These determine:

- how subtasks are created
- how agents are selected for work

This keeps planning and routing separate from the HFSM itself.

### `agentic_runtime/coordinator.py`

This is what turns the system from “static agent execution” into a real orchestrated multi-agent workflow.

It contains:

- `CoordinatorConfig`
- `CoordinatorAgent`
- `CoordinatorTaskPlanner`

The coordinator:

- receives the current request
- sees structured task status from the blackboard
- sees available agent capabilities
- asks a model to return JSON subtasks
- emits only novel tasks
- can plan additional tasks after earlier tasks complete

This is different from the plain planning policy.

The planning policy is deterministic infrastructure.
The coordinator is a model-driven planner/orchestrator.

### `agentic_runtime/llm.py`

This contains the model abstraction and the LiteLLM adapter.

Important points:

- the system uses `IChatModel`
- the default implementation is `LiteLLMChatModel`
- tool schemas are normalized to OpenAI-compatible function-tool format
- assistant tool calls and tool result messages are normalized to OpenAI-style message shapes

This is important because many model providers behind LiteLLM expect OpenAI-style chat/tool conventions.

### `agentic_runtime/tools.py`

This defines local tool abstractions.

Important pieces:

- `ToolDefinition`
- `ITool`
- `FunctionTool`
- `ToolRegistry`

A local tool is just a registered async handler plus its schema.

### `agentic_runtime/mcp.py`

This defines HTTP-only MCP integration.

Important pieces:

- `MCPHttpClient`
- `MCPTool`
- `MCPToolRegistry`

The runtime discovers MCP tools over HTTP and exposes them to agents in the same general way as local tools.

## Agent Model

Agents can be created in two main ways.

### 1. Config-driven agents

These are `AgentConfig` specs turned into `ConfiguredLLMAgent` instances automatically.

Use this when:

- the agent is mostly standard LLM behavior
- differences are declarative
- you want simple runtime construction

Typical fields include:

- `name`
- `system_prompt`
- `description`
- `capabilities`
- `selection_keywords`
- `tools`
- `mcp_servers`
- `memory_window`
- `model`

### 2. Concrete agent classes

You can subclass `BaseLLMAgent` or implement `IExpertAgent` directly and pass those agents into `build_multi_agent_system(agents=[...])`.

Use this when:

- you need custom behavior
- you want nonstandard tool behavior
- you want custom memory or finalization logic
- you want an agent with bespoke routing or task semantics

## Policy-Based Design

One of the main design goals is to avoid a large inheritance tree where every new behavior requires a new agent subclass.

Instead, the system is built around policy composition.

### Agent policies

These change how an agent behaves internally:

- memory strategy
- context strategy
- tool execution strategy
- finalization strategy

### Runtime policies

These change how the system behaves around agents:

- planning policy
- routing policy

### Coordinator

The coordinator adds another layer:

- model-driven orchestration across multiple rounds

This separation is deliberate:

- policies handle predictable infrastructure behavior
- the coordinator handles dynamic, model-driven orchestration

## Request Lifecycle

Here is the practical runtime flow for a typical request:

1. `MultiAgentSystem.respond()` is called.
2. The context compiler writes the request and inferred constraints into the blackboard.
3. The runtime enters `PLAN`.
4. A planner or coordinator generates subtasks.
5. The runtime enters `EXECUTE`.
6. The execution service finds ready tasks.
7. The router chooses the agent for each task.
8. The agent:
   - builds messages
   - resolves local and MCP tools
   - calls LiteLLM
   - handles tool calls if present
   - finalizes an `AgentResult`
9. The blackboard records the result and marks tasks complete.
10. The runtime may re-enter `PLAN` to add more work.
11. When no more novel work exists, the runtime validates and synthesizes the final response.
12. The response is returned.

## Coordinator vs Planner

This distinction matters.

### Planning policy

The planning policy is infrastructure logic.

It answers:

- given the request and known agents, what subtasks should exist?

It is usually:

- deterministic
- rule-based
- predictable

### Coordinator agent

The coordinator is an actual model-driven orchestrator.

It answers:

- what should happen next based on what has already happened?

It is:

- dynamic
- state-aware
- capable of multi-round replanning

You can run the system without a coordinator.
But if you want more realistic multi-agent behavior, the coordinator is the piece that makes the orchestration adaptive.

## How to Use the System

### Basic config-driven usage

```python
import asyncio

from agentic_runtime import build_multi_agent_system


async def main():
    system = await build_multi_agent_system(
        config={
            "agents": [
                {
                    "name": "assistant",
                    "system_prompt": "You answer user questions.",
                    "capabilities": ["general_qa"],
                    "model": {"provider": "litellm", "model": "openai/gpt-4o-mini"},
                }
            ]
        }
    )
    try:
        answer = await system.respond("Explain the architecture.")
        print(answer)
    finally:
        await system.aclose()


asyncio.run(main())
```

### With a coordinator

```python
import asyncio

from agentic_runtime import build_multi_agent_system


async def main():
    system = await build_multi_agent_system(
        config={
            "agents": [
                {
                    "name": "researcher",
                    "system_prompt": "You gather information.",
                    "capabilities": ["research"],
                    "model": {"provider": "litellm", "model": "openai/gpt-4o-mini"},
                },
                {
                    "name": "writer",
                    "system_prompt": "You write final explanations.",
                    "capabilities": ["writing"],
                    "model": {"provider": "litellm", "model": "openai/gpt-4o-mini"},
                },
            ]
        },
        coordinator_spec={
            "name": "coordinator",
            "system_prompt": "Plan subtasks as JSON using task status and agent capabilities.",
            "model": {"provider": "litellm", "model": "openai/gpt-4o-mini"},
        },
    )
    try:
        print(await system.respond("Research the system and write a summary."))
    finally:
        await system.aclose()


asyncio.run(main())
```

### With a custom agent instance

```python
import asyncio

from agentic_runtime import AgentConfig, BaseLLMAgent, ModelSettings, build_multi_agent_system


class CustomAgent(BaseLLMAgent):
    pass


async def main():
    agent = CustomAgent(
        AgentConfig(
            name="custom_agent",
            system_prompt="You are a custom agent.",
            model=ModelSettings(provider="litellm", model="openai/gpt-4o-mini"),
            capabilities=("custom_reasoning",),
        ),
        model=...,
    )

    system = await build_multi_agent_system(agents=[agent])
    try:
        print(await system.respond("Do something custom."))
    finally:
        await system.aclose()


asyncio.run(main())
```

## MCP Usage

MCP is HTTP-only in this codebase.

An MCP server entry looks like:

```json
{
  "name": "demo-tools",
  "url": "http://localhost:8000/mcp"
}
```

Agents can reference MCP servers by name:

```json
{
  "name": "assistant",
  "mcp_servers": ["demo-tools"]
}
```

The demo HTTP MCP server lives in:

- mcp/simple_server.py

## Command-Line Usage

For a CLI chat entry point, use:

- examples/cli_chat.py

Example:

```powershell
python .\examples\cli_chat.py
```

With MCP:

```powershell
python .\examples\cli_chat.py --mcp-url http://localhost:8000/mcp
```

## Design Strengths

The current design is strong in a few ways.

### 1. Clear separation of concerns

- runtime control is separate from agent behavior
- agent behavior is separate from policy behavior
- model access is separate from tool access
- MCP integration is separate from local tools

### 2. Config-first, but not config-only

You can start with simple config-driven agents, then graduate to custom agent classes without rewriting the whole runtime.

### 3. Good extension seams

You can customize:

- planning
- routing
- memory
- context building
- tool execution
- finalization
- coordination

without rewriting the lifecycle controller.

### 4. Coordinator support

The runtime no longer assumes all work must be planned up front. That is essential for real multi-agent orchestration.

## Current Limitations

The architecture is in good shape, but there are still practical limitations.

### 1. Coordinator output is prompt-based JSON

The coordinator currently relies on the model returning the expected JSON shape. That works, but structured output validation could be stronger.

### 2. Validation is still lightweight

The validator is intentionally simple and does not yet deeply judge quality, consistency, or evidence.

### 3. Tool policies are basic

There is now a tool execution strategy seam, but default behavior is still straightforward. More sophisticated policies could add:

- retries
- sandboxing
- allow/deny lists
- cost controls
- tool ranking

### 4. No persistent memory layer yet

Agent memory is in-process and policy-driven, but not persistent or retrieval-backed.

## Recommended Next Steps

If you continue developing this system, the highest-value next steps are:

1. Add structured output validation for coordinator planning.
2. Add richer validator logic for answer quality and evidence.
3. Add persistent or retrieval-backed memory policies.
4. Add tool authorization and retry controls.
5. Add better coordinator prompts and agent capability schemas.
6. Add observability around planning rounds, model calls, and tool usage.