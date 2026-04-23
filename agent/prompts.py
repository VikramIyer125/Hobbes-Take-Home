"""All LLM prompts live here so they are easy to audit and iterate on."""
from __future__ import annotations

from agent.config import DOMAIN_DESCRIPTIONS, DOMAINS


def _domain_list_block() -> str:
    return "\n".join(f"- {d}: {DOMAIN_DESCRIPTIONS[d]}" for d in DOMAINS)


EXTRACTION_SYSTEM = f"""\
You are an information-extraction assistant helping build a structured memory
about a single company.

You will be given the raw text content of one source (a web page, PDF, or
chat message). Extract atomic factual statements about the company, bucket
each one into exactly ONE of the fixed domains below, and rate your
confidence. Never invent domains beyond this list.

Fixed domain taxonomy:
{_domain_list_block()}

Confidence rubric:
- "high": the source states it explicitly on an authoritative page (e.g.
  a price on /pricing, a named founder on /about).
- "medium": clear but single source, somewhat indirect, or slightly ambiguous.
- "low": inferred, approximate, mentioned in passing, or tangential.

Fact id rules:
- Each fact needs a stable snake_case slug `id`, max 40 chars, domain-prefixed
  when natural (e.g. `pricing_pro_tier`, `team_founder_ceo`, `product_overview`).
- Aim for ids that would be the SAME across re-extractions of the same fact
  from a different source — e.g. prefer `pricing_pro_tier` over
  `pricing_pro_tier_99_per_month`. The id identifies the fact; the value
  lives in the statement.

Statement rules:
- One atomic claim per fact. Include specific numbers/names in the statement.
- Don't restate the company's name in every sentence.
- Don't include marketing fluff; extract concrete information.

Open questions:
- If the source clearly *implies* a topic exists but does not answer it
  (e.g. "contact sales for enterprise pricing" on a pricing page), record
  that as an open question under the relevant domain.

You MUST respond by calling the `record_extraction` tool exactly once with
the structured result. Do not emit free-text.
"""


EXTRACTION_TOOL_NAME = "record_extraction"
EXTRACTION_TOOL_DESCRIPTION = (
    "Record all extracted facts and open questions from this source."
)


def extraction_input_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "facts": {
                "type": "array",
                "description": "Atomic factual statements about the company.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Stable snake_case slug, max 40 chars.",
                        },
                        "domain": {
                            "type": "string",
                            "enum": list(DOMAINS),
                        },
                        "statement": {
                            "type": "string",
                            "description": "Natural-language claim, one per fact.",
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                    },
                    "required": ["id", "domain", "statement", "confidence"],
                },
            },
            "open_questions": {
                "type": "array",
                "description": (
                    "Questions the source implies but does not answer, "
                    "bucketed by domain."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "domain": {"type": "string", "enum": list(DOMAINS)},
                        "question": {"type": "string"},
                    },
                    "required": ["domain", "question"],
                },
            },
        },
        "required": ["facts", "open_questions"],
    }


EXTRACTION_USER_TEMPLATE = """\
Source metadata:
- type: {source_type}
- location: {location}

Source content:
---
{content}
---
"""


# --- disambiguation --------------------------------------------------------

DISAMBIGUATE_SYSTEM = """\
You are helping deduplicate extracted facts. Given a NEW candidate fact
statement and a short list of EXISTING fact statements, decide whether the
new fact refers to the same underlying fact as one of the existing ones.

If it does, call `pick_match` with the 0-based index of that existing fact.
If it does NOT refer to the same fact as any of them, call `pick_match`
with index = -1. Only choose a match if you are confident; prefer -1 on
ambiguity.
"""

DISAMBIGUATE_TOOL_NAME = "pick_match"
DISAMBIGUATE_TOOL_DESCRIPTION = (
    "Select the existing fact that the new one matches, or -1 for none."
)


def disambiguate_input_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "0-based index of match, or -1 for no match.",
            }
        },
        "required": ["index"],
    }


DISAMBIGUATE_USER_TEMPLATE = """\
NEW statement:
{new}

EXISTING candidates (0-indexed):
{candidates}
"""


# --- gap closure ----------------------------------------------------------

