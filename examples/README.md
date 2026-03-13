# CLI Chat Example

Run the chat example from the repository root:

```powershell
python .\examples\cli_chat.py
```

This uses config-driven agents built through `build_multi_agent_system(config=...)`.
It is intentionally chat-first:

- `chat_assistant` handles normal conversation
- `tool_assistant` handles requests that explicitly mention tools, MCP, server usage, or calculation

## Custom Agent Example

Run the custom-agent example from the repository root:

```powershell
python .\examples\custom_agents_chat.py
```

This example uses concrete `BaseLLMAgent` subclasses passed directly to `build_multi_agent_system(agents=[...])`.
It also keeps the coordinator enabled, so it is the better example if you want to study multi-round orchestration.

## Environment Configuration

Both examples load settings from the repository `.env` file.

Current variables:

- `CHAT_MODEL`
- `LITELLM_API_BASE`
- `LITELLM_API_KEY`
- `MCP_SERVER_URL`
- `DEBUG_LITELLM_RESPONSES`
- `DEBUG_LITELLM_PRINT`
- `DEBUG_LITELLM_LOG_PATH`

Example:

```dotenv
CHAT_MODEL=openai/gpt-4o-mini
LITELLM_API_BASE=
LITELLM_API_KEY=
MCP_SERVER_URL=http://localhost:8000/mcp
DEBUG_LITELLM_RESPONSES=0
DEBUG_LITELLM_PRINT=1
DEBUG_LITELLM_LOG_PATH=logs/litellm_responses.jsonl
```

If `MCP_SERVER_URL` is empty, the examples run without MCP.

To capture raw LiteLLM response payloads while debugging, set:

```dotenv
DEBUG_LITELLM_RESPONSES=1
```

That will print the raw normalized payload to the terminal and also append it to `DEBUG_LITELLM_LOG_PATH` if that path is set.
