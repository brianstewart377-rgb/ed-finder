from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

import asyncpg

from journal_import.api_models import (
    JournalImportFileRef,
    JournalImportReceipt,
    JournalImportRequest,
    JournalImportSummary,
)


def _json_dumps(value: object) -> str:
    return json.dumps(value, separators=(',', ':'), sort_keys=True)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dt_to_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _git_sha() -> str:
    raw = os.getenv('GIT_COMMIT_SHA') or os.getenv('RAILWAY_GIT_COMMIT_SHA') or 'unknown'
    raw = raw.strip()
    return raw[:40] if raw else 'unknown'


def _build_file_refs(files: list[dict[str, object]]) -> list[JournalImportFileRef]:
    refs: list[JournalImportFileRef] = []
    for item in files:
        refs.append(
            JournalImportFileRef(
                name=str(item.get('name') or ''),
                event_count=int(item.get('event_count') or 0),
            ),
        )
    return refs


async def import_journal_batch(
    pool: asyncpg.Pool,
    request: JournalImportRequest,
) -> JournalImportReceipt:
    run_key = f'jrnl-{_utc_now().strftime("%Y%m%d%H%M%S")}-{uuid4().hex[:8]}'
    started_at = _utc_now()
    started_perf = perf_counter()
    event_counts = Counter(observation.event_type for observation in request.observations)
    rows_read = len(request.observations)
    rows_staged = 0
    rows_skipped = 0

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                '''
                INSERT INTO source_runs (
                    source_run_key,
                    source_name,
                    source_category,
                    domain,
                    import_scope,
                    status,
                    source_manifest_sha256,
                    started_at,
                    git_commit_sha,
                    importer_name,
                    importer_version,
                    trigger_context,
                    rows_read,
                    rows_staged,
                    rows_rejected,
                    rows_skipped,
                    safety_boundary,
                    metadata
                ) VALUES (
                    $1, 'frontier_journal', 'source_of_evidence', 'systems', 'staging_only',
                    'running', NULL, $2, $3, 'frontend_journal_import', 'a1', 'user_upload',
                    $4, 0, 0, 0, $5::jsonb, $6::jsonb
                )
                ''',
                run_key,
                started_at,
                _git_sha(),
                rows_read,
                _json_dumps({
                    'privacy_strip_before_network': True,
                    'canonical_write_path_opened': False,
                    'allowlisted_client_parse': True,
                }),
                _json_dumps({
                    'parser_version': request.client_manifest.parser_version,
                    'files': [item.model_dump(mode='json') for item in request.client_manifest.files],
                    'event_counts': dict(event_counts),
                }),
            )

            for observation in request.observations:
                inserted = await conn.fetchrow(
                    '''
                    INSERT INTO journal_import_staging (
                        source_run_key,
                        source_file_name,
                        source_record_hash,
                        event_type,
                        system_id64,
                        system_name,
                        subject_type,
                        subject_id,
                        observed_at,
                        summary,
                        payload_json,
                        privacy_boundary
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9::timestamptz, $10, $11::jsonb, $12::jsonb
                    )
                    ON CONFLICT (source_record_hash) DO NOTHING
                    RETURNING source_record_hash
                    ''',
                    run_key,
                    observation.source_file,
                    observation.observation_key,
                    observation.event_type,
                    observation.system_id64,
                    observation.system_name,
                    observation.subject_type,
                    observation.subject_id,
                    observation.observed_at,
                    observation.summary,
                    _json_dumps(observation.payload),
                    _json_dumps(observation.privacy_boundary),
                )
                if inserted is None:
                    rows_skipped += 1
                    continue

                rows_staged += 1
                observation_id = f'obs_{uuid4().hex}'
                evidence_key = f'evd_{uuid4().hex}'
                observed_value = {
                    'event_type': observation.event_type,
                    'summary': observation.summary,
                    'payload': observation.payload,
                }
                metadata = {
                    'source_name': 'frontier_journal',
                    'source_run_key': run_key,
                    'source_file': observation.source_file,
                    'observation_key': observation.observation_key,
                }

                await conn.execute(
                    '''
                    INSERT INTO observed_facts (
                        observation_id, system_id64, area, source, source_type, fact_type,
                        subject_type, subject_id, status, observed_value, observed_value_json,
                        expected_value_json, confidence, notes, build_fingerprint,
                        simulation_fingerprint, target_archetype, facility_template_id,
                        facility_id, local_body_id, body_id, service_id, economy, tags_json,
                        metadata_json, created_at
                    ) VALUES (
                        $1, $2, 'note', 'imported', 'journal_upload', 'note',
                        $3, $4, 'unverified', $5::jsonb, $5::jsonb,
                        'null'::jsonb, 'medium', $6, NULL,
                        NULL, NULL, NULL,
                        NULL, NULL, NULL, NULL, NULL, $7::jsonb,
                        $8::jsonb, NOW()
                    )
                    ''',
                    observation_id,
                    observation.system_id64,
                    observation.subject_type,
                    observation.subject_id,
                    _json_dumps(observed_value),
                    observation.summary,
                    _json_dumps(['frontier_journal', observation.event_type]),
                    _json_dumps(metadata),
                )

                await conn.execute(
                    '''
                    INSERT INTO evidence_records (
                        evidence_key,
                        system_id64,
                        source_name,
                        origin,
                        subject_type,
                        subject_id,
                        evidence_type,
                        record_status,
                        freshness_status,
                        confidence,
                        summary,
                        source_record_id,
                        source_run_key,
                        observed_at,
                        collected_at,
                        expires_at,
                        value_json,
                        provenance_json,
                        tags_json,
                        metadata_json
                    ) VALUES (
                        $1, $2, 'frontier_journal', 'imported', $3, $4, 'journal_observation',
                        'active', 'current', 'medium', $5, $6, $7, $8::timestamptz, NOW(), NULL,
                        $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb
                    )
                    ''',
                    evidence_key,
                    observation.system_id64,
                    observation.subject_type,
                    observation.subject_id,
                    observation.summary,
                    observation.observation_key,
                    run_key,
                    observation.observed_at,
                    _json_dumps(observed_value),
                    _json_dumps({
                        'source_file': observation.source_file,
                        'parser_version': request.client_manifest.parser_version,
                        'privacy_boundary': observation.privacy_boundary,
                    }),
                    _json_dumps(['frontier_journal', observation.event_type]),
                    _json_dumps(metadata),
                )

            duration_ms = int((perf_counter() - started_perf) * 1000)
            await conn.execute(
                '''
                UPDATE source_runs
                SET
                    status = 'succeeded',
                    finished_at = NOW(),
                    duration_ms = $2,
                    rows_read = $3,
                    rows_staged = $4,
                    rows_skipped = $5,
                    updated_at = NOW(),
                    metadata = metadata || $6::jsonb
                WHERE source_run_key = $1
                ''',
                run_key,
                duration_ms,
                rows_read,
                rows_staged,
                rows_skipped,
                _json_dumps({
                    'summary': {
                        'observations_received': rows_read,
                        'observations_staged': rows_staged,
                        'duplicates_skipped': rows_skipped,
                        'conflicts_flagged': 0,
                        'files_seen': len(request.client_manifest.files),
                        'event_counts': dict(event_counts),
                    },
                }),
            )

    return JournalImportReceipt(
        run_key=run_key,
        status='succeeded',
        parser_version=request.client_manifest.parser_version,
        started_at=_dt_to_str(started_at),
        finished_at=_dt_to_str(_utc_now()),
        files=request.client_manifest.files,
        summary=JournalImportSummary(
            observations_received=rows_read,
            observations_staged=rows_staged,
            duplicates_skipped=rows_skipped,
            conflicts_flagged=0,
            files_seen=len(request.client_manifest.files),
            event_counts=dict(event_counts),
        ),
    )


