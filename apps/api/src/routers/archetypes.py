"""
ED Finder — Archetype API Router
Version: 1.0

Endpoints:
    GET  /api/archetypes/rankings          ranked list by archetype + filters
    POST /api/archetypes/rerank            rerank a set of systems by archetype weights
    GET  /api/archetypes/system/{id64}     full archetype breakdown for one system
    POST /api/archetypes/simulate          build simulation scoring
    GET  /api/archetypes/profiles          preset rerank profiles

`/rankings` (F3 Task 4) reads generation-pinned from the published V3
`v3_app.system_archetype`/`v3_app.system_search` projections via the ranking
profile (`edfinder_api.ranking`) — it no longer touches the legacy
`mv_archetype_rankings` materialized view and has no cache layer. The
remaining routes (`/rerank`, `/system/{id64}`, `/simulate`, `/profiles`) are
still legacy V2: `/rerank` and `/system/{id64}` read `system_archetype_scores`
directly; `/simulate` and `/profiles` are unaffected either way. They are out
of scope for this task (tracked as F3 slice 2).

Cache strategy (legacy routes only):
    system    → Redis key arch:v{ver}:sys:{id64}                                   TTL 300s
    rerank    → Redis key arch:v{ver}:rerank:{hash}                                TTL 120s
    profiles  → Redis key arch:profiles                                            TTL 3600s

Route scope:
    Development rerank and archetype endpoints live under /api/archetypes/*.
"""

import hashlib
import json
import math
import time
from typing import Any, Optional

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request

from edfinder_api.config import log, limiter
from edfinder_api.ingest.slot_prediction import INSUFFICIENT_DATA_REASON, predict_system_slots
from edfinder_api.local_search import _current_derived_generation
from edfinder_api.mechanics.confidence import (
    ConfidenceLayer,
    archetype_numeric_confidence_to_canonical,
)
from edfinder_api.models import (
    ArchetypeRankingsResponse,
    ArchetypeRerankRequest,
    ArchetypeRerankResponse,
    ArchetypeRerankWeights,
    ArchetypesProfilesResponse,
    BuildSimulateRequest,
    BuildSimulateResponse,
    SystemArchetypeResponse,
)
from edfinder_api.ranking.profile import (
    ARCHETYPE_KEYS,
    PROFILE_SPEC,
    RANKING_VERSION,
    TIER_THRESHOLDS,
    ranking_sha256,
)
from edfinder_api.ranking.ranking_sql import build_count_query, build_ranked_query
from edfinder_api.state import get_pool_singleton as get_pool, get_redis_singleton as get_redis

router = APIRouter(prefix='/api/archetypes', tags=['archetypes'])

# ---------------------------------------------------------------------------
# Archetype metadata (mirrors ARCHETYPE_DEFINITIONS in build_archetype_scores.py)
# ---------------------------------------------------------------------------
_ARCHETYPE_LABELS: dict[str, str] = {
    'refinery_industrial':       'Refinery / Industrial Megacomplex',
    'extraction_refinery':       'Extraction / Refinery Mining Hub',
    'agriculture_terraforming':  'Agriculture / Terraforming Colony',
    'hitech_tourism':            'HighTech / Tourism Prestige Colony',
    'expansion_capital':         'Expansion Capital',
    'trade_logistics':           'Trade / Logistics Hub',
    'population_capital':        'Population Capital',
    'ax_forward_base':           'AX Forward Operating Base',
    'military_industrial':       'Military / Industrial Complex',
    'flexible_multirole':        'Flexible Multi-Role Colony',
}

_SCORE_COL: dict[str, str] = {
    'refinery_industrial':      'score_refinery_industrial',
    'extraction_refinery':      'score_extraction_refinery',
    'agriculture_terraforming': 'score_agriculture_terraforming',
    'hitech_tourism':           'score_hitech_tourism',
    'expansion_capital':        'score_expansion_capital',
    'trade_logistics':          'score_trade_logistics',
    'population_capital':       'score_population_capital',
    'ax_forward_base':          'score_ax_forward_base',
    'military_industrial':      'score_military_industrial',
    'flexible_multirole':       'score_flexible_multirole',
}

# V3-native archetype labels (F3 Task 4). `ARCHETYPE_KEYS` (imported from
# `edfinder_api.ranking.profile`) is the 8-key set the V3 `system_archetype`
# builder (`scripts/v3_system_archetype_model.py`) actually scores every
# system against -- distinct from the 10-key legacy `_SCORE_COL`/
# `_ARCHETYPE_LABELS` set above, which stays wired to `/rerank`, `/system`
# and `/simulate` (untouched by this task).
_V3_ARCHETYPE_LABELS: dict[str, str] = {
    'paradise':            'Paradise World',
    'mining_hub':          'Mining Hub',
    'manufacturing_hub':   'Manufacturing Hub',
    'megacomplex':         'Megacomplex',
    'research_hub':        'Research Hub',
    'stronghold':          'Stronghold',
    'population_capital':  'Population Capital',
    'flexible':            'Flexible Multi-Role Colony',
}

