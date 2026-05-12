"""Simulation Preview API routes."""
from __future__ import annotations

from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends

from deps import get_pool
from domain.facilities import FacilityTemplate, get_catalogue, load_catalogue_from_rows
from models import (
    FacilityTemplateResponse,
    SimulateBuildRequest,
    SimulateBuildResponse,
)
from simulation.build_preview import PreviewContext, PreviewPlacement, simulate_build_preview


router = APIRouter(tags=['simulation-preview'])


@router.get('/api/facility-templates', response_model=list[FacilityTemplateResponse])
async def get_facility_templates(
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[FacilityTemplateResponse]:
    catalogue = await _catalogue_or_db(pool)
    return [
        FacilityTemplateResponse(
            id=f.id,
            name=f.name,
            category=f.category,
            tier=f.tier,
            economy=f.economy,
            is_port=f.is_port,
            is_support_facility=f.is_support_facility,
            allowed_location=f.allowed_location,
            pad_size=f.pad_size,
            confidence=f.data_confidence,
            notes=f.stat_effects.get('note') if isinstance(f.stat_effects, dict) else None,
            yellow_cp_generated=f.yellow_cp_generated,
            green_cp_generated=f.green_cp_generated,
            yellow_cp_cost=f.yellow_cp_cost,
            green_cp_cost=f.green_cp_cost,
        )
        for f in sorted(catalogue.values(), key=lambda item: (item.tier, item.category, item.name))
    ]


@router.post('/api/simulate/build', response_model=SimulateBuildResponse)
async def post_simulate_build(
    body: SimulateBuildRequest,
    pool: asyncpg.Pool = Depends(get_pool),
) -> SimulateBuildResponse:
    catalogue = await _catalogue_or_db(pool)
    context = await _preview_context(pool, body.system_id64)
    result = simulate_build_preview(
        system_id64=body.system_id64,
        target_archetype=body.target_archetype,
        placements=[
            PreviewPlacement(
                facility_template_id=p.facility_template_id,
                local_body_id=p.local_body_id,
                is_primary_port=p.is_primary_port,
                build_order=p.build_order,
            )
            for p in body.placements
        ],
        catalogue=catalogue,
        context=context,
    )
    return SimulateBuildResponse.model_validate(result)


async def _catalogue_or_db(pool: asyncpg.Pool) -> dict[str, FacilityTemplate]:
    catalogue = get_catalogue()
    if catalogue:
        return catalogue

    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT * FROM facility_templates ORDER BY tier, id')
    load_catalogue_from_rows([dict(row) for row in rows])
    return get_catalogue()


async def _preview_context(pool: asyncpg.Pool, system_id64: int) -> PreviewContext:
    async with pool.acquire() as conn:
        topology = await conn.fetchrow(
            """
            SELECT estimated_orbital_slots, estimated_ground_slots,
                   has_ringed_gas_giant, has_viable_surface_port
            FROM system_slot_topology
            WHERE system_id64 = $1
            """,
            system_id64,
        )
        buildability = await conn.fetchrow(
            """
            SELECT estimated_orbital_slots, estimated_ground_slots, slot_confidence
            FROM buildability_analysis
            WHERE system_id64 = $1
            """,
            system_id64,
        )
        body_rows = await conn.fetch(
            """
            SELECT body_id, planet_class, is_landable, is_terraformable, confidence
            FROM body_scan_facts
            WHERE system_address = $1
            """,
            system_id64,
        )

    topology_dict = dict(topology) if topology else None
    buildability_dict = dict(buildability) if buildability else None

    orbital = _maybe_int(buildability_dict, 'estimated_orbital_slots')
    ground = _maybe_int(buildability_dict, 'estimated_ground_slots')
    slot_confidence = _maybe_float(buildability_dict, 'slot_confidence')

    if topology_dict:
        orbital = orbital if orbital is not None else _maybe_int(topology_dict, 'estimated_orbital_slots')
        ground = ground if ground is not None else _maybe_int(topology_dict, 'estimated_ground_slots')
        slot_confidence = slot_confidence if slot_confidence is not None else 0.65

    body_profiles = {
        str(body['body_id']): {
            'base_economy': _body_economy(body),
            'confidence': float(body.get('confidence') or 0.45),
        }
        for body in (dict(row) for row in body_rows)
        if body.get('body_id') is not None
    }

    return PreviewContext(
        system_id64=system_id64,
        estimated_orbital_slots=orbital,
        estimated_ground_slots=ground,
        slot_confidence=slot_confidence,
        has_ringed_body=bool(topology_dict and topology_dict['has_ringed_gas_giant']),
        local_body_profiles=body_profiles,
    )


def _maybe_int(row: Optional[dict], key: str) -> Optional[int]:
    if not row or row.get(key) is None:
        return None
    return int(row[key])


def _maybe_float(row: Optional[dict], key: str) -> Optional[float]:
    if not row or row.get(key) is None:
        return None
    return float(row[key])


def _body_economy(row: dict) -> Optional[str]:
    planet_class = str(row.get('planet_class') or '').lower()
    if row.get('is_terraformable') or 'earth-like' in planet_class or 'water world' in planet_class:
        return 'Agriculture'
    if 'metal' in planet_class or 'high metal' in planet_class:
        return 'Refinery'
    if 'rocky' in planet_class:
        return 'Industrial'
    if 'icy' in planet_class:
        return 'Extraction'
    if row.get('is_landable'):
        return 'Industrial'
    return None
