"""Stage 3: budget-aware context assembly.

Walks domains in ranked order, loading their rendered markdown until the
token budget is consumed. Returns the assembled markdown and a list of
``(domain, token_estimate, loaded_fact_ids)`` tuples for the active-context
record.
"""
from __future__ import annotations

from dataclasses import dataclass

from agent.config import BUDGET_TOKENS, CHARS_PER_TOKEN
from agent.domains import load_domain
from agent.render import render_domain_file


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class DomainSlice:
    domain: str
    rendered: str
    tokens: int
    fact_ids: list[str]
    truncated: bool = False


@dataclass
class AssembledContext:
    slices: list[DomainSlice]
    total_tokens: int

    def to_markdown(self) -> str:
        if not self.slices:
            return "(no knowledge memory loaded)\n"
        return "\n\n".join(s.rendered for s in self.slices).rstrip() + "\n"

    def loaded_domains(self) -> list[str]:
        return [s.domain for s in self.slices]

    def loaded_fact_ids(self) -> list[str]:
        out: list[str] = []
        for s in self.slices:
            out.extend(s.fact_ids)
        return out


def _keyword_overlap_score(question: str, statement: str) -> int:
    q = {t for t in _tokenize(question.lower()) if len(t) >= 3}
    s = set(_tokenize(statement.lower()))
    return len(q & s)


def _tokenize(text: str) -> list[str]:
    import re as _re

    return _re.findall(r"[a-z0-9]+", text)


def _fallback_trim(domain: str, question: str, budget: int) -> DomainSlice | None:
    """When a single domain exceeds the whole budget, keep only the top-N facts
    by keyword-overlap score against the question."""
    df = load_domain(domain)
    if not df.facts:
        return None

    scored = sorted(
        df.facts,
        key=lambda f: (-_keyword_overlap_score(question, f.statement), f.id),
    )

    from agent.models import DomainFile

    kept: list = []
    for fact in scored:
        trial = DomainFile(
            domain=df.domain,
            last_updated=df.last_updated,
            open_questions=df.open_questions,
            facts=kept + [fact],
        )
        rendered = render_domain_file(trial)
        if estimate_tokens(rendered) > budget and kept:
            break
        kept.append(fact)

    if not kept:
        return None

    trimmed = DomainFile(
        domain=df.domain,
        last_updated=df.last_updated,
        open_questions=df.open_questions,
        facts=kept,
    )
    rendered = render_domain_file(trimmed)
    rendered = (
        rendered.rstrip()
        + f"\n\n> _Note: this domain was trimmed to top {len(kept)}/"
        f"{len(df.facts)} facts by keyword overlap._\n"
    )
    return DomainSlice(
        domain=domain,
        rendered=rendered,
        tokens=estimate_tokens(rendered),
        fact_ids=[f.id for f in kept],
        truncated=True,
    )


def assemble_context(
    ranked_domains: list[str],
    question: str,
    *,
    budget: int = BUDGET_TOKENS,
) -> AssembledContext:
    remaining = budget
    slices: list[DomainSlice] = []

    for i, domain in enumerate(ranked_domains):
        df = load_domain(domain)
        rendered = render_domain_file(df)
        est = estimate_tokens(rendered)

        if est <= remaining:
            slices.append(
                DomainSlice(
                    domain=domain,
                    rendered=rendered,
                    tokens=est,
                    fact_ids=[f.id for f in df.facts],
                )
            )
            remaining -= est
            continue

        # Doesn't fit whole. If this is the top-ranked domain (nothing loaded
        # yet) and it exceeds the full budget by itself, fall back to
        # keyword-overlap trimming.
        if not slices and est > budget:
            trimmed = _fallback_trim(domain, question, budget)
            if trimmed is not None:
                slices.append(trimmed)
                remaining = max(0, budget - trimmed.tokens)
            continue

        # Otherwise: skip this domain and see if a later, smaller one fits.
        continue

    total = sum(s.tokens for s in slices)
    return AssembledContext(slices=slices, total_tokens=total)
