"""
ED:Finder — Hetzner Local Search Module (PostgreSQL / asyncpg edition)
=======================================================================
Drop-in replacement for localdb/local_search.py on the Pi.

Public API — identical signatures to the Pi version:
    local_db_search(body, pool)        -> dict   # mirrors Spansh /systems/search
    local_db_system(id64, pool)        -> dict   # mirrors Spansh /system/{id64}
    local_db_autocomplete(q, pool)     -> list   # system name autocomplete
    local_db_status(pool)              -> dict   # DB health + stats
    rate_system(sys)                   -> dict   # pre-compute colonisation score

Key differences from the Pi SQLite version:
    • All DB calls are async (asyncpg.Pool) — no run_in_executor needed.
    • No MAX_SEARCH_RADIUS cap — 128 GB RAM handles any radius comfortably.
    • No 500k RAW_ROW_CAP — PostgreSQL streaming cursor + asyncpg handles density.
    • Spatial grid is a proper indexed table — bounding-box queries are instant.
    • Bodies table is always present (Phase 2 is built at import time).
    • economy / security / allegiance / government come from typed enum columns.
    • New endpoints supported: galaxy-wide search, multi-economy cluster search.
    • Full primary_economy / secondary_economy exposed in every result.

Response shapes are intentionally wire-compatible with the Pi version and with
the Spansh API so the frontend requires zero changes.

Version: 1.0 (Hetzner)
Target:  PostgreSQL 16 + asyncpg 0.29+
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
# No radius cap on Hetzner — 128 GB RAM, NVMe, 12-thread i7-8700.
# The spatial index makes 500+ LY searches instant.
# Frontend still enforces its own distance slider (≤500 LY in Spansh mode,
# unlimited in galaxy-wide mode).
MAX_SEARCH_RADIUS = float(os.getenv("MAX_SEARCH_RADIUS_LY", "10000"))

# Max rows returned per standard distance search
DEFAULT_PAGE_SIZE = 50_000
MAX_PAGE_SIZE     = 200_000

# Cluster search: all systems within this radius of each anchor are checked
CLUSTER_RADIUS_LY = float(os.getenv("CLUSTER_RADIUS_LY", "500"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _economy_str(val: Any) -> str:
    """Normalize asyncpg enum / str economy value to a plain string."""
    if val is None:
        return "Unknown"
    s = str(val)
    # asyncpg returns enum as '<EnumClass.VALUE: value>' on older drivers —
    # strip to just the value string.
    if "<" in s:
        s = s.split("'")[-2] if "'" in s else s.split(".")[-1].strip(">")
    return s


def _build_system_record(row: asyncpg.Record, bodies: list | None = None) -> dict:
    """
    Convert an asyncpg Row from the systems+ratings JOIN into the wire format
    that the frontend expects (compatible with Pi local_db and Spansh API shapes).
    """
    bodies = bodies or []
    return {
        "id64":              row["id64"],
        "id":                str(row["id64"]),
        "name":              row["name"],
        "coords":            {
            "x": float(row["x"]),
            "y": float(row["y"]),
            "z": float(row["z"]),
        },
        "distance":          float(row.get("distance", 0) or 0),
        "main_star":         row.get("main_star_class") or row.get("main_star"),
        "needs_permit":      bool(row.get("needs_permit", False)),
        "population":        row.get("population") or 0,
        "is_colonised":      int(bool(row.get("is_colonised", False))),
        "is_being_colonised": int(bool(row.get("is_being_colonised", False))),
        "controlling_minor_faction": row.get("controlling_faction"),
        "government":        _economy_str(row.get("government")),
        "allegiance":        _economy_str(row.get("allegiance")),
        "security":          _economy_str(row.get("security")),
        # Primary and secondary economy — enriched from populated dump
        "primaryEconomy":    _economy_str(row.get("primary_economy")),
        "secondaryEconomy":  _economy_str(row.get("secondary_economy")),
        # Pre-computed score from ratings table (NULL = unvisited)
        "rating":            row.get("score"),
        "score_components":  {
            "slots":         row.get("r_slots"),
            "bodyQuality":   row.get("r_body_quality"),
            "compactness":   row.get("r_compactness"),
            "signalQuality": row.get("r_signal_quality"),
            "orbitalSafety": row.get("r_orbital_safety"),
            "starBonus":     row.get("r_star_bonus"),
        } if row.get("score") is not None else None,
        "bodies":            bodies,
        "source":            "local_db",
    }


def _normalize_body(row: asyncpg.Record) -> dict:
    """Convert a body row into the wire format the frontend expects."""
    # ring_types: stored as JSONB array in PG
    rings_raw = row.get("ring_types") or []
    if isinstance(rings_raw, str):
        try:
            rings_raw = json.loads(rings_raw)
        except Exception:
            rings_raw = []
    rings = [{"type": t} for t in rings_raw if t]

    # signals: stored as JSONB [{name, count}] in PG
    signals_raw = row.get("signals") or []
    if isinstance(signals_raw, str):
        try:
            signals_raw = json.loads(signals_raw)
        except Exception:
            signals_raw = []

    # Fallback: derive signals from volcanism proxy (bodies table may not have
    # the signals column populated for older imports)
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


# ---------------------------------------------------------------------------
# Core search
# ---------------------------------------------------------------------------
async def local_db_search(body: dict, pool: asyncpg.Pool) -> dict:
    """
    Execute a filtered system search against the Hetzner PostgreSQL DB.

    Accepts the same body format as the Pi version / Spansh API:
        reference_coords {x, y, z}
        filters:
            distance    {min, max}
            population  {value, comparison}
        body_filters   {key: {min, max}}     — body type counts
        require_bio    bool
        require_geo    bool
        require_terra  bool
        star_types     [str]
        min_rating     int
        economy        str                   — primary_economy filter
        secondary_economy str               — secondary_economy filter
        size           int                   — page size
        from           int                   — page offset
        sort_by        'rating' | 'distance' — default 'rating'

    Returns the same response shape as the Pi version:
        {results: [...], count: int, total: int, source: 'local_db', query_ms: int}
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
    economy_filter   = body.get("economy")    or body.get("filters", {}).get("economy")
    sec_econ_filter  = body.get("secondary_economy")
    galaxy_wide      = bool(body.get("galaxy_wide", False))

    # ── Build the main distance-search query ─────────────────────────────────
    # Strategy:
    #   1. Bounding-box pre-filter (uses idx_sys_coords — instant)
    #   2. Precise Euclidean distance check in WHERE
    #   3. LEFT JOIN ratings for pre-computed scores
    #   4. Optional: filter on economy, star_type, population, min_rating
    #   5. Sort by rating DESC (default) or distance ASC
    #   6. Paginate
    #
    # Body filters (require_bio, require_geo, require_terra, body_filters) are
    # applied in Python after the main query using a batch bodies fetch — same
    # pattern as the Pi version.  This avoids a many-to-many JOIN explosion on
    # the 800M-row bodies table.

    params: list = []
    wheres: list = []
    p = 1  # asyncpg uses $1, $2, ... placeholders

    def add(val):
        nonlocal p
        params.append(val)
        idx = p
        p += 1
        return f"${idx}"

    if not galaxy_wide:
        # Bounding box (pre-filter — hits the coordinate B-tree index)
        wheres.append(f"s.x BETWEEN {add(rx - max_dist)} AND {add(rx + max_dist)}")
        wheres.append(f"s.y BETWEEN {add(ry - max_dist)} AND {add(ry + max_dist)}")
        wheres.append(f"s.z BETWEEN {add(rz - max_dist)} AND {add(rz + max_dist)}")
        # Precise distance (Euclidean)
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

    if star_types:
        placeholders = ", ".join(add(st) for st in star_types)
        wheres.append(f"s.main_star_class IN ({placeholders})")

    if min_rating > 0:
        wheres.append(f"r.score >= {add(min_rating)}")

    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    # Distance expression for ORDER BY / SELECT
    if not galaxy_wide:
        dist_expr = (
            f"SQRT((s.x-{add(rx)})*(s.x-{add(rx)}) + "
            f"(s.y-{add(ry)})*(s.y-{add(ry)}) + "
            f"(s.z-{add(rz)})*(s.z-{add(rz)}))"
        )
    else:
        dist_expr = "0.0"

    order_sql = (
        "ORDER BY r.score DESC NULLS LAST, dist ASC"
        if sort_by == "rating"
        else "ORDER BY dist ASC"
    )

    sql = f"""
        SELECT
            s.id64, s.name, s.x, s.y, s.z,
            s.main_star_class,
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
            r.score,
            r.slots               AS r_slots,
            r.body_quality        AS r_body_quality,
            r.compactness         AS r_compactness,
            r.signal_quality      AS r_signal_quality,
            r.orbital_safety      AS r_orbital_safety,
            r.star_bonus          AS r_star_bonus,
            {dist_expr} AS dist
        FROM systems s
        LEFT JOIN ratings r ON r.system_id64 = s.id64
        {where_sql}
        {order_sql}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)

    # ── Body filters (Python-side, batch bodies fetch) ─────────────────────
    need_bodies = bool(body_filters or require_bio or require_geo or require_terra)
    bodies_map: Dict[int, list] = {}

    if need_bodies and rows:
        cand_ids = [r["id64"] for r in rows]
        async with pool.acquire() as conn:
            body_rows = await conn.fetch("""
                SELECT
                    b.system_id64,
                    b.id, b.name, b.type, b.subtype,
                    b.distance_from_star, b.is_landable, b.is_tidal_lock,
                    b.atmosphere, b.volcanism, b.terraform_state,
                    b.surface_gravity, b.surface_temp,
                    b.mass, b.radius,
                    b.bio_signals, b.geo_signals,
                    b.mapped_value, b.scan_value,
                    b.ring_types, b.signals, b.has_signals
                FROM bodies b
                WHERE b.system_id64 = ANY($1::bigint[])
                ORDER BY b.system_id64, b.distance_from_star
            """, cand_ids)

        for br in body_rows:
            sid = br["system_id64"]
            bodies_map.setdefault(sid, []).append(_normalize_body(br))

    # Apply body filters and assemble results
    results: list = []
    for row in rows:
        sid = row["id64"]
        body_list = bodies_map.get(sid, [])

        if need_bodies:
            if body_filters:
                counts = _count_body_types(body_list)
                skip = False
                for key, rng in body_filters.items():
                    val = counts.get(key, 0)
                    if rng.get("min", 0) > 0 and val < rng["min"]:
                        skip = True; break
                    if rng.get("max") is not None and val > rng["max"]:
                        skip = True; break
                if skip:
                    continue
            if require_bio and not any(b.get("has_signals") for b in body_list):
                continue
            if require_geo and not any(
                b.get("volcanism") and b["volcanism"] not in ("", "No volcanism")
                for b in body_list
            ):
                continue
            if require_terra and not any(
                b.get("terraforming_state") and
                b["terraforming_state"] not in ("Not terraformable", "")
                for b in body_list
            ):
                continue

        rec = _build_system_record(row, body_list)
        rec["distance"] = round(float(row["dist"]), 2)

        # If no pre-computed score, compute live (unvisited / Phase-2-missing)
        if rec["rating"] is None and body_list:
            rated = rate_system(rec)
            rec["rating"] = rated["total"]
            rec["score_components"] = rated

        results.append(rec)

    # Pagination
    total   = len(results)
    page    = results[from_idx: from_idx + size]
    elapsed = round((time.time() - t0) * 1000)

    log.debug("local_db_search: %d total, returning %d (from=%d) in %dms",
              total, len(page), from_idx, elapsed)

    resp: Dict[str, Any] = {
        "results":  page,
        "count":    len(page),
        "total":    total,
        "source":   "local_db",
        "query_ms": elapsed,
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
    """
    Galaxy-wide economy search — no distance filter.

    Returns the highest-scoring uncolonised systems with the given economy,
    sorted by pre-computed rating score DESC.  Uses the compound index
    idx_sys_econ_pop (primary_economy, population WHERE population=0).

    Body:
        economy       str    — required: 'HighTech', 'Agriculture', etc.
        min_score     int    — minimum rating (default 0)
        limit         int    — max results (default 100, max 500)
        include_colonised bool — include already-colonised systems (default false)
    """
    t0 = time.time()

    economy  = body.get("economy", "")
    min_score = int(body.get("min_score", 0))
    limit    = min(int(body.get("limit", 100)), 500)
    include_colonised = bool(body.get("include_colonised", False))

    if not economy or economy in ("any", "Any", ""):
        return {"error": "economy is required for galaxy-wide search", "results": []}

    params = [economy, limit]
    extra_where = ""
    if not include_colonised:
        extra_where += " AND s.population = 0 AND s.is_colonised = FALSE"
    if min_score > 0:
        params.insert(1, min_score)
        extra_where += f" AND r.score >= ${len(params) - 1}"
        params[-1] = limit   # fix limit position

    # Rebuild cleanly
    params = []
    wheres = ["s.primary_economy = $1::economy_type"]
    params.append(economy)
    p = 2

    if not include_colonised:
        wheres.append("s.population = 0")
        wheres.append("s.is_colonised = FALSE")

    if min_score > 0:
        wheres.append(f"r.score >= ${p}")
        params.append(min_score)
        p += 1

    params.append(limit)
    limit_ph = f"${p}"

    sql = f"""
        SELECT
            s.id64, s.name, s.x, s.y, s.z,
            s.main_star_class,
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
            r.score,
            r.slots               AS r_slots,
            r.body_quality        AS r_body_quality,
            r.compactness         AS r_compactness,
            r.signal_quality      AS r_signal_quality,
            r.orbital_safety      AS r_orbital_safety,
            r.star_bonus          AS r_star_bonus,
            0.0                   AS dist
        FROM systems s
        LEFT JOIN ratings r ON r.system_id64 = s.id64
        WHERE {' AND '.join(wheres)}
        ORDER BY r.score DESC NULLS LAST
        LIMIT {limit_ph}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)

    results = [_build_system_record(r) for r in rows]
    elapsed = round((time.time() - t0) * 1000)

    log.info("galaxy_search(%s, min_score=%d): %d results in %dms",
             economy, min_score, len(results), elapsed)
    return {
        "results":  results,
        "count":    len(results),
        "total":    len(results),
        "source":   "local_db",
        "query_ms": elapsed,
    }


