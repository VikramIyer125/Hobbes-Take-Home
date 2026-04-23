"""Stage 2: domain selection — return all 9 domains ranked by relevance."""
from __future__ import annotations

from agent import llm, prompts
from agent.config import DOMAINS
from agent.render import render_domain_index


def rank_domains(question: str) -> list[str]:
    data = llm.forced_tool_call(
        system=prompts.SELECT_SYSTEM,
        user=prompts.SELECT_USER_TEMPLATE.format(
            index=render_domain_index(),
            question=question,
        ),
        tool_name=prompts.SELECT_TOOL_NAME,
        tool_description=prompts.SELECT_TOOL_DESCRIPTION,
        input_schema=prompts.select_input_schema(),
        max_tokens=256,
    )
    ranked = [d for d in (data.get("ranked") or []) if d in DOMAINS]
    # Ensure every domain appears exactly once; append any missing at the end.
    seen: set[str] = set()
    unique: list[str] = []
    for d in ranked:
        if d not in seen:
            unique.append(d)
            seen.add(d)
    for d in DOMAINS:
        if d not in seen:
            unique.append(d)
            seen.add(d)
    return unique