async def get_journal_import_receipt(
    pool: asyncpg.Pool,
    run_key: str,
) -> JournalImportReceipt | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''
            SELECT
                source_run_key,
                status,
                started_at,
                finished_at,
                metadata,
                rows_read,
                rows_staged,
                rows_skipped
            FROM source_runs
            WHERE source_run_key = $1
              AND source_name = 'frontier_journal'
            ''',
            run_key,
        )
    if row is None:
        return None

    metadata = dict(row['metadata'] or {})
    summary = dict(metadata.get('summary') or {})
    return JournalImportReceipt(
        run_key=str(row['source_run_key']),
        status=str(row['status']),
        parser_version=str(metadata.get('parser_version') or 'unknown'),
        started_at=_dt_to_str(row['started_at']),
        finished_at=_dt_to_str(row['finished_at']),
        files=_build_file_refs(list(metadata.get('files') or [])),
        summary=JournalImportSummary(
            observations_received=int(summary.get('observations_received') or row['rows_read'] or 0),
            observations_staged=int(summary.get('observations_staged') or row['rows_staged'] or 0),
            duplicates_skipped=int(summary.get('duplicates_skipped') or row['rows_skipped'] or 0),
            conflicts_flagged=int(summary.get('conflicts_flagged') or 0),
            files_seen=int(summary.get('files_seen') or len(metadata.get('files') or [])),
            event_counts=dict(summary.get('event_counts') or {}),
        ),
    )
