import os

import uvicorn
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP


server = FastMCP("demo-tools")


@server.tool()
def echo_text(text: str) -> str:
    return f"echo: {text}"


@server.tool()
def add_numbers(a: int, b: int) -> int:
    return a + b


app = FastAPI(title="Demo MCP Server")
app.mount("/mcp", server.streamable_http_app())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
