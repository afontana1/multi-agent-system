import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send
from mcp.server.fastmcp import FastMCP


server = FastMCP("demo-tools")
server.settings.streamable_http_path = "/"


@server.tool()
def echo_text(text: str) -> str:
    return f"echo: {text}"


@server.tool()
def add_numbers(a: int, b: int) -> int:
    return a + b


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with server.session_manager.run():
        yield


app = FastAPI(title="Demo MCP Server", lifespan=lifespan)


class MCPPathNormalizer:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
        await self._app(scope, receive, send)


app.add_middleware(MCPPathNormalizer)
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
