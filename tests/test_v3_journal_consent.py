"""Unit tests for the V3 versioned research-consent ledger (Task 4, R7).

Covers edfinder_api.journal.consent (effective_consent, record_consent)
against a fake pool that materializes the append-only decision ledger:
effective state = the row with the greatest decided_at. Upload must never be
conditional on consent — this module is deliberately never referenced from
the journal import path.

Transition machine under test:
NONE -> GRANT (ok) -> duplicate GRANT (refused) -> WITHDRAW (ok)
-> re-GRANT (refused while withdrawn) -> duplicate WITHDRAW (refused).
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

import pytest

from edfinder_api.journal.consent import (
    AUDIENCE,
    CONSENT_VERSION,
    PURPOSE,
    SANITIZED_CONTRACT_VERSION,
    ConsentStateError,
    effective_consent,
    record_consent,
)

ACCOUNT_ID = uuid.UUID('22222222-2222-4222-8222-222222222222')

# Documented INSERT column order in consent.py (mirrored by the fake).
_CONSENT_COLUMNS = (
    'research_consent_id', 'owner_account_id', 'consent_version',
    'sanitized_contract_version', 'purpose', 'audience_code', 'decision',
    'decided_at', 'withdrawn_at',
)


class _FakePool:
    """Fake asyncpg pool materializing the append-only research_consent
    ledger. execute(INSERT) appends a row; fetch returns rows ordered by
    decided_at DESC (the effective-state query's contract). decided_at is
    nudged forward if two inserts land in the same microsecond, modelling
    the real DB's strictly-increasing per-transaction timestamps."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.calls: list[tuple[str, str, tuple]] = []

    async def fetch(self, sql: str, *args):
        self.calls.append(('fetch', sql, args))
        # Model the effective-state query (account-scoped, ordered by
        # decided_at DESC) and the grant-existence query (account + version
        # + decision='GRANT').
        account_id, *_rest = args
        rows = [r for r in self.rows if r['owner_account_id'] == account_id]
        if "decision = 'GRANT'" in sql:
            rows = [r for r in rows if r['decision'] == 'GRANT']
        return sorted(rows, key=lambda r: r['decided_at'], reverse=True)

    async def execute(self, sql: str, *args):
        self.calls.append(('execute', sql, args))
        if 'research_consent' in sql and 'INSERT' in sql:
            row = dict(zip(_CONSENT_COLUMNS, args, strict=False))
            if self.rows and row['decided_at'] <= self.rows[-1]['decided_at']:
                row['decided_at'] = self.rows[-1]['decided_at'] + timedelta(microseconds=1)
            self.rows.append(row)


def _assert_state_keys(state: dict) -> None:
    assert set(state) == {
        'decision', 'consent_version', 'sanitized_contract_version',
        'purpose', 'audience_code', 'decided_at',
    }
    assert state['consent_version'] == CONSENT_VERSION == '1.0'
    assert state['sanitized_contract_version'] == SANITIZED_CONTRACT_VERSION == '1.0.0'
    assert state['purpose'] == PURPOSE == 'CRE_RESEARCH_EVIDENCE'
    assert state['audience_code'] == AUDIENCE == 'CRE'


# ---------------------------------------------------------------------------
# effective_consent
# ---------------------------------------------------------------------------

def test_effective_consent_none_when_no_rows():
    pool = _FakePool()
    state = asyncio.run(
        effective_consent(pool, ACCOUNT_ID)
    )
    assert state is None


def test_effective_consent_returns_latest_decided_at_row():
    pool = _FakePool()
    pool.rows = [
        {
            'research_consent_id': uuid.uuid4(),
            'owner_account_id': ACCOUNT_ID,
            'consent_version': CONSENT_VERSION,
            'sanitized_contract_version': SANITIZED_CONTRACT_VERSION,
            'purpose': PURPOSE,
            'audience_code': AUDIENCE,
            'decision': 'GRANT',
            'decided_at': datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
            'withdrawn_at': None,
        },
        {
            'research_consent_id': uuid.uuid4(),
            'owner_account_id': ACCOUNT_ID,
            'consent_version': CONSENT_VERSION,
            'sanitized_contract_version': SANITIZED_CONTRACT_VERSION,
            'purpose': PURPOSE,
            'audience_code': AUDIENCE,
            'decision': 'WITHDRAW',
            'decided_at': datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc),
            'withdrawn_at': datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc),
        },
    ]
    state = asyncio.run(
        effective_consent(pool, ACCOUNT_ID)
    )
    assert state is not None
    assert state['decision'] == 'WITHDRAW'
    assert state['decided_at'] == datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)
    _assert_state_keys(state)


