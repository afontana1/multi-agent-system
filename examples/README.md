# CLI Chat Example

Run the chat example from the repository root:

```powershell
python .\examples\cli_chat.py
```

With an HTTP MCP server:

```powershell
python .\examples\cli_chat.py --mcp-url http://localhost:8000/mcp
```

Optional flags:

- `--model openai/gpt-4o-mini`
- `--api-base http://localhost:4000`
- `--api-key <token>`

Environment variables also work:

- `CHAT_MODEL`
- `LITELLM_API_BASE`
- `LITELLM_API_KEY`
- `MCP_SERVER_URL`
