from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from deps import get_pool
from evidence_store import store
from evidence_store.api_models import (
    DerivedFeatureCreateRequest,
    DerivedFeatureListResponse,
    DerivedFeatureResponse,
    EvidenceRecordCreateRequest,
    EvidenceRecordListResponse,
    EvidenceRecordResponse,
    EvidenceSourceCatalogEntryResponse,
    EvidenceSourceCatalogResponse,
    EvidenceSystemSummaryResponse,
    RuleDecisionRequest,
    RuleDecisionResponse,
    RuleProposalCreateRequest,
    RuleProposalListResponse,
    RuleProposalResponse,
)
from evidence_store.source_catalog import SCHEMA_VERSION as SOURCE_CATALOG_SCHEMA_VERSION, list_evidence_sources

router = APIRouter(tags=['evidence'])


@router.get('/api/evidence/sources', response_model=EvidenceSourceCatalogResponse)
async def evidence_source_catalog() -> EvidenceSourceCatalogResponse:
    return EvidenceSourceCatalogResponse(
        schema_version=SOURCE_CATALOG_SCHEMA_VERSION,
        sources=[EvidenceSourceCatalogEntryResponse.model_validate(row) for row in list_evidence_sources()],
    )


@router.post('/api/evidence/records', response_model=EvidenceRecordResponse)
async def create_evidence_record(
    body: EvidenceRecordCreateRequest,
    pool: asyncpg.Pool = Depends(get_pool),
) -> EvidenceRecordResponse:
    record = await store.create_evidence_record(pool, body)
    return EvidenceRecordResponse.from_domain(record)


@router.get('/api/evidence/records', response_model=EvidenceRecordListResponse)
async def list_evidence_records(
    system_id64: int | None = Query(default=None, gt=0),
    source_name: str | None = None,
    origin: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    pool: asyncpg.Pool = Depends(get_pool),
) -> EvidenceRecordListResponse:
    records, total = await store.list_evidence_records(
        pool,
        system_id64=system_id64,
        source_name=source_name,
        origin=origin,
        limit=limit,
        offset=offset,
    )
    return EvidenceRecordListResponse(
        records=[EvidenceRecordResponse.from_domain(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post('/api/evidence/features', response_model=DerivedFeatureResponse)
async def create_derived_feature(
    body: DerivedFeatureCreateRequest,
    pool: asyncpg.Pool = Depends(get_pool),
) -> DerivedFeatureResponse:
    feature = await store.create_derived_feature(pool, body)
    return DerivedFeatureResponse.from_domain(feature)


@router.get('/api/evidence/features', response_model=DerivedFeatureListResponse)
async def list_derived_features(
    system_id64: int | None = Query(default=None, gt=0),
    feature_name: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    pool: asyncpg.Pool = Depends(get_pool),
) -> DerivedFeatureListResponse:
    features, total = await store.list_derived_features(
        pool,
        system_id64=system_id64,
        feature_name=feature_name,
        limit=limit,
        offset=offset,
    )
    return DerivedFeatureListResponse(
        features=[DerivedFeatureResponse.from_domain(feature) for feature in features],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post('/api/evidence/rule-proposals', response_model=RuleProposalResponse)
async def create_rule_proposal(
    body: RuleProposalCreateRequest,
    pool: asyncpg.Pool = Depends(get_pool),
) -> RuleProposalResponse:
    proposal = await store.create_rule_proposal(pool, body)
    return RuleProposalResponse.from_domain(proposal)


@router.get('/api/evidence/rule-proposals', response_model=RuleProposalListResponse)
async def list_rule_proposals(
    status: str | None = None,
    domain: str | None = None,
    scope_key: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    pool: asyncpg.Pool = Depends(get_pool),
) -> RuleProposalListResponse:
    proposals, total = await store.list_rule_proposals(
        pool,
        status=status,
        domain=domain,
        scope_key=scope_key,
        limit=limit,
        offset=offset,
    )
    return RuleProposalListResponse(
        proposals=[RuleProposalResponse.from_domain(proposal) for proposal in proposals],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post('/api/evidence/rule-proposals/{proposal_key}/decisions', response_model=RuleDecisionResponse)
async def decide_rule_proposal(
    proposal_key: str,
    body: RuleDecisionRequest,
    pool: asyncpg.Pool = Depends(get_pool),
) -> RuleDecisionResponse:
    decision = await store.create_rule_decision(pool, proposal_key, body)
    if decision is None:
        raise HTTPException(404, f'Rule proposal {proposal_key} not found')
    return RuleDecisionResponse.from_domain(decision)


@router.get('/api/evidence/systems/{system_id64}/summary', response_model=EvidenceSystemSummaryResponse)
async def evidence_system_summary(
    system_id64: int,
    pool: asyncpg.Pool = Depends(get_pool),
) -> EvidenceSystemSummaryResponse:
    summary = await store.build_evidence_system_summary(pool, system_id64)
    return EvidenceSystemSummaryResponse.from_domain(summary)
