from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from agentic_runtime import ChatMessage, build_multi_agent_system


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chat with the multi-agent runtime from the command line.")
    parser.add_argument("--model", default=os.getenv("CHAT_MODEL", "openai/gpt-4o-mini"), help="LiteLLM model name.")
    parser.add_argument("--api-base", default=os.getenv("LITELLM_API_BASE"), help="Optional LiteLLM API base.")
    parser.add_argument("--api-key", default=os.getenv("LITELLM_API_KEY"), help="Optional LiteLLM API key.")
    parser.add_argument("--mcp-url", default=os.getenv("MCP_SERVER_URL"), help="Optional HTTP MCP endpoint, for example http://localhost:8000/mcp.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    config = {
        "max_parallel": 2,
        "agents": [
            {
                "name": "assistant",
                "system_prompt": (
                    "You are a helpful multi-agent assistant. "
                    "Use MCP tools when they are relevant and answer clearly."
                ),
                "selection_keywords": [],
                "mcp_servers": ["demo-tools"] if args.mcp_url else [],
                "model": {
                    "provider": "litellm",
                    "model": args.model,
                    **({"api_base": args.api_base} if args.api_base else {}),
                    **({"api_key": args.api_key} if args.api_key else {}),
                },
            }
        ],
        "mcp_servers": ([{"name": "demo-tools", "url": args.mcp_url}] if args.mcp_url else []),
    }

    system = await build_multi_agent_system(config)
    history: list[ChatMessage] = []
    turn = 1

    print("Type a question. Type 'exit' or 'quit' to stop.")
    if args.mcp_url:
        print(f"MCP server: {args.mcp_url}")
    print(f"Model: {args.model}")

    try:
        while True:
            question = input("\nYou> ").strip()
            if question.lower() in {"exit", "quit"}:
                break
            if not question:
                continue

            history.append(ChatMessage("user", question, turn))
            answer = await system.respond(question, history)
            turn += 1

            print(f"\nBot> {answer}")
            history.append(ChatMessage("assistant", answer, turn))
            turn += 1
    finally:
        await system.aclose()


if __name__ == "__main__":
    asyncio.run(main())
