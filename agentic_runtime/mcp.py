from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence
from urllib import request
from urllib.error import HTTPError, URLError

from .domain import MCPServerConfig, ToolResult
from .tools import ITool, ToolDefinition


class MCPProtocolError(RuntimeError):
    pass


class MCPHttpClient:
    def __init__(self, config: MCPServerConfig) -> None:
        self._config = config
        self._next_id = 0
        self._initialized = False

    async def start(self) -> None:
        if self._initialized:
            return
        await self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agentic-runtime", "version": "0.1.0"},
            },
        )
        await self.notify("notifications/initialized", {})
        self._initialized = True

    async def list_tools(self) -> Sequence[Dict[str, Any]]:
        response = await self.request("tools/list", {})
        return tuple(response.get("tools", []) or ())

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        payload = await self.request("tools/call", {"name": name, "arguments": arguments})
        content = payload.get("content", [])
        text_chunks = []
        for item in content:
            if item.get("type") == "text":
                text_chunks.append(item.get("text", ""))
        if not text_chunks and "structuredContent" in payload:
            text_chunks.append(json.dumps(payload["structuredContent"]))
        return ToolResult(
            tool_name=name,
            content="\n".join(text_chunks),
            is_error=bool(payload.get("isError")),
            metadata={"server": self._config.name, "url": self._config.url},
        )

    async def notify(self, method: str, params: Dict[str, Any]) -> None:
        await self._post({"jsonrpc": "2.0", "method": method, "params": params}, expect_response=False)

    async def request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self._next_id += 1
        payload = await self._post({"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params})
        if "error" in payload:
            raise MCPProtocolError(str(payload["error"]))
        return dict(payload.get("result", {}))

    async def aclose(self) -> None:
        return None

    async def _post(self, payload: Dict[str, Any], expect_response: bool = True) -> Dict[str, Any]:
        return await asyncio.to_thread(self._post_sync, payload, expect_response)

    def _post_sync(self, payload: Dict[str, Any], expect_response: bool) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self._config.headers,
        }
        req = request.Request(self._config.url, data=body, headers=headers, method="POST")
        try:
            with request.urlopen(req) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise MCPProtocolError(f"HTTP {exc.code} from MCP server '{self._config.name}': {detail}") from exc
        except URLError as exc:
            raise MCPProtocolError(f"Could not reach MCP server '{self._config.name}' at {self._config.url}: {exc}") from exc
        if not expect_response or not raw:
            return {}
        return json.loads(raw.decode("utf-8"))


@dataclass
class MCPTool(ITool):
    client: MCPHttpClient
    server_name: str
    name: str
    description: str
    parameters: Dict[str, Any]

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            source="mcp",
            metadata={"server": self.server_name},
        )

    async def invoke(self, arguments: Dict[str, Any]) -> ToolResult:
        return await self.client.call_tool(self.name, arguments)


class MCPToolRegistry:
    def __init__(self, configs: Sequence[MCPServerConfig]) -> None:
        self._configs = tuple(config for config in configs if config.enabled)
        self._clients: Dict[str, MCPHttpClient] = {}
        self._tools: Dict[str, MCPTool] = {}

    async def load(self, selected_servers: Optional[Sequence[str]] = None) -> Sequence[ITool]:
        allowed = set(selected_servers or ())
        for config in self._configs:
            if allowed and config.name not in allowed:
                continue
            if config.name in self._clients:
                continue
            client = MCPHttpClient(config)
            await client.start()
            self._clients[config.name] = client
            for tool in await client.list_tools():
                name = tool["name"]
                self._tools[name] = MCPTool(
                    client=client,
                    server_name=config.name,
                    name=name,
                    description=tool.get("description", f"MCP tool from {config.name}"),
                    parameters=tool.get("inputSchema", {"type": "object", "properties": {}}),
                )
        if allowed:
            return tuple(tool for tool in self._tools.values() if tool.server_name in allowed)
        return tuple(self._tools.values())

    async def aclose(self) -> None:
        for client in tuple(self._clients.values()):
            await client.aclose()
        self._clients.clear()
        self._tools.clear()
