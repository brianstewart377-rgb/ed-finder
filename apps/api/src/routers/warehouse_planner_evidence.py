from __future__ import annotations

from fastapi import APIRouter

from warehouse_planner_evidence import build_warehouse_planner_evidence
from warehouse_planner_evidence_models import WarehousePlannerEvidenceContract


router = APIRouter(tags=['colony-planner'])


@router.get(
    '/api/colony-planner/system/{id64}/warehouse-planner-evidence',
    response_model=WarehousePlannerEvidenceContract,
    include_in_schema=False,
)
async def warehouse_planner_evidence(id64: int) -> WarehousePlannerEvidenceContract:
    return build_warehouse_planner_evidence(id64)
