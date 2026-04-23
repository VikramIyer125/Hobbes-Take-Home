"""Shared orchestrator: take a prepared Source + content, extract, and merge.

Both URL and file ingestion flows land here once the raw bytes have been
saved to disk and a ``Source`` object has been minted.
"""
from __future__ import annotations

from typing import Any

from agent import changelog  # noqa: F401  (merge_fact writes through this)
from agent import extract, sources
from agent.domains import load_domain, save_domain
from agent.merge import MergeResult, merge_fact
from agent.models import Source


def ingest_source(source: Source, content: str) -> dict[str, Any]:
    """Extract from ``content``, merge every fact, append open questions.

    Returns the source's ``ingestion_summary`` dict.
    """
    result = extract.extract_from_source(
        content=content,
        source_type=source.type,
        location=source.location,
    )

    summary = {
        "facts_added": 0,
        "facts_updated": 0,
        "conflicts_introduced": 0,
        "user_overrides": 0,
        "open_questions_added": 0,
    }

    for ef in result.facts:
        try:
            r = merge_fact(ef, source, disambiguate=extract.llm_disambiguator)
        except Exception:
            continue
        if r is MergeResult.ADDED:
            summary["facts_added"] += 1
        elif r is MergeResult.CONFIRMED:
            summary["facts_updated"] += 1
        elif r is MergeResult.CONFLICTED:
            summary["conflicts_introduced"] += 1
        elif r is MergeResult.USER_OVERRIDE:
            summary["user_overrides"] += 1

    for domain, qs in result.open_questions.items():
        if not qs:
            continue
        dfile = load_domain(domain)
        existing = set(dfile.open_questions)
        for q in qs:
            if q not in existing:
                dfile.open_questions.append(q)
                existing.add(q)
                summary["open_questions_added"] += 1
        save_domain(dfile)

    source.ingestion_summary = summary
    sources.save_source(source)
    return summary
