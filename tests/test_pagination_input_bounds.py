"""Regression tests: out-of-range pagination inputs must not reach the database.

Two sibling defects hardened here:

* ``GET /api/events/recent`` clamped only the *upper* limit bound
  (``min(limit, 200)``), so ``?limit=-1`` passed a negative ``LIMIT`` straight
  to Postgres — which rejects it (``LIMIT must not be negative``) and, with no
  try/except on the handler, returned an HTTP 500. The fix clamps the lower
  bound to ``0`` (``max(0, min(limit, 200))``), not ``1`` — a valid ``limit=0``
  request (``LIMIT 0`` is accepted by Postgres) must still return an empty set,
  not be silently bumped to one row.

* The search request models (``LocalSearchRequest.from_``,
  ``GalaxySearchRequest.offset``, ``ClusterSearchRequest.offset``) accepted
  negative offsets, which flow into a negative SQL ``OFFSET`` and surface as a
  misleading 503 ("backend temporarily unavailable") for what is really a
  client input error. Their sibling fields (``min_score``, ``galaxy_region_id``)
  already declare ``ge=`` bounds.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')
os.environ.setdefault('ENVIRONMENT', 'test')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('DATABASE_URL', 'postgresql://user:password@localhost:5432/ed_finder_test')

import pytest
from pydantic import ValidationError

from edfinder_api.models import (
    ClusterSearchRequest,
    GalaxySearchRequest,
    LocalSearchRequest,
    SlotRequirement,
)
from edfinder_api.routers import events as events_router


# --------------------------------------------------------------------------- #
# Request-model guards: negative pagination offsets are rejected at the edge.
# --------------------------------------------------------------------------- #

def test_local_search_rejects_negative_from():
    with pytest.raises(ValidationError):
        LocalSearchRequest(**{'from': -1})


def test_local_search_accepts_zero_and_positive_from():
    assert LocalSearchRequest(**{'from': 0}).from_ == 0
    assert LocalSearchRequest(**{'from': 25}).from_ == 25


def test_galaxy_search_rejects_negative_offset():
    with pytest.raises(ValidationError):
        GalaxySearchRequest(offset=-1)


def test_galaxy_search_accepts_zero_and_positive_offset():
    assert GalaxySearchRequest(offset=0).offset == 0
    assert GalaxySearchRequest(offset=100).offset == 100


def test_cluster_search_rejects_negative_offset():
    with pytest.raises(ValidationError):
        ClusterSearchRequest(
            slots=[SlotRequirement(archetype_key='refinery_industrial')],
            offset=-1,
        )


def test_cluster_search_accepts_zero_and_positive_offset():
    req = ClusterSearchRequest(
        slots=[SlotRequirement(archetype_key='refinery_industrial')],
        offset=40,
    )
    assert req.offset == 40


# --------------------------------------------------------------------------- #
# recent_events must clamp ``limit`` to a valid range before it reaches SQL.
# A fake pool records the value passed to ``LIMIT $1`` so we can assert the
# clamp without a live Postgres (a real Postgres would 500 on a negative limit).
# --------------------------------------------------------------------------- #

class _FakeConn:
    def __init__(self, recorded_limits: list[int]) -> None:
        self._recorded_limits = recorded_limits

    async def fetch(self, _query: str, limit: int):
        self._recorded_limits.append(limit)
        return []


class _FakeAcquire:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _FakePool:
    def __init__(self) -> None:
        self.limits: list[int] = []

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(_FakeConn(self.limits))


def _call_recent_events(limit: int) -> _FakePool:
    pool = _FakePool()
    asyncio.run(events_router.recent_events(limit=limit, pool=pool))
    return pool


def test_recent_events_clamps_negative_limit_to_zero():
    # Without the fix this passes -1 into ``LIMIT $1`` -> Postgres 500.
    # Clamped to 0 (not 1) so the fix never invents an extra row.
    assert _call_recent_events(-1).limits == [0]


def test_recent_events_passes_zero_limit_through():
    # LIMIT 0 is a valid request (empty result); it must not be bumped to 1.
    assert _call_recent_events(0).limits == [0]


def test_recent_events_clamps_upper_bound():
    assert _call_recent_events(10_000).limits == [200]


def test_recent_events_passes_valid_limit_through():
    assert _call_recent_events(25).limits == [25]
