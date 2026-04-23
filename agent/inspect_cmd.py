"""Pretty-printers for the ``inspect`` CLI command."""
from __future__ import annotations

import json
from typing import Optional

from agent import changelog, paths, working
from agent.config import DOMAINS
from agent.domains import list_existing_domains, load_domain


def inspect_tree() -> str:
    root = paths.memory_root()
    lines = [f"memory/ (at {root})"]
    if not root.exists():
        lines.append("  (not yet initialized)")
        return "\n".join(lines)

    for sub in ("working", "knowledge", "sources"):
        sub_path = root / sub
        lines.append(f"  {sub}/")
        if not sub_path.exists():
            lines.append("    (empty)")
            continue
        for p in sorted(sub_path.iterdir()):
            if p.is_dir():
                lines.append(f"    {p.name}/")
                for q in sorted(p.iterdir()):
                    lines.append(f"      {q.name}")
            else:
                lines.append(f"    {p.name}")

    cl = paths.changelog_path()
    if cl.exists():
        nlines = sum(1 for _ in cl.open())
        lines.append(f"  changelog.jsonl  ({nlines} events)")
    else:
        lines.append("  changelog.jsonl  (none)")
    return "\n".join(lines)


def inspect_domain(domain: str) -> str:
    if domain not in DOMAINS:
        return f"Unknown domain: {domain!r}. Must be one of: {', '.join(DOMAINS)}"
    df = load_domain(domain)
    return df.model_dump_json(indent=2)


def inspect_all_domains() -> str:
    parts: list[str] = []
    names = list_existing_domains()
    if not names:
        return "(no domain files yet)"
    for name in names:
        df = load_domain(name)
        parts.append(f"=== {name} ({len(df.facts)} facts) ===")
        parts.append(df.model_dump_json(indent=2))
    return "\n\n".join(parts)


def inspect_changelog(n: int = 20) -> str:
    events = changelog.tail(n)
    if not events:
        return "(changelog empty)"
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in events)


def inspect_working() -> str:
    hist = working.load_session_history()
    ctx = working.load_active_context()
    parts = ["=== session_history ==="]
    parts.append(json.dumps(hist, ensure_ascii=False, indent=2))
    parts.append("")
    parts.append("=== active_context ===")
    parts.append(json.dumps(ctx, ensure_ascii=False, indent=2))
    return "\n".join(parts)
