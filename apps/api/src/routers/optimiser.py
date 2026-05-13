from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from deps import get_pool
from domain.facilities import FacilityTemplate, get_catalogue, load_bundled_catalogue, load_catalogue_from_rows
from models import OptimiserCandidatesRequest, OptimiserCandidatesResponse
from recommendations.optimiser_generator import generate_optimiser_candidates


router = APIRouter(tags=["optimiser"])


@router.post("/api/optimiser/candidates", response_model=OptimiserCandidatesResponse)
async def post_optimiser_candidates(
    body: OptimiserCandidatesRequest,
    pool: asyncpg.Pool = Depends(get_pool),
) -> OptimiserCandidatesResponse:
    catalogue = await _catalogue_or_db(pool)
    candidates, warnings = await generate_optimiser_candidates(
        system_id64=body.system_id64,
        target_archetype_key=body.target_archetype_key,
        catalogue=catalogue,
        pool=pool,
        max_candidates=body.max_candidates,
    )

    return OptimiserCandidatesResponse(
        candidates=candidates,
        warnings=warnings,
    )


async def _catalogue_or_db(pool: asyncpg.Pool) -> dict[str, FacilityTemplate]:
    catalogue = get_catalogue()
    if catalogue:
        return catalogue

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM facility_templates")
            catalogue = load_catalogue_from_rows(rows)
            return catalogue
    except Exception as e:
        # Log the error and return an empty catalogue with a warning
        print(f"Error loading catalogue from DB: {e}")
        return load_bundled_catalogue() # Fallback to bundled catalogue
