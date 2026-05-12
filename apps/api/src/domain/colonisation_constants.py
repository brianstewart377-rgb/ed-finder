"""Colonisation mechanics constants with source-conscious defaults."""
from __future__ import annotations


STRONG_LINK_BY_TIER: dict[int, float] = {
    1: 0.4,
    2: 0.8,
    3: 1.2,
}

WEAK_LINK_STRENGTH = 0.05
MIN_STRONG_LINK_MODIFIER = 0.1
