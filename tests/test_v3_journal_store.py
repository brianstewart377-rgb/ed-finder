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
        self.owner_edge_row: dict | None = None
        self.artifact_insert_results: deque[dict | None] = deque()
        self.file_insert_results: deque[dict | None] = deque()
        self.run_result: dict | None = {'source_run_id': uuid.uuid4()}
        # Batched event inserts: per-call number of duplicate rows the fake
        # reports as ON CONFLICT-skipped (command tag excludes them).
        self.event_insert_skipped: deque[int] = deque()

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
        if kind == 'commander_edge':
            # Direct-edge query binds ($1 account, $2 commander); the OWNER
            # fallback query binds only ($1 account).
            if len(args) == 1:
                return self.owner_edge_row
            return self.commander_edge_row
        return None

    async def execute(self, sql: str, *args: object) -> str:
        self.record(sql, args)
        kind = _classify(sql)
        if kind == 'event_insert':
            # Batched unnest INSERT: the command tag counts inserted rows
            # only (ON CONFLICT DO NOTHING rows are excluded), so the fake
            # reports len(array) minus configured duplicates.
            batch_size = len(args[0])
            skipped = self.event_insert_skipped.popleft() if self.event_insert_skipped else 0
            return f'INSERT 0 {max(batch_size - skipped, 0)}'
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
    # Batched inserts: the 3 events go in ONE unnest statement.
    event_calls = conn.calls_of('event_insert')
    assert len(event_calls) == 1
    assert len(event_calls[0][0]) == 3  # journal_event_id array length == events


def test_file_dedupe_and_event_dedupe_counts():
    conn = _FakeJournalConn()
    conn.event_insert_skipped = deque([1])  # 1 of the 2 batched events conflicts
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
    # The skipped file's FSDJump must never reach an event INSERT (the one
    # batched call carries only the admitted file's event).
    event_calls = conn.calls_of('event_insert')
    assert len(event_calls) == 1
    assert len(event_calls[0][0]) == 1
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
    assert kinds == ['other', 'quota']


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


def test_owner_edge_fallback_branch_uses_accounts_active_owner_edge():
    # Backend fix wave (review 2.7): when no commander_id is supplied (or the
    # supplied edge is inactive), the store falls back to the account's
    # active OWNER access edge — the composite FK (owner_account_id,
    # owner_commander_id) requires an existing edge either way.
    OWNER_ID = uuid.UUID('33333333-3333-4333-8333-333333333333')
    conn = _FakeJournalConn()
    conn.owner_edge_row = {'commander_id': OWNER_ID}
    _asyncio_run(import_journal_batch(
        _FakeJournalPool(conn), account_id=ACCOUNT_ID, commander_id=None,
        parser_version='p1', files=_files(HASH_A), events=_events('Scan'),
    ))
    import_args = conn.calls_of('private_import_insert')[0]
    assert import_args[2] == OWNER_ID
    # Direct edge absent (fake returns None for the 2-arg query) but the
    # account's active OWNER edge present -> OWNER wins.
    conn2 = _FakeJournalConn()
    conn2.commander_edge_row = None
    conn2.owner_edge_row = {'commander_id': OWNER_ID}
    _asyncio_run(import_journal_batch(
        _FakeJournalPool(conn2), account_id=ACCOUNT_ID,
        commander_id=COMMANDER_ID,  # no direct edge -> fallback
        parser_version='p1', files=_files(HASH_A), events=_events('Scan'),
    ))
    import_args2 = conn2.calls_of('private_import_insert')[0]
    assert import_args2[2] == OWNER_ID
    # No edge anywhere -> NULL owner_commander_id (composite FK satisfied by
    # the existing account-only case).
    conn3 = _FakeJournalConn()
    conn3.commander_edge_row = None
    conn3.owner_edge_row = None
    _asyncio_run(import_journal_batch(
        _FakeJournalPool(conn3), account_id=ACCOUNT_ID, commander_id=None,
        parser_version='p1', files=_files(HASH_A), events=_events('Scan'),
    ))
    assert conn3.calls_of('private_import_insert')[0][2] is None


def test_event_inserts_are_chunked_at_the_batch_boundary(monkeypatch):
    # Backend fix wave (perf): chunked unnest inserts of <= 5,000; with the
    # chunk size monkeypatched small, 5 events split into 3 batched calls of
    # sizes [2, 2, 1] and all counts still add up.
    import edfinder_api.journal.store as store_module

    monkeypatch.setattr(store_module, 'EVENT_INSERT_CHUNK_SIZE', 2)
    conn = _FakeJournalConn()
    _import_id, counts = _asyncio_run(import_journal_batch(
        _FakeJournalPool(conn),
        account_id=ACCOUNT_ID,
        parser_version='p1',
        files=_files(HASH_A, HASH_B),
        events=_events('Scan', 'ScanOrganic', 'FSDJump', 'Scan', 'Scan'),
    ))
    event_calls = conn.calls_of('event_insert')
    assert [len(args[0]) for args in event_calls] == [2, 2, 1]
    assert counts.events_received == 5
    assert counts.events_inserted == 5
    assert counts.duplicates_skipped == 0


def test_same_name_files_both_admitted_and_events_resolve_by_content_sha():
    # Backend fix wave (review 2.5): admitted_file_ids keys on content_sha256,
    # NOT the file name, so two same-named files in one request each get
    # their own journal_import_file row (the admission map is ambiguity-free).
    # Events still carry only the source file NAME, so they resolve through
    # the name -> sha bridge deterministically (last-wins for duplicate
    # names) — the guarantee pinned here is that no file row or event is
    # dropped and every event attributes to an admitted row's id.
    conn = _FakeJournalConn()
    file_rows = [{'journal_file_id': uuid.uuid4()}, {'journal_file_id': uuid.uuid4()}]
    conn.file_insert_results = deque(file_rows)
    files = [
        {'name': 'Journal.dup.log', 'content_sha256': HASH_A, 'size_bytes': 100,
         'line_count': 1, 'event_count': 1},
        {'name': 'Journal.dup.log', 'content_sha256': HASH_B, 'size_bytes': 200,
         'line_count': 1, 'event_count': 1},
    ]
    events = _events('Scan', 'ScanOrganic')
    events[0]['source_file'] = 'Journal.dup.log'
    events[1]['source_file'] = 'Journal.dup.log'
    events[0]['source_record_hash'] = hashlib.sha256(b'x1').hexdigest()
    events[1]['source_record_hash'] = hashlib.sha256(b'x2').hexdigest()
    _import_id, counts = _asyncio_run(import_journal_batch(
        _FakeJournalPool(conn),
        account_id=ACCOUNT_ID,
        parser_version='p1',
        files=files,
        events=events,
    ))
    assert counts.files_admitted == 2
    assert counts.files_skipped == 0
    assert counts.events_inserted == 2
    assert len(conn.calls_of('file_insert')) == 2
    event_calls = conn.calls_of('event_insert')
    assert len(event_calls) == 1
    journal_file_ids = event_calls[0][3]  # $4 = journal_file_id array
    # Both events resolve to the SECOND same-named file's content sha
    # (last-wins through the name -> sha bridge) — a deterministic,
    # non-dropping resolution; the admission map itself holds both shas.
    assert journal_file_ids == [file_rows[1]['journal_file_id']] * 2


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
