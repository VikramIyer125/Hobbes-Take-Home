"""``merge_fact`` — the only mutation path into ``memory/knowledge/``.

Callable contract::

    merge_fact(new: ExtractedFact, source: Source) -> MergeResult

Responsibilities:

1. Apply the source-trust cap to the extraction's confidence hint.
2. Find a matching existing fact via a tiered strategy:
   - Tier 1: exact ``id`` slug match.
   - Tier 2: normalized bidirectional substring match on the statement.
   - Tier 3: if Tier-2 returns >=2 candidates, a single Claude yes/no
     disambiguation call picks one (or none).
3. Branch to ``add`` / ``confirm`` / ``conflict`` / ``user_correction`` and
   write exactly one changelog event for the branch taken.

All storage writes (domain file save, changelog append, ``source.derived_fact_ids``
mutation) happen here. No other module mutates knowledge files.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from agent import changelog
from agent.confidence import apply_trust_cap, bump_up
from agent.domains import load_domain, save_domain
from agent.models import ExtractedFact, Fact, HistoryEntry, Source


class MergeResult(str, Enum):
    ADDED = "added"
    CONFIRMED = "confirmed"
    CONFLICTED = "conflicted"
    USER_OVERRIDE = "user_override"


# --- text normalisation helpers ------------------------------------------------

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")


def _normalize(text: str) -> str:
    text = text.lower()
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def _statements_equivalent(a: str, b: str) -> bool:
    return _normalize(a) == _normalize(b)


def _bidirectional_substring(a_norm: str, b_norm: str) -> bool:
    if not a_norm or not b_norm:
        return False
    shorter, longer = (a_norm, b_norm) if len(a_norm) <= len(b_norm) else (b_norm, a_norm)
    return shorter in longer


# --- match finder --------------------------------------------------------------

# Type alias for a disambiguation callable: given a statement and several
# candidate statements, return the index of the matching candidate or None.
DisambiguateFn = Callable[[str, list[str]], Optional[int]]


def _default_disambiguate(_new_stmt: str, _candidates: list[str]) -> Optional[int]:
    """Default: do not assume a match when substring search is ambiguous.

    Treating ambiguity as "no match" adds a new fact rather than risking a
    bad merge; the Claude disambiguator is plugged in by the ingestion
    pipeline.
    """
    return None


def find_match(
    facts: list[Fact],
    new: ExtractedFact,
    disambiguate: DisambiguateFn = _default_disambiguate,
) -> Optional[Fact]:
    # Tier 1: exact id slug match.
    for f in facts:
        if f.id == new.id:
            return f

    # Tier 2: normalized bidirectional substring match on the statement.
    new_norm = _normalize(new.statement)
    tier2: list[Fact] = []
    for f in facts:
        existing_norm = _normalize(f.statement)
        if existing_norm == new_norm or _bidirectional_substring(new_norm, existing_norm):
            tier2.append(f)

    if len(tier2) == 1:
        return tier2[0]
    if len(tier2) >= 2:
        # Tier 3: disambiguate among candidates.
        idx = disambiguate(new.statement, [f.statement for f in tier2])
        if idx is not None and 0 <= idx < len(tier2):
            return tier2[idx]

    return None


# --- main entry point ---------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def merge_fact(
    new: ExtractedFact,
    source: Source,
    *,
    disambiguate: DisambiguateFn = _default_disambiguate,
) -> MergeResult:
    capped = apply_trust_cap(new.confidence_hint, source.trust)

    dfile = load_domain(new.domain)
    match = find_match(dfile.facts, new, disambiguate=disambiguate)

    if match is None:
        fact = Fact(
            id=new.id,
            statement=new.statement,
            confidence=capped,
            sources=[source.source_id],
            last_updated=_now(),
            conflicted=False,
            history=[],
        )
        dfile.facts.append(fact)
        save_domain(dfile)
        changelog.append_event(
            "add",
            source=source.source_id,
            fact_id=fact.id,
            domain=new.domain,
            value=new.statement,
        )
        if fact.id not in source.derived_fact_ids:
            source.derived_fact_ids.append(fact.id)
        return MergeResult.ADDED

    if _statements_equivalent(match.statement, new.statement):
        if source.source_id not in match.sources:
            match.sources.append(source.source_id)
        if source.type == "user_chat":
            match.confidence = "high"
            match.conflicted = False
        else:
            match.confidence = bump_up(match.confidence)
        match.last_updated = _now()
        save_domain(dfile)
        changelog.append_event(
            "confirm",
            source=source.source_id,
            fact_id=match.id,
            domain=new.domain,
            value=match.statement,
        )
        if match.id not in source.derived_fact_ids:
            source.derived_fact_ids.append(match.id)
        return MergeResult.CONFIRMED

    prior_statement = match.statement
    prior_sources = list(match.sources)
    match.history.append(
        HistoryEntry(
            statement=prior_statement,
            sources=prior_sources,
            superseded_at=_now(),
        )
    )
    match.statement = new.statement
    match.sources = [source.source_id]
    match.last_updated = _now()

    if source.type == "user_chat":
        match.confidence = "high"
        match.conflicted = False
        op = "user_correction"
        result = MergeResult.USER_OVERRIDE
    else:
        match.confidence = "medium"
        match.conflicted = True
        op = "conflict"
        result = MergeResult.CONFLICTED

    save_domain(dfile)
    changelog.append_event(
        op,
        source=source.source_id,
        fact_id=match.id,
        domain=new.domain,
        old=prior_statement,
        new=new.statement,
    )
    if match.id not in source.derived_fact_ids:
        source.derived_fact_ids.append(match.id)
    return result
