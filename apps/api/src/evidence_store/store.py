from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

import asyncpg

from observations.store import observed_fact_summary

from .api_models import (
    DerivedFeatureCreateRequest,
    EvidenceRecordCreateRequest,
    RuleDecisionRequest,
    RuleProposalCreateRequest,
)
from .models import DerivedFeature, EvidenceRecord, EvidenceSystemSummary, RuleDecision, RuleProposal


def _json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(',', ':'), sort_keys=True)


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value


def _dt_to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _dedupe_text_list(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def row_to_evidence_record(row: Any) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_key=str(row['evidence_key']),
        system_id64=int(row['system_id64']),
        source_name=str(row['source_name']),
        origin=str(row['origin']),
        subject_type=str(row['subject_type']),
        subject_id=row['subject_id'],
        evidence_type=str(row['evidence_type']),
        record_status=str(row['record_status']),
        freshness_status=str(row['freshness_status']),
        confidence=str(row['confidence']),
        summary=row['summary'],
        source_record_id=row['source_record_id'],
        source_run_key=row['source_run_key'],
        observed_at=_dt_to_str(row['observed_at']),
        collected_at=_dt_to_str(row['collected_at']),
        expires_at=_dt_to_str(row['expires_at']),
        value=dict(_json_loads(row['value_json'], {})),
        provenance=dict(_json_loads(row['provenance_json'], {})),
        tags=list(_json_loads(row['tags_json'], [])),
        metadata=dict(_json_loads(row['metadata_json'], {})),
        created_at=_dt_to_str(row['created_at']),
        updated_at=_dt_to_str(row['updated_at']),
    )


def row_to_derived_feature(row: Any) -> DerivedFeature:
    return DerivedFeature(
        feature_key=str(row['feature_key']),
        system_id64=int(row['system_id64']),
        feature_name=str(row['feature_name']),
        feature_version=str(row['feature_version']),
        feature_status=str(row['feature_status']),
        confidence=str(row['confidence']),
        summary=row['summary'],
        derived_from_run_key=row['derived_from_run_key'],
        derived_at=_dt_to_str(row['derived_at']),
        expires_at=_dt_to_str(row['expires_at']),
        value=dict(_json_loads(row['value_json'], {})),
        evidence_refs=list(_json_loads(row['evidence_refs_json'], [])),
        metadata=dict(_json_loads(row['metadata_json'], {})),
        created_at=_dt_to_str(row['created_at']),
        updated_at=_dt_to_str(row['updated_at']),
    )


def row_to_rule_proposal(row: Any) -> RuleProposal:
    return RuleProposal(
        proposal_key=str(row['proposal_key']),
        proposal_type=str(row['proposal_type']),
        domain=str(row['domain']),
        scope_type=str(row['scope_type']),
        scope_key=str(row['scope_key']),
        status=str(row['status']),
        priority=str(row['priority']),
        risk_level=str(row['risk_level']),
        auto_approval_eligible=bool(row['auto_approval_eligible']),
        summary=str(row['summary']),
        proposed_by=str(row['proposed_by']),
        decided_by=row['decided_by'],
        decision_notes=row['decision_notes'],
        proposed_change=dict(_json_loads(row['proposed_change_json'], {})),
        evidence_refs=list(_json_loads(row['evidence_refs_json'], [])),
        impact_summary=dict(_json_loads(row['impact_summary_json'], {})),
        metadata=dict(_json_loads(row['metadata_json'], {})),
        created_at=_dt_to_str(row['created_at']),
        updated_at=_dt_to_str(row['updated_at']),
        decided_at=_dt_to_str(row['decided_at']),
    )


def row_to_rule_decision(row: Any) -> RuleDecision:
    return RuleDecision(
        decision_id=int(row['decision_id']),
        proposal_key=str(row['proposal_key']),
        decision=str(row['decision']),
        decided_by=str(row['decided_by']),
        reason=row['reason'],
        metadata=dict(_json_loads(row['metadata_json'], {})),
        created_at=_dt_to_str(row['created_at']),
    )


