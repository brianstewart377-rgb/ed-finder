"""Unit tests for the V3 deterministic sanitized export builder (Task 4).

Covers edfinder_api.journal.export (build_export_payload, payload_bytes,
build_export, supersede_lineage_batches) against a fake pool recording SQL
calls — never a real database in unit tests.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from edfinder_api.journal.export import (
    EXPORT_SCHEMA,
    EXPORT_SCHEMA_VERSION,
    build_export,
    build_export_payload,
    payload_bytes,
    supersede_lineage_batches,
)

ACCOUNT_ID = uuid.UUID('11111111-1111-4111-8111-111111111111')
SRC = bytes.fromhex('ab' * 32)
TS = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)

ATTESTATION_NOTE = (
    'attested-not-proven: one Commander = one observer chain; '
    'lineage tokens do not verify cross-export independence'
)

LINEAGE_RE = re.compile(r'^[A-Za-z0-9_-]{16,64}$')


class _FakeConnection:
    """Records SQL calls; fetch returns configured rows; execute appends to
    the call log. Insert calls into research_export_batch update a receipt
    ledger so supersede behaviour can be asserted deterministically. Exposes
    a no-op transaction() (mirrors the store-test fake discipline)."""

    def __init__(self, *, rows: list[dict] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[tuple[str, str, tuple]] = []
        self.receipt_rows: list[dict] = []

    async def fetch(self, sql: str, *args):
        self.calls.append(('fetch', sql, args))
        return list(self.rows)

    async def execute(self, sql: str, *args):
        self.calls.append(('execute', sql, args))
        if 'research_export_batch' in sql and 'INSERT' in sql:
            # Mirrors the documented INSERT column order in export.py.
            (
                export_batch_id, owner, consent_version, sanitized_contract_version,
                lineage_token, observation_count, manifest, payload_sha256,
                batch_state, superseded_by_batch_id, created_at,
            ) = args
            self.receipt_rows.append({
                'export_batch_id': export_batch_id,
                'owner_account_id': owner,
                'consent_version': consent_version,
                'sanitized_contract_version': sanitized_contract_version,
                'lineage_token': lineage_token,
                'observation_count': observation_count,
                'manifest': manifest,
                'payload_sha256': payload_sha256,
                'batch_state': batch_state,
                'superseded_by_batch_id': superseded_by_batch_id,
                'created_at': created_at,
            })

    def transaction(self) -> '_FakeTransaction':
        return _FakeTransaction()


class _FakeTransaction:
    async def __aenter__(self) -> '_FakeTransaction':
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _FakePool:
    """Pool shim: build_export calls pool.fetch/execute directly (Task 4's
    interface); supersede_lineage_batches runs through acquire(). All calls
    are recorded on the single fake connection."""

    def __init__(self, *, rows: list[dict] | None = None) -> None:
        self.conn = _FakeConnection(rows=rows)

    async def fetch(self, sql: str, *args):
        return await self.conn.fetch(sql, *args)

    async def execute(self, sql: str, *args):
        return await self.conn.execute(sql, *args)

    def acquire(self) -> '_FakeAcquire':
        return _FakeAcquire(self.conn)


class _FakeAcquire:
    def __init__(self, conn: _FakeConnection) -> None:
        self.conn = conn

    async def __aenter__(self) -> _FakeConnection:
        return self.conn

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def _event_row(event_type: str, key: dict, payload: dict, ts: datetime = TS) -> dict:
    return {
        'event_type': event_type,
        'event_key': key,
        'event_payload': payload,
        'event_timestamp': ts,
        'source_record_hash': SRC,
    }


# ---------------------------------------------------------------------------
# build_export_payload / payload_bytes — exact shape and byte determinism
# ---------------------------------------------------------------------------

def test_build_export_payload_exact_shape():
    batch_id = str(uuid.uuid4())
    observations = [
        {'observation_id': str(uuid.uuid4()), 'observation_type': 'Scan'},
    ]
    payload = build_export_payload(
        export_batch_id=batch_id,
        lineage_token='tok-1',
        consent_version='1.0',
        generated_at='2026-08-28T12:00:00Z',
        observations=observations,
    )
    assert payload['schema'] == EXPORT_SCHEMA == 'ed-finder-cre-journal-observation-export'
    assert payload['schema_version'] == EXPORT_SCHEMA_VERSION == '1.0.0'
    assert payload['export_batch_id'] == batch_id
    assert payload['lineage_token'] == 'tok-1'
    assert payload['consent_version'] == '1.0'
    assert payload['sanitized_contract_version'] == '1.0.0'
    assert payload['generated_at'] == '2026-08-28T12:00:00Z'
    assert payload['manifest'] == {
        'observation_count': 1,
        'contributing_accounts_attested': 1,
        'attestation_note': ATTESTATION_NOTE,
    }
    assert payload['observations'] == observations


def test_payload_bytes_is_deterministic_across_builds():
    kwargs = dict(
        export_batch_id=str(uuid.uuid4()),
        lineage_token='tok-1',
        consent_version='1.0',
        generated_at='2026-08-28T12:00:00Z',
    )
    # The observations list itself is order-significant (it is an array);
    # determinism means: same list content + same element dicts built in any
    # key-insertion order -> identical bytes.
    obs_a = [
        {'observation_id': 'id-2', 'observation_type': 'Scan', 'observed_week': '2026-W35'},
        {'observation_id': 'id-1', 'observation_type': 'ScanOrganic', 'genus': '$Genus_Foo;'},
    ]
    obs_b = [
        {'observed_week': '2026-W35', 'observation_type': 'Scan', 'observation_id': 'id-2'},
        {'genus': '$Genus_Foo;', 'observation_type': 'ScanOrganic', 'observation_id': 'id-1'},
    ]
    payload_a = build_export_payload(observations=obs_a, **kwargs)
    payload_b = build_export_payload(observations=obs_b, **kwargs)
    assert payload_a == payload_b
    assert payload_bytes(payload_a) == payload_bytes(payload_b)
    assert isinstance(payload_bytes(payload_a), bytes)


def test_payload_bytes_is_compact_sorted_json():
    kwargs = dict(
        export_batch_id=str(uuid.uuid4()),
        lineage_token='tok-1',
        consent_version='1.0',
        generated_at='2026-08-28T12:00:00Z',
        observations=[{'b': 2, 'a': 1}],
    )
    payload = build_export_payload(**kwargs)
    expected = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    assert payload_bytes(payload) == expected
    assert json.loads(payload_bytes(payload)) == payload


# ---------------------------------------------------------------------------
# build_export — payload/sha/receipt consistency against a fake pool
# ---------------------------------------------------------------------------

def test_build_export_payload_sha_receipt_consistent():
    pool = _FakePool(rows=[
        # Excluded travel event must be dropped from the export.
        _event_row('FSDJump', {'SystemAddress': 7, 'EventTimestamp': '2026-01-01T00:00:00Z'}, {}),
        _event_row('Scan', {'SystemAddress': 12345, 'BodyID': 3}, {'StarSystem': 'Sol', 'BodyName': 'Earth'}),
    ])
    payload, sha_hex, receipt = asyncio.run(build_export(pool, ACCOUNT_ID, limit=1000))
    # sha is the sha256 of the exact payload bytes.
    assert sha_hex == hashlib.sha256(payload_bytes(payload)).hexdigest()
    assert receipt['payload_sha256'] == sha_hex
    assert receipt['export_batch_id'] == payload['export_batch_id']
    assert receipt['observation_count'] == 1
    assert receipt['batch_state'] == 'CREATED'
    assert receipt['consent_version'] == '1.0'
    assert receipt['sanitized_contract_version'] == '1.0.0'
    assert LINEAGE_RE.fullmatch(receipt['lineage_token'])
    assert payload['lineage_token'] == receipt['lineage_token']
    assert payload['manifest']['observation_count'] == 1
    assert payload['manifest']['contributing_accounts_attested'] == 1
    assert payload['observations'][0]['observation_type'] == 'Scan'
    assert payload['observations'][0]['evidence_quality'] == 'OBSERVED_PERSONAL'
    assert payload['observations'][0]['observed_week'] == '2026-W35'
    assert payload['observations'][0]['source_event_sha256'] == 'ab' * 32
    # Receipt insert carries the sha256 as bytea bytes.
    assert pool.conn.receipt_rows and pool.conn.receipt_rows[0]['payload_sha256'] == bytes.fromhex(sha_hex)


def test_build_export_orders_observations_deterministically():
    # Rows are returned in arbitrary order; the export must order them by
    # (event_type, canonical key json, event_timestamp).
    rows = [
        _event_row('Scan', {'SystemAddress': 2, 'BodyID': 1}, {'StarSystem': 'B'}, ts=TS),
        _event_row('Scan', {'SystemAddress': 1, 'BodyID': 1}, {'StarSystem': 'A'}, ts=TS),
        _event_row('CodexEntry', {'SystemAddress': 1, 'BodyID': 1, 'EntryID': 'E1'}, {'StarSystem': 'A'}, ts=TS),
    ]
    pool = _FakePool(rows=rows)
    payload, _sha, _receipt = asyncio.run(build_export(pool, ACCOUNT_ID, limit=1000))
    types = [o['observation_type'] for o in payload['observations']]
    # CodexEntry < Scan alphabetically; within Scan, system_id64 1 before 2.
    assert types == ['CodexEntry', 'Scan', 'Scan']
    assert payload['observations'][1]['system_id64'] == '1'
    assert payload['observations'][2]['system_id64'] == '2'


def test_build_export_respects_limit():
    pool = _FakePool(rows=[
        _event_row('Scan', {'SystemAddress': 1}, {'StarSystem': 'A'}),
        _event_row('Scan', {'SystemAddress': 2}, {'StarSystem': 'B'}),
    ])
    payload, _sha, receipt = asyncio.run(build_export(pool, ACCOUNT_ID, limit=1))
    assert len(payload['observations']) == 1
    assert receipt['observation_count'] == 1


def test_build_export_sql_is_account_scoped():
    pool = _FakePool(rows=[])
    asyncio.run(build_export(pool, ACCOUNT_ID, limit=1000))
    fetch_sql = next(sql for kind, sql, _args in pool.conn.calls if kind == 'fetch')
    assert 'owner_account_id' in fetch_sql and '$1' in fetch_sql
    insert_sql = next(sql for kind, sql, _args in pool.conn.calls if kind == 'execute')
    assert 'research_export_batch' in insert_sql


def test_build_export_binds_created_at_as_datetime():
    # Backend fix wave: timestamptz columns are bound as tz-aware datetime
    # objects, never ISO strings. generated_at (payload) stays the
    # second-precision Z string derived from the SAME instant, so receipt
    # created_at == generated_at (replay contract).
    pool = _FakePool(rows=[
        _event_row('Scan', {'SystemAddress': 1, 'BodyID': 3}, {'StarSystem': 'Sol'}),
    ])
    payload, _sha, receipt = asyncio.run(build_export(pool, ACCOUNT_ID, limit=1000))
    insert_args = next(
        args for kind, sql, args in pool.conn.calls
        if kind == 'execute' and 'INSERT' in sql
    )
    created_at_arg = insert_args[10]  # _EXPORT_BATCH_COLUMNS order: created_at last
    assert isinstance(created_at_arg, datetime), type(created_at_arg)
    assert created_at_arg.tzinfo is not None
    assert isinstance(receipt['created_at'], datetime)
    # generated_at is the same instant, second-precision UTC with 'Z'.
    assert payload['generated_at'] == (
        created_at_arg.astimezone(timezone.utc)
        .isoformat(timespec='seconds').replace('+00:00', 'Z')
    )


def test_receipt_manifest_persists_limit_payload_manifest_does_not():
    # Backend fix wave: the raw-row limit is receipt-internal replay
    # metadata (manifest.limit in the RECEIPT's manifest column) — the
    # CRE-visible payload manifest stays schema-frozen (the consumer schema
    # enforces additionalProperties: false).
    pool = _FakePool(rows=[
        _event_row('Scan', {'SystemAddress': 1, 'BodyID': 3}, {'StarSystem': 'Sol'}),
        _event_row('Scan', {'SystemAddress': 2, 'BodyID': 3}, {'StarSystem': 'Beta'}),
    ])
    payload, _sha, receipt = asyncio.run(build_export(pool, ACCOUNT_ID, limit=1))
    assert 'limit' not in payload['manifest']
    assert receipt['observation_count'] == 1
    assert receipt['manifest']['limit'] == 1
    assert receipt['manifest']['observation_count'] == 1
    # The INSERTed receipt manifest is the limit-carrying one (JSON text).
    insert_args = next(
        args for kind, sql, args in pool.conn.calls
        if kind == 'execute' and 'INSERT' in sql
    )
    # Bound as a dict (the app pool's jsonb codec encodes dicts to jsonb
    # objects; pre-encoded text would become a jsonb string).
    stored_manifest = insert_args[6]
    assert stored_manifest['limit'] == 1


# ---------------------------------------------------------------------------
# supersede_lineage_batches — supersede-not-delete on consent withdrawal
# ---------------------------------------------------------------------------

def test_supersede_marks_batches_and_emits_payload():
    batch_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    pool = _FakePool(rows=[
        {'export_batch_id': batch_ids[0], 'lineage_token': 'tok-1', 'created_at': TS},
        {'export_batch_id': batch_ids[1], 'lineage_token': 'tok-1', 'created_at': TS},
    ])
    payload = asyncio.run(supersede_lineage_batches(pool, ACCOUNT_ID, 'tok-1'))
    assert payload['schema'] == EXPORT_SCHEMA
    assert payload['schema_version'] == EXPORT_SCHEMA_VERSION
    assert payload['kind'] == 'supersede'
    assert payload['lineage_token'] == 'tok-1'
    assert payload['consent_version'] == '1.0'
    assert payload['manifest'] == {'withdrawal': True}
    assert sorted(payload['superseded_export_batch_ids']) == sorted(batch_ids)
    # Superseded batches are referenced by a new ledger row (supersede receipt).
    assert pool.conn.receipt_rows
    supersede_receipt = pool.conn.receipt_rows[0]
    assert supersede_receipt['lineage_token'] == 'tok-1'
    assert supersede_receipt['batch_state'] == 'SUPERSEDED'
    assert supersede_receipt['observation_count'] == 0
    # jsonb column is passed as JSON text to the DB (asyncpg convention).
    assert supersede_receipt['manifest'] == {'withdrawal': True}
    # The UPDATE marks the old batches SUPERSEDED, pointing at the new receipt.
    update_sql = next(sql for kind, sql, _args in pool.conn.calls if kind == 'execute' and 'UPDATE' in sql)
    assert 'SUPERSEDED' in update_sql and 'superseded_by_batch_id' in update_sql
    update_args = next(args for kind, sql, args in pool.conn.calls if kind == 'execute' and 'UPDATE' in sql)
    # $1 = account_id, $2 = lineage_token, $3 = superseded_by_batch_id.
    assert update_args[0] == ACCOUNT_ID and update_args[1] == 'tok-1'
    assert update_args[2] == supersede_receipt['export_batch_id']


def test_supersede_payload_sha_matches_receipt_bytes():
    batch_ids = [str(uuid.uuid4())]
    pool = _FakePool(rows=[
        {'export_batch_id': batch_ids[0], 'lineage_token': 'tok-1', 'created_at': TS},
    ])
    payload = asyncio.run(supersede_lineage_batches(pool, ACCOUNT_ID, 'tok-1'))
    sha = hashlib.sha256(payload_bytes(payload)).hexdigest()
    assert pool.conn.receipt_rows[0]['payload_sha256'] == bytes.fromhex(sha)


def test_supersede_with_no_batches_emits_empty_payload_no_receipt():
    pool = _FakePool(rows=[])
    payload = asyncio.run(supersede_lineage_batches(pool, ACCOUNT_ID, 'tok-1'))
    assert payload['kind'] == 'supersede'
    assert payload['superseded_export_batch_ids'] == []
    assert pool.conn.receipt_rows == []
    # Only the fetch ran — no UPDATE, no INSERT.
    assert all(kind == 'fetch' for kind, _sql, _args in pool.conn.calls)


def test_supersede_only_touches_created_batches_for_account_and_token():
    # A batch of another lineage token must be untouched by the UPDATE.
    pool = _FakePool(rows=[
        {'export_batch_id': str(uuid.uuid4()), 'lineage_token': 'tok-1', 'created_at': TS},
        {'export_batch_id': str(uuid.uuid4()), 'lineage_token': 'other-tok', 'created_at': TS},
    ])
    asyncio.run(supersede_lineage_batches(pool, ACCOUNT_ID, 'tok-1'))
    update_calls = [(sql, args) for kind, sql, args in pool.conn.calls if kind == 'execute' and 'UPDATE' in sql]
    assert len(update_calls) == 1
    sql, args = update_calls[0]
    assert 'owner_account_id' in sql and 'lineage_token' in sql and "batch_state = 'CREATED'" in sql
    # $1 = account_id, $2 = lineage_token.
    assert args[0] == ACCOUNT_ID and args[1] == 'tok-1'
