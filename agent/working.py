"""Working (short-term) memory I/O.

``session_history.json`` — sliding window of last N turns.
``active_context.json`` — retrieval decision + loaded domains for current question.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from typing import Any

from agent import paths
from agent.config import SESSION_HISTORY_MAX_TURNS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def reset_working() -> None:
    """Wipe ``memory/working/`` at the start of a new chat session."""
    wdir = paths.working_dir()
    if wdir.exists():
        shutil.rmtree(wdir)
    wdir.mkdir(parents=True, exist_ok=True)


def load_session_history() -> list[dict[str, Any]]:
    path = paths.session_history_path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def append_turn(role: str, content: str) -> None:
    """Append a turn and trim to the last ``SESSION_HISTORY_MAX_TURNS`` turns."""
    history = load_session_history()
    history.append({"role": role, "content": content, "ts": _now_iso()})
    if len(history) > SESSION_HISTORY_MAX_TURNS:
        history = history[-SESSION_HISTORY_MAX_TURNS:]
    paths.working_dir().mkdir(parents=True, exist_ok=True)
    paths.session_history_path().write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_active_context(ctx: dict[str, Any]) -> None:
    paths.working_dir().mkdir(parents=True, exist_ok=True)
    paths.active_context_path().write_text(
        json.dumps(ctx, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_active_context() -> dict[str, Any] | None:
    path = paths.active_context_path()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