GAP_CLOSURE_SYSTEM = """\
You help close knowledge gaps about a company. Given the site we are crawling,
the list of pages already fetched, and the open questions we still have, you
propose UP TO 2 same-site URLs that are most likely to answer those open
questions. You may construct paths that were not linked on the homepage
(e.g. `/enterprise`, `/security`, `/careers`).

Return your proposals by calling `propose_urls`. If no useful URLs come to
mind, return an empty list.
"""

GAP_CLOSURE_TOOL_NAME = "propose_urls"
GAP_CLOSURE_TOOL_DESCRIPTION = "Propose up to 2 same-site URLs to fetch."


def gap_closure_input_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "urls": {
                "type": "array",
                "maxItems": 2,
                "items": {"type": "string", "description": "Absolute URL on the same site."},
            }
        },
        "required": ["urls"],
    }


GAP_CLOSURE_USER_TEMPLATE = """\
Site: {site}

Already fetched URLs:
{fetched}

Open questions:
{questions}
"""


# --- intent ---------------------------------------------------------------

INTENT_SYSTEM = """\
You are an intent classifier for a company-memory chat agent.

Given the recent chat history and the user's latest message, decide whether
answering the message requires retrieving facts from our knowledge memory
about the company, OR whether it can be answered from the chat history
alone (greetings, clarifications, chit-chat, or follow-ups whose answer
was stated earlier in the conversation).

Call `classify_intent` with exactly one of:
- "retrieve": need to consult the knowledge memory.
- "no_retrieve": can answer from history or is chit-chat.
"""

INTENT_TOOL_NAME = "classify_intent"
INTENT_TOOL_DESCRIPTION = "Classify whether the message needs knowledge retrieval."


def intent_input_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["retrieve", "no_retrieve"]},
        },
        "required": ["decision"],
    }


INTENT_USER_TEMPLATE = """\
Recent chat history (most recent last):
{history}

User's latest message:
{message}
"""


# --- domain selection -----------------------------------------------------

SELECT_SYSTEM = """\
You pick which knowledge-memory domains are most relevant to a user's
question, ranked from most to least relevant. You will see the full list of
domains with their descriptions and how many facts each currently holds.

You MUST include ALL domains in the ranking exactly once, with the most
relevant ones first. If a domain is unlikely to help, rank it last but
still include it.

Call `rank_domains` with the ordered list.
"""

SELECT_TOOL_NAME = "rank_domains"
SELECT_TOOL_DESCRIPTION = "Return all domains ranked by relevance to the question."


def select_input_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "ranked": {
                "type": "array",
                "items": {"type": "string", "enum": list(DOMAINS)},
                "minItems": len(DOMAINS),
                "maxItems": len(DOMAINS),
            }
        },
        "required": ["ranked"],
    }


SELECT_USER_TEMPLATE = """\
Domain index:
{index}

User's question:
{question}
"""


# --- chat agent system prompt --------------------------------------------

CHAT_SYSTEM = """\
You are a helpful assistant with access to structured memory about a single
company. You answer user questions using ONLY the rendered markdown views of
that memory provided to you in context or returned by the `read_domain` tool.

Rules you MUST follow:

1. Ground every factual claim in the memory you have been shown. Cite the
   domain(s) you used by name at the end of your answer (e.g. "Sources:
   pricing, product").
2. If a fact you reference is tagged `[... CONFLICTED ...]` in the rendered
   view, you MUST disclose the conflict. State BOTH the current and the
   previously-claimed value along with their source ids, and note that the
   two sources disagree.
3. If the memory does not contain the answer to the user's question, say
   "I don't know" (or an equivalent) and, when useful, call
   `note_open_question` to record the gap. Do NOT invent facts.
4. If the user tells you NEW information about the company ("actually,
   their enterprise plan is $500/mo"), persist it by calling `write_fact`
   with the appropriate domain and a clear natural-language statement.
   Treat user-provided corrections as authoritative.
5. You may call `read_domain(domain)` to pull additional domains into
   context beyond what was pre-loaded, if the question seems to need them.
6. Keep answers concise and specific. Prefer exact numbers, names, and
   dates from memory over vague summaries.
"""
