"""LLM-guided URL proposal for bounded gap closure."""
from __future__ import annotations

from urllib.parse import urlparse

from agent import llm, prompts
from agent.config import GAP_CLOSURE_MAX_FETCHES
from agent.domains import list_existing_domains, load_domain


def _collect_open_questions() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for d in list_existing_domains():
        df = load_domain(d)
        for q in df.open_questions:
            out.append((d, q))
    return out


def propose_gap_closure_urls(start_url: str, fetched_urls: list[str]) -> list[str]:
    """Ask Claude for up to ``GAP_CLOSURE_MAX_FETCHES`` same-site URLs.

    Returns an empty list if there are no open questions or the model
    declines.
    """
    open_qs = _collect_open_questions()
    if not open_qs:
        return []

    parsed = urlparse(start_url)
    site = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")

    fetched_block = "\n".join(f"- {u}" for u in fetched_urls) or "- (none)"
    questions_block = "\n".join(f"- [{d}] {q}" for d, q in open_qs)

    data = llm.forced_tool_call(
        system=prompts.GAP_CLOSURE_SYSTEM,
        user=prompts.GAP_CLOSURE_USER_TEMPLATE.format(
            site=site,
            fetched=fetched_block,
            questions=questions_block,
        ),
        tool_name=prompts.GAP_CLOSURE_TOOL_NAME,
        tool_description=prompts.GAP_CLOSURE_TOOL_DESCRIPTION,
        input_schema=prompts.gap_closure_input_schema(),
        max_tokens=256,
    )
    urls = [str(u).strip() for u in (data.get("urls") or [])]
    return urls[:GAP_CLOSURE_MAX_FETCHES]
