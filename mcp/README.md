# FastMCP Demo Server

This folder contains a minimal FastMCP server exposed over HTTP with FastAPI. Use it as a known-good MCP target while wiring the runtime to MCP over the network.

## Run

```powershell
python .\mcp\simple_server.py
```

It binds to `0.0.0.0:8000` by default.

To change the bind address:

```powershell
$env:HOST="0.0.0.0"
$env:PORT="8080"
python .\mcp\simple_server.py
```

## Tools

- `echo_text(text: str) -> str`
- `add_numbers(a: int, b: int) -> int`

## Endpoints

- `GET /health`
- MCP transport mounted at `/mcp`

## Example runtime config

```json
{
  "mcp_servers": [
    {
      "name": "demo-tools",
      "url": "http://localhost:8000/mcp"
    }
  ]
}
```
