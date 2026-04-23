"""Pydantic v2 data models for the memory system."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from agent.config import DOMAINS


Confidence = Literal["high", "medium", "low"]
SourceType = Literal["url", "file", "user_chat"]


class HistoryEntry(BaseModel):
    statement: str
    sources: list[str]
    superseded_at: datetime


class Fact(BaseModel):
    id: str
    statement: str
    confidence: Confidence
    sources: list[str]
    last_updated: datetime
    conflicted: bool = False
    history: list[HistoryEntry] = Field(default_factory=list)


class DomainFile(BaseModel):
    domain: str
    last_updated: datetime
    open_questions: list[str] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)

    @field_validator("domain")
    @classmethod
    def _valid_domain(cls, v: str) -> str:
        if v not in DOMAINS:
            raise ValueError(f"Unknown domain: {v!r}. Must be one of {DOMAINS}.")
        return v


class Source(BaseModel):
    source_id: str
    type: SourceType
    location: str
    fetched_at: datetime
    raw_content_path: Optional[str] = None
    content_hash: str
    trust: float
    derived_fact_ids: list[str] = Field(default_factory=list)
    ingestion_summary: dict[str, Any] = Field(default_factory=dict)


class ExtractedFact(BaseModel):
    """What the extraction LLM returns for a single fact."""

    id: str
    domain: str
    statement: str
    confidence_hint: Confidence

    @field_validator("domain")
    @classmethod
    def _valid_domain(cls, v: str) -> str:
        if v not in DOMAINS:
            raise ValueError(f"Unknown domain: {v!r}.")
        return v


class ExtractionResult(BaseModel):
    facts: list[ExtractedFact] = Field(default_factory=list)
    open_questions: dict[str, list[str]] = Field(default_factory=dict)
