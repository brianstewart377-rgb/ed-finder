from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from deps import get_pool
from observations import store
from observations.api_models import (
    ObservedFactCreateRequest,
    ObservedFactDeleteResponse,
    ObservedFactListResponse,
    ObservedFactResponse,
    ObservedFactUpdateRequest,
    ObservationFactSummaryResponse,
)

router = APIRouter(tags=['observations'])


@router.post('/api/observations/facts', response_model=ObservedFactResponse)
async def create_observed_fact(
    body: ObservedFactCreateRequest,
    pool: asyncpg.Pool = Depends(get_pool),
) -> ObservedFactResponse:
    fact = await store.create_observed_fact(pool, body)
    return ObservedFactResponse.from_domain(fact)


@router.get('/api/observations/facts', response_model=ObservedFactListResponse)
async def list_observed_facts(
    system_id64: int = Query(..., gt=0),
    fact_type: str | None = None,
    subject_type: str | None = None,
    status: str | None = None,
    target_archetype: str | None = None,
    build_fingerprint: str | None = None,
    simulation_fingerprint: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    pool: asyncpg.Pool = Depends(get_pool),
) -> ObservedFactListResponse:
    facts, total = await store.list_observed_facts(
        pool,
        system_id64=system_id64,
        fact_type=fact_type,
        subject_type=subject_type,
        status=status,
        target_archetype=target_archetype,
        build_fingerprint=build_fingerprint,
        simulation_fingerprint=simulation_fingerprint,
        limit=limit,
        offset=offset,
    )
    # Summary must describe the full filtered result set, not just the
    # paginated page returned above. We re-run the same filter without
    # limit/offset so total and summary describe identical row sets.
    summary = await store.summarise_observed_facts_for_filter(
        pool,
        system_id64=system_id64,
        fact_type=fact_type,
        subject_type=subject_type,
        status=status,
        target_archetype=target_archetype,
        build_fingerprint=build_fingerprint,
        simulation_fingerprint=simulation_fingerprint,
    )
    return ObservedFactListResponse(
        facts=[ObservedFactResponse.from_domain(fact) for fact in facts],
        total=total,
        limit=limit,
        offset=offset,
        summary=ObservationFactSummaryResponse.from_domain(summary),
    )


@router.get('/api/observations/facts/{observation_id}', response_model=ObservedFactResponse)
async def get_observed_fact(
    observation_id: str,
    pool: asyncpg.Pool = Depends(get_pool),
) -> ObservedFactResponse:
    fact = await store.get_observed_fact(pool, observation_id)
    if fact is None:
        raise HTTPException(404, f'Observed fact {observation_id} not found')
    return ObservedFactResponse.from_domain(fact)


@router.patch('/api/observations/facts/{observation_id}', response_model=ObservedFactResponse)
async def update_observed_fact(
    observation_id: str,
    body: ObservedFactUpdateRequest,
    pool: asyncpg.Pool = Depends(get_pool),
) -> ObservedFactResponse:
    fact = await store.update_observed_fact(pool, observation_id, body)
    if fact is None:
        raise HTTPException(404, f'Observed fact {observation_id} not found')
    return ObservedFactResponse.from_domain(fact)


@router.delete('/api/observations/facts/{observation_id}', response_model=ObservedFactDeleteResponse)
async def delete_observed_fact(
    observation_id: str,
    pool: asyncpg.Pool = Depends(get_pool),
) -> ObservedFactDeleteResponse:
    deleted = await store.delete_observed_fact(pool, observation_id)
    if not deleted:
        raise HTTPException(404, f'Observed fact {observation_id} not found')
    return ObservedFactDeleteResponse(observation_id=observation_id, deleted=True)