async def create_evidence_record(
    pool: asyncpg.Pool,
    request: EvidenceRecordCreateRequest,
) -> EvidenceRecord:
    evidence_key = f'evd_{uuid4().hex}'
    payload = request.model_dump(mode='json')
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
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
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14::timestamptz, $15::timestamptz, $16::timestamptz,
                $17::jsonb, $18::jsonb, $19::jsonb, $20::jsonb
            )
            RETURNING *
            ''',
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
            payload.get('observed_at'),
            payload.get('collected_at'),
            payload.get('expires_at'),
            _json_dumps(payload.get('value') or {}),
            _json_dumps(payload.get('provenance') or {}),
            _json_dumps(payload.get('tags') or []),
            _json_dumps(payload.get('metadata') or {}),
        )
    return row_to_evidence_record(row)


async def list_evidence_records(
    pool: asyncpg.Pool,
    *,
    system_id64: int | None = None,
    source_name: str | None = None,
    origin: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[EvidenceRecord], int]:
    where, args_for_count = _build_optional_filters(
        ('system_id64', system_id64),
        ('source_name', source_name),
        ('origin', origin),
    )
    args = list(args_for_count)
    args.extend([limit, offset])
    limit_pos = len(args) - 1
    offset_pos = len(args)
    async with pool.acquire() as conn:
        total = await conn.fetchval(f'SELECT count(*) FROM evidence_records WHERE {where}', *args_for_count)
        rows = await conn.fetch(
            f'''
            SELECT * FROM evidence_records
            WHERE {where}
            ORDER BY COALESCE(observed_at, collected_at, created_at) DESC, evidence_key DESC
            LIMIT ${limit_pos} OFFSET ${offset_pos}
            ''',
            *args,
        )
    return [row_to_evidence_record(row) for row in rows], int(total or 0)


async def create_derived_feature(
    pool: asyncpg.Pool,
    request: DerivedFeatureCreateRequest,
) -> DerivedFeature:
    feature_key = f'feat_{uuid4().hex}'
    payload = request.model_dump(mode='json')
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''
            INSERT INTO derived_features (
                feature_key,
                system_id64,
                feature_name,
                feature_version,
                feature_status,
                confidence,
                summary,
                derived_from_run_key,
                derived_at,
                expires_at,
                value_json,
                evidence_refs_json,
                metadata_json
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9::timestamptz, $10::timestamptz,
                $11::jsonb, $12::jsonb, $13::jsonb
            )
            RETURNING *
            ''',
            feature_key,
            payload['system_id64'],
            payload['feature_name'],
            payload['feature_version'],
            payload['feature_status'],
            payload['confidence'],
            payload.get('summary'),
            payload.get('derived_from_run_key'),
            payload.get('derived_at'),
            payload.get('expires_at'),
            _json_dumps(payload.get('value') or {}),
            _json_dumps(_dedupe_text_list(payload.get('evidence_refs') or [])),
            _json_dumps(payload.get('metadata') or {}),
        )
    return row_to_derived_feature(row)


async def list_derived_features(
    pool: asyncpg.Pool,
    *,
    system_id64: int | None = None,
    feature_name: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[DerivedFeature], int]:
    where, args_for_count = _build_optional_filters(
        ('system_id64', system_id64),
        ('feature_name', feature_name),
    )
    args = list(args_for_count)
    args.extend([limit, offset])
    limit_pos = len(args) - 1
    offset_pos = len(args)
    async with pool.acquire() as conn:
        total = await conn.fetchval(f'SELECT count(*) FROM derived_features WHERE {where}', *args_for_count)
        rows = await conn.fetch(
            f'''
            SELECT * FROM derived_features
            WHERE {where}
            ORDER BY COALESCE(derived_at, created_at) DESC, feature_key DESC
            LIMIT ${limit_pos} OFFSET ${offset_pos}
            ''',
            *args,
        )
    return [row_to_derived_feature(row) for row in rows], int(total or 0)


