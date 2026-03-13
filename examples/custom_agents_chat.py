from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from dotenv import load_dotenv

from agentic_runtime import AgentConfig, BaseLLMAgent, ChatMessage, EventSourcedBlackboard, ModelSettings, SubTask, build_multi_agent_system


class ResearchAgent(BaseLLMAgent):
    async def run(self, subtask: SubTask, bb: EventSourcedBlackboard):
        direct = await self._maybe_handle_addition(bb, subtask)
        if direct is not None:
            return direct
        return await super().run(subtask, bb)

    async def _maybe_handle_addition(self, bb: EventSourcedBlackboard, subtask: SubTask):
        match = re.search(r"(?P<a>\d+)\s*\+\s*(?P<b>\d+)", bb.state.current_user_request)
        if match is None:
            return None

        tools = await self.resolve_tools()
        tool = next((item for item in tools if item.definition.name == "add_numbers"), None)
        if tool is None:
            return None

        arguments = {"a": int(match.group("a")), "b": int(match.group("b"))}
        result = await tool.invoke(arguments)
        final_text = f"The sum of {arguments['a']} and {arguments['b']} is {result.content}."
        self.append_memory("user", bb.state.current_user_request)
        self.append_memory("assistant", final_text)
        return self.build_agent_result(subtask, bb, final_text, (result,))


class WriterAgent(BaseLLMAgent):
    pass


def model_settings(model: str, api_base: str | None, api_key: str | None) -> ModelSettings:
    return ModelSettings(
        provider="litellm",
        model=model,
        api_base=api_base,
        api_key=api_key,
    )


async def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    empty_agent_log = REPO_ROOT / "logs" / "empty_agent_responses.jsonl"
    empty_cli_log = REPO_ROOT / "logs" / "custom_agents_empty_responses.jsonl"
    litellm_log = REPO_ROOT / "logs" / "litellm_responses.jsonl"
    os.environ.setdefault("DEBUG_EMPTY_RESPONSES", "1")
    os.environ.setdefault("DEBUG_EMPTY_RESPONSE_LOG_PATH", str(empty_agent_log))
    os.environ.setdefault("DEBUG_LITELLM_LOG_PATH", str(litellm_log))
    model = os.getenv("CHAT_MODEL", "openai/gpt-4o-mini")
    api_base = os.getenv("LITELLM_API_BASE") or None
    api_key = os.getenv("LITELLM_API_KEY") or None
    mcp_url = os.getenv("MCP_SERVER_URL") or None
    shared_model = model_settings(model, api_base, api_key)

    researcher = ResearchAgent(
        AgentConfig(
            name="researcher",
            system_prompt=(
                "You are a research specialist. "
                "Only handle requests that require research, fact gathering, or external tool use. "
                "Do not answer casual greetings or simple conversational prompts unless explicitly assigned."
            ),
            description="Research-focused specialist.",
            capabilities=("research", "fact_gathering", "tool_usage", "mcp_usage", "calculation"),
            selection_keywords=("research", "investigate", "find", "tool", "mcp", "server", "calculate", "add", "sum"),
            mcp_servers=("demo-tools",) if mcp_url else (),
            model=shared_model,
        ),
        model=build_model(model, api_base, api_key),
    )
    writer = WriterAgent(
        AgentConfig(
            name="writer",
            system_prompt=(
                "You are the primary conversational assistant. "
                "Answer directly, naturally, and concisely. "
                "If research findings are available, synthesize them into a clean final response. "
                "If the user asks whether tools or MCP were used, answer based on the provided context and prior results. "
                "Pay attention to any bracketed tool activity notes in the conversation history. "
                "Do not claim inability if another agent already performed the tool work."
            ),
            description="Primary conversational and synthesis specialist.",
            capabilities=("conversation", "direct_qa", "writing", "synthesis"),
            model=shared_model,
        ),
        model=build_model(model, api_base, api_key),
    )

    system = await build_multi_agent_system(
        agents=[researcher, writer],
        coordinator_spec={
            "name": "coordinator",
            "system_prompt": (
                "Plan subtasks as JSON using task status and agent capabilities. "
                "For casual conversation, greetings, or simple direct questions, assign only the writer. "
                "Use the researcher when information gathering, factual lookup, MCP usage, tool usage, or calculation is needed. "
                "If the user asks whether a tool or MCP server was used, include the writer only if a final conversational explanation is needed. "
                "If both are needed, use researcher first and then writer for the final response. "
                "Do not assign both agents for a simple conversational turn."
            ),
            "model": {
                "provider": "litellm",
                "model": model,
                **({"api_base": api_base} if api_base else {}),
                **({"api_key": api_key} if api_key else {}),
            },
        },
        config={
            "mcp_servers": ([{"name": "demo-tools", "url": mcp_url}] if mcp_url else []),
            "agents": [],
        },
    )

    history: list[ChatMessage] = []
    turn = 1

    print("Type a question. Type 'exit' or 'quit' to stop.")
    print("Custom agents: researcher, writer")
    if mcp_url:
        print(f"MCP server: {mcp_url}")
    print(f"Model: {model}")
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

            trace = await system.respond_with_trace(question, history)
            answer = trace.response

            if answer.strip():
                print(f"\nBot> {answer}")
            else:
                _write_cli_empty_log(empty_cli_log, question, answer, history)
                print(f"\nBot> [empty response logged to {empty_cli_log}]")
            if trace.agents_called:
                print(f"Agents called: {', '.join(trace.agents_called)}")
            tool_activity = _tool_activity_lines(trace.results_by_agent)
            if tool_activity:
                print(f"Tool activity: {' | '.join(tool_activity)}")
            if trace.failures:
                print(f"Failures: {' | '.join(trace.failures)}")
            history.append(ChatMessage("user", question, turn))
            turn += 1
            history.append(ChatMessage("assistant", _history_entry_content(answer, tool_activity), turn))
            turn += 1
    finally:
        await system.aclose()


def build_model(model: str, api_base: str | None, api_key: str | None):
    from agentic_runtime import LiteLLMChatModel

    return LiteLLMChatModel(
        model=model,
        api_base=api_base,
        api_key=api_key,
    )


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


def _tool_activity_lines(results_by_agent: dict[str, list[dict] | tuple[dict, ...]]) -> list[str]:
    lines: list[str] = []
    for agent_name, outputs in results_by_agent.items():
        for output in outputs:
            tool_results = output.get("tool_results", [])
            tool_names = [item.get("tool_name") for item in tool_results if item.get("tool_name")]
            if tool_names:
                lines.append(f"{agent_name}: {', '.join(tool_names)}")
    return lines


def _history_entry_content(answer: str, tool_activity: list[str]) -> str:
    if not tool_activity:
        return answer
    return f"{answer}\n\n[Tool activity: {' | '.join(tool_activity)}]"


if __name__ == "__main__":
    asyncio.run(main())
