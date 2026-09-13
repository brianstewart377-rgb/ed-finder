from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

os.environ.setdefault('CORS_ORIGINS', 'http://testserver')

from edfinder_api.journal.commanders import (  # noqa: E402
    ISSUER, associate_verified_commander, fid_from_customer_id,
)
from edfinder_api.journal.ownership import classify_files  # noqa: E402
from edfinder_api.routers.auth import identity_from_frontier_payloads  # noqa: E402


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
    conn.fetchrow.return_value = {'commander_id': commander_id, 'commander_state': 'ACTIVE'}
    conn.fetchval.return_value = account_id
    actual = await associate_verified_commander(
        conn, account_id=account_id, issuer=ISSUER, fid='F123',
        verified_at=datetime.now(timezone.utc),
    )
    assert actual == commander_id
    assert all('commander_name' not in call.args[0] for call in conn.execute.call_args_list)
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
