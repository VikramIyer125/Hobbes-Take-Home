"""Chat session lifecycle helpers."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from agent import working


def new_session_id() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())


@dataclass
class ChatSession:
    session_id: str
    turn_index: int = 0
    current_turn_source_id: str | None = field(default=None)

    def next_turn(self) -> None:
        self.turn_index += 1
        self.current_turn_source_id = None  # lazy-minted on first write_fact


def start_session() -> ChatSession:
    """Reset working/ and return a fresh session context."""
    working.reset_working()
    return ChatSession(session_id=new_session_id(), turn_index=0)
