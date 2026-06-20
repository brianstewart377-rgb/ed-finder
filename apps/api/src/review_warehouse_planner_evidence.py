from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from deps import get_pool
from review_contract_store import load_review_warehouse_contract
from warehouse_planner_evidence import build_warehouse_planner_evidence
from warehouse_planner_evidence_models import WarehousePlannerEvidenceContract
from warehouse_planner_evidence_provider import load_live_planner_evidence


router = APIRouter(tags=['colony-planner'])


@router.get(
    '/api/colony-planner/system/{id64}/warehouse-planner-evidence',
    response_model=WarehousePlannerEvidenceContract,
    include_in_schema=False,
)
async def warehouse_planner_evidence(
    id64: int,
    pool: asyncpg.Pool = Depends(get_pool),
) -> WarehousePlannerEvidenceContract:
    review_contract = await load_review_warehouse_contract(pool, id64)
    if review_contract is not None:
        return review_contract
    live_result = await load_live_planner_evidence(pool, id64)
    return build_warehouse_planner_evidence(id64, live_result=live_result)
