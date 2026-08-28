"""Unit tests for store.import_journal_batch against a fake pool.

The fake pool records every SQL call (statement + parameter tuple) and
simulates ON CONFLICT outcomes via per-test result queues — never touches
a real database (mirrors the _FakeJournalImportStore unit-test discipline
of tests/test_journal_import.py).
"""

from __future__ import annotations

import hashlib
import sys
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

import pytest

from edfinder_api.journal.store import (
    MAX_DAILY_EVENTS_PER_ACCOUNT,
    ImportCounts,
    JournalQuotaExceededError,
    import_journal_batch,
)

TS1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
TS2 = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
ACCOUNT_ID = uuid.UUID('11111111-1111-1111-1111-111111111111')
COMMANDER_ID = uuid.UUID('22222222-2222-2222-2222-222222222222')
HASH_A = hashlib.sha256(b'file-a').hexdigest()
HASH_B = hashlib.sha256(b'file-b').hexdigest()
RECORD_HASH = hashlib.sha256(b'line-1').hexdigest()


def _classify(sql: str) -> str:
    if 'date_trunc' in sql and 'journal_event' in sql:
        return 'quota'
    if 'INSERT INTO v3_source.source_artifact' in sql:
        return 'artifact_insert'
    if 'FROM v3_source.source_artifact' in sql:
        return 'artifact_select'
    if 'INSERT INTO v3_source.source_run' in sql:
        return 'run_insert'
    if 'FROM v3_source.source_run' in sql:
        return 'run_select'
    if 'INSERT INTO v3_source.source_rights_policy' in sql:
        return 'rights_insert'
    if 'FROM v3_source.source_rights_policy' in sql:
        return 'rights_select'
    if 'INSERT INTO v3_source.source' in sql:
        return 'source_insert'
    if 'FROM v3_source.source' in sql:
        return 'source_select'
    if 'INSERT INTO v3_private.private_import' in sql:
        return 'private_import_insert'
    if 'INSERT INTO v3_private.journal_import_file' in sql:
        return 'file_insert'
    if 'INSERT INTO v3_private.journal_event' in sql:
        return 'event_insert'
    if 'account_commander_access' in sql:
        return 'commander_edge'
    return 'other'


class _FakeJournalConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.quota_used = 0
        self.source_row: dict | None = {'source_id': 1}
        self.rights_row: dict | None = {'rights_policy_id': 1}
        self.commander_edge_row: dict | None = None
        self.artifact_insert_results: deque[dict | None] = deque()
        self.file_insert_results: deque[dict | None] = deque()
        self.event_insert_results: deque[dict | None] = deque()
        self.run_result: dict | None = {'source_run_id': uuid.uuid4()}

    def record(self, sql: str, args: tuple) -> None:
        self.calls.append((sql, args))

    async def fetchval(self, sql: str, *args: object) -> object:
        self.record(sql, args)
        kind = _classify(sql)
        if kind == 'quota':
            return self.quota_used
        return None

    async def fetchrow(self, sql: str, *args: object) -> dict | None:
        self.record(sql, args)
        kind = _classify(sql)
        if kind == 'source_select':
            return self.source_row
        if kind == 'source_insert':
            return {'source_id': 1}
        if kind == 'rights_insert':
            return self.rights_row
        if kind == 'rights_select':
            return {'rights_policy_id': 1}
        if kind == 'artifact_insert':
            return self.artifact_insert_results.popleft() if self.artifact_insert_results else {'artifact_id': uuid.uuid4()}
        if kind == 'artifact_select':
            return {'artifact_id': uuid.uuid4()}
        if kind == 'run_insert':
            return self.run_result
        if kind == 'run_select':
            return {'source_run_id': uuid.uuid4()}
        if kind == 'private_import_insert':
            return {'private_import_id': uuid.uuid4()}
        if kind == 'file_insert':
            return self.file_insert_results.popleft() if self.file_insert_results else {'journal_file_id': uuid.uuid4()}
        if kind == 'event_insert':
            return self.event_insert_results.popleft() if self.event_insert_results else {'journal_event_id': uuid.uuid4()}
        if kind == 'commander_edge':
            return self.commander_edge_row
        return None

    async def execute(self, sql: str, *args: object) -> str:
        self.record(sql, args)
        return 'INSERT 0 0'

    def calls_of(self, kind: str) -> list[tuple]:
        return [args for sql, args in self.calls if _classify(sql) == kind]

    def sqls_of(self, kind: str) -> list[str]:
        return [sql for sql, _args in self.calls if _classify(sql) == kind]

    def transaction(self) -> '_FakeTransaction':
        return _FakeTransaction()