# Preset rerank profiles
_PROFILES = [
    {
        'id':          'industrial_empire',
        'label':       'Industrial Empire',
        'description': 'Refinery/Industrial megacomplex — maximum manufacturing output',
        'archetype':   'refinery_industrial',
        'weights': {'purity': 0.35, 'buildability': 0.25, 'slots': 0.20,
                    'expansion': 0.10, 'logistics': 0.10},
    },
    {
        'id':          'space_farms',
        'label':       'Space Farms',
        'description': 'Agriculture and terraforming — maximum population growth',
        'archetype':   'agriculture_terraforming',
        'weights': {'purity': 0.30, 'buildability': 0.20, 'slots': 0.20,
                    'expansion': 0.20, 'logistics': 0.10},
    },
    {
        'id':          'prestige_capital',
        'label':       'Prestige Capital',
        'description': 'HighTech / Tourism prestige colony — ELW and exotic stars',
        'archetype':   'hitech_tourism',
        'weights': {'purity': 0.25, 'buildability': 0.20, 'slots': 0.15,
                    'expansion': 0.20, 'logistics': 0.20},
    },
    {
        'id':          'ax_logistics',
        'label':       'AX Logistics Hub',
        'description': 'Military / HighTech anti-xeno forward base',
        'archetype':   'ax_forward_base',
        'weights': {'purity': 0.20, 'buildability': 0.30, 'slots': 0.20,
                    'expansion': 0.15, 'logistics': 0.15},
    },
    {
        'id':          'expansion_capital',
        'label':       'Expansion Capital',
        'description': 'Flexible system for multi-jump colonisation chains',
        'archetype':   'expansion_capital',
        'weights': {'purity': 0.15, 'buildability': 0.20, 'slots': 0.25,
                    'expansion': 0.25, 'logistics': 0.15},
    },
    {
        'id':          'mining_hub',
        'label':       'Mining Hub',
        'description': 'Extraction / Refinery — HMC and metal-rich focus',
        'archetype':   'extraction_refinery',
        'weights': {'purity': 0.25, 'buildability': 0.30, 'slots': 0.25,
                    'expansion': 0.10, 'logistics': 0.10},
    },
    {
        'id':          'generalist',
        'label':       'Generalist',
        'description': 'Balanced weights — no strong archetype preference',
        'archetype':   None,
        'weights': {'purity': 0.20, 'buildability': 0.20, 'slots': 0.20,
                    'expansion': 0.20, 'logistics': 0.20},
    },
]


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

# A Redis outage degrades every request to a DB read, which is correct
# behavior — but with a bare `except Exception: pass`, that outage was
# previously invisible: no log line, no metric, nothing to distinguish it
# from a mysterious latency regression. Throttled so a sustained outage
# logs once per interval, not once per request.
_CACHE_ERROR_LOG_INTERVAL_SECONDS = 60
# None, not 0.0: time.monotonic()'s reference point is platform-defined and
# commonly host-boot-relative, not guaranteed far from zero — a literal 0.0
# sentinel would suppress the first failure (and everything for up to 60s
# after it) whenever `now` itself is under 60, e.g. shortly after a host
# reboot. None always compares as "never logged yet" regardless of what
# time.monotonic() actually returns.
_last_cache_error_logged_at: float | None = None


def _log_cache_error_throttled(where: str, exc: Exception) -> None:
    global _last_cache_error_logged_at
    now = time.monotonic()
    if _last_cache_error_logged_at is None or now - _last_cache_error_logged_at >= _CACHE_ERROR_LOG_INTERVAL_SECONDS:
        _last_cache_error_logged_at = now
        log.warning('Archetype cache %s failed, degrading to DB: %s', where, exc)


async def _cache_version(redis) -> int:
    """Return the current cache version counter (default 1)."""
    if redis is None:
        return 1
    try:
        v = await redis.get('arch:version')
        return int(v) if v else 1
    except Exception as exc:
        _log_cache_error_throttled('version', exc)
        return 1


async def _cache_get(redis, key: str) -> Optional[Any]:
    if redis is None:
        return None
    try:
        raw = await redis.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        _log_cache_error_throttled('get', exc)
        return None


async def _cache_set(redis, key: str, value: Any, ttl: int = 300):
    if redis is None:
        return
    try:
        await redis.set(key, json.dumps(value), ex=ttl)
    except Exception as exc:
        _log_cache_error_throttled('set', exc)


