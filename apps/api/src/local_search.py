"""
ED Finder — Search Module (PostgreSQL / asyncpg)
=================================================
Version: 4.0
Target:  PostgreSQL 16 + asyncpg 0.29+

Changes in v4.0:
  • Fixed schema/API disconnect: removed references to non-existent columns
    (main_star_class is now a generated column, needs_permit is now real).
  • Added galaxy_region filter: players can filter by named ED codex region
    (Inner Orion Spur, Formorian Frontier, etc.).
  • Searched economy score: when filtering by economy, the score shown in
    results is the economy-specific score, not the overall score.
  • Updated cluster search to use the new cluster_summary schema (v4.0).
  • Removed the stale server-side rate_system() fallback — all systems now
    have pre-computed ratings from build_ratings.py v3.0.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any, Dict, List, Optional

import asyncpg

from helpers import SOL_ID64, safe_coords_from_row
from search_economies import (
    ratings_score_column,
    archetype_score_column,
    cluster_count_column,
    economy_enum_value,
    BODY_FILTER_COLS,
    normalise_body_filters,
)

log = logging.getLogger("ed-finder.local_search")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MAX_SEARCH_RADIUS = float(os.getenv("MAX_SEARCH_RADIUS_LY", "10000"))
DEFAULT_PAGE_SIZE = 50_000
MAX_PAGE_SIZE     = 200_000
CLUSTER_RADIUS_LY = float(os.getenv("CLUSTER_RADIUS_LY", "500"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _economy_str(val: Any) -> str:
    if val is None:
        return "Unknown"
    s = str(val)
    if "<" in s:
        s = s.split("'")[-2] if "'" in s else s.split(".")[-1].strip(">")
    return s


def _safe_coords(row: Any) -> dict:
    return safe_coords_from_row(row)


def _safe_distance(val: Any) -> float | None:
    """Return a valid positive distance or None.

    Older galaxy-wide searches projected ``0.0`` when there was no reference.
    Converting that to ``float(0.0)`` on the wire made the frontend show
    ``0.00 LY`` for every system. Treat ``None``, non-finite, and zero as
    unknown so the UI can render ``—`` instead.
    """
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if not __import__('math').isfinite(f) or f <= 0:
        return None
    return round(f, 2)


def _archetype_tier(score: Any) -> str | None:
    if score is None:
        return None
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(s):
        return None
    if s >= 88:
        return "S"
    if s >= 76:
        return "A"
    if s >= 60:
        return "B"
    if s >= 45:
        return "C"
    return "D"


def _build_system_record(row: asyncpg.Record, bodies: list | None = None) -> dict:
    bodies = bodies or []

    # Determine which score to show:
    # - If the row has a display_score (set when filtering by economy), use it
    # - Otherwise use the overall score
    display_score = row.get("display_score") or row.get("score")

    return {
        "id64":              row["id64"],
        "id":                str(row["id64"]),
        "name":              row["name"],
        "coords":            _safe_coords(row),
        "distance":          _safe_distance(row.get("dist")),
        # main_star_class is a generated column (= main_star_type) — always present
        "main_star":         row.get("main_star_class") or row.get("main_star_type"),
        "archetype_score":   row.get("archetype_score"),
        "archetype_tier":    _archetype_tier(row.get("archetype_score")),
        "primary_archetype": row.get("primary_archetype"),
        "secondary_archetype": row.get("secondary_archetype"),
        "archetype_confidence": row.get("archetype_confidence"),
        "overall_development_potential": row.get("overall_development_potential"),
        "buildability_score": row.get("buildability_score"),
        "build_complexity": row.get("build_complexity"),
        "purity_score":     row.get("purity_score"),
        "contamination_risk": row.get("contamination_risk"),
        "est_total_slots":  row.get("est_total_slots"),
        "tags":             list(row.get("display_tags") or []),
        "needs_permit":      bool(row.get("needs_permit", False)),
        "population":        row.get("population"),
        "is_colonised":      int(bool(row.get("is_colonised", False))),
        "is_being_colonised": int(bool(row.get("is_being_colonised", False))),
        "controlling_minor_faction": row.get("controlling_faction"),
        "government":        _economy_str(row.get("government")),
        "allegiance":        _economy_str(row.get("allegiance")),
        "security":          _economy_str(row.get("security")),
        "primaryEconomy":    _economy_str(row.get("primary_economy")),
        "secondaryEconomy":  _economy_str(row.get("secondary_economy")),
        # Galaxy region (named ED codex region)
        "galaxy_region_id":  row.get("galaxy_region_id"),
        "galaxy_region":     row.get("galaxy_region_name"),
        "updated_at":        row["updated_at"].isoformat() if row.get("updated_at") else None,
        "bodies":            bodies,
        "source":            "local_db",
    }


# ---------------------------------------------------------------------------
# Core search
# ---------------------------------------------------------------------------
async def local_db_search(body: dict, pool: asyncpg.Pool) -> dict:
    """
    Execute a filtered system search against the PostgreSQL DB.

    Key features:
    - Body filters pushed into SQL via pre-computed ratings columns.
    - Galaxy region filter (named ED codex regions 1-42).
    - When filtering by economy, display_score = economy-specific score.
    - When browsing without economy filter, display_score = overall score.
    - Unified local and galaxy-wide search (galaxy_wide=True skips distance).
    """
    t0 = time.time()

    filters       = body.get("filters", {})
    ref           = body.get("reference_coords", {})
    size          = min(int(body.get("size", DEFAULT_PAGE_SIZE)), MAX_PAGE_SIZE)
    from_idx      = int(body.get("from", 0))
    sort_by       = body.get("sort_by", "development")
    galaxy_wide   = bool(body.get("galaxy_wide", False))

    ref_has_coords = all(ref.get(axis) is not None for axis in ("x", "y", "z"))
    if not galaxy_wide and not ref_has_coords:
        raise ValueError("reference_coords must include x, y, z for distance-bounded search")
    rx = float(ref["x"]) if ref_has_coords else 0.0
    ry = float(ref["y"]) if ref_has_coords else 0.0
    rz = float(ref["z"]) if ref_has_coords else 0.0

    dist_filter   = filters.get("distance", {})
    min_dist      = float(dist_filter.get("min", 0))
    max_dist_req  = float(dist_filter.get("max", 500))
    max_dist      = min(max_dist_req, MAX_SEARCH_RADIUS)
    radius_capped = max_dist < max_dist_req

    pop_filter    = filters.get("population", {})
    pop_val       = pop_filter.get("value")
    pop_cmp       = pop_filter.get("comparison", "equal")
    require_empty = (pop_val == 0 and pop_cmp == "equal")

    body_filters  = body.get("body_filters", {}) or {}
    require_bio   = bool(body.get("require_bio", False))
    require_geo   = bool(body.get("require_geo", False))
    require_terra = bool(body.get("require_terra", False))
    star_types    = body.get("star_types", []) or []
    min_development_score = int(body.get("min_development_score", 0))
    economy_filter   = body.get("economy") or body.get("filters", {}).get("economy")
    sec_econ_filter  = body.get("secondary_economy")
    galaxy_region_id = body.get("galaxy_region_id")  # NEW: named region filter

    # Determine which score column to use for display and sorting.
    # search_economies.ratings_score_column() centralises this and was
    # the fix for AUDIT_REPORT.md §C5: the previous local map was
    # missing 'extraction', so filtering by extraction silently fell
    # back to the overall r.score and produced different ordering than
    # the inline fallback (which knew about extraction).
    display_score_col = ratings_score_column(economy_filter, alias='r')
    primary_score_col = archetype_score_column(economy_filter, alias='m')
    finder_score_expr = f"COALESCE({primary_score_col}, {display_score_col})"

    params: list = []
    wheres: list = []
    select_params: list = []  # kept separately so count_sql doesn't see them
    p = 1

    def add_where(val):
        """Bind a value used in the WHERE clause. The same placeholder
        is reused by count_sql, which builds from the WHERE list only."""
        nonlocal p
        params.append(val)
        idx = p
        p += 1
        return f"${idx}"

    def add_select(val):
        """Bind a value used in the SELECT projection (e.g. dist_expr)
        or in LIMIT/OFFSET. count_sql NEVER sees these — passing them
        would fail asyncpg's positional-argument-count validation,
        which is exactly the regression ed1fce6 fixed."""
        nonlocal p
        params.append(val)
        select_params.append(val)
        idx = p
        p += 1
        return f"${idx}"

    # Backwards-compatible alias for the body of this function — every
    # site below was reaching for `add()` with 'goes into WHERE' intent.
    add = add_where

    # ── Distance filter ───────────────────────────────────────────────────
    if not galaxy_wide:
        wheres.append(
            f"(s.x IS NOT NULL AND s.y IS NOT NULL AND s.z IS NOT NULL "
            f"AND NOT (s.x = 0 AND s.y = 0 AND s.z = 0 AND s.id64 != {SOL_ID64}))"
        )
        wheres.append(f"s.x BETWEEN {add(rx - max_dist)} AND {add(rx + max_dist)}")
        wheres.append(f"s.y BETWEEN {add(ry - max_dist)} AND {add(ry + max_dist)}")
        wheres.append(f"s.z BETWEEN {add(rz - max_dist)} AND {add(rz + max_dist)}")
        wheres.append(
            f"((s.x-{add(rx)})*(s.x-{add(rx)}) + "
            f"(s.y-{add(ry)})*(s.y-{add(ry)}) + "
            f"(s.z-{add(rz)})*(s.z-{add(rz)})) "
            f"BETWEEN {add(min_dist*min_dist)} AND {add(max_dist*max_dist)}"
        )

    if require_empty:
        wheres.append("s.population = 0")
        wheres.append("s.is_colonised = FALSE")

    if economy_filter and economy_filter not in ("any", "Any", "Unknown", ""):
        # Normalise to the PostgreSQL enum literal — the enum is Title-cased
        # ('Agriculture', 'HighTech', …) and casting a raw user input like
        # 'High Tech' or 'hightech' to ::economy_type raises
        # InvalidTextRepresentationError, which after Phase-2 surfaces as
        # HTTP 503 (no silent fallback). Unknown inputs skip the filter,
        # matching the existing 'any' / 'Unknown' / '' semantics above.
        enum_val = economy_enum_value(economy_filter)
        if enum_val is not None:
            wheres.append(f"s.primary_economy = {add(enum_val)}::economy_type")

    if sec_econ_filter and sec_econ_filter not in ("any", "Any", "Unknown", ""):
        sec_enum_val = economy_enum_value(sec_econ_filter)
        if sec_enum_val is not None:
            wheres.append(f"s.secondary_economy = {add(sec_enum_val)}::economy_type")

    # ── Galaxy region filter (NEW) ────────────────────────────────────────
    if galaxy_region_id:
        wheres.append(f"s.galaxy_region_id = {add(int(galaxy_region_id))}")

    # ── Star type filter ──────────────────────────────────────────────────
    if star_types:
        # main_star_class is a generated column = main_star_type
        placeholders = ", ".join(add(st) for st in star_types)
        wheres.append(f"s.main_star_class IN ({placeholders})")

    if min_development_score > 0:
        # Filter on the archetype-led finder score when available, falling
        # back to the legacy display score for systems that do not yet have
        # archetype data.
        wheres.append(f"{finder_score_expr} >= {add(min_development_score)}")

    # ── Body filters via ratings columns ─────────────────────────────────
    # Column / alias maps now live in search_economies.py — see
    # AUDIT_REPORT.md §H8 / §C5 for the rationale (eliminates the
    # 4-way dict drift across search/map/ratings/local_search).
    body_filters = normalise_body_filters(body_filters)

    for filter_key, col in BODY_FILTER_COLS.items():
        rng = body_filters.get(filter_key) or {}
        if not isinstance(rng, dict):
            continue
        min_val = int(rng.get("min", 0) or 0)
        max_val = rng.get("max")
        # local_search joins ratings as `r`, so prefix the column.
        qcol = f'r.{col}'
        if min_val > 0:
            wheres.append(f"({qcol} IS NOT NULL AND {qcol} >= {add(min_val)})")
        if max_val is not None:
            wheres.append(f"({qcol} IS NULL OR {qcol} <= {add(max_val)})")

    if require_bio:
        wheres.append("(r.bio_signal_total IS NOT NULL AND r.bio_signal_total > 0)")
    if require_geo:
        wheres.append("(r.geo_signal_total IS NOT NULL AND r.geo_signal_total > 0)")
    if require_terra:
        wheres.append("(r.terraformable_count IS NOT NULL AND r.terraformable_count > 0)")

    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    # Snapshot the param count for the WHERE clause. count_sql consumes
    # only the WHERE-clause placeholders; everything below this line is
    # SELECT-side (dist_expr, LIMIT, OFFSET) and must use add_select()
    # so it lands in `select_params` but not in the count_sql arg list.
    # Keeping the snapshot here as a cross-check / regression guard
    # against future inserts of add_where() below this line.
    where_param_count = len(params)

    # Distance expression — projected, not filtered. Uses add_select()
    # so its placeholders are NOT replayed against count_sql.
    #
    # Guard: systems with (0,0,0) that aren't Sol have fake/missing coords.
    # After migration 019 they will be NULL in the DB, but pre-migration
    # they still exist as (0,0,0). The CASE ensures dist is NULL so
    # _safe_distance() returns None and the UI shows "—".
    _COORD_GUARD = (
        f"CASE WHEN s.x = 0 AND s.y = 0 AND s.z = 0 AND s.id64 != {SOL_ID64} "
        "THEN NULL::float "
    )
    if not galaxy_wide:
        dist_expr = (
            f"{_COORD_GUARD}ELSE SQRT((s.x-{add_select(rx)})*(s.x-{add_select(rx)}) + "
            f"(s.y-{add_select(ry)})*(s.y-{add_select(ry)}) + "
            f"(s.z-{add_select(rz)})*(s.z-{add_select(rz)})) END"
        )
    else:
        dist_expr = "NULL::float"

    # Sort by the display score (economy-specific when filtering, overall otherwise)
    order_sql = (
        f"ORDER BY {finder_score_expr} DESC NULLS LAST, dist ASC"
        if sort_by == "development"
        else "ORDER BY dist ASC"
    )

    count_sql = f"""
        SELECT COUNT(*)
        FROM systems s
        LEFT JOIN ratings r ON r.system_id64 = s.id64
        LEFT JOIN mv_archetype_rankings m ON m.id64 = s.id64
        {where_sql}
    """

    # Galaxy-wide queries with no distance filter can otherwise trigger
    # a sequential scan of the entire 186 M-row `systems` table just to
    # produce the `total` counter the v2 frontend renders as "X+ results".
    # Cap that at the largest `LIMIT $cap` envelope we want to spend
    # planner time on. The "+" badge in the UI already communicates
    # truncation; precise totals on galaxy-wide are not worth the cost.
    GALAXY_WIDE_COUNT_CAP = 10_000
    if galaxy_wide:
        count_sql = f"""
            SELECT COUNT(*) FROM (
                SELECT 1
                FROM systems s
                LEFT JOIN ratings r ON r.system_id64 = s.id64
                LEFT JOIN mv_archetype_rankings m ON m.id64 = s.id64
                {where_sql}
                LIMIT {GALAXY_WIDE_COUNT_CAP}
            ) t
        """

    sql = f"""
        SELECT
            s.id64, s.name, s.x, s.y, s.z,
            s.main_star_class,
            s.main_star_type,
            s.needs_permit,
            s.population,
            s.is_colonised,
            s.is_being_colonised,
            s.controlling_faction,
            s.government::text    AS government,
            s.allegiance::text    AS allegiance,
            s.security::text      AS security,
            s.primary_economy::text   AS primary_economy,
            s.secondary_economy::text AS secondary_economy,
            s.galaxy_region_id,
            gr.name               AS galaxy_region_name,
            s.updated_at,
            r.score,
            {display_score_col}   AS display_score,
            {finder_score_expr}   AS archetype_score,
            r.score_agriculture, r.score_refinery, r.score_industrial,
            r.score_hightech, r.score_military, r.score_tourism,
            r.score_extraction,
            r.economy_suggestion,
            r.slots               AS r_slots,
            r.body_quality        AS r_body_quality,
            r.compactness         AS r_compactness,
            r.signal_quality      AS r_signal_quality,
            r.orbital_safety      AS r_orbital_safety,
            r.star_bonus          AS r_star_bonus,
            r.elw_count, r.ww_count, r.ammonia_count,
            r.gas_giant_count, r.neutron_count, r.black_hole_count,
            r.white_dwarf_count, r.landable_count, r.terraformable_count,
            r.bio_signal_total, r.geo_signal_total,
            r.terraforming_potential, r.body_diversity,
            r.confidence, r.rationale,
            r.rating_version,
            m.primary_archetype,
            m.secondary_archetype,
            m.archetype_confidence,
            m.overall_development_potential,
            m.buildability_score,
            m.build_complexity,
            m.purity_score,
            m.contamination_risk,
            m.est_total_slots,
            m.display_tags,
            {dist_expr} AS dist
        FROM systems s
        LEFT JOIN ratings r ON r.system_id64 = s.id64
        LEFT JOIN mv_archetype_rankings m ON m.id64 = s.id64
        LEFT JOIN galaxy_regions gr ON gr.id = s.galaxy_region_id
        {where_sql}
        {order_sql}
        LIMIT {add_select(size)} OFFSET {add_select(from_idx)}
    """

    async with pool.acquire() as conn:
        rows  = await conn.fetch(sql, *params)
        # count_sql uses ONLY the WHERE-clause placeholders; pass the
        # snapshot taken before any add_select() call. Asserting here
        # (instead of slicing by index) makes the contract explicit
        # and means any future drift between add_where/add_select
        # surfaces as a test failure, not a runtime asyncpg error.
        assert len(params) == where_param_count + len(select_params), (
            "param accounting drifted: WHERE+SELECT must equal total"
        )
        total = await conn.fetchval(count_sql, *params[:where_param_count])

    results: list = []
    for row in rows:
        rec = _build_system_record(row)
        rec["distance"] = _safe_distance(row["dist"])
        results.append(rec)

    elapsed = round((time.time() - t0) * 1000)
    log.debug("local_db_search: %d total, returning %d (from=%d) in %dms",
              total, len(results), from_idx, elapsed)

    resp: Dict[str, Any] = {
        "results":  results,
        "count":    len(results),
        "total":    total,
        "source":   "local_db",
        "query_ms": elapsed,
        "display_economy": economy_filter or "overall",
    }
    if galaxy_wide and total is not None and total >= GALAXY_WIDE_COUNT_CAP:
        # The frontend should render "10,000+ matches" when this is set.
        # See `SearchResponse.total_is_capped` in apps/api/src/models.py.
        resp["total_is_capped"] = True
    if radius_capped:
        resp["warning"] = (
            f"Search radius capped at {int(MAX_SEARCH_RADIUS):,} LY "
            f"(requested {int(max_dist_req):,} LY)."
        )
    return resp


# ---------------------------------------------------------------------------
# Galaxy-wide economy search
# ---------------------------------------------------------------------------
async def local_db_galaxy_search(body: dict, pool: asyncpg.Pool) -> dict:
    """Galaxy-wide economy search — no distance filter."""
    economy       = body.get("economy", "")
    min_score     = int(body.get("min_score", 0))
    limit         = min(int(body.get("limit", 100)), 500)
    offset        = int(body.get("offset", 0))
    include_col   = bool(body.get("include_colonised", False))
    galaxy_region = body.get("galaxy_region_id")

    if not economy or economy in ("any", "Any", ""):
        return {"error": "economy is required for galaxy-wide search", "results": []}

    unified_body = {
        "galaxy_wide": True,
        "economy":     economy,
        "filters": {
            "population": {} if include_col else {"value": 0, "comparison": "equal"},
        },
        "min_development_score": min_score,
        "sort_by":               "development",
        "size":             limit,
        "from":             offset,
        "galaxy_region_id": galaxy_region,
    }
    return await local_db_search(unified_body, pool)


# ---------------------------------------------------------------------------
# Multi-economy cluster search (v4.0 — uses new cluster_summary schema)
# ---------------------------------------------------------------------------
async def local_db_cluster_search(body: dict, pool: asyncpg.Pool) -> dict:
    """
    Multi-economy cluster search using the macro-grid cluster_summary table.

    Each result represents an anchor system whose 500 LY bubble contains
    viable systems for each requested economy type.

    v4.0: Updated to use the new cluster_summary schema with per-economy
    count/best/top_id columns. Supports galaxy_region_id filter.
    """
    t0 = time.time()

    requirements    = body.get("requirements", [])
    limit           = min(int(body.get("limit", 50)), 200)
    ref             = body.get("reference_coords") or {}
    has_ref         = all(ref.get(axis) is not None for axis in ("x", "y", "z"))
    rx              = float(ref["x"]) if has_ref else 0.0
    ry              = float(ref["y"]) if has_ref else 0.0
    rz              = float(ref["z"]) if has_ref else 0.0
    galaxy_region   = body.get("galaxy_region_id")

    if not requirements:
        return {"error": "requirements list is required", "clusters": []}

    # Build WHERE clauses from requirements
    where_parts = []
    params      = []
    p           = 1

    def add(val):
        nonlocal p
        params.append(val)
        idx = p
        p += 1
        return f"${idx}"

    for req in requirements:
        econ      = req.get("economy")
        min_count = int(req.get("min_count", 1))
        col       = cluster_count_column(econ, alias='cs')
        if col:
            where_parts.append(f"{col} >= {add(min_count)}")

    if not where_parts:
        return {"error": "No valid economy requirements provided", "clusters": []}

    if galaxy_region:
        where_parts.append(f"s.galaxy_region_id = {add(int(galaxy_region))}")

    where_sql = "WHERE " + " AND ".join(where_parts) + " AND cs.coverage_score IS NOT NULL"

    # Distance expression for sorting
    _COORD_GUARD = (
        f"CASE WHEN s.x = 0 AND s.y = 0 AND s.z = 0 AND s.id64 != {SOL_ID64} "
        "THEN NULL::float ELSE "
    )
    if has_ref:
        dist_expr    = f"{_COORD_GUARD}SQRT(POWER(s.x - {rx}, 2) + POWER(s.y - {ry}, 2) + POWER(s.z - {rz}, 2)) END"
        order_clause = f"{dist_expr} ASC"
    else:
        dist_expr    = "NULL::float"
        order_clause = "cs.coverage_score DESC NULLS LAST"

    sql = f"""
        SELECT
            s.id64              AS anchor_id64,
            s.name              AS anchor_name,
            s.x                 AS anchor_x,
            s.y                 AS anchor_y,
            s.z                 AS anchor_z,
            s.population        AS anchor_population,
            s.galaxy_region_id,
            gr.name             AS galaxy_region_name,
            cs.coverage_score,
            cs.economy_diversity,
            cs.total_viable,
            cs.agriculture_count, cs.agriculture_best, cs.agriculture_top_id,
            cs.refinery_count,    cs.refinery_best,    cs.refinery_top_id,
            cs.industrial_count,  cs.industrial_best,  cs.industrial_top_id,
            cs.hightech_count,    cs.hightech_best,    cs.hightech_top_id,
            cs.military_count,    cs.military_best,    cs.military_top_id,
            cs.tourism_count,     cs.tourism_best,     cs.tourism_top_id,
            {dist_expr}         AS distance_ly
        FROM cluster_summary cs
        JOIN systems s ON s.id64 = cs.system_id64
        LEFT JOIN galaxy_regions gr ON gr.id = s.galaxy_region_id
        {where_sql}
        ORDER BY {order_clause}
        LIMIT {add(limit)}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)

    clusters = []
    for row in rows:
        dist_ly = float(row["distance_ly"]) if row["distance_ly"] is not None else None
        anchor_coords = _safe_coords({
            "id64": row["anchor_id64"],
            "x":    row["anchor_x"],
            "y":    row["anchor_y"],
            "z":    row["anchor_z"],
        })
        clusters.append({
            "anchor_id64":          row["anchor_id64"],
            "system_id64":          row["anchor_id64"],  # alias for compatibility
            "anchor_name":          row["anchor_name"],
            "anchor_x":             anchor_coords["x"],
            "anchor_y":             anchor_coords["y"],
            "anchor_z":             anchor_coords["z"],
            "anchor_coords":        anchor_coords,
            "galaxy_region_id":     row["galaxy_region_id"],
            "galaxy_region":        row["galaxy_region_name"],
            "coverage_score":       row["coverage_score"],
            "economy_diversity":    row["economy_diversity"],
            "total_viable":         row["total_viable"],
            "agriculture_count":    row["agriculture_count"],
            "agriculture_best":     row["agriculture_best"],
            "agriculture_top_id":   row["agriculture_top_id"],
            "refinery_count":       row["refinery_count"],
            "refinery_best":        row["refinery_best"],
            "refinery_top_id":      row["refinery_top_id"],
            "industrial_count":     row["industrial_count"],
            "industrial_best":      row["industrial_best"],
            "industrial_top_id":    row["industrial_top_id"],
            "hightech_count":       row["hightech_count"],
            "hightech_best":        row["hightech_best"],
            "hightech_top_id":      row["hightech_top_id"],
            "military_count":       row["military_count"],
            "military_best":        row["military_best"],
            "military_top_id":      row["military_top_id"],
            "tourism_count":        row["tourism_count"],
            "tourism_best":         row["tourism_best"],
            "tourism_top_id":       row["tourism_top_id"],
            "distance_ly":          round(dist_ly, 1) if dist_ly is not None else None,
            "cluster_radius_ly":    CLUSTER_RADIUS_LY,
        })

    elapsed = round((time.time() - t0) * 1000)
    log.info("cluster_search(%d requirements, region=%s, ref=%s): %d clusters in %dms",
             len(requirements), galaxy_region or "any",
             "yes" if has_ref else "no", len(clusters), elapsed)

    return {
        "clusters":          clusters,
        "count":             len(clusters),
        "requirements":      requirements,
        "cluster_radius_ly": CLUSTER_RADIUS_LY,
        "query_ms":          elapsed,
    }