async def create_rule_proposal(
    pool: asyncpg.Pool,
    request: RuleProposalCreateRequest,
) -> RuleProposal:
    proposal_key = f'prop_{uuid4().hex}'
    payload = request.model_dump(mode='json')
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''
            INSERT INTO rule_proposals (
                proposal_key,
                proposal_type,
                domain,
                scope_type,
                scope_key,
                status,
                priority,
                risk_level,
                auto_approval_eligible,
                summary,
                proposed_by,
                decision_notes,
                proposed_change_json,
                evidence_refs_json,
                impact_summary_json,
                metadata_json
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9,
                $10, $11, $12, $13::jsonb, $14::jsonb, $15::jsonb, $16::jsonb
            )
            RETURNING *
            ''',
            proposal_key,
            payload['proposal_type'],
            payload['domain'],
            payload['scope_type'],
            payload['scope_key'],
            payload['status'],
            payload['priority'],
            payload['risk_level'],
            payload['auto_approval_eligible'],
            payload['summary'],
            payload['proposed_by'],
            payload.get('decision_notes'),
            _json_dumps(payload.get('proposed_change') or {}),
            _json_dumps(_dedupe_text_list(payload.get('evidence_refs') or [])),
            _json_dumps(payload.get('impact_summary') or {}),
            _json_dumps(payload.get('metadata') or {}),
        )
    return row_to_rule_proposal(row)


async def list_rule_proposals(
    pool: asyncpg.Pool,
    *,
    status: str | None = None,
    statuses: list[str] | None = None,
    domain: str | None = None,
    scope_key: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[RuleProposal], int]:
    where, args_for_count = _build_rule_proposal_filters(
        status=status,
        statuses=statuses,
        domain=domain,
        scope_key=scope_key,
    )
    args = list(args_for_count)
    args.extend([limit, offset])
    limit_pos = len(args) - 1
    offset_pos = len(args)
    async with pool.acquire() as conn:
        total = await conn.fetchval(f'SELECT count(*) FROM rule_proposals WHERE {where}', *args_for_count)
        rows = await conn.fetch(
            f'''
            SELECT * FROM rule_proposals
            WHERE {where}
            ORDER BY created_at DESC, proposal_key DESC
            LIMIT ${limit_pos} OFFSET ${offset_pos}
            ''',
            *args,
        )
    return [row_to_rule_proposal(row) for row in rows], int(total or 0)


async def create_rule_decision(
    pool: asyncpg.Pool,
    proposal_key: str,
    request: RuleDecisionRequest,
) -> RuleDecision | None:
    status_map = {
        'approved': 'approved',
        'rejected': 'rejected',
        'superseded': 'superseded',
        'rolled_back': 'superseded',
    }
    payload = request.model_dump(mode='json')
    async with pool.acquire() as conn:
        async with conn.transaction():
            proposal_exists = await conn.fetchval(
                'SELECT 1 FROM rule_proposals WHERE proposal_key = $1',
                proposal_key,
            )
            if proposal_exists is None:
                return None
            row = await conn.fetchrow(
                '''
                INSERT INTO rule_decisions (
                    proposal_key,
                    decision,
                    decided_by,
                    reason,
                    metadata_json
                ) VALUES (
                    $1, $2, $3, $4, $5::jsonb
                )
                RETURNING *
                ''',
                proposal_key,
                payload['decision'],
                payload['decided_by'],
                payload.get('reason'),
                _json_dumps(payload.get('metadata') or {}),
            )
            await conn.execute(
                '''
                UPDATE rule_proposals
                SET status = $2,
                    decided_by = $3,
                    decision_notes = COALESCE($4, decision_notes),
                    decided_at = now(),
                    updated_at = now()
                WHERE proposal_key = $1
                ''',
                proposal_key,
                status_map[payload['decision']],
                payload['decided_by'],
                payload.get('reason'),
            )
    return row_to_rule_decision(row) if row else None


async def build_evidence_system_summary(
    pool: asyncpg.Pool,
    system_id64: int,
    *,
    record_limit: int = 5,
    feature_limit: int = 5,
    proposal_limit: int = 5,
) -> EvidenceSystemSummary:
    observed = await observed_fact_summary(pool, system_id64)
    records, imported_record_count = await list_evidence_records(
        pool,
        system_id64=system_id64,
        limit=record_limit,
        offset=0,
    )
    features, derived_feature_count = await list_derived_features(
        pool,
        system_id64=system_id64,
        limit=feature_limit,
        offset=0,
    )
    open_proposals, open_rule_proposal_count = await list_rule_proposals(
        pool,
        statuses=['pending_review', 'approved', 'auto_approved'],
        scope_key=str(system_id64),
        limit=proposal_limit,
        offset=0,
    )
    return EvidenceSystemSummary(
        schema_version='evidence_store/v1',
        system_id64=system_id64,
        observed_fact_count=int(observed.get('total_count', 0) or 0),
        imported_record_count=imported_record_count,
        derived_feature_count=derived_feature_count,
        open_rule_proposal_count=open_rule_proposal_count,
        records=records,
        derived_features=features,
        open_rule_proposals=open_proposals,
    )


def _build_optional_filters(*filters: tuple[str, Any]) -> tuple[str, list[Any]]:
    conditions = ['1 = 1']
    args: list[Any] = []
    for column, value in filters:
        if value is None:
            continue
        args.append(value)
        conditions.append(f'{column} = ${len(args)}')
    return ' AND '.join(conditions), args


def _build_rule_proposal_filters(
    *,
    status: str | None,
    statuses: list[str] | None,
    domain: str | None,
    scope_key: str | None,
) -> tuple[str, list[Any]]:
    conditions = ['1 = 1']
    args: list[Any] = []
    if status is not None:
        args.append(status)
        conditions.append(f'status = ${len(args)}')
    if statuses:
        args.append(statuses)
        conditions.append(f'status = ANY(${len(args)}::text[])')
    if domain is not None:
        args.append(domain)
        conditions.append(f'domain = ${len(args)}')
    if scope_key is not None:
        args.append(scope_key)
        conditions.append(f'scope_key = ${len(args)}')
    return ' AND '.join(conditions), args