# ---------------------------------------------------------------------------
# record_consent — the state machine
# ---------------------------------------------------------------------------

def test_grant_from_none_records_and_returns_effective_state():
    pool = _FakePool()
    state = asyncio.run(
        record_consent(pool, ACCOUNT_ID, decision='GRANT')
    )
    assert state is not None
    assert state['decision'] == 'GRANT'
    _assert_state_keys(state)
    # One append-only ledger row.
    assert len(pool.rows) == 1 and pool.rows[0]['decision'] == 'GRANT'
    assert pool.rows[0]['withdrawn_at'] is None


def test_duplicate_grant_refused():
    pool = _FakePool()
    asyncio.run(record_consent(pool, ACCOUNT_ID, decision='GRANT'))
    with pytest.raises(ConsentStateError):
        asyncio.run(record_consent(pool, ACCOUNT_ID, decision='GRANT'))
    # Refusal must not have appended a row.
    assert len(pool.rows) == 1


def test_withdraw_without_grant_refused():
    pool = _FakePool()
    with pytest.raises(ConsentStateError):
        asyncio.run(
            record_consent(pool, ACCOUNT_ID, decision='WITHDRAW')
        )
    assert pool.rows == []


def test_withdraw_after_grant_records_withdrawn_at():
    pool = _FakePool()
    asyncio.run(record_consent(pool, ACCOUNT_ID, decision='GRANT'))
    state = asyncio.run(record_consent(pool, ACCOUNT_ID, decision='WITHDRAW'))
    assert state['decision'] == 'WITHDRAW'
    withdraw_row = pool.rows[-1]
    assert withdraw_row['withdrawn_at'] is not None
    assert withdraw_row['decided_at'] is not None
    # Decision history preserved: GRANT row still present.
    assert [r['decision'] for r in pool.rows] == ['GRANT', 'WITHDRAW']


def test_regrant_after_withdraw_refused():
    pool = _FakePool()
    asyncio.run(record_consent(pool, ACCOUNT_ID, decision='GRANT'))
    asyncio.run(record_consent(pool, ACCOUNT_ID, decision='WITHDRAW'))
    with pytest.raises(ConsentStateError):
        asyncio.run(record_consent(pool, ACCOUNT_ID, decision='GRANT'))
    assert len(pool.rows) == 2


def test_double_withdraw_refused():
    pool = _FakePool()
    asyncio.run(record_consent(pool, ACCOUNT_ID, decision='GRANT'))
    asyncio.run(record_consent(pool, ACCOUNT_ID, decision='WITHDRAW'))
    with pytest.raises(ConsentStateError):
        asyncio.run(record_consent(pool, ACCOUNT_ID, decision='WITHDRAW'))
    assert len(pool.rows) == 2


def test_invalid_decision_rejected():
    pool = _FakePool()
    with pytest.raises(ValueError):
        asyncio.run(
            record_consent(pool, ACCOUNT_ID, decision='MAYBE')
        )
    assert pool.rows == []


def test_record_consent_sql_is_account_scoped_and_parameterized():
    pool = _FakePool()
    asyncio.run(record_consent(pool, ACCOUNT_ID, decision='GRANT'))
    fetch_sql = next(sql for kind, sql, _args in pool.calls if kind == 'fetch')
    assert 'owner_account_id' in fetch_sql and '$1' in fetch_sql
    insert_sql = next(sql for kind, sql, _args in pool.calls if kind == 'execute')
    assert 'research_consent' in insert_sql and '$1' in insert_sql
    # No raw values are ever interpolated into SQL text.
    assert str(ACCOUNT_ID) not in insert_sql and str(ACCOUNT_ID) not in fetch_sql


def test_consent_never_touches_import_path():
    # Upload is never conditional on consent: the module exposes only the
    # consent ledger surface (no journal-event symbols).
    import edfinder_api.journal.consent as consent_module

    public_names = {n for n in dir(consent_module) if not n.startswith('_')}
    assert not any('journal_event' in n.lower() or 'import' in n.lower() for n in public_names)