class _FakeTransaction:
    async def __aenter__(self) -> '_FakeTransaction':
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _FakeJournalPool:
    def __init__(self, conn: _FakeJournalConn) -> None:
        self.conn = conn

    def acquire(self) -> '_FakeAcquire':
        return _FakeAcquire(self.conn)


class _FakeAcquire:
    def __init__(self, conn: _FakeJournalConn) -> None:
        self.conn = conn

    async def __aenter__(self) -> _FakeJournalConn:
        return self.conn

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def _files(*hashes: str) -> list[dict]:
    return [
        {
            'name': f'Journal.{index}.log',
            'content_sha256': content_hash,
            'size_bytes': 1000 + index,
            'line_count': 10 + index,
            'event_count': 1,
            'first_event_at': TS1,
            'last_event_at': TS2,
        }
        for index, content_hash in enumerate(hashes)
    ]


def _events(*kinds: str) -> list[dict]:
    events = []
    for index, kind in enumerate(kinds):
        if kind == 'FSDJump':
            payload = {'SystemAddress': 7}
        else:
            payload = {'SystemAddress': 10, 'BodyID': 3, 'BodyName': f'Body {index}'}
        events.append({
            'event_type': kind,
            'event_timestamp': TS1,
            'source_record_hash': hashlib.sha256(f'line-{index}'.encode()).hexdigest(),
            # events beyond the first two files reuse file 1
            'source_file': f'Journal.{min(index, 1)}.log',
            'source_offset': index * 100,
            'payload': payload,
        })
    return events


def test_happy_path_counts_and_returns_import_id():
    conn = _FakeJournalConn()
    pool = _FakeJournalPool(conn)
    import_id, counts = _asyncio_run(import_journal_batch(
        pool,
        account_id=ACCOUNT_ID,
        parser_version='journal-import-worker-v2',
        files=_files(HASH_A, HASH_B),
        events=_events('Scan', 'ScanOrganic', 'FSDJump'),
    ))
    assert isinstance(import_id, uuid.UUID)
    assert counts == ImportCounts(
        files_received=2, files_skipped=0, files_admitted=2,
        events_received=3, events_inserted=3, duplicates_skipped=0,
        privacy_stripped_fields=0,
        event_counts={'Scan': 1, 'ScanOrganic': 1, 'FSDJump': 1},
    )
    assert len(conn.calls_of('file_insert')) == 2
    assert len(conn.calls_of('event_insert')) == 3


def test_file_dedupe_and_event_dedupe_counts():
    conn = _FakeJournalConn()
    conn.event_insert_results = deque([None, {'journal_event_id': uuid.uuid4()}])
    pool = _FakeJournalPool(conn)
    _import_id, counts = _asyncio_run(import_journal_batch(
        pool,
        account_id=ACCOUNT_ID,
        parser_version='p1',
        files=_files(HASH_A, HASH_B),
        events=_events('Scan', 'Scan'),
    ))
    assert counts.files_received == 2
    assert counts.files_admitted == 2
    assert counts.files_skipped == 0
    assert counts.events_received == 2
    assert counts.events_inserted == 1
    assert counts.duplicates_skipped == 1


def test_events_from_skipped_files_are_not_processed():
    conn = _FakeJournalConn()
    # Second file insert conflicts (duplicate content already admitted).
    conn.file_insert_results = deque([{'journal_file_id': uuid.uuid4()}, None])
    pool = _FakeJournalPool(conn)
    _import_id, counts = _asyncio_run(import_journal_batch(
        pool,
        account_id=ACCOUNT_ID,
        parser_version='p1',
        files=_files(HASH_A, HASH_B),
        events=_events('Scan', 'FSDJump'),  # FSDJump belongs to the skipped file
    ))
    assert counts.files_skipped == 1
    assert counts.events_inserted == 1
    assert counts.duplicates_skipped == 0
    # The skipped file's FSDJump must never reach an event INSERT; a missing
    # EventTimestamp would have raised if it had been processed.
    assert len(conn.calls_of('event_insert')) == 1
    assert counts.event_counts == {'Scan': 1, 'FSDJump': 1}


def test_quota_exceeded_raises_and_writes_nothing():
    conn = _FakeJournalConn()
    conn.quota_used = MAX_DAILY_EVENTS_PER_ACCOUNT - 1
    pool = _FakeJournalPool(conn)
    with pytest.raises(JournalQuotaExceededError):
        _asyncio_run(import_journal_batch(
            pool,
            account_id=ACCOUNT_ID,
            parser_version='p1',
            files=_files(HASH_A),
            events=_events('Scan', 'Scan'),
        ))
    kinds = [_classify(sql) for sql, _args in conn.calls]
    assert kinds == ['quota']


