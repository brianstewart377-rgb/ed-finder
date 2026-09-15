from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import asyncpg
import pytest
import pytest_asyncio
from fastapi import HTTPException

os.environ.setdefault('CORS_ORIGINS', 'http://testserver')

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.helpers import db_isolation  # noqa: E402

from edfinder_api.journal.commanders import (  # noqa: E402
    ISSUER, associate_verified_commander, fid_from_customer_id,
)
from edfinder_api.journal.ownership import classify_files  # noqa: E402
from edfinder_api.routers.auth import identity_from_frontier_payloads  # noqa: E402

ACCOUNT_A = uuid.uuid4()
NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def db_conn():
    """A real, disposable-DB-only connection wrapped in a rolled-back transaction.

    Reuses the repo's fail-closed DB isolation helpers (tests/helpers/db_isolation.py)
    so this never targets a production-looking host/database. Skips (rather than
    fails) when no local disposable Postgres is reachable, per the project's
    "real-service tests must skip explicitly when the service is absent" rule.
    """
    target = db_isolation.default_target(os.environ)
    try:
        conn = await asyncpg.connect(target.dsn)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f'disposable test Postgres unreachable at {target.redacted_dsn}: {exc}')
        return
    transaction = conn.transaction()
    await transaction.start()
    try:
        await conn.execute(
            "INSERT INTO v3_identity.account (account_id) VALUES ($1) "
            "ON CONFLICT (account_id) DO NOTHING",
            ACCOUNT_A,
        )
        yield conn
    finally:
        await transaction.rollback()
        await conn.close()


def test_child_customer_is_preserved_separately_from_parent_account():
    first = identity_from_frontier_payloads(
        {'iss': ISSUER, 'usr': {'customer_id': '123'}},
        {'customer_id': '123', 'parent_id': '999'},
    )
    second = identity_from_frontier_payloads(
        {'iss': ISSUER, 'usr': {'customer_id': '456'}},
        {'customer_id': '456', 'parent_id': '999'},
    )
    assert first.subject == second.subject == '999'
    assert first.journal_fid == 'F123'
    assert second.journal_fid == 'F456'
    assert first.commander_name is None


@pytest.mark.parametrize('value', [None, '', True, 1.5, '1.5', '-123', ' 123', '00123', 'F123', 'x' * 100])
def test_unknown_customer_formats_never_become_verified_fids(value):
    assert fid_from_customer_id(value) is None


def test_parent_or_profile_name_cannot_supply_missing_customer_proof():
    identity = identity_from_frontier_payloads(
        {'iss': ISSUER, 'usr': {}}, {'parent_id': '999'},
        {'commander': {'name': 'Known name', 'fid': 'F999'}},
    )
    assert identity.subject == '999'
    assert identity.journal_fid is None


@pytest.mark.asyncio
async def test_verified_association_reuses_fid_identity_and_cannot_change_owner():
    commander_id, account_id = uuid.uuid4(), uuid.uuid4()
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        'commander_id': commander_id,
        'commander_state': 'ACTIVE',
        'commander_name': 'Verified commander',
        'journal_name_observed_at': None,
    }
    conn.fetchval.return_value = account_id
    actual = await associate_verified_commander(
        conn, account_id=account_id, issuer=ISSUER, fid='F123',
        verified_at=datetime.now(timezone.utc),
    )
    assert actual == commander_id
    assert any(
        'SET commander_name = $2' in call.args[0]
        for call in conn.execute.call_args_list
    )
    conn.reset_mock()
    conn.fetchval.return_value = uuid.uuid4()
    with pytest.raises(HTTPException) as caught:
        await associate_verified_commander(
            conn, account_id=account_id, issuer=ISSUER, fid='F123',
            verified_at=datetime.now(timezone.utc),
        )
    assert caught.value.status_code == 409
    assert all('UPDATE' not in call.args[0] and 'INSERT' not in call.args[0]
               for call in conn.execute.call_args_list)