def _json_object(value: Any) -> dict[str, Any]:
    """Normalise JSON-ish DB values into plain dicts for response models.

    Some environments hand JSONB columns back as already-decoded dicts,
    while others surface text that still needs json.loads(). Keep the
    response contract stable either way.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


def _rationale_with_canonical_confidence(rationale: dict[str, Any]) -> dict[str, Any]:
    """Enrich archetype rationale with canonical confidence if data_confidence present.

    Converts numeric data_confidence to canonical form for EDRE-aligned workflows.
    """
    if not rationale or not isinstance(rationale.get('data_confidence'), (int, float)):
        return rationale

    data_confidence_score = float(rationale['data_confidence'])
    canonical = archetype_numeric_confidence_to_canonical(
        data_confidence_score,
        layer=ConfidenceLayer.PROJECTED_OPERATIONAL,
        reason=f'Body-data completeness: {data_confidence_score:.1%}',
    )
    rationale['canonical_confidence'] = canonical.to_dict()
    return rationale
    return {}


# ---------------------------------------------------------------------------
# GET /api/archetypes/rankings (F3 Task 4 — V3, generation-pinned)
# ---------------------------------------------------------------------------
# Repointed off the legacy `mv_archetype_rankings` materialized view onto the
# published V3 `v3_app.system_archetype` / `v3_app.system_search` projections
# via `ranking.ranking_sql.build_ranked_query`/`build_count_query`, mirroring
# the `local_db_search_v3` pattern in `edfinder_api.local_search` (F3 Task 3):
# a plain, DB-pool-taking helper function that the thin, rate-limited route
# handler delegates to, so the helper stays directly unit-testable without
# going through slowapi's `Request`-bound limiter decorator.
#
# `min_slots` and `max_contamination` have no `v3_app.system_archetype`
# column at all (no slot-count or contamination projection exists in the F2b
# relation) -- like `local_db_search_v3`'s population-filter handling, a
# caller who explicitly asks for either gets a clear 422 rather than a
# silently-ignored filter. `has_elw` maps onto the elw_count range filters:
# true -> `elw_count_min = 1` (at least one ELW), false -> `elw_count_max = 0`
# (exactly zero), so both directions are honoured rather than dropped.
#
# `max_distance_ly` and the always-shown `distance_to_sol` both measure from
# Sol at the coordinate origin (the same `(0, 0, 0)` convention
# `local_search.py`'s `SOL_ID64` guard and the legacy
# `SQRT(x*x + y*y + z*z)` this endpoint replaces both rely on), so
# `reference_coords` is always `(0.0, 0.0, 0.0)` here -- never `None`.
async def _archetype_rankings_v3(
    *,
    archetype: str,
    min_score: int,
    galaxy_region: Optional[int],
    max_distance_ly: Optional[float],
    has_elw: Optional[bool],
    min_slots: Optional[int],
    max_contamination: Optional[float],
    limit: int,
    offset: int,
    pool: asyncpg.Pool,
) -> dict:
    t0 = time.monotonic()

    if archetype not in ARCHETYPE_KEYS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown archetype '{archetype}'. "
                f"Valid values: {sorted(ARCHETYPE_KEYS)}"
            ),
        )
    if min_slots is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                'min_slots is not supported by V3 archetype rankings '
                '(v3_app.system_archetype has no slot-count column).'
            ),
        )
    if max_contamination is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                'max_contamination is not supported by V3 archetype rankings '
                '(v3_app.system_archetype has no contamination column).'
            ),
        )
    hard_filters: dict[str, Any] = {'min_development_score': min_score}
    if galaxy_region is not None:
        hard_filters['galaxy_region'] = galaxy_region
    if max_distance_ly is not None:
        hard_filters['max_distance_ly'] = max_distance_ly
    # has_elw True -> at least one ELW (elw_count >= 1); False -> exactly zero
    # (elw_count <= 0). Both are now expressible via the elw_count_min /
    # elw_count_max hard filters, so has_elw=false is honoured rather than 422'd.
    if has_elw is True:
        hard_filters['elw_count_min'] = 1
    elif has_elw is False:
        hard_filters['elw_count_max'] = 0

    reference_coords = (0.0, 0.0, 0.0)

    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=archetype,
        picked_economy=None,
        hard_filters=hard_filters,
        reference_coords=reference_coords,
        limit=limit,
        offset=offset,
    )
    count_sql, count_params = build_count_query(
        PROFILE_SPEC,
        picked_archetype=archetype,
        picked_economy=None,
        hard_filters=hard_filters,
        reference_coords=reference_coords,
    )

    try:
        async with pool.acquire() as conn:
            # REPEATABLE READ so the generation pin, the ranked page and the
            # COUNT share one snapshot — a governed publish mid-request can no
            # longer return a page and a total from two different generations.
            async with conn.transaction(isolation='repeatable_read', readonly=True):
                generation_row = await _current_derived_generation(conn)
                rows = await conn.fetch(sql, *params)
                total = await conn.fetchval(count_sql, *count_params)
    except HTTPException:
        raise
    except (asyncpg.exceptions.UndefinedTableError,
            asyncpg.exceptions.InvalidSchemaNameError) as exc:
        raise HTTPException(503, 'Archetype rankings are unavailable') from exc
    except asyncpg.PostgresError as e:
        log.error('archetypes.rankings DB error: %s', e)
        raise HTTPException(
            status_code=503,
            detail={'type': 'https://httpstatuses.com/503',
                    'title': 'Database error', 'status': 503, 'detail': str(e)},
        )

    query_ms = int((time.monotonic() - t0) * 1000)
    results = [_build_v3_ranking_row(row, archetype) for row in rows]

    return {
        'archetype':       archetype,
        'archetype_label': _V3_ARCHETYPE_LABELS.get(archetype, archetype),
        'results':         results,
        'total':           int(total) if total is not None else len(results),
        'count':           len(results),
        'source':          f'v3:{RANKING_VERSION}',
        'query_ms':        query_ms,
        'ranking': {
            'ranking_version': RANKING_VERSION,
            'ranking_sha256': ranking_sha256(),
            'derived_generation_id': generation_row['derived_generation_id'],
            'publication_sequence': generation_row['publication_sequence'],
        },
    }


def _v3_ranking_tier(score: Any) -> str:
    s = float(score or 0)
    if s >= TIER_THRESHOLDS['S']:
        return 'S'
    if s >= TIER_THRESHOLDS['A']:
        return 'A'
    if s >= TIER_THRESHOLDS['B']:
        return 'B'
    if s >= TIER_THRESHOLDS['C']:
        return 'C'
    return 'D'


def _build_v3_ranking_row(row: asyncpg.Record, archetype: str) -> dict:
    """Shape one `build_ranked_query` row into an `ArchetypeRankingRow`.

    `build_ranked_query` selects `s.*` (the `v3_app.system_search` columns)
    plus `primary_score` (= `a.archetype_score` for a picked archetype),
    `ranking_confidence` (= the raw `a.confidence` confidence factor the
    uncertainty modifier reads), and `uncertainty_factor`
    (= `a.confidence * s.completeness`). `archetype_confidence` is read
    directly from `ranking_confidence` rather than reconstructed by dividing
    `uncertainty_factor` back out by `completeness` -- the division is
    undefined at `completeness = 0` and conflates the archetype's judgement
    confidence with the general data-completeness fraction.
    """
    x, y, z = row.get('x_ly'), row.get('y_ly'), row.get('z_ly')
    distance_to_sol = (
        round(math.sqrt(x * x + y * y + z * z), 2)
        if x is not None and y is not None and z is not None
        else None
    )

    completeness = row.get('completeness')
    ranking_confidence = row.get('ranking_confidence')
    archetype_confidence = (
        round(float(ranking_confidence), 4) if ranking_confidence is not None else None
    )

    score = float(row['primary_score']) if row['primary_score'] is not None else 0.0
    elw_count = row.get('elw_count')

    return {
        'id64':                row['system_id64'],
        'name':                row['name'],
        'coords':              {'x': x, 'y': y, 'z': z},
        'distance_to_sol':     distance_to_sol,
        'score':               score,
        'tier':                _v3_ranking_tier(score),
        # The system's ACTUAL primary/secondary archetype and overall best
        # potential, read from the summary (finding #20) -- not the requested
        # archetype. The requested one is exposed as `selected_archetype`.
        'selected_archetype':  archetype,
        'primary_archetype':   row.get('summary_primary_archetype'),
        'secondary_archetype': row.get('summary_secondary_archetype'),
        'archetype_confidence': archetype_confidence,
        'overall_development_potential': (
            float(row['summary_best_colony_potential'])
            if row.get('summary_best_colony_potential') is not None else None
        ),
        'buildability_score':  None,
        'build_complexity':    None,
        'purity_score':        None,
        'contamination_risk':  None,
        'confidence':          archetype_confidence,
        'has_elw':             bool(elw_count) if elw_count is not None else None,
        'elw_count':           elw_count,
        'landable_count':      row.get('landable_count'),
        'est_total_slots':     None,
        'tags':                [],
        'completeness':        completeness,
    }


@router.get(
    '/rankings',
    response_model=ArchetypeRankingsResponse,
    summary='Ranked systems by colony archetype',
    description=(
        'Returns systems ranked by a specific colony archetype score, read '
        'generation-pinned from the published V3 `v3_app.system_archetype` '
        'projection via the ranking profile.'
    ),
)
@limiter.limit('60/minute')
async def get_archetype_rankings(
    request: Request,
    archetype:       str            = Query(..., description='Colony archetype key'),
    min_score:       int            = Query(40,  ge=0,   le=100),
    galaxy_region:   Optional[int]  = Query(None, ge=0, le=2_147_483_647),
    max_distance_ly: Optional[float]= Query(None, ge=0),
    has_elw:         Optional[bool] = Query(None),
    min_slots:       Optional[int]  = Query(None, ge=0),
    max_contamination: Optional[float] = Query(None, ge=0, le=100),
    limit:           int            = Query(50,  ge=1,  le=500),
    offset:          int            = Query(0,   ge=0),
):
    pool = get_pool()
    return await _archetype_rankings_v3(
        archetype=archetype,
        min_score=min_score,
        galaxy_region=galaxy_region,
        max_distance_ly=max_distance_ly,
        has_elw=has_elw,
        min_slots=min_slots,
        max_contamination=max_contamination,
        limit=limit,
        offset=offset,
        pool=pool,
    )


# ---------------------------------------------------------------------------
# POST /api/archetypes/rerank
# ---------------------------------------------------------------------------

@router.post(
    '/rerank',
    response_model=ArchetypeRerankResponse,
    summary='Rerank systems by custom archetype weights',
)
@limiter.limit('30/minute')
async def post_archetype_rerank(request: Request, body: ArchetypeRerankRequest):
    t0 = time.monotonic()

    if not body.id64s:
        raise HTTPException(status_code=422, detail='id64s list is required')
    if len(body.id64s) > 500:
        raise HTTPException(status_code=422, detail='Maximum 500 systems per rerank request')

    # Resolve weights: use profile if provided, else body.weights, else defaults
    weights = _resolve_weights(body)

    # Resolve archetype score column
    archetype   = body.archetype
    score_col   = _SCORE_COL.get(archetype, 'overall_development_potential') if archetype else \
                  'overall_development_potential'

    # Cache key
    redis = get_redis()
    cache_key = _rerank_cache_key(body.id64s, weights, archetype)
    cached = await _cache_get(redis, cache_key)
    if cached:
        cached['_cached'] = True
        return cached

    # Fetch from DB
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    a.system_id64           AS id64,
                    a.{score_col}           AS archetype_score,
                    a.purity_score,
                    a.buildability_score,
                    t.est_total_slots       AS slots,
                    a.overall_development_potential AS expansion,
                    CASE WHEN s.main_star_type IN ('O','B','A','F','G','K','M')
                         THEN 80 ELSE 40 END AS logistics,
                    a.confidence,
                    a.rationale
                FROM system_archetype_scores a
                JOIN systems s              ON s.id64 = a.system_id64
                JOIN system_archetype_traits t ON t.system_id64 = a.system_id64
                WHERE a.system_id64 = ANY($1::bigint[])
                  AND a.dirty = FALSE
            """.format(score_col=score_col), body.id64s)
    except asyncpg.PostgresError as e:
        log.error('archetypes.rerank DB error: %s', e)
        raise HTTPException(
            status_code=503,
            detail={'type': 'https://httpstatuses.com/503',
                    'title': 'Database error', 'status': 503, 'detail': str(e)},
        )

    # Apply weights
    reranked = []
    for row in rows:
        raw = (
            float(row['purity_score'] or 0)      * weights.purity +
            float(row['buildability_score'] or 0) * weights.buildability +
            float(row['slots'] or 0)              * weights.slots +
            float(row['expansion'] or 0)          * weights.expansion +
            float(row['logistics'] or 0)          * weights.logistics
        )
        reranked.append({
            'id64':             row['id64'],
            'reranked_score':   int(round(raw)),
            'original_score':   round(float(row['archetype_score'] or 0), 2),
            'confidence':       round(float(row['confidence'] or 0.85), 3),
            'rationale':        _rationale_with_canonical_confidence(_json_object(row['rationale'])),
        })

    reranked.sort(key=lambda r: r['reranked_score'], reverse=True)

    query_ms = int((time.monotonic() - t0) * 1000)
    response = {
        'archetype':       archetype,
        'profile_applied': body.profile,
        'weights_applied': weights.model_dump(),
        'results':         reranked,
        'query_ms':        query_ms,
    }
    await _cache_set(redis, cache_key, response, ttl=120)
    return response


