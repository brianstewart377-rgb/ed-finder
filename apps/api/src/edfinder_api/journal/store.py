"""Account-scoped V3 journal import store.

Single-transaction ingestion of normalized allowlisted journal events into
the ``v3_private`` journal lane: acquisition-ledger bootstrap (source,
rights policy, artifacts, run with deterministic idempotency key), a
``private_import`` receipt row, file-level dedupe by content hash, and
event-level semantic dedupe on ``(owner_account_id, event_type, event_key)``.
All SQL is parameterized; values are never interpolated.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone

import asyncpg

from edfinder_api.journal.event_contract import strip_payload
from edfinder_api.journal.identity import event_identity

MAX_DAILY_EVENTS_PER_ACCOUNT = 200_000

# Level-2 event inserts are chunked parallel-array ``unnest`` statements
# (the adjudicated perf fix: per-event INSERT measured 125-272 events/s;
# batched inserts clear the >= 2,000/s floor). Chunk size bounded so one
# statement stays well under parameter-count and work-memory limits.
EVENT_INSERT_CHUNK_SIZE = 5_000

_SOURCE_CODE = 'frontier_journal'
_RIGHTS_POLICY_VERSION = '1.0'
_ARTIFACT_KIND = 'JOURNAL_FILE'
_MEDIA_TYPE = 'text/x-elite-dangerous-journal'
_RETENTION_CLASS = 'PRIVATE_USER_CONTENT'
_NORMALIZER_VERSION = 'v3.0'

# Deterministic placeholders for the ledger's 32-byte sha256 columns; the
# code/config/normalizer identity is the journal store itself (no
# deploy-specific revision is available at runtime).
_IMPORTER_CODE_SHA256 = hashlib.sha256(b'ed-finder-v3-journal-store:code:1').digest()
_IMPORTER_CONFIG_SHA256 = hashlib.sha256(b'ed-finder-v3-journal-store:config:1').digest()
_NORMALIZER_SHA256 = hashlib.sha256(b'ed-finder-v3-journal-identity:v3.0').digest()

# Column order of v3_private.journal_event (mirrors migration 003 DDL).
_EVENT_BATCH_INSERT_SQL = '''
    INSERT INTO v3_private.journal_event (
        journal_event_id, owner_account_id, private_import_id,
        journal_file_id, source_run_id, event_type,
        event_key, event_payload, event_timestamp,
        source_record_hash, source_offset
    )
    SELECT * FROM unnest(
        $1::uuid[], $2::uuid[], $3::uuid[], $4::uuid[], $5::uuid[],
        $6::text[], $7::jsonb[], $8::jsonb[], $9::timestamptz[],
        $10::bytea[], $11::bigint[]
    )
    ON CONFLICT (owner_account_id, event_type, event_key) DO NOTHING
'''


async def _insert_event_chunk(
    conn: asyncpg.Connection,
    *,
    chunk: list[dict],
) -> int:
    """One chunked batched event insert; returns the inserted rowcount.

    ``chunk`` entries carry the fully prepared values (stripped payload,
    canonical event_key, 32-byte hash, tz-aware timestamp). event_key and
    event_payload are bound as DICTS, not pre-encoded JSON text: the app's
    pool registers a jsonb codec with ``encoder=json.dumps`` (main.py
    ``_init_conn``), which re-encodes a Python str as a JSON string scalar
    (``jsonb_typeof = 'string'`` -> CHECK violation); dicts encode to proper
    jsonb objects under either codec regime. The command tag ('INSERT 0 N')
    yields the inserted count — ON CONFLICT DO NOTHING rows are excluded
    from N.
    """
    tag = await conn.execute(
        _EVENT_BATCH_INSERT_SQL,
        [row['journal_event_id'] for row in chunk],
        [row['owner_account_id'] for row in chunk],
        [row['private_import_id'] for row in chunk],
        [row['journal_file_id'] for row in chunk],
        [row['source_run_id'] for row in chunk],
        [row['event_type'] for row in chunk],
        [row['event_key'] for row in chunk],
        [row['event_payload'] for row in chunk],
        [row['event_timestamp'] for row in chunk],
        [row['source_record_hash'] for row in chunk],
        [row['source_offset'] for row in chunk],
    )
    return int(tag.rsplit(' ', 1)[-1])


class JournalQuotaExceededError(RuntimeError):
    """Raised when the daily per-account event cap would be exceeded."""


@dataclass(frozen=True)
class ImportCounts:
    files_received: int
    files_skipped: int
    files_admitted: int
    events_received: int
    events_inserted: int
    duplicates_skipped: int
    privacy_stripped_fields: int
    event_counts: dict[str, int]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_ts(value: object, *, required: bool = False) -> datetime | None:
    if value is None:
        if required:
            raise ValueError('event_timestamp is required')
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime):
        raise ValueError(f'expected an ISO-8601 timestamp, got {value!r}')
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hash_bytes(value: object, *, field: str) -> bytes:
    """Accept 32-byte bytes or 64-char hex; return 32 raw bytes."""
    if isinstance(value, bytes):
        if len(value) != 32:
            raise ValueError(f'{field} must be a 32-byte sha256, got {len(value)} bytes')
        return value
    text = str(value).strip().lower()
    if len(text) != 64:
        raise ValueError(f'{field} must be a 64-char hex sha256, got {len(text)} chars')
    try:
        return bytes.fromhex(text)
    except ValueError as exc:
        raise ValueError(f'{field} must be hex, got {value!r}') from exc


def _idempotency_key(account_id: uuid.UUID, parser_version: str, files: list[dict]) -> str:
    """Deterministic run identity: account | parser | sorted file hashes."""
    content_hashes = sorted(str(item.get('content_sha256') or '').strip().lower() for item in files)
    canonical = f'{account_id}|{parser_version}|{"|".join(content_hashes)}'
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


async def import_journal_batch(
    pool: asyncpg.Pool,
    *,
    account_id: uuid.UUID,
    commander_id: uuid.UUID | None = None,
    parser_version: str,
    files: list[dict],
    events: list[dict],
) -> tuple[uuid.UUID, ImportCounts]:
    """Import one journal batch for one account in a single transaction.

    ``files``: ``[{name, content_sha256(hex), size_bytes, line_count,
    event_count, first_event_at?, last_event_at?}]``
    ``events``: ``[{event_type, event_timestamp(tz-aware), source_record_hash(hex),
    source_file, source_offset, payload}]`` — events whose ``source_file``
    maps to a skipped (already-known-content) file are not processed.

    Returns ``(private_import_id, counts)``. Raises
    ``JournalQuotaExceededError`` when the daily per-account event cap would
    be exceeded (the router maps it to 429).
    """
    received_files = len(files)
    received_events = len(events)
    event_counts = Counter(str(item.get('event_type') or '') for item in events)
    private_import_id = uuid.uuid4()
    counts = ImportCounts(
        files_received=received_files,
        files_skipped=0,
        files_admitted=0,
        events_received=received_events,
        events_inserted=0,
        duplicates_skipped=0,
        privacy_stripped_fields=0,
        event_counts=dict(event_counts),
    )
    started_at = _utc_now()

    async with pool.acquire() as conn:
        async with conn.transaction():
            stored_today = int(await conn.fetchval(
                '''
                SELECT count(*)
                  FROM v3_private.journal_event
                 WHERE owner_account_id = $1
                   AND created_at >= date_trunc('day', now())
                ''',
                account_id,
            ) or 0)
            if stored_today + received_events > MAX_DAILY_EVENTS_PER_ACCOUNT:
                raise JournalQuotaExceededError(
                    f'Journal import quota exceeded for account {account_id}: '
                    f'{stored_today + received_events:,} events today '
                    f'(limit {MAX_DAILY_EVENTS_PER_ACCOUNT:,}).'
                )

            # (1) Acquisition-ledger bootstrap: source identity.
            source_row = await conn.fetchrow(
                '''
                SELECT source_id
                  FROM v3_source.source
                 WHERE source_code = $1
                ''',
                _SOURCE_CODE,
            )
            if source_row is None:
                source_row = await conn.fetchrow(
                    '''
                    INSERT INTO v3_source.source (
                        source_code, display_name, authority_class
                    ) VALUES (
                        $1, $2, 'FRONTIER_DIRECT'
                    )
                    ON CONFLICT (source_code) DO NOTHING
                    RETURNING source_id
                    ''',
                    _SOURCE_CODE,
                    'Frontier Elite Dangerous Journal',
                )
            if source_row is None:
                source_row = await conn.fetchrow(
                    '''
                    SELECT source_id
                      FROM v3_source.source
                     WHERE source_code = $1
                    ''',
                    _SOURCE_CODE,
                )
            source_id = source_row['source_id']

            # (1b) Rights policy bootstrap (private-only acquisition posture).
            rights_row = await conn.fetchrow(
                '''
                INSERT INTO v3_source.source_rights_policy (
                    source_id, policy_version, rights_class,
                    retention_class, distribution_allowed, effective_at
                ) VALUES (
                    $1, $2, 'PRIVATE_ONLY', $3, false, $4
                )
                ON CONFLICT (source_id, policy_version) DO NOTHING
                RETURNING rights_policy_id
                ''',
                source_id,
                _RIGHTS_POLICY_VERSION,
                _RETENTION_CLASS,
                started_at,
            )
            if rights_row is None:
                rights_row = await conn.fetchrow(
                    '''
                    SELECT rights_policy_id
                      FROM v3_source.source_rights_policy
                     WHERE source_id = $1 AND policy_version = $2
                    ''',
                    source_id,
                    _RIGHTS_POLICY_VERSION,
                )
            rights_policy_id = rights_row['rights_policy_id']

            # (1c) Owner commander: only with an active access edge.
            owner_commander_id = None
            if commander_id is not None:
                edge = await conn.fetchrow(
                    '''
                    SELECT commander_id
                      FROM v3_identity.account_commander_access
                     WHERE account_id = $1 AND commander_id = $2
                       AND revoked_at IS NULL
                     LIMIT 1
                    ''',
                    account_id,
                    commander_id,
                )
                if edge is not None:
                    owner_commander_id = commander_id
            if owner_commander_id is None:
                owner_edge = await conn.fetchrow(
                    '''
                    SELECT commander_id
                      FROM v3_identity.account_commander_access
                     WHERE account_id = $1 AND revoked_at IS NULL
                       AND access_role = 'OWNER'
                     ORDER BY granted_at DESC
                     LIMIT 1
                    ''',
                    account_id,
                )
                if owner_edge is not None:
                    owner_commander_id = owner_edge['commander_id']

            # (2) Immutable content-addressed artifacts (shared across
            # accounts by design: content hash only, no personal data).
            for item in files:
                content_sha = _hash_bytes(item.get('content_sha256'), field='content_sha256')
                artifact_row = await conn.fetchrow(
                    '''
                    INSERT INTO v3_source.source_artifact (
                        artifact_id, source_id, rights_policy_id,
                        artifact_kind, content_sha256, size_bytes,
                        media_type, retrieved_at, retention_class
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9
                    )
                    ON CONFLICT (source_id, content_sha256) DO NOTHING
                    RETURNING artifact_id
                    ''',
                    uuid.uuid4(),
                    source_id,
                    rights_policy_id,
                    _ARTIFACT_KIND,
                    content_sha,
                    int(item.get('size_bytes') or 0),
                    _MEDIA_TYPE,
                    started_at,
                    _RETENTION_CLASS,
                )
                if artifact_row is None:
                    await conn.fetchrow(
                        '''
                        SELECT artifact_id
                          FROM v3_source.source_artifact
                         WHERE source_id = $1 AND content_sha256 = $2
                        ''',
                        source_id,
                        content_sha,
                    )

            # (3) Source run with deterministic idempotency key: a retry of
            # the same (account, parser, files) links by stable identity.
            idempotency_key = _idempotency_key(account_id, parser_version, files)
            run_row = await conn.fetchrow(
                '''
                INSERT INTO v3_source.source_run (
                    source_run_id, source_id, rights_policy_id,
                    acquisition_kind, trust_zone, run_state,
                    idempotency_key, started_at, completed_at,
                    importer_version, importer_code_sha256,
                    importer_config_sha256, normalizer_version,
                    normalizer_sha256
                ) VALUES (
                    $1, $2, $3,
                    'JOURNAL_IMPORT', 'PRIVATE', 'SUCCEEDED',
                    $4, $5, $5,
                    $6, $7,
                    $8, $9,
                    $10
                )
                ON CONFLICT (source_id, idempotency_key) DO NOTHING
                RETURNING source_run_id
                ''',
                uuid.uuid4(),
                source_id,
                rights_policy_id,
                idempotency_key,
                started_at,
                parser_version,
                _IMPORTER_CODE_SHA256,
                _IMPORTER_CONFIG_SHA256,
                _NORMALIZER_VERSION,
                _NORMALIZER_SHA256,
            )
            if run_row is None:
                run_row = await conn.fetchrow(
                    '''
                    SELECT source_run_id
                      FROM v3_source.source_run
                     WHERE source_id = $1 AND idempotency_key = $2
                    ''',
                    source_id,
                    idempotency_key,
                )
            source_run_id = run_row['source_run_id']

            # (4) The account-owned import receipt row.
            await conn.fetchrow(
                '''
                INSERT INTO v3_private.private_import (
                    private_import_id, owner_account_id, owner_commander_id,
                    source_run_id, import_kind, import_state
                ) VALUES (
                    $1, $2, $3, $4, 'journal_import_v1', 'READY'
                )
                RETURNING private_import_id
                ''',
                private_import_id,
                account_id,
                owner_commander_id,
                source_run_id,
            )

            # (5) Per-file admission: content hash is the level-1 dedupe key.
            # admitted_file_ids keys on content_sha256 (NOT the file name):
            # two same-named files in one request then attribute their
            # events to the correct journal_import_file row (the review's
            # provenance fix — name-keying was last-wins).
            admitted_file_ids: dict[bytes, uuid.UUID] = {}
            for item in files:
                content_sha = _hash_bytes(item.get('content_sha256'), field='content_sha256')
                file_row = await conn.fetchrow(
                    '''
                    INSERT INTO v3_private.journal_import_file (
                        journal_file_id, private_import_id, owner_account_id,
                        file_name, content_sha256, size_bytes,
                        line_count, event_count,
                        first_event_at, last_event_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6,
                        $7, $8,
                        $9, $10
                    )
                    ON CONFLICT (owner_account_id, content_sha256) DO NOTHING
                    RETURNING journal_file_id
                    ''',
                    uuid.uuid4(),
                    private_import_id,
                    account_id,
                    str(item.get('name') or ''),
                    content_sha,
                    int(item.get('size_bytes') or 0),
                    int(item.get('line_count') or 0),
                    int(item.get('event_count') or 0),
                    _normalize_ts(item.get('first_event_at')),
                    _normalize_ts(item.get('last_event_at')),
                )
                if file_row is None:
                    counts = replace(counts, files_skipped=counts.files_skipped + 1)
                else:
                    counts = replace(counts, files_admitted=counts.files_admitted + 1)
                    admitted_file_ids[content_sha] = file_row['journal_file_id']
            # Events carry only the source FILE NAME, so a name -> content
            # sha map bridges the two key spaces (names unique in practice;
            # content sha is the ambiguity-free admission key).
            file_sha_by_name = {
                str(item.get('name') or ''): _hash_bytes(
                    item.get('content_sha256'), field='content_sha256',
                )
                for item in files
            }

            # (6) Per event: server re-strip (defense-in-depth), semantic
            # identity, then chunked batched inserts on the level-2 dedupe
            # key (ON CONFLICT DO NOTHING inside each chunk).
            prepared: list[dict] = []
            for event in events:
                content_sha = file_sha_by_name.get(str(event.get('source_file') or ''))
                journal_file_id = (
                    admitted_file_ids.get(content_sha)
                    if content_sha is not None else None
                )
                if journal_file_id is None:
                    # Events from skipped/unknown files are not processed.
                    continue
                event_type = str(event['event_type'])
                payload = dict(event.get('payload') or {})
                stripped, n_removed = strip_payload(event_type, payload)
                record_hash = _hash_bytes(
                    event.get('source_record_hash'), field='source_record_hash',
                )
                event_key = event_identity(
                    event_type,
                    payload,
                    record_hash,
                    event_timestamp=_normalize_ts(event.get('event_timestamp'), required=True),
                )
                counts = replace(
                    counts,
                    privacy_stripped_fields=counts.privacy_stripped_fields + n_removed,
                )
                prepared.append({
                    'journal_event_id': uuid.uuid4(),
                    'owner_account_id': account_id,
                    'private_import_id': private_import_id,
                    'journal_file_id': journal_file_id,
                    'source_run_id': source_run_id,
                    'event_type': event_type,
                    'event_key': event_key,
                    'event_payload': stripped,
                    'event_timestamp': _normalize_ts(event.get('event_timestamp'), required=True),
                    'source_record_hash': record_hash,
                    'source_offset': int(event.get('source_offset') or 0),
                })

            inserted = 0
            for start in range(0, len(prepared), EVENT_INSERT_CHUNK_SIZE):
                chunk = prepared[start:start + EVENT_INSERT_CHUNK_SIZE]
                inserted += await _insert_event_chunk(conn, chunk=chunk)
            counts = replace(
                counts,
                events_inserted=counts.events_inserted + inserted,
                duplicates_skipped=counts.duplicates_skipped + (len(prepared) - inserted),
            )

    return private_import_id, counts
