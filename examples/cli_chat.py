from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from dotenv import load_dotenv

from agentic_runtime import ChatMessage, build_multi_agent_system


async def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    empty_agent_log = REPO_ROOT / "logs" / "empty_agent_responses.jsonl"
    empty_cli_log = REPO_ROOT / "logs" / "cli_empty_responses.jsonl"
    litellm_log = REPO_ROOT / "logs" / "litellm_responses.jsonl"
    os.environ.setdefault("DEBUG_EMPTY_RESPONSES", "1")
    os.environ.setdefault("DEBUG_EMPTY_RESPONSE_LOG_PATH", str(empty_agent_log))
    os.environ.setdefault("DEBUG_LITELLM_LOG_PATH", str(litellm_log))
    model = os.getenv("CHAT_MODEL", "openai/gpt-4o-mini")
    api_base = os.getenv("LITELLM_API_BASE") or None
    api_key = os.getenv("LITELLM_API_KEY") or None
    mcp_url = os.getenv("MCP_SERVER_URL") or None
    config = {
        "max_parallel": 2,
        "agents": [
            {
                "name": "chat_assistant",
                "system_prompt": (
                    "You are a helpful conversational assistant. "
                    "Answer directly and naturally. Do not assume tools are needed."
                ),
                "description": "General conversation and direct question answering.",
                "capabilities": ["conversation", "general_qa"],
                "selection_keywords": [],
                "model": {
                    "provider": "litellm",
                    "model": model,
                    **({"api_base": api_base} if api_base else {}),
                    **({"api_key": api_key} if api_key else {}),
                },
            },
            {
                "name": "tool_assistant",
                "system_prompt": (
                    "You are a tool-using assistant. "
                    "Use available tools or MCP tools when the request needs external help, calculation, or lookup."
                ),
                "description": "Uses MCP tools for external actions and lookups.",
                "capabilities": ["tool_usage", "mcp_usage", "calculation", "lookup"],
                "selection_keywords": ["tool", "mcp", "calculate", "lookup", "add", "sum", "use the server", "external"],
                "mcp_servers": ["demo-tools"] if mcp_url else [],
                "model": {
                    "provider": "litellm",
                    "model": model,
                    **({"api_base": api_base} if api_base else {}),
                    **({"api_key": api_key} if api_key else {}),
                },
            },
        ],
        "mcp_servers": ([{"name": "demo-tools", "url": mcp_url}] if mcp_url else []),
    }

    system = await build_multi_agent_system(config)
    history: list[ChatMessage] = []
    turn = 1

    print("Type a question. Type 'exit' or 'quit' to stop.")
    if mcp_url:
        print(f"MCP server: {mcp_url}")
    print(f"Model: {model}")
    print("Agents: chat_assistant, tool_assistant")
    print("Use normal questions for chat_assistant.")
    print("Use phrases like 'use the server', 'tool', 'calculate', or 'sum' to trigger tool_assistant.")
    print(f"Empty agent log: {empty_agent_log}")
    print(f"Empty CLI log: {empty_cli_log}")
    print(f"LiteLLM log: {litellm_log}")
    if system.session_log_path is not None:
        print(f"Session log: {system.session_log_path}")

    try:
        while True:
            question = input("\nYou> ").strip()
            if question.lower() in {"exit", "quit"}:
                break
            if not question:
                continue

            answer = await system.respond(question, history)

            if answer.strip():
                print(f"\nBot> {answer}")
            else:
                _write_cli_empty_log(empty_cli_log, question, answer, history)
                print(f"\nBot> [empty response logged to {empty_cli_log}]")
            history.append(ChatMessage("user", question, turn))
            turn += 1
            history.append(ChatMessage("assistant", answer, turn))
            turn += 1
    finally:
        await system.aclose()

def _write_cli_empty_log(path: Path, question: str, answer: str, history: list[ChatMessage]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "question": question,
        "answer_repr": repr(answer),
        "history": [
            {"role": message.role, "content": message.content, "turn_index": message.turn_index}
            for message in history
        ],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
