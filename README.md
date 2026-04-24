# Company Memory Agent

A Python CLI agent that ingests information about a single company (websites +
documents), organizes it into a structured two-layer memory, and answers
questions by retrieving from that memory.

The core philosophy: **the LLM manipulates facts; the engine manipulates JSON.**
The LLM only ever reads rendered markdown views of memory and mutates memory
through typed tools. It never reads or writes raw JSON.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_MODEL=claude-opus-4-5   # or any Claude model you have access to

# Optional: run unit tests for the merge core
pytest -q

# End-to-end demo against Linear
./demo.sh
```

CLI commands:

```bash
python -m agent ingest-url https://linear.app
python -m agent ingest-file ./fixtures/linear_contradiction.pdf
python -m agent chat                           # interactive
python -m agent chat --script turns.txt        # non-interactive
python -m agent inspect                        # memory tree
python -m agent inspect --domain pricing
python -m agent inspect --changelog --tail 30
python -m agent inspect --working
```

All state lives under `./memory/` (override with `AGENT_MEMORY_DIR=...`).

## Architecture

```
memory/
  working/              reset per CLI invocation
    session_history.json
    active_context.json
  knowledge/            persistent
    pricing.json  product.json  company_overview.json  ...
  sources/              provenance
    src_001.json   src_chat_<session>_t001.json  ...
    raw/
      src_001.html  src_002.pdf  ...
  changelog.jsonl
