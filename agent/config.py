"""Global configuration constants for the agent."""
from __future__ import annotations

import os

MODEL: str = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-5")

BUDGET_TOKENS: int = 3000
CHARS_PER_TOKEN: int = 4

SESSION_HISTORY_MAX_TURNS: int = 10

SUBPAGE_MAX_FETCHES: int = 8
GAP_CLOSURE_MAX_FETCHES: int = 2

HTTP_TIMEOUT_SECS: float = 20.0
HTTP_USER_AGENT: str = (
    "Mozilla/5.0 (compatible; CompanyMemoryAgent/0.1; +https://example.invalid)"
)

DOMAINS: tuple[str, ...] = (
    "company_overview",
    "product",
    "pricing",
    "customers",
    "team",
    "funding",
    "tech_stack",
    "positioning",
    "other",
)

DOMAIN_DESCRIPTIONS: dict[str, str] = {
    "company_overview": "Mission, what the company does, founding story, high-level summary.",
    "product": "Product capabilities, features, how the product works, integrations.",
    "pricing": "Plans, tiers, per-seat costs, enterprise pricing, discounts, trials.",
    "customers": "Named customers, case studies, customer counts, target segments.",
    "team": "Founders, executives, key hires, headcount, notable team facts.",
    "funding": "Rounds, investors, valuations, revenue, financial milestones.",
    "tech_stack": "Languages, frameworks, cloud, infra, architecture choices.",
    "positioning": "Competitors, differentiators, category/market stance, messaging.",
    "other": "Anything that does not fit a specific domain above.",
}

TRUST_BY_TYPE: dict[str, float] = {
    "user_chat": 1.0,
    "file": 0.9,
    "url": 0.8,
    "third_party": 0.5,
}

TRUST_CAP_THRESHOLD: float = 0.7
