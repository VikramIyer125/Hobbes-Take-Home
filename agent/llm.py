"""Anthropic client wrapper with helpers for text + tool-use calls."""
from __future__ import annotations

import os
from typing import Any, Optional

from anthropic import Anthropic

from agent.config import MODEL


_client: Optional[Anthropic] = None


def client() -> Anthropic:
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Export it before running the agent."
            )
        _client = Anthropic()
    return _client


def complete_text(
    *,
    system: str,
    user: str,
    max_tokens: int = 1024,
    model: Optional[str] = None,
) -> str:
    """Plain text completion — returns the concatenated text blocks."""
    resp = client().messages.create(
        model=model or MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(
        block.text for block in resp.content if getattr(block, "type", "") == "text"
    ).strip()


def forced_tool_call(
    *,
    system: str,
    user: str,
    tool_name: str,
    tool_description: str,
    input_schema: dict[str, Any],
    max_tokens: int = 4096,
    model: Optional[str] = None,
) -> dict[str, Any]:
    """Force Claude to call a single tool and return its ``input`` dict.

    This is the structured-output primitive: we never ask Claude to emit JSON
    as text, only through a typed tool.
    """
    tool = {
        "name": tool_name,
        "description": tool_description,
        "input_schema": input_schema,
    }
    resp = client().messages.create(
        model=model or MODEL,
        max_tokens=max_tokens,
        system=system,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": user}],
    )
    for block in resp.content:
        if getattr(block, "type", "") == "tool_use" and block.name == tool_name:
            return dict(block.input)
    raise RuntimeError(
        f"Model did not return a tool_use block for {tool_name!r}; "
        f"stop_reason={resp.stop_reason}"
    )