# ---------------------------------------------------------------------------
# GET /api/archetypes/system/{id64}
# ---------------------------------------------------------------------------

@router.get(
    '/system/{id64}',
    response_model=SystemArchetypeResponse,
    summary='Full archetype breakdown for a single system',
)
@limiter.limit('120/minute')
async def get_system_archetypes(request: Request, id64: int):
    t0 = time.monotonic()

    redis     = get_redis()
    ver       = await _cache_version(redis)
    cache_key = f"arch:v{ver}:sys:{id64}"

    cached = await _cache_get(redis, cache_key)
    if cached:
        cached['_cached'] = True
        return cached

    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            # System + archetype scores
            row = await conn.fetchrow("""
                SELECT
                    s.id64, s.name, s.x, s.y, s.z,
                    SQRT(s.x*s.x + s.y*s.y + s.z*s.z) AS distance_to_sol,
                    s.main_star_type,
                    a.primary_archetype, a.secondary_archetype,
                    a.archetype_confidence,
                    a.score_refinery_industrial,
                    a.score_extraction_refinery,
                    a.score_agriculture_terraforming,
                    a.score_hitech_tourism,
                    a.score_expansion_capital,
                    a.score_trade_logistics,
                    a.score_population_capital,
                    a.score_ax_forward_base,
                    a.score_military_industrial,
                    a.score_flexible_multirole,
                    a.overall_development_potential,
                    a.buildability_score, a.build_complexity,
                    a.cp_efficiency, a.t3_scaling_viability, a.slot_efficiency,
                    a.purity_score, a.contamination_risk, a.stable_top_two_prob,
                    a.confidence,
                    a.rationale,
                    a.score_breakdown
                FROM systems s
                JOIN system_archetype_scores a ON a.system_id64 = s.id64
                WHERE s.id64 = $1
                  AND a.dirty = FALSE
            """, id64)

            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail=f'System {id64} not found or archetype scores not yet computed',
                )

            # Topology
            topo_row = await conn.fetchrow("""
                SELECT estimated_orbital_slots, estimated_ground_slots,
                       estimated_total_slots, strong_link_potential,
                       weak_link_stability, contamination_risk AS topo_contamination,
                       orbital_synergy, ground_synergy, nesting_potential,
                       build_flexibility, has_viable_surface_port,
                       has_deep_orbital_anchor, has_ringed_gas_giant
                FROM system_slot_topology WHERE system_id64 = $1
            """, id64)

            # Pair synergy rows
            pair_rows = await conn.fetch("""
                SELECT economy_a, economy_b, synergy_score, purity_achievable,
                       contamination_paths
                FROM economy_pair_synergy
                WHERE system_id64 = $1
                ORDER BY synergy_score DESC
                LIMIT 10
            """, id64)

            # Traits
            trait_row = await conn.fetchrow("""
                SELECT display_tags, est_total_slots, landable_count,
                       elw_count, gas_giant_count, total_body_count
                FROM system_archetype_traits WHERE system_id64 = $1
            """, id64)

            slot_fact_rows = await conn.fetch("""
                SELECT
                    system_address,
                    body_id,
                    body_name,
                    radius,
                    gravity,
                    surface_temp,
                    planet_class,
                    terraform_state,
                    atmosphere,
                    volcanism,
                    has_geo,
                    has_bio,
                    geo_signal_count,
                    bio_signal_count,
                    is_landable,
                    is_terraformable,
                    CASE
                        WHEN EXISTS (
                            SELECT 1
                              FROM bodies b
                              JOIN body_rings br
                                ON br.system_id64 = b.system_id64
                               AND br.body_id = b.id
                               AND br.association_status = 'local_matched'
                             WHERE b.system_id64 = body_scan_facts.system_address
                               AND (
                                   b.id = body_scan_facts.body_id::bigint
                                   OR b.name = body_scan_facts.body_name
                               )
                        ) THEN TRUE
                        WHEN body_scan_facts.is_ringed IS FALSE THEN FALSE
                        ELSE NULL
                    END AS is_ringed
                FROM body_scan_facts
                WHERE system_address = $1
                ORDER BY body_id
            """, id64)
            if slot_fact_rows:
                slot_facts = [dict(r) for r in slot_fact_rows]
            else:
                slot_facts = [
                    {
                        'system_address': id64,
                        'body_id': r['id'],
                        'body_name': r['name'],
                        'radius': r['radius'],
                        'gravity': r['gravity'],
                        'surface_temp': r['surface_temp'],
                        'planet_class': r['subtype'],
                        'terraform_state': None,
                        'atmosphere': None,
                        'volcanism': None,
                        'has_geo': (r['geo_signal_count'] or 0) > 0,
                        'has_bio': (r['bio_signal_count'] or 0) > 0,
                        'geo_signal_count': r['geo_signal_count'],
                        'bio_signal_count': r['bio_signal_count'],
                        'is_landable': r['is_landable'],
                        'is_terraformable': r['is_terraformable'],
                        'is_ringed': r['is_ringed'],
                    }
                    for r in await conn.fetch("""
                        SELECT id, name, subtype, radius, gravity, surface_temp,
                               geo_signal_count, bio_signal_count,
                               is_landable, is_terraformable,
                               CASE
                                   WHEN EXISTS (
                                       SELECT 1
                                       FROM body_rings br
                                       WHERE br.system_id64 = bodies.system_id64
                                         AND br.body_id = bodies.id
                                         AND br.association_status = 'local_matched'
                                   ) THEN TRUE
                                   ELSE NULL
                               END AS is_ringed
                        FROM bodies
                        WHERE system_id64 = $1 AND body_type != 'Star'
                        ORDER BY id
                    """, id64)
                ]

    except asyncpg.PostgresError as e:
        log.error('archetypes.system DB error: %s', e)
        raise HTTPException(
            status_code=503,
            detail={'type': 'https://httpstatuses.com/503',
                    'title': 'Database error', 'status': 503, 'detail': str(e)},
        )

    query_ms = int((time.monotonic() - t0) * 1000)
    slot_prediction = predict_system_slots(slot_facts) if slot_facts else {
        'predicted_orbital_slots_total': None,
        'predicted_ground_slots_total': None,
        'prediction_status': 'unknown',
    }

    # Build per-archetype score dict
    archetypes_out = {}
    for key, col in _SCORE_COL.items():
        s = float(row[col] or 0)
        archetypes_out[key] = {
            'score':       s,
            'tier':        _tier(s),
            'label':       _ARCHETYPE_LABELS[key],
        }
    # Add rationale to primary archetype entry
    primary = row['primary_archetype']
    if primary in archetypes_out and row['rationale']:
        archetypes_out[primary]['rationale'] = _rationale_with_canonical_confidence(_json_object(row['rationale']))

    topology_out = None
    if topo_row:
        topology_out = {
            'estimated_orbital_slots': slot_prediction.get('predicted_orbital_slots_total'),
            'estimated_ground_slots':  slot_prediction.get('predicted_ground_slots_total'),
            'estimated_total_slots': (
                (slot_prediction.get('predicted_orbital_slots_total') or 0)
                + (slot_prediction.get('predicted_ground_slots_total') or 0)
                if slot_prediction.get('predicted_orbital_slots_total') is not None
                and slot_prediction.get('predicted_ground_slots_total') is not None
                else None
            ),
            'strong_link_potential':   topo_row['strong_link_potential'],
            'weak_link_stability':     topo_row['weak_link_stability'],
            'contamination_risk':      topo_row['topo_contamination'],
            'orbital_synergy':         topo_row['orbital_synergy'],
            'ground_synergy':          topo_row['ground_synergy'],
            'nesting_potential':       topo_row['nesting_potential'],
            'build_flexibility':       topo_row['build_flexibility'],
            'has_viable_surface_port': topo_row['has_viable_surface_port'],
            'has_deep_orbital_anchor': topo_row['has_deep_orbital_anchor'],
            'prediction_status':       slot_prediction.get('prediction_status', 'unknown'),
            'slot_prediction_note': (
                None if slot_prediction.get('prediction_status') != 'unknown'
                else f'{INSUFFICIENT_DATA_REASON}. Verify in Architect Mode.'
            ),
        }

    economy_pairs_out = [
        {
            'economy_a':          pr['economy_a'],
            'economy_b':          pr['economy_b'],
            'synergy_score':      pr['synergy_score'],
            'purity_achievable':  pr['purity_achievable'],
            'contamination_paths': pr['contamination_paths'] or [],
        }
        for pr in pair_rows
    ]

    response = {
        'id64':               row['id64'],
        'name':               row['name'],
        'coords':             {'x': row['x'], 'y': row['y'], 'z': row['z']},
        'distance_to_sol':    row['distance_to_sol'],
        'main_star_type':     row['main_star_type'],
        'archetypes':         archetypes_out,
        'primary_archetype':  row['primary_archetype'],
        'secondary_archetype':row['secondary_archetype'],
        'archetype_confidence': row['archetype_confidence'],
        'overall_development_potential': row['overall_development_potential'],
        'buildability_score': row['buildability_score'],
        'build_complexity':   row['build_complexity'],
        'cp_efficiency':      row['cp_efficiency'],
        't3_scaling_viability': row['t3_scaling_viability'],
        'slot_efficiency':    row['slot_efficiency'],
        'purity_score':       row['purity_score'],
        'contamination_risk': row['contamination_risk'],
        'stable_top_two_prob': row['stable_top_two_prob'],
        'confidence':         row['confidence'],
        'topology':           topology_out,
        'economy_pairs':      economy_pairs_out,
        'tags':               list(trait_row['display_tags'] or []) if trait_row else [],
        'query_ms':           query_ms,
    }

    await _cache_set(redis, cache_key, response, ttl=300)
    return response


