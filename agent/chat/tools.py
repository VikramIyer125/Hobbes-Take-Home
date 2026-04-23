"""Chat-time tools the LLM can invoke: read_domain, write_fact, note_open_question.

Tool schemas follow the Anthropic tool-use format.

The handlers mutate memory through the same ``merge_fact`` path as ingestion,
lazily minting one Source per chat turn that produces facts.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from agent import paths, sources
from agent.chat.session import ChatSession
from agent.config import DOMAINS, TRUST_BY_TYPE
from agent.domains import load_domain, save_domain
from agent.merge import merge_fact
from agent.models import ExtractedFact, Source
from agent.render import render_domain


# --- tool schemas ---------------------------------------------------------

CHAT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_domain",
        "description": (
            "Load a domain of the knowledge memory and return it as rendered "
            "markdown. Use this to pull in additional context when the "
            "pre-loaded domains are not enough."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "enum": list(DOMAINS)},
            },
            "required": ["domain"],
        },
    },
    {
        "name": "write_fact",
        "description": (
            "Persist a new or corrected fact to knowledge memory, attributed "
            "to the current user. Use this when the user provides fresh "
            "information about the company."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "enum": list(DOMAINS)},
                "statement": {
                    "type": "string",
                    "description": "Natural-language claim, one atomic fact.",
                },
                "confidence_hint": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "How certain this fact is.",
                },
            },
            "required": ["domain", "statement", "confidence_hint"],
        },
    },
    {
        "name": "note_open_question",
        "description": (
            "Record a question that the memory cannot currently answer so "
            "future ingestion can target it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "enum": list(DOMAINS)},
                "question": {"type": "string"},
            },
            "required": ["domain", "question"],
        },
    },
]


# --- helpers --------------------------------------------------------------


def _slugify_statement(statement: str, domain: str) -> str:
    """Deterministic slug id from a chat-originated statement.

    Chat tools cannot round-trip through the extraction LLM, so we pick an
    id here. Prefix with the domain for readability; cap at 40 chars.
    """
    s = statement.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    s = re.sub(r"_+", "_", s)
    s = s[:30]
    return f"{domain}_{s}".strip("_")[:40] or f"{domain}_fact"


def _ensure_turn_source(session: ChatSession, user_text: str) -> Source:
    """Lazily create (or return) the chat Source for the current turn."""
    if session.current_turn_source_id:
        return sources.load_source(session.current_turn_source_id)

    sid = sources.mint_chat_source_id(session.session_id, session.turn_index)
    raw_path = sources.save_raw_text(sid, user_text, "txt")
    src = Source(
        source_id=sid,
        type="user_chat",
        location=f"chat_sess_{session.session_id}#turn_{session.turn_index:03d}",
        fetched_at=datetime.now(timezone.utc),
        raw_content_path=str(raw_path),
        content_hash=sources.hash_of_text(user_text),
        trust=TRUST_BY_TYPE["user_chat"],
        derived_fact_ids=[],
        ingestion_summary={},
    )
    sources.save_source(src)
    session.current_turn_source_id = sid
    return src


# --- handlers -------------------------------------------------------------


def handle_read_domain(args: dict[str, Any]) -> str:
    domain = args.get("domain")
    if domain not in DOMAINS:
        return f"Unknown domain: {domain!r}"
    return render_domain(domain)


def handle_write_fact(
    args: dict[str, Any],
    *,
    session: ChatSession,
    user_text: str,
) -> str:
    domain = args.get("domain")
    statement = (args.get("statement") or "").strip()
    confidence_hint = args.get("confidence_hint") or "medium"
    if domain not in DOMAINS or not statement:
        return "write_fact failed: invalid domain or empty statement."

    src = _ensure_turn_source(session, user_text)
    ef = ExtractedFact(
        id=_slugify_statement(statement, domain),
        domain=domain,
        statement=statement,
        confidence_hint=confidence_hint,  # type: ignore[arg-type]
    )
    result = merge_fact(ef, src)
    sources.save_source(src)
    return f"write_fact ok: {result.value} ({ef.id}) in {domain}"


def handle_note_open_question(
    args: dict[str, Any],
    *,
    session: ChatSession,
    user_text: str,
) -> str:
    domain = args.get("domain")
    question = (args.get("question") or "").strip()
    if domain not in DOMAINS or not question:
        return "note_open_question failed: invalid domain or empty question."

    # Persist to the domain file directly; no changelog entry (spec only
    # requires changelog for fact mutations).
    df = load_domain(domain)
    if question not in df.open_questions:
        df.open_questions.append(question)
        save_domain(df)
    # Touch the turn source so provenance is captured even if no fact was added.
    _ensure_turn_source(session, user_text)
    return f"note_open_question ok: {question!r} in {domain}"


def dispatch_tool(
    name: str,
    args: dict[str, Any],
    *,
    session: ChatSession,
    user_text: str,
) -> str:
    if name == "read_domain":
        return handle_read_domain(args)
    if name == "write_fact":
        return handle_write_fact(args, session=session, user_text=user_text)
    if name == "note_open_question":
        return handle_note_open_question(args, session=session, user_text=user_text)
    return f"Unknown tool: {name}"