# ---------------------------------------------------------------------------
# System detail
# ---------------------------------------------------------------------------
async def local_db_system(id64: int, pool: asyncpg.Pool) -> Optional[dict]:
    """Return full system data including bodies and stations."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                s.id64, s.name, s.x, s.y, s.z,
                s.main_star_class,
                s.main_star_type,
                s.needs_permit,
                s.population,
                s.is_colonised,
                s.is_being_colonised,
                s.controlling_faction,
                s.government::text    AS government,
                s.allegiance::text    AS allegiance,
                s.security::text      AS security,
                s.primary_economy::text   AS primary_economy,
                s.secondary_economy::text AS secondary_economy,
                s.galaxy_region_id,
                gr.name               AS galaxy_region_name,
                s.updated_at,
                r.score,
                r.score               AS display_score,
                r.score_agriculture, r.score_refinery, r.score_industrial,
                r.score_hightech, r.score_military, r.score_tourism,
                r.score_extraction,
                r.economy_suggestion,
                r.slots               AS r_slots,
                r.body_quality        AS r_body_quality,
                r.compactness         AS r_compactness,
                r.signal_quality      AS r_signal_quality,
                r.orbital_safety      AS r_orbital_safety,
                r.star_bonus          AS r_star_bonus,
                r.elw_count, r.ww_count, r.ammonia_count,
                r.gas_giant_count, r.neutron_count, r.black_hole_count,
                r.white_dwarf_count, r.landable_count, r.terraformable_count,
                r.bio_signal_total, r.geo_signal_total,
                r.score_breakdown,
                r.terraforming_potential, r.body_diversity,
                r.confidence, r.rationale, r.rating_version,
                NULL::float           AS dist
            FROM systems s
            LEFT JOIN ratings r ON r.system_id64 = s.id64
            LEFT JOIN galaxy_regions gr ON gr.id = s.galaxy_region_id
            WHERE s.id64 = $1
        """, id64)

        if not row:
            return None

        body_rows = await conn.fetch("""
            SELECT
                b.id, b.name,
                b.body_type::text AS type,
                b.subtype,
                b.distance_from_star,
                b.is_landable,
                b.is_tidal_lock,
                b.atmosphere_type AS atmosphere,
                b.volcanism,
                b.terraforming_state AS terraform_state,
                b.gravity AS surface_gravity,
                b.surface_temp,
                b.mass,
                b.radius,
                b.bio_signal_count AS bio_signals,
                b.geo_signal_count AS geo_signals,
                b.estimated_mapping_value AS mapped_value,
                b.estimated_scan_value AS scan_value,
                NULL::text AS ring_types,
                NULL::text AS signals,
                (b.bio_signal_count > 0 OR b.geo_signal_count > 0) AS has_signals
            FROM bodies b
            WHERE b.system_id64 = $1
            ORDER BY b.distance_from_star
        """, id64)

    body_list = [_normalize_body(b) for b in body_rows]
    record = _build_system_record(row, body_list)
    record["body_count"] = len(body_list)

    # Expose score breakdown for the popover
    if row.get("score_breakdown"):
        breakdown = row["score_breakdown"]
        if isinstance(breakdown, str):
            try:
                breakdown = json.loads(breakdown)
            except Exception:
                breakdown = {}
        record["score_breakdown"] = breakdown

    # Fetch stations
    async with pool.acquire() as conn:
        station_rows = await conn.fetch("""
            SELECT
                id, name,
                station_type::text AS type,
                distance_from_star,
                body_name,
                landing_pad_size::text AS landing_pad_size,
                primary_economy::text AS primary_economy,
                secondary_economy::text AS secondary_economy,
                has_market, has_shipyard, has_outfitting,
                has_refuel, has_repair, has_rearm,
                has_black_market, has_material_trader,
                has_technology_broker, has_interstellar_factors,
                has_universal_cartographics, has_search_rescue,
                updated_at
            FROM stations
            WHERE system_id64 = $1
            ORDER BY distance_from_star
        """, id64)

    stations = []
    for st in station_rows:
        services = []
        if st["has_market"]:          services.append("Market")
        if st["has_shipyard"]:        services.append("Shipyard")
        if st["has_outfitting"]:      services.append("Outfitting")
        if st["has_refuel"]:          services.append("Refuel")
        if st["has_repair"]:          services.append("Repair")
        if st["has_rearm"]:           services.append("Restock")
        if st["has_black_market"]:    services.append("Black Market")
        if st["has_material_trader"]: services.append("Material Trader")
        if st["has_technology_broker"]: services.append("Technology Broker")
        if st["has_interstellar_factors"]: services.append("Interstellar Factors")
        if st["has_universal_cartographics"]: services.append("Universal Cartographics")
        if st["has_search_rescue"]:   services.append("Search and Rescue")

        stations.append({
            "id":                   st["id"],
            "name":                 st["name"],
            "type":                 st["type"],
            "distance_to_arrival":  st["distance_from_star"],
            "body_name":            st["body_name"],
            "landingPads":          {"large": 1 if st["landing_pad_size"] == "L" else 0},
            "economies":            [
                {"name": st["primary_economy"]} if st["primary_economy"] else None,
                {"name": st["secondary_economy"]} if st["secondary_economy"] else None,
            ],
            "services":             services,
            "updated_at":           st["updated_at"].isoformat() if st["updated_at"] else None,
        })

    record["stations"] = stations
    record["source"]   = "local_db"

    return {"record": record}


