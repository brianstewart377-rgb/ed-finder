from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Iterable

import asyncpg
from shared_contracts.evidence_identity import (
    coerce_optional_datetime as _coerce_optional_datetime,
    content_addressed_evidence_key as _content_addressed_evidence_key,
    datetime_to_utc_isoformat as _dt_to_str,
)


_CANONICAL_PROMOTION_SOURCE = 'canonical_app_data'
_CANONICAL_PROMOTION_ALLOWED_TYPES = {'body_completeness', 'colonisation_status', 'ring_composition'}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(',', ':'), sort_keys=True)


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value


def _stamp_supersession_metadata(metadata: Mapping[str, Any] | None, superseded_count: int) -> dict[str, Any]:
    stamped = dict(metadata or {})
    lifecycle_value = stamped.get('lifecycle')
    lifecycle = dict(lifecycle_value) if isinstance(lifecycle_value, Mapping) else {}
    lifecycle['superseded_record_count'] = superseded_count
    stamped['lifecycle'] = lifecycle
    return stamped


async def _find_equivalent_active_evidence_record(
    conn: asyncpg.Connection,
    payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        SELECT *
        FROM evidence_records
        WHERE system_id64 = $1
          AND source_name = $2
          AND subject_type = $3
          AND subject_id IS NOT DISTINCT FROM $4
          AND evidence_type = $5
          AND record_status = 'active'
        ORDER BY COALESCE(observed_at, collected_at, created_at) DESC, evidence_key DESC
        LIMIT 1
        """,
        payload['system_id64'],
        payload['source_name'],
        payload['subject_type'],
        payload.get('subject_id'),
        payload['evidence_type'],
    )
    if row is None:
        return None
    same_value = dict(_json_loads(row['value_json'], {})) == dict(payload.get('value') or {})
    same_summary = (row['summary'] or None) == (payload.get('summary') or None)
    same_confidence = str(row['confidence']) == str(payload['confidence'])
    same_origin = str(row['origin']) == str(payload['origin'])
    same_freshness = str(row['freshness_status']) == str(payload['freshness_status'])
    if all((same_value, same_summary, same_confidence, same_origin, same_freshness)):
        return dict(row)
    return None


async def _supersede_active_evidence_records(
    conn: asyncpg.Connection,
    payload: Mapping[str, Any],
    *,
    replacement_key: str,
) -> int:
    if payload.get('record_status') != 'active':
        return 0
    return int(
        await conn.fetchval(
            """
            WITH updated AS (
                UPDATE evidence_records
                   SET record_status = 'superseded',
                       freshness_status = 'superseded',
                       updated_at = now(),
                       metadata_json = COALESCE(metadata_json, '{}'::jsonb) || jsonb_build_object(
                           'superseded_by',
                           $5::text,
                           'superseded_at',
                           to_jsonb(now())
                       )
                 WHERE system_id64 = $1
                   AND subject_type = $2
                   AND subject_id IS NOT DISTINCT FROM $3
                   AND evidence_type = $4
                   AND record_status = 'active'
                RETURNING 1
            )
            SELECT COUNT(*)::int FROM updated
            """,
            payload['system_id64'],
            payload['subject_type'],
            payload.get('subject_id'),
            payload['evidence_type'],
            replacement_key,
        )
        or 0
    )


async def _create_evidence_record_with_conn(
    conn: asyncpg.Connection,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    evidence_key = _content_addressed_evidence_key(payload)
    for attempt in range(2):
        existing_row = await conn.fetchrow(
            """
            SELECT *
            FROM evidence_records
            WHERE evidence_key = $1
            """,
            evidence_key,
        )
        if existing_row is not None:
            return dict(existing_row)

        try:
            superseded_count = await _supersede_active_evidence_records(conn, payload, replacement_key=evidence_key)
            metadata = _stamp_supersession_metadata(payload.get('metadata'), superseded_count)
            row = await conn.fetchrow(
                """
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
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14::timestamptz, $15::timestamptz, $16::timestamptz,
                    $17::jsonb, $18::jsonb, $19::jsonb, $20::jsonb
                )
                ON CONFLICT (evidence_key) DO UPDATE
                    SET updated_at = evidence_records.updated_at
                RETURNING *
                """,
                evidence_key,
                payload['system_id64'],
                payload['source_name'],
                payload['origin'],
                payload['subject_type'],
                payload.get('subject_id'),
                payload['evidence_type'],
                payload['record_status'],
                payload['freshness_status'],
                payload['confidence'],
                payload.get('summary'),
                payload.get('source_record_id'),
                payload.get('source_run_key'),
                _coerce_optional_datetime(payload.get('observed_at')),
                _coerce_optional_datetime(payload.get('collected_at')),
                _coerce_optional_datetime(payload.get('expires_at')),
                payload.get('value') or {},
                payload.get('provenance') or {},
                payload.get('tags') or [],
                metadata,
            )
            return dict(row)
        except asyncpg.exceptions.UniqueViolationError:
            if attempt == 1:
                raise
    raise RuntimeError('eddn canonical evidence insert retry exhausted unexpectedly')


async def promote_canonical_evidence_for_systems(
    conn: asyncpg.Connection,
    *,
    system_ids: Iterable[int],
    evidence_types: list[str],
    source_run_key: str | None = None,
    trigger_context: str | None = None,
) -> dict[str, Any]:
    promoted: list[dict[str, Any]] = []
    warnings: list[str] = []
    deduped_count = 0

    for system_id64 in sorted({int(system_id) for system_id in system_ids if system_id is not None}):
        payloads, payload_warnings = await _build_canonical_evidence_payloads(
            conn,
            system_id64=system_id64,
            evidence_types=evidence_types,
            source_run_key=source_run_key,
            trigger_context=trigger_context,
        )
        warnings.extend(payload_warnings)
        for payload in payloads:
            existing = await _find_equivalent_active_evidence_record(conn, payload)
            if existing is not None:
                deduped_count += 1
                warnings.append(
                    f"{payload['evidence_type']} for system {system_id64} already matches the active canonical evidence record."
                )
                continue
            promoted.append(await _create_evidence_record_with_conn(conn, payload))

    return {
        'records': promoted,
        'warnings': warnings,
        'created_count': len(promoted),
        'deduped_count': deduped_count,
    }


async def _build_canonical_evidence_payloads(
    conn: asyncpg.Connection,
    *,
    system_id64: int,
    evidence_types: list[str],
    source_run_key: str | None = None,
    trigger_context: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    requested = [evidence_type for evidence_type in evidence_types if evidence_type in _CANONICAL_PROMOTION_ALLOWED_TYPES]
    if not requested:
        return [], ['No supported canonical evidence types were requested.']

    system_row = await conn.fetchrow(
        """
        SELECT
            id64,
            name,
            body_count,
            is_colonised,
            is_being_colonised,
            COALESCE(eddn_updated_at, updated_at)::text AS status_updated_at,
            updated_at::text AS updated_at
        FROM systems
        WHERE id64 = $1
        """,
        system_id64,
    )
    if system_row is None:
        raise LookupError(f'System {system_id64} not found')

    payloads: list[dict[str, Any]] = []
    warnings: list[str] = []

    if 'body_completeness' in requested:
        body_payload = await _build_body_completeness_payload(
            conn,
            system_row,
            source_run_key=source_run_key,
            trigger_context=trigger_context,
        )
        if body_payload is None:
            warnings.append('Body completeness could not be promoted because canonical body coverage is still absent.')
        else:
            payloads.append(body_payload)

    if 'colonisation_status' in requested:
        colonisation_payload = _build_colonisation_status_payload(
            system_row,
            source_run_key=source_run_key,
            trigger_context=trigger_context,
        )
        if colonisation_payload is None:
            warnings.append('Colonisation status could not be promoted because canonical status data is still absent.')
        else:
            payloads.append(colonisation_payload)

    if 'ring_composition' in requested:
        ring_payload = await _build_ring_composition_payload(
            conn,
            system_row,
            source_run_key=source_run_key,
            trigger_context=trigger_context,
        )
        if ring_payload is None:
            warnings.append('Ring composition could not be promoted because canonical ring-bearing body data is still absent.')
        else:
            payloads.append(ring_payload)

    return payloads, warnings


async def _build_body_completeness_payload(
    conn: asyncpg.Connection,
    system_row: Mapping[str, Any],
    *,
    source_run_key: str | None = None,
    trigger_context: str | None = None,
) -> dict[str, Any] | None:
    system_id64 = int(system_row['id64'])
    system_name = str(system_row['name'] or system_id64)
    catalogue_body_count = int(system_row['body_count'] or 0)
    system_updated_at = system_row['updated_at']
    body_row_count = int(
        await conn.fetchval('SELECT COUNT(*)::int FROM bodies WHERE system_id64 = $1', system_id64)
        or 0
    )
    scan_fact_count = int(
        await conn.fetchval('SELECT COUNT(*)::int FROM body_scan_facts WHERE system_address = $1', system_id64)
        or 0
    )
    body_data_updated_at = await conn.fetchval(
        'SELECT MAX(updated_at)::text FROM body_scan_facts WHERE system_address = $1',
        system_id64,
    )
    total_body_count = max(catalogue_body_count, body_row_count, scan_fact_count)
    if total_body_count <= 0:
        return None

    known_body_count = max(body_row_count, scan_fact_count)
    coverage_ratio = round(known_body_count / total_body_count, 4) if total_body_count > 0 else None
    if scan_fact_count > 0:
        summary = (
            f'Canonical body coverage for {system_name} currently covers '
            f'{min(scan_fact_count, total_body_count)}/{total_body_count} scanned bodies.'
        )
        confidence = 'high' if scan_fact_count >= total_body_count else 'medium'
    elif body_row_count > 0:
        summary = (
            f'Canonical body coverage for {system_name} currently includes '
            f'{body_row_count}/{total_body_count} body rows.'
        )
        confidence = 'medium'
    else:
        summary = f'Canonical system metadata for {system_name} currently expects {total_body_count} bodies.'
        confidence = 'low'

    observed_at = body_data_updated_at or system_updated_at
    return {
        'system_id64': system_id64,
        'source_name': _CANONICAL_PROMOTION_SOURCE,
        'origin': 'derived',
        'subject_type': 'system',
        'subject_id': str(system_id64),
        'evidence_type': 'body_completeness',
        'record_status': 'active',
        'freshness_status': 'current',
        'confidence': confidence,
        'summary': summary,
        'source_record_id': None,
        'source_run_key': source_run_key,
        'observed_at': observed_at,
        'collected_at': None,
        'expires_at': None,
        'value': {
            'system_name': system_name,
            'catalogue_body_count': catalogue_body_count,
            'canonical_body_row_count': body_row_count,
            'scan_fact_count': scan_fact_count,
            'known_body_count': known_body_count,
            'total_body_count': total_body_count,
            'coverage_ratio': coverage_ratio,
        },
        'provenance': {
            'promotion_lane': 'system_canonical_evidence/v1',
            'trigger_context': trigger_context,
            'source_run_key': source_run_key,
            'source_tables': ['systems', 'bodies', 'body_scan_facts'],
            'body_data_updated_at': body_data_updated_at,
            'system_updated_at': system_updated_at,
        },
        'tags': ['canonical_promotion', 'coverage'],
        'metadata': {
            'promotion_lane': 'system_canonical_evidence/v1',
            'trigger_context': trigger_context,
            'requested_evidence_type': 'body_completeness',
        },
    }


def _build_colonisation_status_payload(
    system_row: Mapping[str, Any],
    *,
    source_run_key: str | None = None,
    trigger_context: str | None = None,
) -> dict[str, Any] | None:
    system_id64 = int(system_row['id64'])
    system_name = str(system_row['name'] or system_id64)
    is_colonised = system_row['is_colonised']
    is_being_colonised = system_row['is_being_colonised']
    observed_at = system_row['status_updated_at'] or system_row['updated_at']

    if observed_at is None and is_colonised is None and is_being_colonised is None:
        return None

    if is_colonised:
        state = 'colonised'
        confidence = 'high'
    elif is_being_colonised:
        state = 'being_colonised'
        confidence = 'high'
    else:
        state = 'not_colonised'
        confidence = 'medium'

    summary = f'Canonical system status for {system_name} currently says this system is {state.replace("_", " ")}.'
    if observed_at:
        summary = (
            f'Canonical system status for {system_name} currently says this system is '
            f'{state.replace("_", " ")} as of {observed_at}.'
        )

    return {
        'system_id64': system_id64,
        'source_name': _CANONICAL_PROMOTION_SOURCE,
        'origin': 'derived',
        'subject_type': 'system',
        'subject_id': str(system_id64),
        'evidence_type': 'colonisation_status',
        'record_status': 'active',
        'freshness_status': 'current',
        'confidence': confidence,
        'summary': summary,
        'source_record_id': None,
        'source_run_key': source_run_key,
        'observed_at': observed_at,
        'collected_at': None,
        'expires_at': None,
        'value': {
            'system_name': system_name,
            'status': state,
            'is_colonised': bool(is_colonised),
            'is_being_colonised': bool(is_being_colonised),
            'status_updated_at': observed_at,
        },
        'provenance': {
            'promotion_lane': 'system_canonical_evidence/v1',
            'trigger_context': trigger_context,
            'source_run_key': source_run_key,
            'source_tables': ['systems'],
            'status_updated_at': observed_at,
        },
        'tags': ['canonical_promotion', 'status'],
        'metadata': {
            'promotion_lane': 'system_canonical_evidence/v1',
            'trigger_context': trigger_context,
            'requested_evidence_type': 'colonisation_status',
        },
    }


async def _build_ring_composition_payload(
    conn: asyncpg.Connection,
    system_row: Mapping[str, Any],
    *,
    source_run_key: str | None = None,
    trigger_context: str | None = None,
) -> dict[str, Any] | None:
    system_id64 = int(system_row['id64'])
    system_name = str(system_row['name'] or system_id64)
    ringed_body_count = int(
        await conn.fetchval(
            'SELECT COUNT(*)::int FROM body_scan_facts WHERE system_address = $1 AND is_ringed IS TRUE',
            system_id64,
        )
        or 0
    )
    ring_identity_count = int(
        await conn.fetchval(
            'SELECT COUNT(DISTINCT body_id)::int FROM body_rings WHERE system_id64 = $1',
            system_id64,
        )
        or 0
    )
    latest_ring_updated_at = await conn.fetchval(
        'SELECT MAX(updated_at)::text FROM body_rings WHERE system_id64 = $1',
        system_id64,
    )
    body_data_updated_at = await conn.fetchval(
        'SELECT MAX(updated_at)::text FROM body_scan_facts WHERE system_address = $1',
        system_id64,
    )
    observed_at = latest_ring_updated_at or body_data_updated_at or system_row['updated_at']

    if ringed_body_count <= 0 and ring_identity_count <= 0:
        return None

    if ringed_body_count > 0 and ring_identity_count > 0:
        summary = (
            f'Canonical ring data for {system_name} currently identifies '
            f'{min(ring_identity_count, ringed_body_count)}/{ringed_body_count} ring-bearing bodies.'
        )
        confidence = 'high' if ring_identity_count >= ringed_body_count else 'medium'
    elif ringed_body_count > 0:
        summary = (
            f'Canonical scan facts for {system_name} currently show {ringed_body_count} ring-bearing bodies, '
            'but ring identities are still incomplete.'
        )
        confidence = 'medium'
    else:
        summary = f'Canonical ring data for {system_name} currently records {ring_identity_count} ring-bearing bodies.'
        confidence = 'medium'

    coverage_ratio = (
        round(min(ring_identity_count, ringed_body_count) / ringed_body_count, 4)
        if ringed_body_count > 0
        else None
    )

    return {
        'system_id64': system_id64,
        'source_name': _CANONICAL_PROMOTION_SOURCE,
        'origin': 'derived',
        'subject_type': 'system',
        'subject_id': str(system_id64),
        'evidence_type': 'ring_composition',
        'record_status': 'active',
        'freshness_status': 'current',
        'confidence': confidence,
        'summary': summary,
        'source_record_id': None,
        'source_run_key': source_run_key,
        'observed_at': observed_at,
        'collected_at': None,
        'expires_at': None,
        'value': {
            'system_name': system_name,
            'ringed_body_count': ringed_body_count,
            'ring_identity_count': ring_identity_count,
            'coverage_ratio': coverage_ratio,
        },
        'provenance': {
            'promotion_lane': 'system_canonical_evidence/v1',
            'trigger_context': trigger_context,
            'source_run_key': source_run_key,
            'source_tables': ['body_scan_facts', 'body_rings'],
            'ring_data_updated_at': latest_ring_updated_at,
            'body_data_updated_at': body_data_updated_at,
        },
        'tags': ['canonical_promotion', 'coverage'],
        'metadata': {
            'promotion_lane': 'system_canonical_evidence/v1',
            'trigger_context': trigger_context,
            'requested_evidence_type': 'ring_composition',
        },
    }
