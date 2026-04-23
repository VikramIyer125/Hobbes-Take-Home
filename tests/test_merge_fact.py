"""Unit tests for ``agent.merge.merge_fact``.

These exercise every branch of the spec-described logic:
- add
- confirm (bump, idempotent)
- conflict (non-user)
- user override
- trust-cap on fresh add
- tier-3 disambiguation hook
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent import changelog, paths
from agent.domains import load_domain, save_domain
from agent.merge import MergeResult, merge_fact
from agent.models import DomainFile, ExtractedFact, Fact, Source


@pytest.fixture(autouse=True)
def _isolated_memory(tmp_path, monkeypatch):
    """Point AGENT_MEMORY_DIR at a fresh tmp dir for every test."""
    monkeypatch.setenv("AGENT_MEMORY_DIR", str(tmp_path))
    paths.ensure_scaffold()
    yield tmp_path


def _src(
    source_id: str = "src_001",
    type_: str = "url",
    trust: float = 0.8,
) -> Source:
    return Source(
        source_id=source_id,
        type=type_,
        location=f"https://example.com/{source_id}",
        fetched_at=datetime.now(timezone.utc),
        raw_content_path=None,
        content_hash="deadbeef",
        trust=trust,
        derived_fact_ids=[],
        ingestion_summary={},
    )


def _ef(
    *,
    id: str = "pricing_pro_tier",
    domain: str = "pricing",
    statement: str = "Pro tier costs $99/month",
    confidence_hint: str = "high",
) -> ExtractedFact:
    return ExtractedFact(
        id=id,
        domain=domain,
        statement=statement,
        confidence_hint=confidence_hint,  # type: ignore[arg-type]
    )


def _changelog_lines() -> list[dict]:
    p = paths.changelog_path()
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


# --- add ---------------------------------------------------------------------


def test_add_into_empty_domain():
    src = _src()
    result = merge_fact(_ef(), src)

    assert result is MergeResult.ADDED
    df = load_domain("pricing")
    assert len(df.facts) == 1
    f = df.facts[0]
    assert f.id == "pricing_pro_tier"
    assert f.statement == "Pro tier costs $99/month"
    assert f.confidence == "high"
    assert f.sources == ["src_001"]
    assert f.conflicted is False
    assert f.history == []
    assert src.derived_fact_ids == ["pricing_pro_tier"]

    events = _changelog_lines()
    assert len(events) == 1
    assert events[0]["op"] == "add"
    assert events[0]["fact_id"] == "pricing_pro_tier"
    assert events[0]["source"] == "src_001"
    assert events[0]["value"] == "Pro tier costs $99/month"


# --- confirm -----------------------------------------------------------------


def test_confirm_bumps_confidence_and_extends_sources():
    merge_fact(_ef(confidence_hint="medium"), _src("src_001"))
    df = load_domain("pricing")
    assert df.facts[0].confidence == "medium"

    src2 = _src("src_002")
    result = merge_fact(_ef(confidence_hint="medium"), src2)
    assert result is MergeResult.CONFIRMED

    df = load_domain("pricing")
    f = df.facts[0]
    assert f.confidence == "high"  # bumped one level: med -> high
    assert f.sources == ["src_001", "src_002"]
    assert f.conflicted is False
    assert src2.derived_fact_ids == ["pricing_pro_tier"]

    events = _changelog_lines()
    assert [e["op"] for e in events] == ["add", "confirm"]


def test_confirm_is_idempotent_for_duplicate_source():
    src = _src("src_001")
    merge_fact(_ef(confidence_hint="low"), src)
    merge_fact(_ef(confidence_hint="low"), src)

    df = load_domain("pricing")
    f = df.facts[0]
    assert f.sources == ["src_001"]  # no duplicate
    assert f.confidence == "medium"  # bumped once by the confirm


# --- conflict ----------------------------------------------------------------


def test_non_user_conflict_preserves_history_and_demotes():
    merge_fact(
        _ef(
            id="pricing_enterprise",
            statement="Enterprise tier costs $800/month",
            confidence_hint="high",
        ),
        _src("src_001"),
    )

    src2 = _src("src_002")
    result = merge_fact(
        _ef(
            id="pricing_enterprise",
            statement="Enterprise tier costs $500/month",
            confidence_hint="high",
        ),
        src2,
    )
    assert result is MergeResult.CONFLICTED

    df = load_domain("pricing")
    f = df.facts[0]
    assert f.statement == "Enterprise tier costs $500/month"
    assert f.sources == ["src_002"]
    assert f.confidence == "medium"
    assert f.conflicted is True
    assert len(f.history) == 1
    prior = f.history[0]
    assert prior.statement == "Enterprise tier costs $800/month"
    assert prior.sources == ["src_001"]

    events = _changelog_lines()
    assert [e["op"] for e in events] == ["add", "conflict"]
    assert events[-1]["old"] == "Enterprise tier costs $800/month"
    assert events[-1]["new"] == "Enterprise tier costs $500/month"


def test_user_override_beats_prior_and_clears_conflicted():
    merge_fact(
        _ef(
            id="pricing_enterprise",
            statement="Enterprise tier costs $800/month",
            confidence_hint="high",
        ),
        _src("src_001"),
    )
    merge_fact(
        _ef(
            id="pricing_enterprise",
            statement="Enterprise tier costs $500/month",
            confidence_hint="high",
        ),
        _src("src_002"),
    )

    # now user corrects to $500
    chat_src = _src("src_chat_abc_t001", type_="user_chat", trust=1.0)
    result = merge_fact(
        _ef(
            id="pricing_enterprise",
            statement="Enterprise tier costs $500/month",
            confidence_hint="high",
        ),
        chat_src,
    )
    # same statement as current => confirm path, but user_chat => high + clear flag
    assert result is MergeResult.CONFIRMED
    df = load_domain("pricing")
    f = df.facts[0]
    assert f.confidence == "high"
    assert f.conflicted is False


def test_user_override_with_different_statement_overwrites():
    merge_fact(
        _ef(
            id="pricing_enterprise",
            statement="Enterprise tier costs $800/month",
            confidence_hint="high",
        ),
        _src("src_001"),
    )

    chat_src = _src("src_chat_abc_t001", type_="user_chat", trust=1.0)
    result = merge_fact(
        _ef(
            id="pricing_enterprise",
            statement="Enterprise tier costs $500/month",
            confidence_hint="high",
        ),
        chat_src,
    )
    assert result is MergeResult.USER_OVERRIDE

    df = load_domain("pricing")
    f = df.facts[0]
    assert f.statement == "Enterprise tier costs $500/month"
    assert f.sources == ["src_chat_abc_t001"]
    assert f.confidence == "high"
    assert f.conflicted is False
    assert len(f.history) == 1
    assert f.history[0].statement == "Enterprise tier costs $800/month"

    events = _changelog_lines()
    assert events[-1]["op"] == "user_correction"
    assert events[-1]["old"] == "Enterprise tier costs $800/month"
    assert events[-1]["new"] == "Enterprise tier costs $500/month"


# --- trust cap ---------------------------------------------------------------


def test_trust_cap_demotes_high_to_medium_on_low_trust_source():
    low_trust = _src("src_001", trust=0.5)
    merge_fact(_ef(confidence_hint="high"), low_trust)
    df = load_domain("pricing")
    assert df.facts[0].confidence == "medium"


def test_trust_cap_does_not_affect_medium_or_low():
    low_trust = _src("src_001", trust=0.5)
    merge_fact(_ef(confidence_hint="medium"), low_trust)
    df = load_domain("pricing")
    assert df.facts[0].confidence == "medium"


# --- tier-3 disambiguation hook ---------------------------------------------


def test_tier2_substring_ambiguity_falls_through_by_default():
    """With the default disambiguator (returns None), ambiguous Tier-2 matches
    are treated as 'no match' so the fact is added rather than risking a bad merge."""
    # Seed two facts whose statements each contain the same short substring.
    merge_fact(
        _ef(id="pricing_a", statement="Teams plan starts at $10 per user"),
        _src("src_001"),
    )
    merge_fact(
        _ef(id="pricing_b", statement="Pro plan starts at $10 per user"),
        _src("src_002"),
    )

    # New extraction whose statement substring-matches both.
    result = merge_fact(
        _ef(id="pricing_c", statement="starts at $10 per user"),
        _src("src_003"),
    )
    # With default disambiguator returning None, a new fact is added.
    assert result is MergeResult.ADDED
    df = load_domain("pricing")
    assert len(df.facts) == 3


def test_tier3_disambiguator_can_pick_a_candidate():
    merge_fact(
        _ef(id="pricing_a", statement="Teams plan starts at $10 per user"),
        _src("src_001"),
    )
    merge_fact(
        _ef(id="pricing_b", statement="Pro plan starts at $10 per user"),
        _src("src_002"),
    )

    def pick_teams(_stmt: str, candidates: list[str]):
        for i, c in enumerate(candidates):
            if "Teams" in c:
                return i
        return None

    src3 = _src("src_003")
    result = merge_fact(
        _ef(id="pricing_c", statement="starts at $10 per user"),
        src3,
        disambiguate=pick_teams,
    )
    # Matched "Teams plan..." — new statement differs, so this is a conflict.
    assert result is MergeResult.CONFLICTED
    df = load_domain("pricing")
    assert len(df.facts) == 2  # no new fact added
    teams = next(f for f in df.facts if f.id == "pricing_a")
    assert teams.conflicted is True
    assert teams.statement == "starts at $10 per user"
    assert len(teams.history) == 1
