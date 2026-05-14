"""Compatibility wrapper for Stage 5A optimiser candidate generation.

Core optimiser logic lives in ``apps/api/src/optimiser/``. This module remains
only for older imports that still call ``generate_optimiser_candidates``.
"""
from __future__ import annotations

from typing import Any, Optional

import asyncpg

from domain.facilities import FacilityTemplate
from optimiser.candidate_generator import generate_candidates
from optimiser.models import CandidateGenerationRequest, candidate_result_to_dict

__all__ = ['generate_candidates', 'generate_optimiser_candidates']


async def generate_optimiser_candidates(
    system_id64: int,
    target_archetype_key: Optional[str],
    catalogue: dict[str, FacilityTemplate],
    pool: asyncpg.Pool,
    max_candidates: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    result = await generate_candidates(
        CandidateGenerationRequest(
            system_id64=system_id64,
            target_archetype=target_archetype_key or 'flexible_multirole',
            max_candidates=max_candidates,
        ),
        catalogue=catalogue,
        pool=pool,
    )
    payload = candidate_result_to_dict(result)
    return payload['candidates'], payload['warnings']
