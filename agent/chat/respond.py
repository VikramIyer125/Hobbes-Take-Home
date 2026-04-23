"""Stage 4: the Claude tool-use loop that produces an assistant reply."""
from __future__ import annotations

from typing import Any

from agent import llm, prompts, working
from agent.chat import budget, intent, select
from agent.chat.session import ChatSession
from agent.chat.tools import CHAT_TOOLS, dispatch_tool
from agent.config import MODEL


MAX_TOOL_ITERATIONS = 6


def _history_as_messages(
    history: list[dict[str, Any]],
    current_user: str,
    preloaded_context: str | None,
) -> list[dict[str, Any]]:
    """Convert stored session history + the current turn into the Anthropic
    messages array."""
    msgs: list[dict[str, Any]] = []
    for t in history:
        role = t.get("role")
        content = (t.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            msgs.append({"role": role, "content": content})

    user_content = current_user
    if preloaded_context:
        user_content = (
            "Here is the currently loaded memory context (rendered markdown):\n\n"
            f"{preloaded_context}\n"
            "---\n"
            f"User: {current_user}"
        )
    msgs.append({"role": "user", "content": user_content})
    return msgs


def respond(
    user_message: str,
    *,
    session: ChatSession,
) -> str:
    session.next_turn()

    history = working.load_session_history()
    decision = intent.classify_intent(user_message, history)

    ctx_markdown: str | None = None
    loaded_domains: list[str] = []
    loaded_fact_ids: list[str] = []
    total_tokens = 0
    ranked: list[str] = []

    if decision == "retrieve":
        ranked = select.rank_domains(user_message)
        ctx = budget.assemble_context(ranked, user_message)
        ctx_markdown = ctx.to_markdown()
        loaded_domains = ctx.loaded_domains()
        loaded_fact_ids = ctx.loaded_fact_ids()
        total_tokens = ctx.total_tokens

    messages = _history_as_messages(history, user_message, ctx_markdown)

    assistant_text = _run_tool_loop(messages, session=session, user_text=user_message)

    working.append_turn("user", user_message)
    working.append_turn("assistant", assistant_text)
    working.write_active_context(
        {
            "decision": decision,
            "ranked_domains": ranked,
            "loaded_domains": loaded_domains,
            "loaded_fact_ids": loaded_fact_ids,
            "token_estimate": total_tokens,
            "question": user_message,
        }
    )
    return assistant_text


def _run_tool_loop(
    messages: list[dict[str, Any]],
    *,
    session: ChatSession,
    user_text: str,
) -> str:
    client = llm.client()

    for _ in range(MAX_TOOL_ITERATIONS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=prompts.CHAT_SYSTEM,
            tools=CHAT_TOOLS,
            messages=messages,
        )

        # Capture assistant turn as-is (required for Anthropic tool protocol).
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            return _extract_text(resp.content)

        tool_results: list[dict[str, Any]] = []
        for block in resp.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            result = dispatch_tool(
                block.name,
                dict(block.input),
                session=session,
                user_text=user_text,
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    return _extract_text(messages[-1].get("content", []))  # best-effort fallback


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content or []:
        t = getattr(block, "type", "")
        if t == "text":
            parts.append(block.text)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts).strip()