@pytest.mark.asyncio
async def test_associate_stores_real_name_on_insert(db_conn):
    cid = await associate_verified_commander(
        db_conn, account_id=ACCOUNT_A, issuer=ISSUER,
        fid='F123', verified_at=NOW, commander_name='Jameson',
    )
    name = await db_conn.fetchval(
        'SELECT commander_name FROM v3_identity.commander WHERE commander_id=$1', cid,
    )
    assert name == 'Jameson'


@pytest.mark.asyncio
async def test_associate_replaces_placeholder_with_real_name(db_conn):
    await associate_verified_commander(
        db_conn, account_id=ACCOUNT_A, issuer=ISSUER, fid='F123', verified_at=NOW,
    )  # placeholder created
    await associate_verified_commander(
        db_conn, account_id=ACCOUNT_A, issuer=ISSUER, fid='F123',
        verified_at=NOW, commander_name='Jameson',
    )
    name = await db_conn.fetchval(
        "SELECT commander_name FROM v3_identity.commander"
        " WHERE commander_id IN (SELECT commander_id FROM"
        " v3_identity.commander_external_identity WHERE subject='F123')",
    )
    assert name == 'Jameson'


@pytest.mark.asyncio
async def test_associate_none_name_does_not_clobber_existing_real_name(db_conn):
    await associate_verified_commander(
        db_conn, account_id=ACCOUNT_A, issuer=ISSUER, fid='F123',
        verified_at=NOW, commander_name='Jameson',
    )
    await associate_verified_commander(
        db_conn, account_id=ACCOUNT_A, issuer=ISSUER, fid='F123', verified_at=NOW,
    )  # no name supplied on this call (e.g. CAPI fail-open)
    name = await db_conn.fetchval(
        "SELECT commander_name FROM v3_identity.commander"
        " WHERE commander_id IN (SELECT commander_id FROM"
        " v3_identity.commander_external_identity WHERE subject='F123')",
    )
    assert name == 'Jameson'


def _event(name, offset, event_type, **payload):
    return {'source_file': name, 'source_offset': offset,
            'event_type': event_type, 'payload': payload}


def test_other_commander_and_unknown_file_do_not_stop_valid_files():
    events = [
        _event('mine.log', 0, 'Fileheader'),
        _event('mine.log', 10, 'Commander', FID='F123', Name='Old name'),
        _event('mine.log', 20, 'Died', KillerName='Different player', Commander='Other'),
        _event('mine.log', 30, 'LoadGame', FID='F123', Commander='New name'),
        _event('other.log', 0, 'Commander', FID='F456', Name='Old name'),
        _event('unknown.log', 0, 'Scan', SystemAddress=123, BodyID=1),
    ]
    rows = classify_files(
        [{'name': name} for name in ['other.log', 'unknown.log', 'mine.log']],
        list(reversed(events)), {'F123'},
    )
    assert [row.reason for row in rows] == ['commander_not_linked', 'missing_commander_header', None]
    assert rows[-1].fid == 'F123'
    assert rows[-1].display_name == 'New name'


def test_midfile_identity_change_is_held_even_when_both_commanders_are_owned():
    events = [_event('mixed.log', 0, 'Commander', FID='F123'),
              _event('mixed.log', 1, 'Commander', FID='F456')]
    assert classify_files([{'name': 'mixed.log'}], events, {'F123', 'F456'})[0].reason == 'mixed_commanders'


@pytest.mark.parametrize('events,reason', [
    ([_event('a', 0, 'Scan'), _event('a', 1, 'Commander', FID='F123')], 'missing_commander_header'),
    ([_event('a', 0, 'Commander', FID='F123'), _event('a', 1, 'LoadGame', Commander='Name')], 'missing_commander_identity'),
    ([_event('a', 0, 'Commander', FID='F123'), _event('a', 0, 'Scan')], 'ambiguous_record_order'),
])
def test_ambiguous_segments_are_recoverable(events, reason):
    assert classify_files([{'name': 'a'}], events, {'F123'})[0].reason == reason


def test_same_named_files_cannot_be_silently_combined():
    rows = classify_files([{'name': 'a'}, {'name': 'a'}], [], {'F123'})
    assert all(row.reason == 'duplicate_file_name' for row in rows)
