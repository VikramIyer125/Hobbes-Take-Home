"""Filesystem layout for the on-disk memory.

Resolution order for the memory root:
1. ``AGENT_MEMORY_DIR`` environment variable if set.
2. ``<cwd>/memory``.
"""
from __future__ import annotations

import os
from pathlib import Path


def memory_root() -> Path:
    env = os.environ.get("AGENT_MEMORY_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / "memory").resolve()


def working_dir() -> Path:
    return memory_root() / "working"


def knowledge_dir() -> Path:
    return memory_root() / "knowledge"


def sources_dir() -> Path:
    return memory_root() / "sources"


def sources_raw_dir() -> Path:
    return sources_dir() / "raw"


def changelog_path() -> Path:
    return memory_root() / "changelog.jsonl"


def session_history_path() -> Path:
    return working_dir() / "session_history.json"


def active_context_path() -> Path:
    return working_dir() / "active_context.json"


def domain_path(domain: str) -> Path:
    return knowledge_dir() / f"{domain}.json"


def source_path(source_id: str) -> Path:
    return sources_dir() / f"{source_id}.json"


def ensure_scaffold() -> None:
    """Create the directory tree if missing. Idempotent."""
    for d in (working_dir(), knowledge_dir(), sources_dir(), sources_raw_dir()):
        d.mkdir(parents=True, exist_ok=True)