```

### Two-layer memory

- **Working memory** (`memory/working/`) is ephemeral. `start_session()` wipes
  it at the start of every `chat` invocation. It holds the last 10 chat turns
  (sliding window) and the most recent retrieval decision (`active_context.json`).
- **Knowledge memory** (`memory/knowledge/`) is durable. Facts live in one JSON
  file per domain drawn from a fixed 9-entry taxonomy
  (`company_overview`, `product`, `pricing`, `customers`, `team`, `funding`,
  `tech_stack`, `positioning`, `other`). The LLM cannot invent new domains.

### The `merge_fact` invariant

Every mutation to `knowledge/*.json` passes through
[`agent/merge.py`](agent/merge.py)::`merge_fact`. Nothing else writes to those
files, and every branch writes exactly one event to `memory/changelog.jsonl`.
This one chokepoint is what makes conflict handling, confidence accounting,
and auditability predictable. It has a standalone unit test suite
(`tests/test_merge_fact.py`, 10 cases) covering every branch: add, confirm,
idempotent confirm, non-user conflict, user override (same or differing
statement), trust cap, and the Tier-3 disambiguator hook.

Dedup is tiered:

1. Exact match on the extraction-provided `id` slug.
2. Normalized bidirectional substring match on the statement.
3. Only when ≥2 Tier-2 candidates exist do we spend one Claude call to
   disambiguate (`agent/extract.py::llm_disambiguator`). The default in-process
   disambiguator returns "no match" on ambiguity, which is the safe choice
   inside unit tests.

### Ingestion

URL ingestion (`agent/ingest/url.py`):

1. Fetch the homepage with `httpx`.
2. Discover internal links with BeautifulSoup, score against regex patterns
   (`/pricing`, `/product`, `/about`, `/team`, `/customers`, `/docs`,
   `/security`, `/enterprise`, `/blog`, …), keep the top 8.
3. For each page: extract clean text with `trafilatura` (fallback to
   BeautifulSoup `get_text()` if empty), save raw HTML under `sources/raw/`,
   write the `Source` JSON, and run the extraction LLM.
4. **Gap closure:** after the initial pass, ask Claude to propose up to 2
   additional same-site URLs most likely to answer outstanding open
   questions. Fetch those, ingest them the same way. Bounded at 2 to keep
   cost predictable.

File ingestion (`agent/ingest/files.py`): PDF via `pypdf`, DOCX via
`python-docx`, `.txt`/`.md` via direct decode. Same extraction path as URL.

Extraction (`agent/extract.py`): one Claude call per source with a **forced
tool call**. The tool schema demands `{id, domain, statement, confidence}`
per fact plus a separate list of open questions bucketed by domain. We never
ask the model to emit free-text JSON.

### Chat (four-stage retrieval pipeline)

For each user turn (see `agent/chat/respond.py`):

1. **Intent classification.** A single Claude call returns `retrieve` or
   `no_retrieve`. Chit-chat and history-answerable follow-ups skip retrieval.
2. **Domain selection.** A second Claude call takes the question + a compact
   domain index (name, 1-line description, fact count) and returns all 9
   domains ranked.
3. **Budget assembly.** We walk the ranked list, render each domain's
   markdown, and accumulate until a 3000-token budget is reached (tokens
   estimated as `len(text) // 4`). If the top-ranked domain alone exceeds
   the whole budget, we fall back to keyword-overlap scoring across facts
   and keep the top N with a visible annotation (this fallback is basic;
   see Limitations).
4. **Respond.** A Claude tool-use loop with three tools: `read_domain(domain)`
   to pull additional context, `write_fact(domain, statement, confidence_hint)`
   to persist user-provided info, and `note_open_question(domain, question)`
   to record gaps. Every LLM view of memory is the same rendered markdown
   format — `⚠️ CONFLICTED` prefix included — so conflict disclosure falls
   out of the view itself, with the system prompt as a backup rule.

### Confidence and conflicts

Confidence is **derived**, never invented:

- At extraction time, Claude rates each fact against a written rubric
  (high / medium / low).
- On merge, non-user confirmations bump the stored confidence one level
  (low→medium→high, clamped).
- A non-user conflict demotes the fact to `medium` and flips `conflicted`
  to true; the superseded value moves into `history[]` with its original
  sources.
- A `user_chat` correction wins authoritatively: `confidence=high`,
  `conflicted=false`, and history is retained for audit.
- A source-trust cap pins `high` ratings from low-trust sources to
  `medium` internally (not surfaced to the user).

### Chat-originated sources

When the user supplies a new fact (e.g. "actually their enterprise plan is
$500/mo"), the chat agent calls `write_fact`. The tool handler lazily mints
**one `Source` per chat turn that produces facts**:
`src_chat_<session_id>_t<turn_index>.json` with `type="user_chat"`,
`trust=1.0`, and the user's literal turn text stored under
`sources/raw/`. Multiple facts from the same turn share this source; idle
turns never create one. This keeps provenance aligned with ingestion events
(one source = one ingestion event) without blowing up the source directory.

## Key design tradeoffs

- **JSON not markdown storage.** Facts need stable IDs, structured history
  entries, and machine-countable source lists. The engine owns the JSON;
  rendered markdown is a derived view. This is what lets us guarantee
  "every fact has sources + confidence + last_updated" at the type level.
- **LLM-routed retrieval, not embeddings.** With a fixed, human-curated
  9-domain taxonomy, embeddings are overkill. A tiny intent call + a
  ranked-domain call consistently reach the right bucket for small-to-medium
  memory, with zero infra dependencies. This won't scale past a few
  thousand facts; see Limitations.
- **Forced tool calls for all structured output.** No JSON-in-text parsing.
  Claude's tool schema validates types and enum memberships, so the
  extraction path can't silently invent a 10th domain.
- **Single write chokepoint.** `merge_fact` is the only code that writes
  to `knowledge/*.json` or to the changelog. Tests target this function
  directly; nothing else needs to be end-to-end-integration-tested to have
  confidence in the state machine.
- **User corrections are authoritative.** The priority rule
  (explicit user correction > newer source > higher-confidence source) is
  encoded in `merge_fact`: `user_chat` sources short-circuit the conflict
  path and pin `confidence=high`, `conflicted=false`.

## Known limitations

- **Intra-domain scale.** If a single domain's rendered markdown exceeds the
  3000-token budget, the keyword-overlap fallback is basic (lowercased word
  overlap). A per-fact LLM pruner or embedding-ranked selection would be
  better.
- **Gap closure is bounded to 2 URLs.** Deeper multi-hop investigation isn't
  attempted; the system prompt makes Claude propose same-site URLs only.
- **No web search.** If the open question can't be answered from the
  company's own site, we simply record it as an open question.
- **No summarization of dropped turns.** The session-history window is a
  hard cap of 10; older turns vanish rather than being summarized.
- **Single-company namespacing.** All knowledge files sit at one level;
  there's no namespace for running the agent against multiple companies
  in one memory directory.
- **Tier-3 disambiguation uses one Claude call per ambiguous merge.** Under
  heavy ingestion this could spike cost. The default (non-LLM) disambiguator
  used in tests returns "no match" on ambiguity, which is safer but can
  produce near-duplicates; the live ingestion path opts into the LLM
  disambiguator explicitly.

## What I would do next

1. **Fact-level LLM pruning** for domains over budget: ask Claude to pick
   the most relevant K facts for a question rather than keyword overlap.
2. **Summarization of dropped session turns** so long conversations retain
   key context beyond the 10-turn window.
3. **Vector search at scale** for intra-domain ranking once a domain passes
   a few hundred facts.
4. **Web-search fallback** for gap closure when the same-site crawl doesn't
   answer an open question (Crunchbase-style third-party sources, capped by
   trust=0.5).
5. **Multi-company namespacing** — `memory/<company>/...` with a top-level
   company-selection CLI option.
6. **Changelog compaction** — periodic squashing of long confirm chains
   into a single "confirmed N times over window X" record.
7. **Extraction deduping across a single ingestion run** — today each page
   is extracted independently, so the same fact may surface with different
   ids from two pages and hit the Tier-2/3 merge path. A within-run id
   reconciliation step would cut Claude calls.

## Layout

```
agent/
  cli.py              # typer app
  config.py           # MODEL, BUDGET_TOKENS=3000, TRUST_BY_TYPE, DOMAINS
  models.py           # Pydantic: Fact, HistoryEntry, DomainFile, Source, ExtractedFact
  render.py           # JSON -> markdown (the only LLM-facing read surface)
  merge.py            # merge_fact: the only writer
  confidence.py       # bump/demote/trust-cap helpers
  changelog.py        # append-only JSONL writer
  domains.py          # load/save domain files, fact counts
  sources.py          # Source I/O, id minting, raw-content persistence
  working.py          # session history + active context
  llm.py              # Anthropic wrapper + forced_tool_call helper
  prompts.py          # every LLM prompt lives here
  extract.py          # one-source extraction tool call
  inspect_cmd.py      # CLI pretty-printers
  ingest/
    pipeline.py       # shared orchestrator (source -> facts -> merge)
    url.py            # homepage + subpage crawl
    gap_closure.py    # LLM-proposed same-site URLs (bounded)
    files.py          # pdf / docx / txt
  chat/
    session.py        # session lifecycle, working/ reset
    intent.py         # stage 1: retrieve | no_retrieve
    select.py         # stage 2: ranked domain list
    budget.py         # stage 3: budget-aware context assembly
    tools.py          # read_domain, write_fact, note_open_question
    respond.py        # stage 4: Claude tool-use loop
fixtures/
  make_contradiction_pdf.py
  linear_contradiction.pdf
tests/
  test_merge_fact.py  # 10 cases, all branches of the state machine
demo.sh
pyproject.toml
README.md
```
