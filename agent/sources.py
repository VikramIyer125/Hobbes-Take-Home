"""Source record I/O plus id minting."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from agent import paths
from agent.models import Source


def mint_source_id() -> str:
    """Return the next unused src_NNN identifier.

    Scans ``memory/sources/`` for existing ``src_###.json`` files and returns
    the next zero-padded slot. Chat-session sources use a different prefix
    so they do not consume URL/file slots.
    """
    sdir = paths.sources_dir()
    sdir.mkdir(parents=True, exist_ok=True)
    used: set[int] = set()
    for p in sdir.glob("src_*.json"):
        m = re.match(r"src_(\d+)$", p.stem)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return f"src_{n:03d}"


def mint_chat_source_id(session_id: str, turn_index: int) -> str:
    """Stable id for a chat turn that produced facts."""
    return f"src_chat_{session_id}_t{turn_index:03d}"


def save_source(source: Source) -> None:
    paths.sources_dir().mkdir(parents=True, exist_ok=True)
    path = paths.source_path(source.source_id)
    path.write_text(source.model_dump_json(indent=2), encoding="utf-8")


def load_source(source_id: str) -> Source:
    path = paths.source_path(source_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    return Source.model_validate(data)


def save_raw_bytes(source_id: str, data: bytes, ext: str) -> Path:
    """Persist raw content under ``sources/raw/<source_id>.<ext>`` and return the path."""
    raw_dir = paths.sources_raw_dir()
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{source_id}.{ext.lstrip('.')}"
    path.write_bytes(data)
    return path


def save_raw_text(source_id: str, text: str, ext: str) -> Path:
    return save_raw_bytes(source_id, text.encode("utf-8"), ext)


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_of_text(text: str) -> str:
    return content_hash(text.encode("utf-8"))