# ---------------------------------------------------------------------------
# Multi-economy cluster search
# ---------------------------------------------------------------------------
async def local_db_cluster_search(body: dict, pool: asyncpg.Pool) -> dict:
    """
    Multi-economy cluster search — find areas of space that satisfy ALL
    requested economy types within CLUSTER_RADIUS_LY (default 500 LY).

    Uses the pre-aggregated cluster_summary table (built by build_clusters.py).
    Each row in cluster_summary covers a 500 LY grid cell and pre-counts
    how many viable systems of each economy type exist within CLUSTER_RADIUS_LY
    of the grid anchor point.

    Body:
        requirements  list of:
            {economy: str, min_count: int, min_score: int (optional)}
        limit         int    — max clusters to return (default 50, max 200)
        min_total_score int  — minimum sum of best scores across requirements

    Returns:
        {clusters: [...], count: int, query_ms: int}
        Each cluster:
            anchor_id64, anchor_name, anchor_x/y/z,
            satisfied_requirements: [{economy, count, best_score}],
            total_best_score,
            systems: [list of top matching systems per economy]
    """
    t0 = time.time()

    requirements = body.get("requirements", [])
    limit        = min(int(body.get("limit", 50)), 200)

    if not requirements:
        return {"error": "requirements list is required", "clusters": []}

    # Build WHERE clause on cluster_summary
    # cluster_summary columns: grid_cell_id, economy_type, viable_count,
    #   best_score, anchor_id64, anchor_x, anchor_y, anchor_z
    # We need clusters that satisfy ALL requirements simultaneously.
    # Approach: use a HAVING COUNT(DISTINCT economy) = N after aggregating
    # grid cells that pass each individual economy requirement.

    req_parts = []
    params    = []
    p         = 1

    for req in requirements:
        econ      = req.get("economy", "")
        min_count = int(req.get("min_count", 1))
        min_score = int(req.get("min_score", 0))
        if not econ or econ in ("any", ""):
            continue

        params.append(econ)
        params.append(min_count)
        sub_where = f"economy_type = ${p}::economy_type AND viable_count >= ${p+1}"
        p += 2
        if min_score > 0:
            params.append(min_score)
            sub_where += f" AND best_score >= ${p}"
            p += 1
        req_parts.append(sub_where)

    if not req_parts:
        return {"error": "No valid requirements provided", "clusters": []}

    n_requirements = len(req_parts)
    combined_filter = " OR ".join(f"({r})" for r in req_parts)

    params.append(n_requirements)
    params.append(limit)

    sql = f"""
        SELECT
            cs.grid_cell_id,
            cs.anchor_id64,
            s.name  AS anchor_name,
            cs.anchor_x, cs.anchor_y, cs.anchor_z,
            COUNT(DISTINCT cs.economy_type)     AS economies_satisfied,
            SUM(cs.best_score)                  AS total_best_score,
            JSON_AGG(JSON_BUILD_OBJECT(
                'economy',    cs.economy_type::text,
                'count',      cs.viable_count,
                'best_score', cs.best_score
            ))                                  AS economy_breakdown
        FROM cluster_summary cs
        JOIN systems s ON s.id64 = cs.anchor_id64
        WHERE {combined_filter}
        GROUP BY cs.grid_cell_id, cs.anchor_id64, s.name,
                 cs.anchor_x, cs.anchor_y, cs.anchor_z
        HAVING COUNT(DISTINCT cs.economy_type) >= ${p - 1}
        ORDER BY total_best_score DESC
        LIMIT ${p}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)

    clusters = []
    for row in rows:
        breakdown = row["economy_breakdown"]
        if isinstance(breakdown, str):
            try:
                breakdown = json.loads(breakdown)
            except Exception:
                breakdown = []

        clusters.append({
            "grid_cell_id":             row["grid_cell_id"],
            "anchor_id64":              row["anchor_id64"],
            "anchor_name":              row["anchor_name"],
            "anchor_coords": {
                "x": float(row["anchor_x"]),
                "y": float(row["anchor_y"]),
                "z": float(row["anchor_z"]),
            },
            "economies_satisfied":      row["economies_satisfied"],
            "total_best_score":         row["total_best_score"],
            "economy_breakdown":        breakdown,
            "cluster_radius_ly":        CLUSTER_RADIUS_LY,
        })

    elapsed = round((time.time() - t0) * 1000)
    log.info("cluster_search(%d requirements): %d clusters in %dms",
             n_requirements, len(clusters), elapsed)

    return {
        "clusters":     clusters,
        "count":        len(clusters),
        "requirements": requirements,
        "cluster_radius_ly": CLUSTER_RADIUS_LY,
        "query_ms":     elapsed,
    }


# ---------------------------------------------------------------------------
# System detail
# ---------------------------------------------------------------------------
async def local_db_system(id64: int, pool: asyncpg.Pool) -> Optional[dict]:
    """
    Return full system data from local DB, including bodies.
    Returns None if not found.
    Response shape: {"record": {...}}  — wire-compatible with Spansh /system/{id64}.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                s.id64, s.name, s.x, s.y, s.z,
                s.main_star_class,
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
                r.score,
                r.slots               AS r_slots,
                r.body_quality        AS r_body_quality,
                r.compactness         AS r_compactness,
                r.signal_quality      AS r_signal_quality,
                r.orbital_safety      AS r_orbital_safety,
                r.star_bonus          AS r_star_bonus,
                0.0                   AS dist
            FROM systems s
            LEFT JOIN ratings r ON r.system_id64 = s.id64
            WHERE s.id64 = $1
        """, id64)

        if not row:
            return None

        body_rows = await conn.fetch("""
            SELECT
                b.id, b.name, b.type, b.subtype,
                b.distance_from_star, b.is_landable, b.is_tidal_lock,
                b.atmosphere, b.volcanism, b.terraform_state,
                b.surface_gravity, b.surface_temp,
                b.mass, b.radius,
                b.bio_signals, b.geo_signals,
                b.mapped_value, b.scan_value,
                b.ring_types, b.signals, b.has_signals
            FROM bodies b
            WHERE b.system_id64 = $1
            ORDER BY b.distance_from_star
        """, id64)

    body_list = [_normalize_body(b) for b in body_rows]

    record = _build_system_record(row, body_list)
    record["body_count"] = len(body_list)

    # Fetch stations
    async with pool.acquire() as conn:
        station_rows = await conn.fetch("""
            SELECT
                id, name, type::text AS type,
                distance_from_star,
                landing_pad_size::text AS landing_pad_size,
                economies, services,
                updated_at
            FROM stations
            WHERE system_id64 = $1
            ORDER BY distance_from_star
        """, id64)

    stations = []
    for st in station_rows:
        economie_raw = st["economies"]
        if isinstance(economie_raw, str):
            try:
                economie_raw = json.loads(economie_raw)
            except Exception:
                economie_raw = []
        services_raw = st["services"]
        if isinstance(services_raw, str):
            try:
                services_raw = json.loads(services_raw)
            except Exception:
                services_raw = []
        stations.append({
            "id":                   st["id"],
            "name":                 st["name"],
            "type":                 st["type"],
            "distance_to_arrival":  st["distance_from_star"],
            "landingPads":          {"large": 1 if st["landing_pad_size"] == "Large" else 0},
            "economies":            economie_raw or [],
            "services":             services_raw or [],
            "updated_at":           st["updated_at"].isoformat() if st["updated_at"] else None,
        })

    record["stations"]   = stations
    record["source"]     = "local_db"

    return {"record": record}


# ---------------------------------------------------------------------------
# Autocomplete
# ---------------------------------------------------------------------------
async def local_db_autocomplete(q: str, pool: asyncpg.Pool) -> list:
    """
    Fast trigram-based prefix search for system names.
    Uses idx_sys_name_trgm (GIN trigram index) on systems.name.
    Returns list of {name, id64, record} dicts (max 10).
    """
    if len(q) < 2:
        return []

    async with pool.acquire() as conn:
        # Try exact prefix first (fastest, uses idx_sys_name btree)
        rows = await conn.fetch("""
            SELECT id64, name, x, y, z
            FROM systems
            WHERE name ILIKE $1
            ORDER BY name
            LIMIT 10
        """, q + "%")

        # If fewer than 5 exact-prefix results, supplement with trigram search
        if len(rows) < 5 and len(q) >= 3:
            trgm_rows = await conn.fetch("""
                SELECT id64, name, x, y, z
                FROM systems
                WHERE name % $1
                  AND name NOT ILIKE $2
                ORDER BY similarity(name, $1) DESC
                LIMIT $3
            """, q, q + "%", 10 - len(rows))
            # Deduplicate
            seen_ids = {r["id64"] for r in rows}
            rows = list(rows) + [r for r in trgm_rows if r["id64"] not in seen_ids]

    return [
        {
            "name":   r["name"],
            "id64":   r["id64"],
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
    """
    Return info about the Hetzner PostgreSQL database.
    Wire-compatible with the Pi local_db_status() response.
    """
    try:
        async with pool.acquire() as conn:
            sys_count   = await conn.fetchval("SELECT COUNT(*) FROM systems")
            rated_count = await conn.fetchval(
                "SELECT COUNT(*) FROM ratings WHERE score IS NOT NULL"
            )
            body_count  = await conn.fetchval("SELECT COUNT(*) FROM bodies")
            station_count = await conn.fetchval("SELECT COUNT(*) FROM stations")
            cluster_count = await conn.fetchval("SELECT COUNT(*) FROM cluster_summary")
            grid_count    = await conn.fetchval("SELECT COUNT(*) FROM spatial_grid")

            # Import progress
            import_rows = await conn.fetch(
                "SELECT dump_name, status, rows_imported, started_at, completed_at "
                "FROM import_progress ORDER BY started_at DESC"
            )
            import_status = {
                r["dump_name"]: {
                    "status":        r["status"],
                    "rows_imported": r["rows_imported"],
                    "started_at":    r["started_at"].isoformat() if r["started_at"] else None,
                    "completed_at":  r["completed_at"].isoformat() if r["completed_at"] else None,
                }
                for r in import_rows
            }

            # DB size
            db_size_bytes = await conn.fetchval(
                "SELECT pg_database_size(current_database())"
            )

            # Last EDDN update
            eddn_row = await conn.fetchrow(
                "SELECT last_seen FROM eddn_log ORDER BY last_seen DESC LIMIT 1"
            )
            eddn_last = eddn_row["last_seen"].isoformat() if eddn_row else None

            # PostgreSQL version
            pg_version = await conn.fetchval("SELECT version()")

        return {
            "available":            True,
            "backend":              "postgresql",
            "pg_version":           pg_version,
            "systems_count":        sys_count,
            "rated_count":          rated_count,    # systems with a pre-computed score
            "body_count":           body_count,
            "station_count":        station_count,
            "cluster_count":        cluster_count,  # rows in cluster_summary
            "grid_cells":           grid_count,
            "db_size_mb":           round(db_size_bytes / 1_048_576, 1) if db_size_bytes else 0,
            "import_status":        import_status,
            "eddn_last_seen":       eddn_last,
            "max_search_radius_ly": int(MAX_SEARCH_RADIUS),
            "cluster_radius_ly":    int(CLUSTER_RADIUS_LY),
            "has_bodies":           True,
            "has_cluster_summary":  cluster_count > 0,
        }
    except Exception as exc:
        log.warning("local_db_status error: %s", exc)
        return {"available": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Body type counting (mirrors frontend countBodyTypes exactly)
# ---------------------------------------------------------------------------
def _count_body_types(bodies: list) -> dict:
    """
    Count body subtypes for filter matching.
    Mirrors countBodyTypes() in frontend/index.html.
    Input: list of normalised body dicts (from _normalize_body).
    """
    from collections import defaultdict
    counts: dict = defaultdict(int)

    SUBTYPE_MAP = {
        # Terrestrial planets
        "Earth-like world":         "elw",
        "Water world":              "ww",
        "Ammonia world":            "ammonia",
        "High metal content world": "hmc",
        "Metal-rich body":          "metalRich",
        "Rocky body":               "rocky",
        "Rocky Ice world":          "rockyIce",
        "Icy body":                 "icy",
        # Gas giants — all classes map to the same counter
        "Class I gas giant":                    "gasGiant",
        "Class II gas giant":                   "gasGiant",
        "Class III gas giant":                  "gasGiant",
        "Class IV gas giant":                   "gasGiant",
        "Class V gas giant":                    "gasGiant",
        "Gas giant with water-based life":      "gasGiant",
        "Gas giant with ammonia-based life":    "gasGiant",
        "Water giant":                          "gasGiant",
        "Helium-rich gas giant":                "gasGiant",
        "Helium gas giant":                     "gasGiant",
        # Stellar remnants
        "Black Hole":    "blackHoles",
        "Neutron Star":  "neutron",
        # White Dwarfs have spectral suffixes — handled via substring below
    }

    for b in bodies:
        sub   = (b.get("subtype") or "").strip()
        btype = (b.get("type") or "").strip()

        key = SUBTYPE_MAP.get(sub)
        if key:
            counts[key] += 1
        elif btype == "Star":
            if "White Dwarf" in sub:
                counts["whiteDwarf"] += 1
            elif sub not in SUBTYPE_MAP:
                counts["otherStars"] += 1

        if b.get("is_landable"):
            counts["landable"] += 1
            atm      = (b.get("atmosphere") or "").strip()
            is_tidal = bool(
                b.get("is_rotational_period_tidally_locked") or
                b.get("is_tidal_lock")
            )
            if (not atm or atm.lower() in ("", "no atmosphere", "none")) and not is_tidal:
                counts["walkable"] += 1

        # Signals — prefer normalised signals array, fall back to bio/geo_signals int cols
        sigs = b.get("signals")
        if isinstance(sigs, list) and sigs:
            for sig in sigs:
                name = sig.get("name", "")
                if name == "Geological":
                    counts["geoSignal"] += 1
                elif name == "Biological":
                    counts["bioSignal"] += 1
        else:
            bio_sigs = b.get("bio_signals") or 0
            geo_sigs = b.get("geo_signals") or 0
            if bio_sigs:
                counts["bioSignal"] += 1
            if geo_sigs:
                counts["geoSignal"] += 1

        # Rings
        rings_list = b.get("rings")
        if isinstance(rings_list, list):
            counts["rings"] += len(rings_list)

    return dict(counts)


# ---------------------------------------------------------------------------
# Server-side rating (mirrors frontend rateSystem() — keep in sync)
# ---------------------------------------------------------------------------
def rate_system(sys: dict) -> dict:
    """
    Compute colonisation-suitability rating for a system dict.

    Used for systems that do not have a pre-computed score in the ratings table
    (e.g. systems visited after the last build_ratings.py run, or systems
     where only star-class data is available).

    Mirrors rateSystem() in frontend/index.html exactly.

    Score components (max):
        starBonus      10  — spectral class
        slots          20  — landable + orbital body count
        bodyQuality    25  — ELW / WW / Ammonia + terraformable bonuses
        compactness    20  — max planet distance to arrival
        signalQuality  15  — bio / geo signals
        orbitalSafety  10  — moon-of-moon proximity penalty
    Total max: 100
    """
    bodies = sys.get("bodies") or []

    if sys.get("needs_permit"):
        return {"total": 0, "slots": 0, "bodyQuality": 0,
                "compactness": 0, "signalQuality": 0,
                "orbitalSafety": 0, "starBonus": 0}

    # ── Star type bonus ───────────────────────────────────────────────────────
    main_star = (
        sys.get("main_star") or
        sys.get("main_star_class") or
        sys.get("mainStar") or ""
    ).upper().strip()
    star_class = main_star.split(" ")[0][:1] if main_star else ""

    if star_class in ("G", "K"):
        star_bonus = 10
    elif star_class in ("F", "M"):
        star_bonus = 7
    elif star_class in ("A", "B"):
        star_bonus = 5
    elif "NEUTRON" in main_star:
        star_bonus = 4
    elif "WHITE DWARF" in main_star:
        star_bonus = 3
    elif "BLACK HOLE" in main_star:
        star_bonus = 2
    else:
        star_bonus = 4  # unknown / other

    # ── Slot score ────────────────────────────────────────────────────────────
    landable = sum(1 for b in bodies if b.get("type") == "Planet" and b.get("is_landable"))
    orbital  = (
        sum(1 for b in bodies if b.get("type") == "Planet" and not b.get("is_landable")) +
        sum(1 for b in bodies if b.get("type") == "Star")
    )
    if not bodies:
        slots = 10
    else:
        slots = min(20, round((min(landable, 10) / 10 + min(orbital, 10) / 10) * 10))

    # ── Body quality ──────────────────────────────────────────────────────────
    body_quality = 0
    for b in bodies:
        sub  = (b.get("subtype") or "").strip()
        sigs = b.get("signals") or []
        has_geo = any(s.get("name") == "Geological" for s in sigs)
        has_bio = any(s.get("name") == "Biological"  for s in sigs)

        if sub == "Earth-like world":
            body_quality += 10
            if (b.get("distance_to_arrival") or 0) < 5000:
                body_quality += 2
        elif sub == "Water world":
            body_quality += 8
            if (b.get("distance_to_arrival") or 0) < 5000:
                body_quality += 1
        elif sub == "Ammonia world":
            body_quality += 5
        elif any(x in sub for x in ("Black Hole", "Neutron", "White Dwarf")):
            body_quality += 4
        elif sub in ("High metal content world", "Metal-rich body"):
            body_quality += 5 if has_bio else (4 if has_geo else 3)
        elif sub == "Rocky body":
            body_quality += 4 if has_bio else (3 if has_geo else 2)
        elif sub == "Rocky Ice world":
            body_quality += 3
        elif sub == "Icy body":
            body_quality += 2

        terra = (b.get("terraforming_state") or "").strip()
        if terra and terra not in ("Not terraformable", ""):
            body_quality += 4 if has_bio else 2

    body_quality = min(25, body_quality)

    # ── Compactness ───────────────────────────────────────────────────────────
    planets = [b for b in bodies if b.get("type") == "Planet"]
    if not planets:
        compactness = 10
    else:
        max_d = max((b.get("distance_to_arrival") or 0) for b in planets)
        if   max_d <= 500:    compactness = 20
        elif max_d <= 1000:   compactness = 17
        elif max_d <= 5000:   compactness = 13
        elif max_d <= 20000:  compactness = 9
        elif max_d <= 50000:  compactness = 6
        elif max_d <= 250000: compactness = 3
        else:                 compactness = 0

    # ── Signal quality ────────────────────────────────────────────────────────
    bio_count = sum(1 for b in bodies if any(
        s.get("name") == "Biological" for s in (b.get("signals") or [])))
    geo_count = sum(1 for b in bodies if any(
        s.get("name") == "Geological" for s in (b.get("signals") or [])))
    both_sigs = sum(1 for b in bodies if (
        any(s.get("name") == "Geological" for s in (b.get("signals") or [])) and
        any(s.get("name") == "Biological"  for s in (b.get("signals") or []))
    ))
    signal_quality = min(15,
        min(bio_count, 3) * 2 +
        min(geo_count, 3) * 2 +
        both_sigs * 3
    )

    # ── Orbital safety ────────────────────────────────────────────────────────
    close_pairs = sum(
        1 for b in bodies
        if any(p.get("type") == "Planet" for p in (b.get("parents") or []))
    )
    if   close_pairs == 0:  orbital_safety = 10
    elif close_pairs <= 2:  orbital_safety = 7
    elif close_pairs <= 5:  orbital_safety = 4
    else:                   orbital_safety = 1

    total = min(100,
        slots + body_quality + compactness + signal_quality + orbital_safety + star_bonus
    )
    return {
        "total":         total,
        "slots":         slots,
        "bodyQuality":   body_quality,
        "compactness":   compactness,
        "signalQuality": signal_quality,
        "orbitalSafety": orbital_safety,
        "starBonus":     star_bonus,
    }