# ---------------------------------------------------------------------------
# POST /api/archetypes/simulate
# ---------------------------------------------------------------------------

@router.post(
    '/simulate',
    response_model=BuildSimulateResponse,
    summary='Build simulation — score a system against a planned build',
)
@limiter.limit('20/minute')
async def post_simulate(request: Request, body: BuildSimulateRequest):
    """
    Given a planned build (list of facility placements), estimate the
    resulting economy distribution and score the system against the plan.

    NOTE: This is a best-effort estimate. Economy outcomes depend on exact
    construction order and Frontier's internal economy weighting, which is
    not publicly documented.
    """
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT a.score_breakdown, a.rationale, a.contamination_risk,
                       a.purity_score, a.buildability_score,
                       a.primary_archetype
                FROM system_archetype_scores a
                WHERE a.system_id64 = $1 AND a.dirty = FALSE
            """, body.id64)
    except asyncpg.PostgresError as e:
        log.error('archetypes.simulate DB error: %s', e)
        raise HTTPException(
            status_code=503,
            detail={'type': 'https://httpstatuses.com/503',
                    'title': 'Database error', 'status': 503, 'detail': str(e)},
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f'System {body.id64} not found or scores not yet computed',
        )

    planned = body.planned_archetype
    score_breakdown = _json_object(row['score_breakdown'])
    pa_score = score_breakdown.get('per_archetype', {}).get(planned, {})
    sim_score = int(pa_score.get('score', 0)) if pa_score else 0

    recs: list[str] = []
    cont_risk = float(row['contamination_risk'] or 0) / 100
    if cont_risk > 0.40:
        recs.append(
            f'High contamination risk ({cont_risk:.0%}). '
            'Add dedicated Refinery Hubs on contaminating bodies to suppress third-economy bleed.'
        )
    if row['buildability_score'] and float(row['buildability_score']) < 50:
        recs.append(
            'Low buildability score. Ensure you have sufficient strong-link anchors '
            'before attempting T3 scaling.'
        )
    if len(body.planned_facilities) > 0:
        t3_count = sum(1 for f in body.planned_facilities if f.tier == 3)
        if t3_count > 0:
            recs.append(
                f'{t3_count} T3 facilities planned. '
                'T3 scaling requires at least one strong-link anchor body.'
            )

    return {
        'id64':               body.id64,
        'planned_archetype':  planned,
        'simulation_score':   sim_score,
        'contamination_risk': cont_risk,
        'purity_score':       round(float(row['purity_score'] or 0), 2),
        'buildability_score': round(float(row['buildability_score'] or 0), 2),
        'recommendations':    recs or ['Build plan looks viable — proceed with standard order.'],
        'disclaimer':         (
            'This is an estimate based on body-composition analysis. '
            'Actual economy outcomes depend on construction order and '
            'Frontier\'s internal economy weighting.'
        ),
    }


# ---------------------------------------------------------------------------
# GET /api/archetypes/profiles
# ---------------------------------------------------------------------------

@router.get(
    '/profiles',
    response_model=ArchetypesProfilesResponse,
    summary='Preset rerank weight profiles',
)
@limiter.limit('120/minute')
async def get_profiles(request: Request):
    redis     = get_redis()
    cache_key = 'arch:profiles'

    cached = await _cache_get(redis, cache_key)
    if cached:
        return cached

    response = {'profiles': _PROFILES}
    await _cache_set(redis, cache_key, response, ttl=3600)
    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tier(score) -> str:
    s = float(score or 0)
    if s >= 88: return 'S'
    if s >= 76: return 'A'
    if s >= 60: return 'B'
    if s >= 45: return 'C'
    return 'D'


def _resolve_weights(body: ArchetypeRerankRequest) -> ArchetypeRerankWeights:
    """Resolve effective weights from profile ID or explicit weights."""
    if body.profile:
        for p in _PROFILES:
            if p['id'] == body.profile:
                return ArchetypeRerankWeights(**p['weights'])

    if body.weights:
        return body.weights

    return ArchetypeRerankWeights()   # defaults


def _rerank_cache_key(id64s: list, weights: ArchetypeRerankWeights, archetype: Optional[str]) -> str:
    digest = hashlib.sha256(
        json.dumps({'ids': sorted(id64s), 'w': weights.model_dump(), 'arch': archetype},
                   sort_keys=True).encode()
    ).hexdigest()[:16]
    return f"arch:rerank:{digest}"
