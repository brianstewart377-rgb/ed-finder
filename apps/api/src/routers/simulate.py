"""Simulation Preview API routes."""
from __future__ import annotations

from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, Query

from deps import get_pool
from domain.facilities import FacilityTemplate, get_catalogue, load_catalogue_from_rows
from models import (
    FacilityTemplateResponse,
    RecommendedBuildPlan,
    RecommendedBuildsResponse,
    SimulateBuildRequest,
    SimulateBuildResponse,
    SimulateBuildPlacement,
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


@router.get('/api/systems/{system_id64}/recommended-builds', response_model=RecommendedBuildsResponse)
async def get_recommended_builds(
    system_id64: int,
    archetype: Optional[str] = Query(None),
    pool: asyncpg.Pool = Depends(get_pool),
) -> RecommendedBuildsResponse:
    catalogue = await _catalogue_or_db(pool)
    context = await _preview_context(pool, system_id64)
    target = archetype or await _suggested_archetype(pool, system_id64) or 'refinery_industrial'
    requests = _recommended_requests(system_id64, target, catalogue, context)
    warnings: list[str] = []

    if not requests:
        warnings.append('No facility catalogue data is available yet. Try Simulation Preview manually once templates load.')

    plans: list[RecommendedBuildPlan] = []
    for idx, (plan_id, label, summary, request, tradeoffs) in enumerate(requests):
        simulation = SimulateBuildResponse.model_validate(simulate_build_preview(
            system_id64=system_id64,
            target_archetype=target,
            placements=[
                PreviewPlacement(
                    facility_template_id=p.facility_template_id,
                    local_body_id=p.local_body_id,
                    is_primary_port=p.is_primary_port,
                    build_order=p.build_order,
                )
                for p in request.placements
            ],
            catalogue=catalogue,
            context=context,
        ))
        plans.append(RecommendedBuildPlan(
            id=plan_id,
            label=label,
            summary=summary,
            complexity=simulation.build_complexity,
            confidence=simulation.confidence,
            final_score=simulation.final_score,
            composition_score=simulation.composition_score,
            buildability_score=simulation.buildability_score,
            economy_result=simulation.economy_composition,
            cp_result=simulation.cp,
            build_order=request.placements,
            strengths=simulation.strengths[:4],
            warnings=simulation.warnings[:4],
            tradeoffs=tradeoffs,
            next_actions=simulation.recommendations[:3] or ['Preview this plan, then adjust body placement before committing in-game.'],
            simulation_request=request,
            is_default=(idx == 1 if len(requests) > 1 else idx == 0),
        ))

    next_action = (
        'Open the balanced recommended build in Simulation Preview.'
        if len(plans) > 1 else
        'Open the recommended build in Simulation Preview.'
        if plans else
        'Try a blank advanced simulation once more topology data is available.'
    )
    if context.slot_confidence is not None and context.slot_confidence < 0.55:
        warnings.append('Slot data is predicted, not observed. Advanced plans are hidden until better topology data is available.')

    return RecommendedBuildsResponse(
        system_id64=system_id64,
        target_archetype=target,
        best_suggested_archetype=target,
        recommended_next_action=next_action,
        plans=plans,
        warnings=warnings,
    )


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


async def _suggested_archetype(pool: asyncpg.Pool, system_id64: int) -> Optional[str]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT primary_archetype
            FROM system_archetype_scores
            WHERE system_id64 = $1
            """,
            system_id64,
        )
    return str(row['primary_archetype']) if row and row['primary_archetype'] else None


def _recommended_requests(
    system_id64: int,
    target: str,
    catalogue: dict[str, FacilityTemplate],
    context: PreviewContext,
) -> list[tuple[str, str, str, SimulateBuildRequest, list[str]]]:
    primary, secondary = _target_economies(target)
    body_id = _first_body_id(context)
    simple = _placements_for(catalogue, body_id, [
        'colony_ship',
        _support_for(catalogue, primary),
        _support_for(catalogue, secondary),
    ])
    balanced = _placements_for(catalogue, body_id, [
        'colony_ship',
        _support_for(catalogue, primary),
        _support_for(catalogue, primary, offset=1),
        'coriolis_station',
        _support_for(catalogue, secondary),
    ])

    plans: list[tuple[str, str, str, SimulateBuildRequest, list[str]]] = []
    if simple:
        plans.append((
            'simple',
            'Simple recommended build',
            f'A low-risk starter plan focused on {primary} with a light {secondary} secondary economy.',
            SimulateBuildRequest(system_id64=system_id64, target_archetype=target, placements=simple),
            ['Lower ceiling than larger plans, but easier to reason about and adjust.'],
        ))
    if balanced:
        plans.append((
            'balanced',
            'Balanced recommended build',
            f'The default {primary} / {secondary} plan: enough support to test economy order before committing.',
            SimulateBuildRequest(system_id64=system_id64, target_archetype=target, placements=balanced),
            ['Build order matters; preview before swapping primary and secondary support.'],
        ))

    confidence = context.slot_confidence if context.slot_confidence is not None else 0.45
    total_slots = (context.estimated_orbital_slots or 0) + (context.estimated_ground_slots or 0)
    if confidence >= 0.6 and total_slots >= 3:
        advanced = _placements_for(catalogue, body_id, [
            'colony_ship',
            _support_for(catalogue, primary),
            _support_for(catalogue, primary, offset=1),
            _support_for(catalogue, secondary),
            'coriolis_station',
            'orbis_t3',
        ])
        if advanced:
            plans.append((
                'advanced',
                'Advanced high-capacity build',
                f'A higher-ceiling {primary} / {secondary} plan with T3 capacity pressure included.',
                SimulateBuildRequest(system_id64=system_id64, target_archetype=target, placements=advanced),
                ['Higher CP pressure; only shown when slot confidence is strong enough for a useful preview.'],
            ))

    return plans[:3]


def _placements_for(
    catalogue: dict[str, FacilityTemplate],
    body_id: Optional[str],
    facility_ids: list[Optional[str]],
) -> list[SimulateBuildPlacement]:
    placements: list[SimulateBuildPlacement] = []
    primary_assigned = False
    for facility_id in facility_ids:
        if not facility_id or facility_id not in catalogue:
            continue
        facility = catalogue[facility_id]
        is_primary = facility.is_port and not primary_assigned
        if is_primary:
            primary_assigned = True
        placements.append(SimulateBuildPlacement(
            facility_template_id=facility_id,
            local_body_id=body_id,
            is_primary_port=is_primary,
            build_order=len(placements) + 1,
        ))
    return placements


def _support_for(catalogue: dict[str, FacilityTemplate], economy: str, *, offset: int = 0) -> Optional[str]:
    matches = [
        f for f in catalogue.values()
        if f.economy == economy and f.is_support_facility
    ]
    matches.sort(key=lambda f: (f.tier, f.name))
    if not matches:
        return None
    return matches[min(offset, len(matches) - 1)].id


def _first_body_id(context: PreviewContext) -> Optional[str]:
    if not context.local_body_profiles:
        return None
    return sorted(context.local_body_profiles.keys())[0]


def _target_economies(target: str) -> tuple[str, str]:
    mapping = {
        'refinery_industrial':      ('Refinery', 'Industrial'),
        'extraction_refinery':      ('Extraction', 'Refinery'),
        'agriculture_terraforming': ('Agriculture', 'Industrial'),
        'hitech_tourism':           ('HighTech', 'Tourism'),
        'military_industrial':      ('Military', 'Industrial'),
        'trade_logistics':          ('Industrial', 'Extraction'),
        'flexible_multirole':       ('Industrial', 'Refinery'),
    }
    return mapping.get(target, ('Industrial', 'Refinery'))


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
