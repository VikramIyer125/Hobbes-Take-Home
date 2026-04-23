"""Load/save DomainFile JSON, creating a skeleton on demand."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent import paths
from agent.models import DomainFile


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load_domain(domain: str) -> DomainFile:
    path = paths.domain_path(domain)
    if not path.exists():
        return DomainFile(domain=domain, last_updated=_now(), open_questions=[], facts=[])
    data = json.loads(path.read_text(encoding="utf-8"))
    return DomainFile.model_validate(data)


def save_domain(dfile: DomainFile) -> None:
    paths.knowledge_dir().mkdir(parents=True, exist_ok=True)
    dfile.last_updated = _now()
    path = paths.domain_path(dfile.domain)
    path.write_text(
        dfile.model_dump_json(indent=2),
        encoding="utf-8",
    )


def list_existing_domains() -> list[str]:
    d = paths.knowledge_dir()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def fact_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in list_existing_domains():
        try:
            df = load_domain(name)
            counts[name] = len(df.facts)
        except Exception:
            counts[name] = 0
    return counts