def test_privacy_stripped_fields_are_counted():
    conn = _FakeJournalConn()
    pool = _FakeJournalPool(conn)
    events = _events('Scan', 'ScanOrganic')
    events[0]['payload'] = {'BodyName': 'A', 'SystemAddress': 1, 'Secret': 42}
    events[1]['payload'] = {
        'SystemAddress': 10, 'Body': 3, 'ScanType': 'Log',
        'Credits': 5, 'FuelLevel': 1.0,
    }
    _import_id, counts = _asyncio_run(import_journal_batch(
        pool,
        account_id=ACCOUNT_ID,
        parser_version='p1',
        files=_files(HASH_A, HASH_B),
        events=events,
    ))
    assert counts.privacy_stripped_fields == 3
    assert counts.events_inserted == 2


def test_idempotency_key_is_deterministic_per_account_parser_and_files():
    conn = _FakeJournalConn()
    pool = _FakeJournalPool(conn)
    files = _files(HASH_B, HASH_A)
    _asyncio_run(import_journal_batch(
        pool, account_id=ACCOUNT_ID, parser_version='p1', files=files, events=_events('Scan'),
    ))
    _asyncio_run(import_journal_batch(
        pool, account_id=ACCOUNT_ID, parser_version='p1', files=files, events=_events('Scan'),
    ))
    run_keys = [args[3] for args in conn.calls_of('run_insert')]
    assert len(run_keys) == 2
    assert run_keys[0] == run_keys[1]
    sorted_hashes = sorted([HASH_A, HASH_B])
    expected = hashlib.sha256(
        f'{ACCOUNT_ID}|p1|{"|".join(sorted_hashes)}'.encode('utf-8'),
    ).hexdigest()
    assert run_keys[0] == expected
    # Different parser version or account -> different key.
    conn2 = _FakeJournalConn()
    _asyncio_run(import_journal_batch(
        _FakeJournalPool(conn2), account_id=ACCOUNT_ID, parser_version='p2',
        files=files, events=_events('Scan'),
    ))
    assert conn2.calls_of('run_insert')[0][3] != expected


def test_source_and_rights_policy_bootstrap_when_absent():
    conn = _FakeJournalConn()
    conn.source_row = None
    conn.rights_row = None
    pool = _FakeJournalPool(conn)
    _asyncio_run(import_journal_batch(
        pool, account_id=ACCOUNT_ID, parser_version='p1',
        files=_files(HASH_A), events=_events('Scan'),
    ))
    assert len(conn.calls_of('source_select')) >= 1
    assert len(conn.calls_of('source_insert')) == 1
    assert len(conn.calls_of('rights_insert')) == 1
    # Rights insert carries the private-only policy contract: literal
    # 'PRIVATE_ONLY' in the statement, policy params in the args.
    rights_sql = conn.sqls_of('rights_insert')[0]
    assert 'PRIVATE_ONLY' in rights_sql
    rights_args = conn.calls_of('rights_insert')[0]
    assert rights_args[1] == '1.0'
    assert rights_args[2] == 'PRIVATE_USER_CONTENT'


def test_owner_commander_id_only_with_active_edge():
    conn = _FakeJournalConn()
    conn.commander_edge_row = {'commander_id': COMMANDER_ID}
    pool = _FakeJournalPool(conn)
    _asyncio_run(import_journal_batch(
        pool, account_id=ACCOUNT_ID, commander_id=COMMANDER_ID,
        parser_version='p1', files=_files(HASH_A), events=_events('Scan'),
    ))
    import_args = conn.calls_of('private_import_insert')[0]
    assert import_args[2] == COMMANDER_ID
    # Without an edge the owner_commander_id stays NULL.
    conn2 = _FakeJournalConn()
    conn2.commander_edge_row = None
    _asyncio_run(import_journal_batch(
        _FakeJournalPool(conn2), account_id=ACCOUNT_ID, commander_id=COMMANDER_ID,
        parser_version='p1', files=_files(HASH_A), events=_events('Scan'),
    ))
    import_args2 = conn2.calls_of('private_import_insert')[0]
    assert import_args2[2] is None


def test_all_sql_is_parameterized():
    conn = _FakeJournalConn()
    pool = _FakeJournalPool(conn)
    _asyncio_run(import_journal_batch(
        pool, account_id=ACCOUNT_ID, commander_id=COMMANDER_ID,
        parser_version='p1', files=_files(HASH_A), events=_events('Scan', 'FSDJump'),
    ))
    for sql, args in conn.calls:
        assert '$' in sql, f'statement without parameters: {sql}'
        for literal in ('11111111-1111-1111-1111-111111111111', HASH_A[:16]):
            assert literal not in sql, f'value interpolated into SQL: {sql}'
        assert isinstance(args, tuple)


def _asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)
