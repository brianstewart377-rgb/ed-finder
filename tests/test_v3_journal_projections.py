"""Unit tests for the V3 journal projections with fake rows.

The fake pool returns queued rows per statement; SQL is recorded so the
tests can assert account isolation (every query scoped by owner_account_id)
and pagination parameters. Never touches a real database.
"""

from __future__ import annotations

import sys
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from edfinder_api.journal.projections import (
    BODY_OBSERVATION_TYPES,
    codex_entries,
    journal_summary,
    organic_progress,
    sale_history,
    scanned_bodies,
    visited_systems,
)

TS1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
TS2 = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
ACCOUNT_ID = uuid.UUID('11111111-1111-1111-1111-111111111111')


class _FakeProjectionConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.fetchval_results: deque[object] = deque()
        self.fetchrow_results: deque[dict | None] = deque()
        self.fetch_results: deque[list[dict]] = deque()

    async def fetchval(self, sql: str, *args: object) -> object:
        self.calls.append((sql, args))
        return self.fetchval_results.popleft()

    async def fetchrow(self, sql: str, *args: object) -> dict | None:
        self.calls.append((sql, args))
        return self.fetchrow_results.popleft()

    async def fetch(self, sql: str, *args: object) -> list[dict]:
        self.calls.append((sql, args))
        return self.fetch_results.popleft()

    def transaction(self) -> '_FakeProjectionTransaction':
        return _FakeProjectionTransaction()


class _FakeProjectionTransaction:
    async def __aenter__(self) -> '_FakeProjectionTransaction':
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _FakeProjectionPool:
    def __init__(self, conn: _FakeProjectionConn) -> None:
        self.conn = conn

    def acquire(self) -> '_FakeProjectionAcquire':
        return _FakeProjectionAcquire(self.conn)


class _FakeProjectionAcquire:
    def __init__(self, conn: _FakeProjectionConn) -> None:
        self.conn = conn

    async def __aenter__(self) -> _FakeProjectionConn:
        return self.conn

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_body_observation_type_set_matches_the_plan():
    assert BODY_OBSERVATION_TYPES == frozenset({
        'Scan', 'FSSBodySignals', 'SAASignalsFound', 'SAAScanComplete',
        'Touchdown', 'Liftoff', 'ApproachBody', 'LeaveBody', 'Location',
        'Disembark', 'Embark', 'Screenshot',
    })


def test_journal_summary_counters():
    conn = _FakeProjectionConn()
    conn.fetchval_results.extend([5, 3, 2, 4])
    conn.fetchrow_results.append({'last_imported_at': TS2})
    conn.fetch_results.append([
        {'event_type': 'Scan', 'event_count': 4},
        {'event_type': 'FSDJump', 'event_count': 1},
    ])
    summary = _run(journal_summary(_FakeProjectionPool(conn), ACCOUNT_ID))
    assert summary == {
        'events_stored': 5,
        'unique_bodies': 3,
        'unique_bio_observations': 2,
        'systems_observed': 4,
        'last_imported_at': TS2,
        'event_counts': {'Scan': 4, 'FSDJump': 1},
    }
    assert len(conn.calls) == 6


def test_journal_summary_without_imports():
    conn = _FakeProjectionConn()
    conn.fetchval_results.extend([0, 0, 0, 0])
    conn.fetchrow_results.append(None)
    conn.fetch_results.append([])
    summary = _run(journal_summary(_FakeProjectionPool(conn), ACCOUNT_ID))
    assert summary['events_stored'] == 0
    assert summary['unique_bodies'] == 0
    assert summary['unique_bio_observations'] == 0
    assert summary['systems_observed'] == 0
    assert summary['last_imported_at'] is None
    assert summary['event_counts'] == {}


def test_visited_systems_returns_rows_and_passes_pagination():
    conn = _FakeProjectionConn()
    rows = [
        {'system_id64': '10477373803', 'system_name': 'Sol',
         'first_observed_at': TS1, 'last_observed_at': TS2, 'visit_count': 3},
        {'system_id64': '9', 'system_name': None,
         'first_observed_at': TS1, 'last_observed_at': TS1, 'visit_count': 1},
    ]
    conn.fetch_results.append(rows)
    result = _run(visited_systems(_FakeProjectionPool(conn), ACCOUNT_ID, offset=20, limit=5))
    assert result == rows
    sql, args = conn.calls[0]
    assert args == (ACCOUNT_ID, 20, 5)
    assert 'OFFSET $2 LIMIT $3' in sql


