from __future__ import annotations

import json

import asyncpg

from provenance_cockpit_models import ProvenanceCockpitResponse
from review_environment_fixtures import (
    review_provenance_contract_key,
    review_warehouse_contract_key,
)
from warehouse_planner_evidence_models import WarehousePlannerEvidenceContract


async def load_review_warehouse_contract(
    pool: asyncpg.Pool,
    id64: int,
) -> WarehousePlannerEvidenceContract | None:
    payload = await _load_app_meta_json(pool, review_warehouse_contract_key(id64))
    if payload is None:
        return None
    return WarehousePlannerEvidenceContract.model_validate(payload)


async def load_review_provenance_contract(
    pool: asyncpg.Pool,
    id64: int,
) -> ProvenanceCockpitResponse | None:
    payload = await _load_app_meta_json(pool, review_provenance_contract_key(id64))
    if payload is None:
        return None
    return ProvenanceCockpitResponse.model_validate(payload)


async def _load_app_meta_json(pool: asyncpg.Pool, key: str) -> dict[str, object] | None:
    async with pool.acquire() as conn:
        value = await conn.fetchval('SELECT value FROM app_meta WHERE key = $1', key)
    if not isinstance(value, str) or not value.strip():
        return None
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else None
