"""Confidence level helpers: ordering, bumping, demoting, trust-cap."""
from __future__ import annotations

from agent.config import TRUST_CAP_THRESHOLD
from agent.models import Confidence


_ORDER: list[Confidence] = ["low", "medium", "high"]


def _idx(c: Confidence) -> int:
    return _ORDER.index(c)


def bump_up(current: Confidence) -> Confidence:
    """Move one level up; clamp at high."""
    i = _idx(current)
    return _ORDER[min(i + 1, len(_ORDER) - 1)]


def demote(current: Confidence) -> Confidence:
    """Move one level down; clamp at low."""
    i = _idx(current)
    return _ORDER[max(i - 1, 0)]


def apply_trust_cap(level: Confidence, trust: float) -> Confidence:
    """Internal cap: low-trust sources cannot assert 'high' confidence.

    If ``trust < TRUST_CAP_THRESHOLD`` and the extraction rated the fact
    ``high``, pin it to ``medium``. Lower levels pass through unchanged.
    """
    if trust < TRUST_CAP_THRESHOLD and level == "high":
        return "medium"
    return level
