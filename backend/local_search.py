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


# Economy column mapping for the "show searched economy score" feature
ECONOMY_SCORE_COL = {
    'agriculture': 'r.score_agriculture',
    'refinery':    'r.score_refinery',
    'industrial':  'r.score_industrial',
    'hightech':    'r.score_hightech',
    'high tech':   'r.score_hightech',
    'military':    'r.score_military',
    'tourism':     'r.score_tourism',
}


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
        "coords":            {
            "x": float(row["x"]),
            "y": float(row["y"]),
            "z": float(row["z"]),
        },
        "distance":          float(row.get("dist", 0) or 0),
        # main_star_class is a generated column (= main_star_type) — always present
        "main_star":         row.get("main_star_class") or row.get("main_star_type"),
        "needs_permit":      bool(row.get("needs_permit", False)),
        "population":        row.get("population") or 0,
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
        # Rating — display_score is the searched economy score when filtering
        "rating":            display_score,
        "score":             row.get("score"),       # always the overall score
        "display_score":     display_score,          # economy-specific when filtering
        "updated_at":        row["updated_at"].isoformat() if row.get("updated_at") else None,
        "score_components":  {
            "slots":         row.get("r_slots"),
            "bodyQuality":   row.get("r_body_quality"),
            "compactness":   row.get("r_compactness"),
            "signalQuality": row.get("r_signal_quality"),
            "orbitalSafety": row.get("r_orbital_safety"),
            "starBonus":     row.get("r_star_bonus"),
        } if row.get("score") is not None else None,
        "_rating": {
            "score":              row.get("score"),
            "displayScore":       display_score,
            "scoreAgriculture":   row.get("score_agriculture"),
            "scoreRefinery":      row.get("score_refinery"),
            "scoreIndustrial":    row.get("score_industrial"),
            "scoreHightech":      row.get("score_hightech"),
            "scoreMilitary":      row.get("score_military"),
            "scoreTourism":       row.get("score_tourism"),
            "economySuggestion":  row.get("economy_suggestion"),
            "elw_count":          row.get("elw_count"),
            "ww_count":           row.get("ww_count"),
            "ammonia_count":      row.get("ammonia_count"),
            "gas_giant_count":    row.get("gas_giant_count"),
            "neutron_count":      row.get("neutron_count"),
            "black_hole_count":   row.get("black_hole_count"),
            "white_dwarf_count":  row.get("white_dwarf_count"),
            "landable_count":     row.get("landable_count"),
            "terraformable_count": row.get("terraformable_count"),
            "bio_signal_total":   row.get("bio_signal_total"),
            "geo_signal_total":   row.get("geo_signal_total"),
        },
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
    sort_by       = body.get("sort_by", "rating")

    rx = float(ref.get("x", 0))
    ry = float(ref.get("y", 0))
    rz = float(ref.get("z", 0))

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
    min_rating    = int(body.get("min_rating", 0))
    economy_filter   = body.get("economy") or body.get("filters", {}).get("economy")
    sec_econ_filter  = body.get("secondary_economy")
    galaxy_wide      = bool(body.get("galaxy_wide", False))
    galaxy_region_id = body.get("galaxy_region_id")  # NEW: named region filter

    # Determine which score column to use for display and sorting
    eco_lower = (economy_filter or "").lower().strip()
    display_score_col = ECONOMY_SCORE_COL.get(eco_lower, 'r.score')

    params: list = []
    wheres: list = []
    p = 1

    def add(val):
        nonlocal p
        params.append(val)
        idx = p
        p += 1
        return f"${idx}"

    # ── Distance filter ───────────────────────────────────────────────────
    if not galaxy_wide:
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
        wheres.append(f"s.primary_economy = {add(economy_filter)}::economy_type")

    if sec_econ_filter and sec_econ_filter not in ("any", "Any", "Unknown", ""):
        wheres.append(f"s.secondary_economy = {add(sec_econ_filter)}::economy_type")

    # ── Galaxy region filter (NEW) ────────────────────────────────────────
    if galaxy_region_id:
        wheres.append(f"s.galaxy_region_id = {add(int(galaxy_region_id))}")

    # ── Star type filter ──────────────────────────────────────────────────
    if star_types:
        # main_star_class is a generated column = main_star_type
        placeholders = ", ".join(add(st) for st in star_types)
        wheres.append(f"s.main_star_class IN ({placeholders})")

    if min_rating > 0:
        # Filter on the display score column (economy-specific or overall)
        wheres.append(f"{display_score_col} >= {add(min_rating)}")

    # ── Body filters via ratings columns ─────────────────────────────────
    BODY_FILTER_COLS = {
        "elw":       "r.elw_count",
        "ww":        "r.ww_count",
        "ammonia":   "r.ammonia_count",
        "gasGiant":  "r.gas_giant_count",
        "neutron":   "r.neutron_count",
        "blackHole": "r.black_hole_count",
        "whiteDwarf": "r.white_dwarf_count",
        "landable":  "r.landable_count",
        "terraformable": "r.terraformable_count",
    }
    for filter_key, col in BODY_FILTER_COLS.items():
        rng = body_filters.get(filter_key, {})
        min_val = int(rng.get("min", 0))
        max_val = rng.get("max")
        if min_val > 0:
            wheres.append(f"({col} IS NOT NULL AND {col} >= {add(min_val)})")
        if max_val is not None:
            wheres.append(f"({col} IS NULL OR {col} <= {add(max_val)})")

    if require_bio:
        wheres.append("(r.bio_signal_total IS NOT NULL AND r.bio_signal_total > 0)")
    if require_geo:
        wheres.append("(r.geo_signal_total IS NOT NULL AND r.geo_signal_total > 0)")
    if require_terra:
        wheres.append("(r.terraformable_count IS NOT NULL AND r.terraformable_count > 0)")

    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    # Distance expression
    if not galaxy_wide:
        dist_expr = (
            f"SQRT((s.x-{add(rx)})*(s.x-{add(rx)}) + "
            f"(s.y-{add(ry)})*(s.y-{add(ry)}) + "
            f"(s.z-{add(rz)})*(s.z-{add(rz)}))"
        )
    else:
        dist_expr = "0.0"

    # Sort by the display score (economy-specific when filtering, overall otherwise)
    order_sql = (
        f"ORDER BY {display_score_col} DESC NULLS LAST, dist ASC"
        if sort_by == "rating"
        else "ORDER BY dist ASC"
    )

    count_sql = f"""
        SELECT COUNT(*)
        FROM systems s
        LEFT JOIN ratings r ON r.system_id64 = s.id64
        {where_sql}
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
            {dist_expr} AS dist
        FROM systems s
        LEFT JOIN ratings r ON r.system_id64 = s.id64
        LEFT JOIN galaxy_regions gr ON gr.id = s.galaxy_region_id
        {where_sql}
        {order_sql}
        LIMIT {add(size)} OFFSET {add(from_idx)}
    """

    async with pool.acquire() as conn:
        rows  = await conn.fetch(sql, *params)
        total = await conn.fetchval(count_sql, *params[:-2])

    results: list = []
    for row in rows:
        rec = _build_system_record(row)
        rec["distance"] = round(float(row["dist"]), 2)
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
        "min_rating":       min_score,
        "sort_by":          "rating",
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
    has_ref         = bool(ref.get("x") is not None)
    rx              = float(ref.get("x", 0))
    ry              = float(ref.get("y", 0))
    rz              = float(ref.get("z", 0))
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

    ECO_COUNT_COLS = {
        'agriculture': 'cs.agriculture_count',
        'refinery':    'cs.refinery_count',
        'industrial':  'cs.industrial_count',
        'hightech':    'cs.hightech_count',
        'high tech':   'cs.hightech_count',
        'military':    'cs.military_count',
        'tourism':     'cs.tourism_count',
    }

    for req in requirements:
        econ      = (req.get("economy") or "").lower().strip()
        min_count = int(req.get("min_count", 1))
        col       = ECO_COUNT_COLS.get(econ)
        if col:
            where_parts.append(f"{col} >= {add(min_count)}")

    if not where_parts:
        return {"error": "No valid economy requirements provided", "clusters": []}

    if galaxy_region:
        where_parts.append(f"s.galaxy_region_id = {add(int(galaxy_region))}")

    where_sql = "WHERE " + " AND ".join(where_parts) + " AND cs.coverage_score IS NOT NULL"

    # Distance expression for sorting
    if has_ref:
        dist_expr    = f"SQRT(POWER(s.x - {rx}, 2) + POWER(s.y - {ry}, 2) + POWER(s.z - {rz}, 2))"
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
        clusters.append({
            "anchor_id64":          row["anchor_id64"],
            "system_id64":          row["anchor_id64"],  # alias for compatibility
            "anchor_name":          row["anchor_name"],
            "anchor_x":             float(row["anchor_x"]),
            "anchor_y":             float(row["anchor_y"]),
            "anchor_z":             float(row["anchor_z"]),
            "anchor_coords": {
                "x": float(row["anchor_x"]),
                "y": float(row["anchor_y"]),
                "z": float(row["anchor_z"]),
            },
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
                r.confidence, r.rationale,
                0.0                   AS dist
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
    """Fast trigram-based prefix search for system names."""
    if len(q) < 2:
        return []

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id64, name, x, y, z, galaxy_region_id
            FROM systems
            WHERE name ILIKE $1
            ORDER BY name
            LIMIT 10
        """, q + "%")

        if len(rows) < 5 and len(q) >= 3:
            trgm_rows = await conn.fetch("""
                SELECT id64, name, x, y, z, galaxy_region_id
                FROM systems
                WHERE name % $1
                  AND name NOT ILIKE $2
                ORDER BY similarity(name, $1) DESC
                LIMIT $3
            """, q, q + "%", 10 - len(rows))
            seen_ids = {r["id64"] for r in rows}
            rows = list(rows) + [r for r in trgm_rows if r["id64"] not in seen_ids]

    return [
        {
            "name":              r["name"],
            "id64":              r["id64"],
            "x":                 float(r["x"]),
            "y":                 float(r["y"]),
            "z":                 float(r["z"]),
            "galaxy_region_id":  r["galaxy_region_id"],
            "record": {
                "id64": r["id64"],
                "name": r["name"],
                "x":    float(r["x"]),
                "y":    float(r["y"]),
                "z":    float(r["z"]),
            },
        }
        for r in rows[:10]
    ]


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
async def local_db_status(pool: asyncpg.Pool) -> dict:
    """Return info about the PostgreSQL database and import progress."""
    try:
        async with pool.acquire() as conn:
            sys_count     = await conn.fetchval("SELECT COUNT(*) FROM systems")
            rated_count   = await conn.fetchval(
                "SELECT COUNT(*) FROM ratings WHERE score IS NOT NULL"
            )
            body_count    = await conn.fetchval("SELECT COUNT(*) FROM bodies")
            station_count = await conn.fetchval("SELECT COUNT(*) FROM stations")
            cluster_count = await conn.fetchval("SELECT COUNT(*) FROM cluster_summary")
            grid_count    = await conn.fetchval("SELECT COUNT(*) FROM spatial_grid")
            macro_count   = await conn.fetchval("SELECT COUNT(*) FROM macro_grid")
            region_count  = await conn.fetchval(
                "SELECT COUNT(DISTINCT galaxy_region_id) FROM systems WHERE galaxy_region_id IS NOT NULL"
            )

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
