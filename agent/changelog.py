"""Append-only JSONL changelog of every mutation in knowledge memory."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from agent import paths


Op = Literal["add", "confirm", "conflict", "user_correction"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_event(
    op: Op,
    *,
    source: str,
    fact_id: str,
    domain: str,
    **extra: Any,
) -> None:
    """Append a single event line to ``memory/changelog.jsonl``."""
    paths.memory_root().mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "ts": _now_iso(),
        "op": op,
        "source": source,
        "fact_id": fact_id,
        "domain": domain,
    }
    record.update(extra)
    path = paths.changelog_path()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def tail(n: int = 20) -> list[dict[str, Any]]:
    path = paths.changelog_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines[-n:] if line.strip()]
