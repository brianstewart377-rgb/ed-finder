from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from deps import get_pool
from review_contract_store import load_review_warehouse_contract
from warehouse_planner_evidence import build_warehouse_planner_evidence
from warehouse_planner_evidence_models import WarehousePlannerEvidenceContract
from warehouse_planner_evidence_provider import load_live_planner_evidence


router = APIRouter(tags=['colony-planner'])
_REVIEW_DELTA_ID64 = 7200000000004


@router.get(
    '/api/colony-planner/system/{id64}/warehouse-planner-evidence',
    response_model=WarehousePlannerEvidenceContract,
    include_in_schema=False,
)
async def warehouse_planner_evidence(
    id64: int,
    pool: asyncpg.Pool = Depends(get_pool),
) -> WarehousePlannerEvidenceContract | JSONResponse:
    if id64 == _REVIEW_DELTA_ID64:
        return JSONResponse(
            status_code=503,
            media_type='application/problem+json',
            content={
                'type': 'https://ed-finder.local/problem/review-delta-dedicated-evidence-unavailable',
                'title': 'Dedicated warehouse evidence intentionally unavailable in review runtime',
                'status': 503,
                'detail': (
                    'Review Delta keeps the dedicated warehouse evidence route unreadable in the '
                    'isolated review runtime so the existing provenance fallback can be exercised.'
                ),
                'system_id64': id64,
                'review_runtime_only': True,
                'fallback_route': f'/api/colony-planner/system/{id64}/provenance-cockpit',
            },
        )
    review_contract = await load_review_warehouse_contract(pool, id64)
    if review_contract is not None:
        return review_contract
    live_result = await load_live_planner_evidence(pool, id64)
    return build_warehouse_planner_evidence(id64, live_result=live_result)
