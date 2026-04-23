"""Stage 1: intent classification (retrieve | no_retrieve)."""
from __future__ import annotations

from typing import Any, Literal

from agent import llm, prompts


IntentDecision = Literal["retrieve", "no_retrieve"]


def _format_history(history: list[dict[str, Any]]) -> str:
    if not history:
        return "(no prior turns)"
    lines = []
    for t in history:
        role = t.get("role", "?")
        content = (t.get("content") or "").strip()
        lines.append(f"[{role}] {content}")
    return "\n".join(lines)


def classify_intent(message: str, history: list[dict[str, Any]]) -> IntentDecision:
    data = llm.forced_tool_call(
        system=prompts.INTENT_SYSTEM,
        user=prompts.INTENT_USER_TEMPLATE.format(
            history=_format_history(history),
            message=message,
        ),
        tool_name=prompts.INTENT_TOOL_NAME,
        tool_description=prompts.INTENT_TOOL_DESCRIPTION,
        input_schema=prompts.intent_input_schema(),
        max_tokens=128,
    )
    decision = str(data.get("decision", "retrieve"))
    return "no_retrieve" if decision == "no_retrieve" else "retrieve"