# ---------------------------------------------------------------------------
# Autocomplete
# ---------------------------------------------------------------------------
async def local_db_autocomplete(q: str, pool: asyncpg.Pool) -> list:
    """Fast trigram-based prefix search for system names.

    The prefix path uses a functional `(lower(name) text_pattern_ops)`
    btree index (idx_sys_name_lower_pattern, sql/011_*). The previous
    `WHERE name ILIKE $1` was unindexable on the existing
    `idx_sys_name` (default text_ops) and forced the planner onto the
    GIN trigram, which on 3-char queries like 'Sol' walks millions of
    candidates and times out at 300s. The new index reduces the
    `lower(name) LIKE 'sol%'` lookup to a sub-ms btree range scan.
    """
    if len(q) < 2:
        return []

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id64, name, x, y, z, galaxy_region_id
            FROM systems
            WHERE lower(name) LIKE $1
            ORDER BY name
            LIMIT 10
        """, q.lower() + "%")

        if len(rows) < 5 and len(q) >= 3:
            trgm_rows = await conn.fetch("""
                SELECT id64, name, x, y, z, galaxy_region_id
                FROM systems
                WHERE name % $1
                  AND lower(name) NOT LIKE $2
                ORDER BY similarity(name, $1) DESC
                LIMIT $3
            """, q, q.lower() + "%", 10 - len(rows))
            seen_ids = {r["id64"] for r in rows}
            rows = list(rows) + [r for r in trgm_rows if r["id64"] not in seen_ids]

    results = []
    for r in rows[:10]:
        coords = _safe_coords(r)
        results.append({
            "name":              r["name"],
            "id64":              r["id64"],
            "x":                 coords["x"],
            "y":                 coords["y"],
            "z":                 coords["z"],
            "galaxy_region_id":  r["galaxy_region_id"],
            "record": {
                "id64": r["id64"],
                "name": r["name"],
                "x":    coords["x"],
                "y":    coords["y"],
                "z":    coords["z"],
            },
        })
    return results


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
async def local_db_status(pool: asyncpg.Pool) -> dict:
    """Return info about the PostgreSQL database and import progress."""
    try:
        async with pool.acquire() as conn:
            # Use pg_class.reltuples (PG's ANALYZE-derived row estimate) instead of
            # COUNT(*) — returns in ~1ms per table vs 30+ seconds for COUNT(*) FROM
            # bodies on the 1B+ row table. Estimates are plenty accurate for a
            # status display and refresh on every autovac/analyze cycle.
            #
            # Why: build_grid.py was being starved of disk I/O by repeated polls
            # of /api/local/status from the V2 Admin tab (every 30s). Each poll
            # triggered 8 sequential COUNT(*) full scans through pgbouncer.
            counts = await conn.fetchrow("""
                SELECT
                  COALESCE((SELECT reltuples::bigint FROM pg_class WHERE relname='systems'),         0) AS sys_count,
                  COALESCE((SELECT reltuples::bigint FROM pg_class WHERE relname='bodies'),          0) AS body_count,
                  COALESCE((SELECT reltuples::bigint FROM pg_class WHERE relname='stations'),        0) AS station_count,
                  COALESCE((SELECT reltuples::bigint FROM pg_class WHERE relname='cluster_summary'), 0) AS cluster_count,
                  COALESCE((SELECT reltuples::bigint FROM pg_class WHERE relname='spatial_grid'),    0) AS grid_count,
                  COALESCE((SELECT reltuples::bigint FROM pg_class WHERE relname='macro_grid'),      0) AS macro_count,
                  COALESCE((SELECT reltuples::bigint FROM pg_class WHERE relname='ratings'),         0) AS rated_count,
                  COALESCE((SELECT count(*)         FROM galaxy_regions),                            0) AS region_count
            """)
            sys_count     = int(counts["sys_count"])
            body_count    = int(counts["body_count"])
            station_count = int(counts["station_count"])
            cluster_count = int(counts["cluster_count"])
            grid_count    = int(counts["grid_count"])
            macro_count   = int(counts["macro_count"])
            rated_count   = int(counts["rated_count"])
            region_count  = int(counts["region_count"])

            import_rows = await conn.fetch("""
                SELECT dump_file, status, rows_processed, errors_encountered,
                       started_at, completed_at
                FROM import_meta ORDER BY id
            """)
            import_status = {
                r["dump_file"]: {
                    "status":             str(r["status"]),
                    "rows_processed":     r["rows_processed"],
                    "errors_encountered": r["errors_encountered"],
                    "started_at":         r["started_at"].isoformat() if r["started_at"] else None,
                    "completed_at":       r["completed_at"].isoformat() if r["completed_at"] else None,
                }
                for r in import_rows
            }

            db_size_bytes = await conn.fetchval(
                "SELECT pg_database_size(current_database())"
            )
            pg_version = await conn.fetchval("SELECT version()")

        return {
            "available":            True,
            "backend":              "postgresql",
            "pg_version":           pg_version,
            "systems_count":        sys_count,
            "rated_count":          rated_count,
            "body_count":           body_count,
            "station_count":        station_count,
            "cluster_count":        cluster_count,
            "grid_cells":           grid_count,
            "macro_grid_cells":     macro_count,
            "galaxy_regions":       region_count,
            "db_size_mb":           round(db_size_bytes / 1_048_576, 1) if db_size_bytes else 0,
            "import_status":        import_status,
            "max_search_radius_ly": int(MAX_SEARCH_RADIUS),
            "cluster_radius_ly":    int(CLUSTER_RADIUS_LY),
            "has_bodies":           True,
            "has_cluster_summary":  cluster_count > 0,
        }
    except Exception as exc:
        log.warning("local_db_status error: %s", exc)
        return {"available": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Body normalizer (for system detail modal)
# ---------------------------------------------------------------------------
def _normalize_body(row: asyncpg.Record) -> dict:
    rings_raw = row.get("ring_types") or []
    if isinstance(rings_raw, str):
        try:
            rings_raw = json.loads(rings_raw)
        except Exception:
            rings_raw = []
    rings = [{"type": t} for t in rings_raw if t]

    signals_raw = row.get("signals") or []
    if isinstance(signals_raw, str):
        try:
            signals_raw = json.loads(signals_raw)
        except Exception:
            signals_raw = []

    if not signals_raw and row.get("has_signals"):
        volc = (row.get("volcanism") or "").strip()
        if volc and volc not in ("", "No volcanism"):
            signals_raw = [{"name": "Geological", "count": 1}]
        else:
            signals_raw = [{"name": "Biological", "count": 1}]

    return {
        "id":                    row.get("id"),
        "name":                  row.get("name"),
        "type":                  row.get("type"),
        "subtype":               row.get("subtype"),
        "distance_to_arrival":   row.get("distance_from_star"),
        "is_landable":           bool(row.get("is_landable", False)),
        "is_rotational_period_tidally_locked": bool(row.get("is_tidal_lock", False)),
        "atmosphere":            row.get("atmosphere"),
        "volcanism":             row.get("volcanism"),
        "terraforming_state":    row.get("terraform_state"),
        "gravity":               row.get("surface_gravity"),
        "surface_temperature":   row.get("surface_temp"),
        "mass":                  row.get("mass"),
        "radius":                row.get("radius"),
        "estimated_mapping_value":  row.get("mapped_value"),
        "estimated_scan_value":     row.get("scan_value"),
        "bio_signals":           row.get("bio_signals") or 0,
        "geo_signals":           row.get("geo_signals") or 0,
        "has_signals":           bool(row.get("has_signals", False)),
        "rings":                 rings,
        "signals":               signals_raw,
    }
