from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from deps import get_pool
from domain.facilities import FacilityTemplate, get_catalogue, load_bundled_catalogue, load_catalogue_from_rows
from models import OptimiserCandidatesRequest, OptimiserCandidatesResponse
from optimiser.candidate_generator import generate_candidates
from optimiser.models import CandidateGenerationRequest, candidate_result_to_dict, ranking_result_to_dict
from optimiser.ranker import rank_candidates


router = APIRouter(tags=['optimiser'])


@router.post('/api/optimiser/candidates', response_model=OptimiserCandidatesResponse)
async def post_optimiser_candidates(
    body: OptimiserCandidatesRequest,
    pool: asyncpg.Pool = Depends(get_pool),
) -> OptimiserCandidatesResponse:
    catalogue = await _catalogue_or_db(pool)
    target_archetype = body.target_archetype or body.target_archetype_key or 'flexible_multirole'
    result = await generate_candidates(
        CandidateGenerationRequest(
            system_id64=body.system_id64,
            target_archetype=target_archetype,
            max_candidates=body.max_candidates,
            preferred_body_ids=body.preferred_body_ids,
            allow_estimated_data=body.allow_estimated_data,
            run_preview=body.run_preview,
        ),
        catalogue=catalogue,
        pool=pool,
    )
    payload = candidate_result_to_dict(result)
    if body.include_ranking:
        ranking = rank_candidates(result.candidates, target_archetype=result.target_archetype)
        payload['ranking'] = ranking_result_to_dict(ranking)
    return OptimiserCandidatesResponse.model_validate(payload)


async def _catalogue_or_db(pool: asyncpg.Pool) -> dict[str, FacilityTemplate]:
    catalogue = get_catalogue()
    if catalogue:
        return catalogue

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch('SELECT * FROM facility_templates')
        return load_catalogue_from_rows(rows)
    except Exception:
        return load_bundled_catalogue()
