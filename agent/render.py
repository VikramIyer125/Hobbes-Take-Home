"""Render JSON memory to markdown for LLM consumption.

This is the only surface the LLM sees when reading memory.
"""
from __future__ import annotations

from agent.config import DOMAIN_DESCRIPTIONS, DOMAINS
from agent.domains import fact_counts, load_domain
from agent.models import DomainFile, Fact


def _fmt_date(dt) -> str:
    return dt.date().isoformat() if dt else "unknown"


def _sources_phrase(sources: list[str]) -> str:
    if not sources:
        return "(no sources)"
    if len(sources) == 1:
        return f"source: {sources[0]}"
    return f"sources: {', '.join(sources)}"


def render_fact_line(fact: Fact) -> str:
    confidence_tag = fact.confidence.upper()
    prefix = f"[{confidence_tag}"
    if fact.conflicted:
        prefix += " \u26a0\ufe0f CONFLICTED"  # ⚠️
    prefix += "]"
    line = f"- {prefix} {fact.statement}  ({_sources_phrase(fact.sources)})"
    if fact.conflicted and fact.history:
        prior = fact.history[-1]
        line += (
            f"\n    Previously claimed: {prior.statement} "
            f"({_sources_phrase(prior.sources)})"
        )
    return line


def render_domain_file(dfile: DomainFile) -> str:
    title = dfile.domain.replace("_", " ").title()
    lines: list[str] = [f"# {title}", f"Last updated: {_fmt_date(dfile.last_updated)}", ""]

    lines.append("## Known facts")
    if dfile.facts:
        for fact in dfile.facts:
            lines.append(render_fact_line(fact))
    else:
        lines.append("- (none yet)")
    lines.append("")

    lines.append("## Open questions")
    if dfile.open_questions:
        for q in dfile.open_questions:
            lines.append(f"- {q}")
    else:
        lines.append("- (none)")

    return "\n".join(lines).rstrip() + "\n"


def render_domain(domain: str) -> str:
    """Load + render a domain file as markdown. Safe on missing domains."""
    dfile = load_domain(domain)
    return render_domain_file(dfile)


def render_domain_index() -> str:
    """Compact index used by the domain selector (stage 2)."""
    counts = fact_counts()
    lines = ["# Domain index", ""]
    for d in DOMAINS:
        desc = DOMAIN_DESCRIPTIONS[d]
        n = counts.get(d, 0)
        lines.append(f"- **{d}** ({n} facts): {desc}")
    return "\n".join(lines) + "\n"
