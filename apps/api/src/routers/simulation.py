"""
ED Finder — Simulation API Router
===================================
Version: 1.0.0

Endpoints:
    GET /api/systems/{id64}/slot-predictions    per-body slot predictions
    GET /api/systems/{id64}/buildability        full buildability analysis
    GET /api/systems/{id64}/simulation-summary  combined simulation + archetype summary

All endpoints:
  • Read from existing tables (body_scan_facts, system_slot_topology,
    system_archetype_scores, system_archetype_traits, buildability_analysis)
  • Compute on-demand when DB data is available; degrade gracefully when not
  • Include confidence labels at every layer
  • Cache via Redis (TTL 300s — shorter than system cache, data is fresher)

Design notes:
  • These endpoints are additive — they do NOT replace existing archetype
    or rating endpoints. They provide the "HOW to build" layer on top of
    the existing "WHERE to colonise" layer.
  • All computation happens in the simulation/ and domain/ modules.
    This router is purely HTTP plumbing + DB fetch + cache.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query

from config import log
from deps import get_pool, get_redis, cache_get, cache_set
from ingest.slot_prediction import predict_system_slots, confidence_label
from simulation.buildability import analyse_buildability
from simulation.topology_simulator import (
    topology_from_row, topology_from_traits, summarise_topology,
)

router = APIRouter(prefix='/api/systems', tags=['simulation'])

_CACHE_TTL = 300   # 5 minutes


# ---------------------------------------------------------------------------
# GET /api/systems/{id64}/slot-predictions
# ---------------------------------------------------------------------------
@router.get('/{id64}/slot-predictions')
async def get_slot_predictions(
    id64: int,
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    """
    Per-body slot predictions for a system.

    Returns predicted orbital and surface slot counts for each scanned body,
    with confidence scores and explainability reasons.

    Data source priority:
      1. body_scan_facts (EDDN-derived, highest confidence)
      2. bodies table (Spansh-imported, moderate confidence)
      3. No data → empty predictions with explanation
    """
    cache_key = f'sim:slots:{id64}'
    cached = await cache_get(cache_key, redis)
    if cached:
        return cached

    async with pool.acquire() as conn:
        # Try body_scan_facts first (EDDN-derived, better confidence)
        scan_facts = await conn.fetch("""
            SELECT system_address, body_id, body_name,
                   radius, mass_em, gravity,
                   planet_class, terraform_state, atmosphere,
                   has_geo, has_bio, geo_signal_count, bio_signal_count,
                   is_landable, is_terraformable, is_ringed,
                   data_sources, confidence
            FROM body_scan_facts
            WHERE system_address = $1
            ORDER BY body_id
        """, id64)

        # Fall back to bodies table (Spansh import)
        if not scan_facts:
            bodies = await conn.fetch("""
                SELECT
                    $1::bigint AS system_address,
                    id AS body_id,
                    name AS body_name,
                    radius,
                    NULL::float AS mass_em,
                    gravity,
                    subtype AS planet_class,
                    NULL AS terraform_state,
                    NULL AS atmosphere,
                    (geo_signal_count > 0) AS has_geo,
                    (bio_signal_count > 0) AS has_bio,
                    geo_signal_count,
                    bio_signal_count,
                    is_landable,
                    is_terraformable,
                    (LOWER(subtype) LIKE '%%ring%%') AS is_ringed,
                    ARRAY['spansh_import'] AS data_sources,
                    0.55::numeric AS confidence
                FROM bodies
                WHERE system_id64 = $1
                  AND body_type != 'Star'
                ORDER BY id
            """, id64)
            scan_facts = bodies

        # System exists check
        system_exists = await conn.fetchval(
            'SELECT 1 FROM systems WHERE id64 = $1', id64
        )
        if not system_exists:
            raise HTTPException(404, f'System {id64} not found')

    if not scan_facts:
        result = {
            'system_id64':             id64,
            'data_source':             'none',
            'body_count':              0,
            'estimated_orbital_slots': 0,
            'estimated_ground_slots':  0,
            'slot_confidence':         0.0,
            'slot_confidence_label':   'No Data',
            'predictions':             [],
            'note': (
                'No body scan data available for this system. '
                'Slot predictions require at least FSS scan data via EDDN. '
                'Visit this system and use the Full Spectrum Scanner to contribute data.'
            ),
        }
        await cache_set(cache_key, result, _CACHE_TTL, redis)
        return result

    facts = [dict(r) for r in scan_facts]
    prediction = predict_system_slots(facts)

    data_source = (
        'eddn' if facts and 'eddn_scan' in (facts[0].get('data_sources') or [])
        else 'spansh'
    )

    result = {
        'system_id64':             id64,
        'data_source':             data_source,
        'body_count':              len(facts),
        'estimated_orbital_slots': prediction['estimated_orbital_slots'],
        'estimated_ground_slots':  prediction['estimated_ground_slots'],
        'slot_confidence':         round(prediction['slot_confidence'], 3),
        'slot_confidence_label':   confidence_label(prediction['slot_confidence']),
        'predictions': [
            p.to_dict() for p in prediction['body_predictions']
            if p.orbital_slots > 0 or p.surface_slots > 0
        ],
    }

    await cache_set(cache_key, result, _CACHE_TTL, redis)
    return result


# ---------------------------------------------------------------------------
# GET /api/systems/{id64}/buildability
# ---------------------------------------------------------------------------
@router.get('/{id64}/buildability')
async def get_buildability(
    id64: int,
    archetype: Optional[str] = Query(None, description='Target archetype key'),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    """
    Full buildability analysis for a system.

    Returns:
      • Slot estimates (orbital + surface) with confidence
      • CP capacity (yellow + green)
      • Max T2/T3 port estimates
      • Bottleneck identification
      • Opportunities (ringed body, deep anchor, etc.)
      • Recommended build order (step-by-step)
      • Build complexity label
      • Topology summary (human-readable points)

    Data source priority:
      1. buildability_analysis (pre-computed, fastest)
      2. system_slot_topology + body_scan_facts (compute on demand)
      3. system_archetype_traits (fallback, lower confidence)
    """
    cache_key = f'sim:build:{id64}:{archetype or "auto"}'
    cached = await cache_get(cache_key, redis)
    if cached:
        return cached

    async with pool.acquire() as conn:
        # Check system exists
        system_row = await conn.fetchrow("""
            SELECT s.id64, s.name,
                   a.primary_archetype, a.overall_development_potential
            FROM systems s
            LEFT JOIN system_archetype_scores a ON a.system_id64 = s.id64
            WHERE s.id64 = $1
        """, id64)

        if not system_row:
            raise HTTPException(404, f'System {id64} not found')

        effective_archetype = archetype or system_row['primary_archetype']

        # Try pre-computed buildability analysis first
        ba_row = await conn.fetchrow("""
            SELECT * FROM buildability_analysis WHERE system_id64 = $1
        """, id64)

        # Topology row
        topo_row = await conn.fetchrow("""
            SELECT estimated_orbital_slots, estimated_ground_slots,
                   orbital_synergy, ground_synergy, build_flexibility,
                   contamination_risk, strong_link_potential,
                   weak_link_stability, nesting_potential,
                   has_viable_surface_port, has_deep_orbital_anchor,
                   has_ringed_gas_giant
            FROM system_slot_topology WHERE system_id64 = $1
        """, id64)

        # Traits row (fallback)
        traits_row = await conn.fetchrow("""
            SELECT est_orbital_slots, est_ground_slots,
                   has_ringed_body, total_body_count
            FROM system_archetype_traits WHERE system_id64 = $1
        """, id64)

    topo_dict   = dict(topo_row)  if topo_row   else None
    traits_dict = dict(traits_row) if traits_row else None

    # Determine slot inputs
    if topo_dict:
        ctx = topology_from_row(topo_dict)
    elif traits_dict:
        ctx = topology_from_traits(traits_dict)
    else:
        ctx = None

    # If we have pre-computed buildability AND no archetype override, use it
    if ba_row and not archetype:
        ba_dict = dict(ba_row)
        topology_summary = summarise_topology(ctx) if ctx else []
        result = {
            'system_id64':             id64,
            'system_name':             system_row['name'],
            'archetype':               effective_archetype,
            'source':                  'precomputed',
            **{k: ba_dict.get(k) for k in [
                'estimated_orbital_slots', 'estimated_ground_slots',
                'slot_confidence', 'estimated_yellow_cp_capacity',
                'estimated_green_cp_capacity', 'max_t2_ports_estimate',
                'max_t3_ports_estimate', 'cp_bottleneck_score',
                'slot_exhaustion_risk', 'build_order_sensitivity',
                'build_complexity', 'bottlenecks', 'opportunities',
                'recommended_build_order',
            ]},
            'slot_confidence_label':   _conf_label(ba_dict.get('slot_confidence', 0.0)),
            'topology_summary':        topology_summary,
            'topology':                ctx.to_dict() if ctx else None,
        }
        await cache_set(cache_key, result, _CACHE_TTL, redis)
        return result

    # Compute on demand
    if not ctx:
        result = {
            'system_id64':   id64,
            'system_name':   system_row['name'],
            'archetype':     effective_archetype,
            'source':        'insufficient_data',
            'build_complexity': 'unknown',
            'note': (
                'Insufficient topology data to compute buildability. '
                'Run build_topology.py to generate slot estimates for this system, '
                'or scan bodies in-game to contribute data via EDDN.'
            ),
        }
        await cache_set(cache_key, result, 60, redis)
        return result

    ba = analyse_buildability(
        system_id64=id64,
        orbital_slots=ctx.orbital_slots,
        surface_slots=ctx.surface_slots,
        slot_confidence=ctx.slot_confidence,
        has_ringed_body=ctx.has_ringed_body,
        has_viable_surface=ctx.has_viable_surface,
        has_deep_anchor=ctx.has_deep_anchor,
        archetype_key=effective_archetype,
        topo_row=topo_dict,
    )

    topology_summary = summarise_topology(ctx)

    result = {
        'system_id64':   id64,
        'system_name':   system_row['name'],
        'archetype':     effective_archetype,
        'source':        'computed',
        **ba.to_dict(),
        'topology_summary': topology_summary,
        'topology':         ctx.to_dict(),
    }

    await cache_set(cache_key, result, _CACHE_TTL, redis)
    return result


# ---------------------------------------------------------------------------
# GET /api/systems/{id64}/simulation-summary
# ---------------------------------------------------------------------------
@router.get('/{id64}/simulation-summary')
async def get_simulation_summary(
    id64: int,
    archetype: Optional[str] = Query(None, description='Target archetype key'),
    pool: asyncpg.Pool = Depends(get_pool),
    redis: Optional[aioredis.Redis] = Depends(get_redis),
):
    """
    Combined simulation + archetype summary for a system.

    This is the primary endpoint for the frontend simulation panel.
    Returns everything needed to render:
      • Archetype classification + scores
      • Buildability analysis
      • Slot predictions summary
      • Composition guidance
      • Recommended build strategy
      • Warnings and opportunities

    Aggregates data from:
      • mv_archetype_rankings (archetype scores)
      • system_slot_topology (topology)
      • buildability_analysis (pre-computed if available)
      • body_scan_facts or bodies (slot predictions)
    """
    cache_key = f'sim:summary:{id64}:{archetype or "auto"}'
    cached = await cache_get(cache_key, redis)
    if cached:
        return cached

    async with pool.acquire() as conn:
        # System + archetype scores
        mv_row = await conn.fetchrow("""
            SELECT
                m.id64, m.name, m.primary_archetype, m.secondary_archetype,
                m.archetype_confidence, m.overall_development_potential,
                m.buildability_score, m.build_complexity,
                m.purity_score, m.contamination_risk,
                m.est_total_slots, m.est_orbital_slots, m.est_ground_slots,
                m.topo_orbital_slots, m.topo_ground_slots,
                m.strong_link_potential, m.weak_link_stability,
                m.nesting_potential, m.orbital_synergy, m.ground_synergy,
                m.build_flexibility, m.topo_contamination_risk,
                m.has_viable_surface_port, m.has_deep_orbital_anchor,
                m.has_ringed_body, m.display_tags, m.confidence,
                m.elw_count, m.hmc_count, m.gas_giant_count,
                m.terraformable_count, m.bio_signal_total, m.geo_signal_total,
                m.distance_to_sol, m.main_star_type,
                a.score_breakdown, a.rationale,
                a.score_refinery_industrial, a.score_extraction_refinery,
                a.score_agriculture_terraforming, a.score_hitech_tourism,
                a.score_expansion_capital, a.score_trade_logistics,
                a.score_population_capital, a.score_ax_forward_base,
                a.score_military_industrial, a.score_flexible_multirole
            FROM mv_archetype_rankings m
            LEFT JOIN system_archetype_scores a ON a.system_id64 = m.id64
            WHERE m.id64 = $1
        """, id64)

        if not mv_row:
            # System exists but not in MV (no archetype scores yet)
            sys_row = await conn.fetchrow(
                'SELECT id64, name FROM systems WHERE id64 = $1', id64
            )
            if not sys_row:
                raise HTTPException(404, f'System {id64} not found')

        # Buildability (pre-computed)
        ba_row = await conn.fetchrow(
            'SELECT * FROM buildability_analysis WHERE system_id64 = $1', id64
        )

        # Body count for slot confidence context
        body_count = await conn.fetchval(
            'SELECT COUNT(*) FROM body_scan_facts WHERE system_address = $1', id64
        ) or await conn.fetchval(
            'SELECT COUNT(*) FROM bodies WHERE system_id64 = $1 AND body_type != $2',
            id64, 'Star'
        ) or 0

    effective_archetype = archetype or (
        mv_row['primary_archetype'] if mv_row else None
    )

    # ── Build response ────────────────────────────────────────────────────
    response: dict[str, Any] = {
        'system_id64': id64,
        'system_name': mv_row['name'] if mv_row else None,
        'archetype':   effective_archetype,
    }

    # Archetype classification
    if mv_row:
        response['classification'] = {
            'primary_archetype':    mv_row['primary_archetype'],
            'secondary_archetype':  mv_row['secondary_archetype'],
            'confidence':           float(mv_row['archetype_confidence'] or 0),
            'overall_potential':    float(mv_row['overall_development_potential'] or 0),
            'purity_score':         float(mv_row['purity_score'] or 0),
            'display_tags':         mv_row['display_tags'] or [],
            'data_confidence':      float(mv_row['confidence'] or 0),
            'rationale':            mv_row['rationale'],
        }

        # All archetype scores for radar display
        response['archetype_scores'] = {
            'refinery_industrial':       float(mv_row['score_refinery_industrial'] or 0),
            'extraction_refinery':       float(mv_row['score_extraction_refinery'] or 0),
            'agriculture_terraforming':  float(mv_row['score_agriculture_terraforming'] or 0),
            'hitech_tourism':            float(mv_row['score_hitech_tourism'] or 0),
            'expansion_capital':         float(mv_row['score_expansion_capital'] or 0),
            'trade_logistics':           float(mv_row['score_trade_logistics'] or 0),
            'population_capital':        float(mv_row['score_population_capital'] or 0),
            'ax_forward_base':           float(mv_row['score_ax_forward_base'] or 0),
            'military_industrial':       float(mv_row['score_military_industrial'] or 0),
            'flexible_multirole':        float(mv_row['score_flexible_multirole'] or 0),
        }

        # Body composition summary
        response['body_summary'] = {
            'elw_count':           mv_row['elw_count'] or 0,
            'hmc_count':           mv_row['hmc_count'] or 0,
            'gas_giant_count':     mv_row['gas_giant_count'] or 0,
            'terraformable_count': mv_row['terraformable_count'] or 0,
            'bio_signal_total':    mv_row['bio_signal_total'] or 0,
            'geo_signal_total':    mv_row['geo_signal_total'] or 0,
            'scanned_body_count':  body_count,
        }

    # Buildability
    if ba_row:
        ba = dict(ba_row)
        response['buildability'] = {
            'source':                  'precomputed',
            'estimated_orbital_slots': ba.get('estimated_orbital_slots', 0),
            'estimated_ground_slots':  ba.get('estimated_ground_slots', 0),
            'slot_confidence':         float(ba.get('slot_confidence', 0)),
            'slot_confidence_label':   _conf_label(float(ba.get('slot_confidence', 0))),
            'estimated_yellow_cp':     ba.get('estimated_yellow_cp_capacity', 0),
            'estimated_green_cp':      ba.get('estimated_green_cp_capacity', 0),
            'max_t2_ports':            ba.get('max_t2_ports_estimate', 0),
            'max_t3_ports':            ba.get('max_t3_ports_estimate', 0),
            'cp_bottleneck_score':     float(ba.get('cp_bottleneck_score', 0)),
            'slot_exhaustion_risk':    float(ba.get('slot_exhaustion_risk', 0)),
            'build_order_sensitivity': float(ba.get('build_order_sensitivity', 0)),
            'build_complexity':        ba.get('build_complexity', 'unknown'),
            'bottlenecks':             ba.get('bottlenecks', []),
            'opportunities':           ba.get('opportunities', []),
            'recommended_build_order': ba.get('recommended_build_order', []),
        }
    elif mv_row and (mv_row['topo_orbital_slots'] or mv_row['est_orbital_slots']):
        # Compute on demand from MV data
        orbital = int(mv_row['topo_orbital_slots'] or mv_row['est_orbital_slots'] or 0)
        surface = int(mv_row['topo_ground_slots']  or mv_row['est_ground_slots']  or 0)
        topo_dict = {
            'estimated_orbital_slots':  orbital,
            'estimated_ground_slots':   surface,
            'orbital_synergy':          mv_row['orbital_synergy'],
            'ground_synergy':           mv_row['ground_synergy'],
            'build_flexibility':        mv_row['build_flexibility'],
            'contamination_risk':       mv_row['topo_contamination_risk'],
            'strong_link_potential':    mv_row['strong_link_potential'],
            'weak_link_stability':      mv_row['weak_link_stability'],
            'nesting_potential':        mv_row['nesting_potential'],
            'has_viable_surface_port':  mv_row['has_viable_surface_port'],
            'has_deep_orbital_anchor':  mv_row['has_deep_orbital_anchor'],
            'has_ringed_gas_giant':     mv_row['has_ringed_body'],
        }
        from simulation.topology_simulator import topology_from_row
        ctx = topology_from_row(topo_dict)
        ba = analyse_buildability(
            system_id64=id64,
            orbital_slots=ctx.orbital_slots,
            surface_slots=ctx.surface_slots,
            slot_confidence=ctx.slot_confidence,
            has_ringed_body=ctx.has_ringed_body,
            has_viable_surface=ctx.has_viable_surface,
            has_deep_anchor=ctx.has_deep_anchor,
            archetype_key=effective_archetype,
            topo_row=topo_dict,
        )
        response['buildability'] = {
            'source': 'computed',
            **ba.to_dict(),
            'slot_confidence_label': _conf_label(ba.slot_confidence),
        }
    else:
        response['buildability'] = {
            'source':       'insufficient_data',
            'build_complexity': 'unknown',
            'note': 'Run build_topology.py to generate slot estimates, or scan bodies in-game.',
        }

    # Topology summary narrative
    if mv_row:
        topo_dict_for_ctx = {
            'estimated_orbital_slots': mv_row['topo_orbital_slots'] or mv_row['est_orbital_slots'] or 0,
            'estimated_ground_slots':  mv_row['topo_ground_slots']  or mv_row['est_ground_slots']  or 0,
            'orbital_synergy':         mv_row['orbital_synergy'],
            'ground_synergy':          mv_row['ground_synergy'],
            'build_flexibility':       mv_row['build_flexibility'],
            'contamination_risk':      mv_row['topo_contamination_risk'],
            'strong_link_potential':   mv_row['strong_link_potential'],
            'weak_link_stability':     mv_row['weak_link_stability'],
            'nesting_potential':       mv_row['nesting_potential'],
            'has_viable_surface_port': mv_row['has_viable_surface_port'],
            'has_deep_orbital_anchor': mv_row['has_deep_orbital_anchor'],
            'has_ringed_gas_giant':    mv_row['has_ringed_body'],
        }
        from simulation.topology_simulator import topology_from_row
        ctx = topology_from_row(topo_dict_for_ctx)
        response['topology_summary'] = summarise_topology(ctx)
        response['distance_to_sol']  = float(mv_row['distance_to_sol'] or 0)
        response['main_star_type']   = mv_row['main_star_type']

    await cache_set(cache_key, response, _CACHE_TTL, redis)
    return response


def _conf_label(v: float) -> str:
    if v >= 0.85: return 'High'
    if v >= 0.65: return 'Moderate'
    if v >= 0.45: return 'Low'
    return 'Estimated'
