from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from evidence_store import store
from evidence_store.api_models import EvidenceRecordCreateRequest


async def test_create_evidence_record_supersedes_prior_active_subject_fact(pool):
    async with pool.acquire() as conn:
        system_id64 = await conn.fetchval('SELECT id64 FROM systems LIMIT 1')

    subject_id = f'system-note-{uuid4().hex}'
    first = await store.create_evidence_record(
        pool,
        EvidenceRecordCreateRequest(
            system_id64=system_id64,
            source_name='manual_operator_source',
            origin='manual',
            subject_type='system',
            subject_id=subject_id,
            evidence_type='operator_note',
            summary='Initial operator note.',
            value={'note': 'first'},
        ),
    )
    second = await store.create_evidence_record(
        pool,
        EvidenceRecordCreateRequest(
            system_id64=system_id64,
            source_name='manual_operator_source',
            origin='manual',
            subject_type='system',
            subject_id=subject_id,
            evidence_type='operator_note',
            summary='Replacement operator note.',
            value={'note': 'second'},
        ),
    )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''
            SELECT evidence_key, record_status, freshness_status, metadata_json
            FROM evidence_records
            WHERE evidence_key = ANY($1::text[])
            ''',
            [first.evidence_key, second.evidence_key],
        )

    by_key = {str(row['evidence_key']): row for row in rows}
    assert by_key[first.evidence_key]['record_status'] == 'superseded'
    assert by_key[first.evidence_key]['freshness_status'] == 'superseded'
    assert by_key[first.evidence_key]['metadata_json']['superseded_by'] == second.evidence_key
    assert by_key[second.evidence_key]['record_status'] == 'active'
    assert by_key[second.evidence_key]['metadata_json']['lifecycle']['superseded_record_count'] == 1


async def test_evidence_record_freshness_sweeper_marks_stale_and_expired_rows(pool):
    async with pool.acquire() as conn:
        system_id64 = await conn.fetchval('SELECT id64 FROM systems LIMIT 1')

    now = datetime.now(timezone.utc)
    stale_subject_id = f'stale-{uuid4().hex}'
    expired_subject_id = f'expired-{uuid4().hex}'

    stale_record = await store.create_evidence_record(
        pool,
        EvidenceRecordCreateRequest(
            system_id64=system_id64,
            source_name='manual_operator_source',
            origin='manual',
            subject_type='system',
            subject_id=stale_subject_id,
            evidence_type='operator_note',
            observed_at=(now - timedelta(days=15)).isoformat(),
            summary='This should age to stale.',
        ),
    )
    expired_record = await store.create_evidence_record(
        pool,
        EvidenceRecordCreateRequest(
            system_id64=system_id64,
            source_name='manual_operator_source',
            origin='manual',
            subject_type='system',
            subject_id=expired_subject_id,
            evidence_type='operator_note',
            observed_at=(now - timedelta(days=25)).isoformat(),
            summary='This should age to expired.',
        ),
    )

    summary = await store.sweep_evidence_record_freshness(
        pool,
        now=now,
        policy_overrides={'operator_note': (10, 20)},
    )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''
            SELECT evidence_key, freshness_status
            FROM evidence_records
            WHERE evidence_key = ANY($1::text[])
            ''',
            [stale_record.evidence_key, expired_record.evidence_key],
        )

    by_key = {str(row['evidence_key']): str(row['freshness_status']) for row in rows}
    assert summary['stale'] >= 1
    assert summary['expired'] >= 1
    assert by_key[stale_record.evidence_key] == 'stale'
    assert by_key[expired_record.evidence_key] == 'expired'


async def test_create_evidence_record_reuses_content_addressed_key_for_replays(pool):
    async with pool.acquire() as conn:
        system_id64 = await conn.fetchval('SELECT id64 FROM systems LIMIT 1')

    subject_id = f'replay-{uuid4().hex}'
    request = EvidenceRecordCreateRequest(
        system_id64=system_id64,
        source_name='manual_operator_source',
        origin='manual',
        subject_type='system',
        subject_id=subject_id,
        evidence_type='operator_note',
        observed_at='2026-07-11T12:34:56Z',
        value={'note': 'stable'},
    )

    first = await store.create_evidence_record(pool, request)
    second = await store.create_evidence_record(pool, request)

    async with pool.acquire() as conn:
        row_count = await conn.fetchval(
            '''
            SELECT COUNT(*)
            FROM evidence_records
            WHERE evidence_key = $1
            ''',
            first.evidence_key,
        )

    assert first.evidence_key == second.evidence_key
    assert row_count == 1