def test_scanned_bodies_rows_and_pagination():
    conn = _FakeProjectionConn()
    rows = [
        {'system_id64': '10477373803', 'body_id': '3', 'body_name': 'Mars',
         'first_observed_at': TS1, 'last_observed_at': TS2, 'scan_count': 2},
    ]
    conn.fetch_results.append(rows)
    result = _run(scanned_bodies(_FakeProjectionPool(conn), ACCOUNT_ID, offset=0, limit=50))
    assert result == rows
    sql, args = conn.calls[0]
    assert args == (ACCOUNT_ID, 0, 50)


def test_codex_entries_rows():
    conn = _FakeProjectionConn()
    rows = [
        {'entry_id': 'E01', 'name': '$Codex_Ent_Stratum_01;', 'category': '$Codex_Category_Biology;',
         'subcategory': '$Codex_SubCategory_Organic;', 'region': 'Inner Orion Spur',
         'system_id64': '10477373803', 'body_id': '4',
         'first_observed_at': TS1, 'last_observed_at': TS2},
    ]
    conn.fetch_results.append(rows)
    result = _run(codex_entries(_FakeProjectionPool(conn), ACCOUNT_ID))
    assert result == rows


def test_organic_progress_stages():
    conn = _FakeProjectionConn()
    rows = [
        {'genus': '$Genus_Foo;', 'species': '$Species_Bar;', 'variant': 'V1',
         'stages': ['Analyse', 'Log', 'Sample'],
         'first_observed_at': TS1, 'last_observed_at': TS2},
    ]
    conn.fetch_results.append(rows)
    result = _run(organic_progress(_FakeProjectionPool(conn), ACCOUNT_ID))
    assert result == rows
    assert result[0]['stages'] == ['Analyse', 'Log', 'Sample']


def test_sale_history_parses_bio_data_json_string():
    conn = _FakeProjectionConn()
    bio_json = '[{"Genus": "$Genus_Foo;", "Species": "$Species_Bar;", "Variant": "V1"}]'
    rows = [
        {'bio_data': bio_json, 'market_id': '128666824', 'observed_at': TS2},
        {'bio_data': None, 'market_id': None, 'observed_at': TS1},
    ]
    conn.fetch_results.append(rows)
    result = _run(sale_history(_FakeProjectionPool(conn), ACCOUNT_ID, offset=0, limit=10))
    assert result[0]['bio_data'] == [
        {'Genus': '$Genus_Foo;', 'Species': '$Species_Bar;', 'Variant': 'V1'},
    ]
    assert result[0]['market_id'] == '128666824'
    assert result[0]['observed_at'] == TS2
    assert result[1]['bio_data'] is None


def test_every_query_is_scoped_by_owner_account_id():
    conn = _FakeProjectionConn()
    conn.fetchval_results.extend([1, 1, 1, 1])
    conn.fetchrow_results.append(None)
    conn.fetch_results.extend([[], [], [], [], [], []])
    pool = _FakeProjectionPool(conn)
    _run(journal_summary(pool, ACCOUNT_ID))
    _run(visited_systems(pool, ACCOUNT_ID))
    _run(scanned_bodies(pool, ACCOUNT_ID))
    _run(codex_entries(pool, ACCOUNT_ID))
    _run(organic_progress(pool, ACCOUNT_ID))
    _run(sale_history(pool, ACCOUNT_ID))
    for sql, _args in conn.calls:
        assert 'owner_account_id' in sql, sql
        assert '$1' in sql, sql


def test_every_query_references_event_payload_never_bare_payload():
    # Regression: migration 003's column is event_payload. A bare `payload`
    # identifier in any projection query is a column bug (Postgres would
    # error at runtime; the fake pool cannot catch it, so the SQL text
    # itself is asserted).
    import re

    conn = _FakeProjectionConn()
    conn.fetchval_results.extend([1, 1, 1, 1])
    conn.fetchrow_results.append(None)
    conn.fetch_results.extend([[], [], [], [], [], []])
    pool = _FakeProjectionPool(conn)
    _run(journal_summary(pool, ACCOUNT_ID))
    _run(visited_systems(pool, ACCOUNT_ID))
    _run(scanned_bodies(pool, ACCOUNT_ID))
    _run(codex_entries(pool, ACCOUNT_ID))
    _run(organic_progress(pool, ACCOUNT_ID))
    _run(sale_history(pool, ACCOUNT_ID))
    assert conn.calls, 'expected recorded SQL calls'
    for sql, _args in conn.calls:
        # \\bpayload\\b does not match inside event_payload ('_' is a word
        # char), so any hit is the bare (wrong) column name.
        assert not re.search(r'\bpayload\b', sql), f'bare payload column in SQL: {sql}'
    # Sanity: at least one recorded statement actually reads event_payload.
    assert any('event_payload' in sql for sql, _args in conn.calls)
