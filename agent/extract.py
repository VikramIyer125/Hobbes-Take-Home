"""One-source extraction LLM call."""
from __future__ import annotations

from typing import Optional

from agent import llm, prompts
from agent.config import DOMAINS
from agent.models import ExtractedFact, ExtractionResult


MAX_CONTENT_CHARS = 40_000  # ~10k tokens, keeps one source to a single call


def _truncate(text: str, limit: int = MAX_CONTENT_CHARS) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit - 200]
    return head + "\n\n[...TRUNCATED...]\n"


def extract_from_source(
    *,
    content: str,
    source_type: str,
    location: str,
) -> ExtractionResult:
    """Run the extraction tool call and return parsed ExtractionResult."""
    user = prompts.EXTRACTION_USER_TEMPLATE.format(
        source_type=source_type,
        location=location,
        content=_truncate(content),
    )
    data = llm.forced_tool_call(
        system=prompts.EXTRACTION_SYSTEM,
        user=user,
        tool_name=prompts.EXTRACTION_TOOL_NAME,
        tool_description=prompts.EXTRACTION_TOOL_DESCRIPTION,
        input_schema=prompts.extraction_input_schema(),
    )

    facts: list[ExtractedFact] = []
    for raw in data.get("facts", []) or []:
        try:
            facts.append(
                ExtractedFact(
                    id=_normalize_id(raw["id"]),
                    domain=raw["domain"],
                    statement=raw["statement"].strip(),
                    confidence_hint=raw["confidence"],
                )
            )
        except Exception:
            # drop malformed facts silently; extraction is best-effort
            continue

    open_qs: dict[str, list[str]] = {}
    for raw in data.get("open_questions", []) or []:
        d = raw.get("domain")
        q = (raw.get("question") or "").strip()
        if d in DOMAINS and q:
            open_qs.setdefault(d, []).append(q)

    return ExtractionResult(facts=facts, open_questions=open_qs)


def _normalize_id(raw: str) -> str:
    """Constrain ids to safe snake_case, max 40 chars."""
    import re

    s = raw.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:40] or "unknown_fact"


def llm_disambiguator(new_stmt: str, candidates: list[str]) -> Optional[int]:
    """Claude-backed Tier-3 disambiguator for merge_fact."""
    numbered = "\n".join(f"[{i}] {c}" for i, c in enumerate(candidates))
    data = llm.forced_tool_call(
        system=prompts.DISAMBIGUATE_SYSTEM,
        user=prompts.DISAMBIGUATE_USER_TEMPLATE.format(new=new_stmt, candidates=numbered),
        tool_name=prompts.DISAMBIGUATE_TOOL_NAME,
        tool_description=prompts.DISAMBIGUATE_TOOL_DESCRIPTION,
        input_schema=prompts.disambiguate_input_schema(),
        max_tokens=128,
    )
    idx = int(data.get("index", -1))
    return idx if idx >= 0 else None
