from __future__ import annotations

from typing import Any, Optional

import asyncpg

from domain.colonisation_rules import TargetProfile, get_target_profile, profile_body
from domain.facilities import FacilityTemplate
from models import BuildabilityData, SimulateBuildPlacement
from mechanics.scoring_rules import (
    ADVANCED_PLAN_MIN_BODY_SCORE,
    ADVANCED_PLAN_MIN_SLOT_CONFIDENCE,
    ADVANCED_PLAN_MIN_TOTAL_SLOTS,
)
from recommendations.body_selector import BodyCandidate, select_body_candidates
from simulation.build_preview import PreviewContext, PreviewPlacement, simulate_build_preview


async def generate_optimiser_candidates(
    system_id64: int,
    target_archetype_key: Optional[str],
    catalogue: dict[str, FacilityTemplate],
    pool: asyncpg.Pool,
    max_candidates: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    full_preview_context, body_rows = await _get_preview_context_and_body_rows(pool, system_id64)
    warnings: list[str] = []
    optimiser_candidates: list[dict[str, Any]] = []

    target_profile = get_target_profile(target_archetype_key or 'flexible_multirole')

    if not target_profile.supported:
        return [], [target_profile.warning or 'Recommended build rules are not implemented for this archetype yet.']

    # Select body candidates based on the target archetype
    body_candidates = select_body_candidates(
        archetype=target_profile.key,
        target=target_profile,
        rows=body_rows,
        limit=max_candidates * 2,
    )

    if not body_candidates:
        return [], ['No suitable body candidates found for this archetype.']

    seen_candidate_ids: set[str] = set()
    for body_candidate in body_candidates:
        primary = target_profile.primary_economies[0] if target_profile.primary_economies else None
        secondary = target_profile.secondary_economies[0] if target_profile.secondary_economies else None

        plan_configs = [
            (
                'simple',
                'Simple recommended build',
                ['colony_ship', _support_for(catalogue, primary)],
                ['Lower ceiling than larger plans, but easier to verify in-game.'],
            ),
            ('balanced', 'Balanced recommended build', [
                'colony_ship',
                _support_for(catalogue, primary),
                _support_for(catalogue, primary, offset=1),
                _preferred_t2_port(catalogue, target_profile, body_candidate.profile),
            ], ['Build order matters; preview before swapping support facilities.']),
        ]

        total_slots = (full_preview_context.estimated_orbital_slots or 0) + (full_preview_context.estimated_ground_slots or 0)
        if _can_generate_advanced(full_preview_context.slot_confidence, total_slots, body_candidate) and 'orbis_t3' in catalogue:
            advanced_ids = [
                'colony_ship',
                _support_for(catalogue, primary),
                _support_for(catalogue, primary, offset=1),
                _support_for(catalogue, secondary),
                _preferred_t2_port(catalogue, target_profile, body_candidate.profile),
                'orbis_t3',
            ]
            plan_configs.append((
                'advanced',
                'Advanced high-capacity build',
                advanced_ids,
                ['Higher CP pressure; only shown when slot confidence and body suitability support it.'],
            ))

        for plan_id_suffix, label_prefix, facility_ids, tradeoffs in plan_configs:
            candidate_id = f'{target_profile.key}-{body_candidate.body_id}-{plan_id_suffix}'
            if candidate_id in seen_candidate_ids:
                continue

            placements = _placements_for(catalogue, body_candidate.body_id, facility_ids)

            if not placements:
                continue

            # Merge the body-specific profile into the full context
            if body_candidate.body_id:
                full_preview_context.local_body_profiles[body_candidate.body_id] = body_candidate.profile.to_context_profile()

            preview_placements = [
                PreviewPlacement(
                    facility_template_id=p.facility_template_id,
                    local_body_id=p.local_body_id,
                    is_primary_port=p.is_primary_port,
                    build_order=p.build_order,
                )
                for p in placements
            ]

            simulation_result = simulate_build_preview(
                system_id64=system_id64,
                target_archetype=target_profile.key,
                placements=preview_placements,
                catalogue=catalogue,
                context=full_preview_context,
            )

            optimiser_candidates.append({
                'id': candidate_id,
                'label': f'{label_prefix} for {body_candidate.body_name}',
                'description': body_candidate.reason,
                'archetype': target_profile.key,
                'placements': placements,
                'preview_summary': BuildabilityData.model_validate({
                    'source': 'computed',
                    'estimated_orbital_slots': full_preview_context.estimated_orbital_slots,
                    'estimated_ground_slots': full_preview_context.estimated_ground_slots,
                    'slot_confidence': full_preview_context.slot_confidence,
                    'slot_confidence_label': None,
                    'estimated_yellow_cp': simulation_result['cp']['yellow_cp_final'],
                    'estimated_green_cp': simulation_result['cp']['green_cp_final'],
                    'score': simulation_result.get('buildability_score'),
                    'warnings': simulation_result.get('warnings', []),
                    'recommendations': simulation_result.get('recommendations', []),
                }),
                'tradeoffs': tradeoffs,
            })
            seen_candidate_ids.add(candidate_id)

            if len(optimiser_candidates) >= max_candidates:
                break
        if len(optimiser_candidates) >= max_candidates:
            break

    return optimiser_candidates, warnings


async def _get_preview_context_and_body_rows(pool: asyncpg.Pool, system_id64: int) -> tuple[PreviewContext, list[dict[str, Any]]]:
    """Fetch system data and construct a PreviewContext."""
    async with pool.acquire() as conn:
        system_row = await conn.fetchrow(
            """SELECT * FROM systems WHERE system_id64 = $1""",
            system_id64,
        )
        if not system_row:
            return PreviewContext(system_id64=system_id64), []

        body_rows = await conn.fetch(
            """SELECT * FROM bodies WHERE system_id64 = $1""",
            system_id64,
        )

        local_body_profiles = {}
        for row in body_rows:
            profile = profile_body(row)
            if profile.body_id:
                local_body_profiles[profile.body_id] = profile.to_context_profile()

        return PreviewContext(
            system_id64=system_id64,
            estimated_orbital_slots=system_row.get("estimated_orbital_slots"),
            estimated_ground_slots=system_row.get("estimated_ground_slots"),
            slot_confidence=system_row.get("slot_confidence"),
            has_ringed_body=system_row.get("has_ringed_body"),
            local_body_profiles=local_body_profiles,
            mechanics_notes=[],
            observed_facts=[]
        ), [dict(row) for row in body_rows]


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
        primary_assigned = primary_assigned or is_primary
        placements.append(SimulateBuildPlacement(
            facility_template_id=facility_id,
            local_body_id=body_id,
            is_primary_port=is_primary,
            build_order=len(placements) + 1,
        ))
    return placements


def _support_for(catalogue: dict[str, FacilityTemplate], economy: Optional[str], *, offset: int = 0) -> Optional[str]:
    if not economy:
        return None
    matches = [f for f in catalogue.values() if f.economy == economy and f.is_support_facility]
    matches.sort(key=lambda f: (f.tier, f.name))
    return matches[min(offset, len(matches) - 1)].id if matches else None


def _preferred_t2_port(
    catalogue: dict[str, FacilityTemplate],
    target: TargetProfile,
    body_profile: Any,
) -> Optional[str]:
    if 'ringed' in body_profile.strategic_tags and 'asteroid_base' in catalogue:
        return 'asteroid_base'
    if any('landable' == tag for tag in body_profile.strategic_tags):
        if target.key in {'agriculture_terraforming', 'military_industrial'} and 'planetary_port' in catalogue:
            return 'planetary_port'
    return 'coriolis_station' if 'coriolis_station' in catalogue else None


def _can_generate_advanced(slot_confidence: Optional[float], total_slots: int, body: BodyCandidate) -> bool:
    return bool(
        slot_confidence is not None
        and slot_confidence >= ADVANCED_PLAN_MIN_SLOT_CONFIDENCE
        and total_slots >= ADVANCED_PLAN_MIN_TOTAL_SLOTS
        and body.score >= ADVANCED_PLAN_MIN_BODY_SCORE
    )


def _summary(label: str, target: TargetProfile, body: BodyCandidate) -> str:
    body_label = body.body_name or f'Body {body.body_id}'
    if target.primary_economies:
        economies = ' / '.join([*target.primary_economies, *target.secondary_economies])
        return f'{label} for {economies}, anchored on {body_label}.'
    return f'{label} focused on slot capacity and flexible economy options, anchored on {body_label}.'


def _mechanics_basis(target: TargetProfile, body: BodyCandidate) -> list[str]:
    notes = [body.reason]
    if target.strategic_tags:
        notes.append(f"Target strategic tags: {', '.join(target.strategic_tags)}.")
    if body.profile.modifier_economies:
        notes.append(f"Modifier economies detected: {', '.join(body.profile.modifier_economies)}.")
    return notes
