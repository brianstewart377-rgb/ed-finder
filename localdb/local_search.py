"""
ED:Finder — Local Galaxy DB Search Module
==========================================
Provides fast local search against the galaxy.db populated by import_systems.py.
Imported by main.py; no network calls — all queries run against local SQLite.

Public API:
    local_db_search(body: dict) -> dict      # mirrors Spansh /systems/search response
    local_db_system(id64: int)  -> dict      # mirrors Spansh /system/{id64} response
    local_db_autocomplete(q: str) -> list    # system name autocomplete from local DB
    local_db_status()           -> dict      # info about the local DB

Response shapes are intentionally compatible with Spansh API responses so the
frontend needs minimal changes — it just points at /api/local/* instead of /api/*.
"""
from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

log = logging.getLogger("ed-finder.localdb")

GALAXY_DB = os.getenv("GALAXY_DB_PATH", "/data/galaxy.db")
CELL_SIZE  = 25.0   # must match import_systems.py spatial grid cell size

# ── DB connection ─────────────────────────────────────────────────────────────
# Hard cap on search radius for the local DB.
# At CELL_SIZE=25 LY, a 500 LY radius = 85k grid cells — fine on Hetzner/desktop
# but overwhelms a Pi's RAM.  Default is 200 LY (8k cells, safe on Pi).
# Override with MAX_SEARCH_RADIUS_LY env var on beefier hardware:
#   Pi 4/5:         MAX_SEARCH_RADIUS_LY=200  (default)
#   Hetzner CX32:   MAX_SEARCH_RADIUS_LY=500
#   Hetzner CX52+:  MAX_SEARCH_RADIUS_LY=750
MAX_SEARCH_RADIUS = float(os.getenv("MAX_SEARCH_RADIUS_LY", "200"))

# ── Schema capability flags ────────────────────────────────────────────────────
# Probed lazily on first use; cached for the lifetime of the process.
# These flags let the search code work gracefully on DBs that haven't yet had
# migrate_v3_28.sql applied (i.e. the is_tidal_lock column is absent).
_BODIES_COLS: Optional[set] = None   # set of column names present in `bodies`
_TIDAL_LOCK_COL_WARNED = False        # emit the upgrade hint only once


def _probe_bodies_schema() -> set:
    """Return the set of column names that actually exist in the bodies table.

    Called lazily; result is cached in _BODIES_COLS so we only hit PRAGMA once.
    If the table does not exist yet (Phase-1-only DB) returns an empty set.
    """
    global _BODIES_COLS, _TIDAL_LOCK_COL_WARNED
    if _BODIES_COLS is not None:
        return _BODIES_COLS
    if not os.path.exists(GALAXY_DB):
        _BODIES_COLS = set()
        return _BODIES_COLS
    try:
        conn = sqlite3.connect(GALAXY_DB, check_same_thread=False, timeout=10)
        try:
            rows = conn.execute("PRAGMA table_info(bodies)").fetchall()
            _BODIES_COLS = {r[1] for r in rows}   # r[1] is the column name
        finally:
            conn.close()
    except Exception:
        _BODIES_COLS = set()
    if _BODIES_COLS and "is_tidal_lock" not in _BODIES_COLS and not _TIDAL_LOCK_COL_WARNED:
        _TIDAL_LOCK_COL_WARNED = True
        log.warning(
            "bodies table is missing the 'is_tidal_lock' column — "
            "tidal-lock filter will be disabled.  "
            "Run:  sqlite3 /data/galaxy.db < /app/localdb/migrate_v3_28.sql  "
            "to add the column and re-enable the filter."
        )
    return _BODIES_COLS


def _bodies_tidal_col() -> str:
    """Return the correct SQL fragment for the is_tidal_lock column.

    If the column exists in the schema, returns 'is_tidal_lock'.
    Otherwise returns '0 AS is_tidal_lock' so the query still works and
    every body is treated as non-tidal-locked (safest default).
    """
    cols = _probe_bodies_schema()
    if "is_tidal_lock" in cols:
        return "is_tidal_lock"
    return "0 AS is_tidal_lock"


def _open_galaxy_db() -> sqlite3.Connection:
    conn = sqlite3.connect(GALAXY_DB, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-32768")    # 32 MB — Pi has limited RAM
    conn.execute("PRAGMA mmap_size=268435456")  # 256 MB mmap
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA query_only=ON")        # read-only guard
    return conn


@contextmanager
def galaxy_conn():
    conn = _open_galaxy_db()
    try:
        yield conn
    finally:
        conn.close()


def is_available() -> bool:
    """Return True if the galaxy DB exists and has been populated."""
    if not os.path.exists(GALAXY_DB):
        return False
    try:
        with galaxy_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM systems").fetchone()[0]
            return count > 0
    except Exception:
        return False


# ── Core search ──────────────────────────────────────────────────────────────
def local_db_search(body: dict) -> dict:
    """
    Execute a filtered system search against the local galaxy DB.

    Accepts the same body format as POST /api/systems/search (Spansh-compatible).
    Returns the same response shape: {results: [...], count: int, total: int}

    Supported filters:
        distance    {min, max}   from reference_coords
        population  {value, comparison}  (only 'equal' with value=0 supported)
        body_filters {key: {min, max}}   body type counts (requires Phase 2 bodies table)
        require_bio  bool                require biological signals
        require_geo  bool                require geological signals
        require_terra bool               require terraformable bodies
        star_types   [str]               allowed main star types
        min_rating   int                 minimum colonisation rating (0-100)

    Sort: rating descending by default (highest-rated systems first).
         Pass sort_by='distance' to get the old distance-ascending order.
    Pagination: from + size.
    No 10k cap — returns ALL matching systems.
    """
    t0 = time.time()

    # Parse request
    filters        = body.get("filters", {})
    ref_coords     = body.get("reference_coords", {})
    size           = min(int(body.get("size", 50_000)), 100_000)  # No 10k cap!
    from_idx       = int(body.get("from", 0))
    sort_by        = body.get("sort_by", "rating")  # 'rating' | 'distance'

    rx = float(ref_coords.get("x", 0))
    ry = float(ref_coords.get("y", 0))
    rz = float(ref_coords.get("z", 0))

    # Distance filter — cap at MAX_SEARCH_RADIUS to prevent Pi OOM
    dist_filter  = filters.get("distance", {})
    min_dist     = float(dist_filter.get("min", 0))
    max_dist_req = float(dist_filter.get("max", 500))
    max_dist     = min(max_dist_req, MAX_SEARCH_RADIUS)
    radius_capped = max_dist < max_dist_req  # True if we had to reduce it

    # Population filter — key improvement over Spansh
    pop_filter = filters.get("population", {})
    pop_val    = pop_filter.get("value")
    pop_cmp    = pop_filter.get("comparison", "equal")
    require_empty = (pop_val == 0 and pop_cmp == "equal")

    # Body filters (active after Phase 2 import)
    body_filters = body.get("body_filters", {})   # {key: {min, max}}
    require_bio   = body.get("require_bio", False)
    require_geo   = body.get("require_geo", False)
    require_terra = body.get("require_terra", False)
    star_types    = body.get("star_types", [])     # e.g. ["K", "G", "F"]
    min_rating    = int(body.get("min_rating", 0))

    systems, density_warning = _spatial_search(rx, ry, rz, min_dist, max_dist, require_empty,
                              body_filters, require_bio, require_geo,
                              require_terra, star_types, min_rating)

    # Surface radius cap to caller so frontend can show a warning banner
    if radius_capped and not density_warning:
        density_warning = (
            f"Search radius capped at {int(MAX_SEARCH_RADIUS)} LY "
            f"(requested {int(max_dist_req)} LY) — larger radii are too slow on this hardware. "
            f"Try ≤{int(MAX_SEARCH_RADIUS)} LY for fast results."
        )

    # ── Server-side rating + sort ─────────────────────────────────────────────
    # Compute rating for every result so we can sort highest-rated first.
    # This mirrors rateSystem() in frontend/index.html exactly so the client
    # and server agree on scores.  Attaching the rating here also means the
    # frontend can skip re-computing it (it will still re-compute for display,
    # but pagination is already in the right order).
    for sys in systems:
        r = rate_system(sys)
        sys["rating"] = r["total"]

    if sort_by == "rating":
        # Highest rating first; break ties by distance ascending
        systems.sort(key=lambda s: (-s["rating"], s["distance"]))
    else:
        # Distance ascending (legacy / explicit request)
        systems.sort(key=lambda s: s["distance"])

    # min_rating filter applied after rating computed
    if min_rating > 0:
        systems = [s for s in systems if s["rating"] >= min_rating]

    # Apply pagination
    total    = len(systems)
    page     = systems[from_idx: from_idx + size]
    elapsed  = round((time.time() - t0) * 1000)

    log.debug("local_db_search: %d total, returning %d (from=%d) in %dms",
              total, len(page), from_idx, elapsed)

    resp: Dict[str, Any] = {
        "results":  page,
        "count":    len(page),
        "total":    total,
        "source":   "local_db",
        "query_ms": elapsed,
    }
    if density_warning:
        resp["warning"] = density_warning
    return resp


def _spatial_search(
    rx: float, ry: float, rz: float,
    min_dist: float, max_dist: float,
    require_empty: bool,
    body_filters: dict = None,
    require_bio: bool = False,
    require_geo: bool = False,
    require_terra: bool = False,
    star_types: list = None,
    min_rating: int = 0,
) -> List[dict]:
    """
    Use spatial grid cells to find candidate systems, then filter by exact distance.

    Strategy:
      1. Calculate which grid cells fall within [min_dist-cell, max_dist+cell]
      2. Fetch systems from those cells (fast index lookup, streaming to bound RAM)
      3. Compute exact Euclidean distance and filter
      4. JOIN colonisation table to exclude inhabited systems when require_empty=True
      5. Optionally JOIN bodies table to apply body filters (Phase 2)
      6. Return sorted by distance asc, enriched with colonisation + body data

    Returns:
        (results: List[dict], warning: str | None)
        warning is set when the raw row cap was hit (dense region like galactic core).
    """
    body_filters  = body_filters  or {}
    star_types    = star_types    or []
    # Grid cells to search
    cell = CELL_SIZE
    # Expand by one cell to handle edge cases
    cx_min = math.floor((rx - max_dist - cell) / cell)
    cx_max = math.ceil( (rx + max_dist + cell) / cell)
    cy_min = math.floor((ry - max_dist - cell) / cell)
    cy_max = math.ceil( (ry + max_dist + cell) / cell)
    cz_min = math.floor((rz - max_dist - cell) / cell)
    cz_max = math.ceil( (rz + max_dist + cell) / cell)

    min_dist_sq = min_dist * min_dist
    max_dist_sq = max_dist * max_dist

    with galaxy_conn() as conn:
        # Check if spatial_grid table exists (created after first import)
        has_grid = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='spatial_grid'"
        ).fetchone() is not None

        # BUG-DENSITY FIX: Dense regions (galactic core, Sgr A*) can produce
        # hundreds of thousands of candidate rows for large search radii.
        # fetchall() loads ALL rows into RAM at once — causing OOM and timeouts.
        # Fix: stream rows via fetchmany() / iteration so RAM stays bounded.
        # We also add a hard cap on RAW candidate rows (before distance filter)
        # to prevent runaway queries near the core.  The cap is generous enough
        # that normal searches (Sol ±500 LY) are unaffected; only extreme-density
        # galactic-core searches are capped, and we surface this to the caller.
        RAW_ROW_CAP = 500_000   # rows fetched from DB before dist filtering

        if has_grid:
            # Fast path: use spatial grid — stream with fetchmany to bound RAM
            cursor = conn.execute("""
                SELECT s.id64, s.name, s.x, s.y, s.z, s.main_star, s.needs_permit,
                       c.population, c.is_colonised, c.is_being_colonised,
                       c.controlling_faction, c.state, c.government, c.allegiance, c.economy
                FROM spatial_grid sg
                JOIN systems s ON s.id64 = sg.id64
                LEFT JOIN colonisation c ON c.id64 = s.id64
                WHERE sg.cx BETWEEN ? AND ?
                  AND sg.cy BETWEEN ? AND ?
                  AND sg.cz BETWEEN ? AND ?
            """, (cx_min, cx_max, cy_min, cy_max, cz_min, cz_max))
            rows = []
            while True:
                batch = cursor.fetchmany(10_000)
                if not batch:
                    break
                rows.extend(batch)
                if len(rows) >= RAW_ROW_CAP:
                    log.warning(
                        "_spatial_search: raw row cap %d hit near (%.1f,%.1f,%.1f) r=%.1f — "
                        "dense region (galactic core?). Results may be incomplete.",
                        RAW_ROW_CAP, rx, ry, rz, max_dist
                    )
                    break
        else:
            # Fallback: bounding-box scan (slower on large DB)
            cursor = conn.execute("""
                SELECT s.id64, s.name, s.x, s.y, s.z, s.main_star, s.needs_permit,
                       c.population, c.is_colonised, c.is_being_colonised,
                       c.controlling_faction, c.state, c.government, c.allegiance, c.economy
                FROM systems s
                LEFT JOIN colonisation c ON c.id64 = s.id64
                WHERE s.x BETWEEN ? AND ?
                  AND s.y BETWEEN ? AND ?
                  AND s.z BETWEEN ? AND ?
            """, (rx - max_dist - cell, rx + max_dist + cell,
                  ry - max_dist - cell, ry + max_dist + cell,
                  rz - max_dist - cell, rz + max_dist + cell))
            rows = []
            while True:
                batch = cursor.fetchmany(10_000)
                if not batch:
                    break
                rows.extend(batch)
                if len(rows) >= RAW_ROW_CAP:
                    log.warning(
                        "_spatial_search: raw row cap %d hit (bounding-box fallback) near "
                        "(%.1f,%.1f,%.1f) r=%.1f — results may be incomplete.",
                        RAW_ROW_CAP, rx, ry, rz, max_dist
                    )
                    break

    # Track whether the raw row cap was hit (dense region warning)
    density_capped = len(rows) >= RAW_ROW_CAP
    results = []

    # ── Phase 2 detection + single-pass body batch-fetch ──────────────────────
    # BUG-P1 FIX: previously we opened galaxy_conn() inside the per-system loop,
    # causing N SQLite connections for N candidate systems (potentially thousands
    # for large radii like 500 LY from Sgr A*).  That saturated the thread pool
    # and reliably exceeded the 30-second frontend timeout.
    #
    # Fix: one connection, one query.  We:
    #   1. Identify candidate system IDs that pass distance/population/star filters.
    #   2. In a single SQL query fetch ALL bodies for those IDs.
    #   3. Build a per-system_id64 dict of body lists.
    #   4. Normalise and filter in pure Python (no more DB round-trips per system).

    # Check if bodies table exists (Phase 2) — still just one connection
    with galaxy_conn() as conn:
        has_bodies = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bodies'"
        ).fetchone() is not None

    use_body_filters  = has_bodies and (body_filters or require_bio or require_geo or require_terra)
    always_fetch_bodies = has_bodies

    # ── Pass 1: distance / population / star-type pre-filter ──────────────────
    # Collect (row, dist, pop, is_col, being_col, ctrl) tuples that survive the
    # cheap scalar filters.  We carry the colonisation columns forward so Pass 3
    # can assemble the result dict without re-querying the DB.
    candidates: List[tuple] = []
    for row in rows:
        dx = row["x"] - rx
        dy = row["y"] - ry
        dz = row["z"] - rz
        dist_sq = dx*dx + dy*dy + dz*dz

        if dist_sq < min_dist_sq or dist_sq > max_dist_sq:
            continue

        pop       = row["population"] or 0
        is_col    = row["is_colonised"] or 0
        being_col = row["is_being_colonised"] or 0
        ctrl      = row["controlling_faction"]

        inhabited = bool(is_col or being_col or ctrl or pop > 0)
        if require_empty and inhabited:
            continue

        if star_types:
            main = (row["main_star"] or "").split()[0]
            if main not in star_types:
                continue

        dist = math.sqrt(dist_sq)
        candidates.append((row, dist, pop, is_col, being_col, ctrl))

    # ── Pass 2: batch-fetch bodies for all candidates in ONE query ─────────────
    # bodies_map: {system_id64: [normalised body dicts]}
    bodies_map: Dict[int, list] = {}
    if always_fetch_bodies and candidates:
        cand_ids = [row["id64"] for row, *_ in candidates]
        # SQLite has a variable-limit (~999 by default); chunk if needed.
        CHUNK = 900
        raw_bodies: list = []
        with galaxy_conn() as bconn:
            for start in range(0, len(cand_ids), CHUNK):
                chunk_ids = cand_ids[start: start + CHUNK]
                placeholders = ",".join("?" * len(chunk_ids))
                raw_bodies.extend(bconn.execute(f"""
                    SELECT system_id64, type, subtype, distance_to_arrival,
                           is_landable, {_bodies_tidal_col()}, has_signals, has_rings, ring_types,
                           atmosphere, volcanism, terraform_state,
                           surface_gravity, surface_temp, estimated_mapping_value, estimated_scan_value
                    FROM bodies
                    WHERE system_id64 IN ({placeholders})
                    ORDER BY system_id64, distance_to_arrival
                """, chunk_ids).fetchall())

        # Normalise and group by system_id64
        for b in raw_bodies:
            sid = b["system_id64"]
            bd  = dict(b)
            bd.pop("system_id64", None)

            # terraform_state → terraforming_state  (Spansh field name)
            bd["terraforming_state"] = bd.pop("terraform_state", None)
            # surface_gravity → gravity  (Spansh field name)
            bd["gravity"] = bd.pop("surface_gravity", None)
            # surface_temp → surface_temperature  (frontend field name)
            bd["surface_temperature"] = bd.pop("surface_temp", None)
            # is_tidal_lock (int 0/1) → is_rotational_period_tidally_locked (bool)
            bd["is_rotational_period_tidally_locked"] = bool(bd.pop("is_tidal_lock", 0))
            # ring_types JSON → rings array of {type: "..."}
            rt = bd.pop("ring_types", None)
            if rt:
                try:
                    names = json.loads(rt) if isinstance(rt, str) else rt
                    bd["rings"] = [{"type": t} for t in names if t]
                except Exception:
                    bd["rings"] = []
            else:
                bd["rings"] = []
            # has_signals int → signals array proxy
            if bd.get("has_signals"):
                volc = (bd.get("volcanism") or "").strip()
                if volc and volc not in ("", "No volcanism"):
                    bd["signals"] = [{"name": "Geological", "count": 1}]
                else:
                    bd["signals"] = [{"name": "Biological", "count": 1}]
            else:
                bd["signals"] = []

            bodies_map.setdefault(sid, []).append(bd)

    # ── Pass 3: body-filter + result assembly ─────────────────────────────────
    for row, dist, pop, is_col, being_col, ctrl in candidates:
        body_list = bodies_map.get(row["id64"], []) if always_fetch_bodies else []

        if always_fetch_bodies:
            # Apply body-type slider filters
            if use_body_filters and body_filters:
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

            # Signal/terra filters
            if require_bio and not any(b.get("has_signals") for b in body_list):
                continue
            if require_geo and not any(
                b.get("volcanism") and b["volcanism"] not in ("", "No volcanism")
                for b in body_list
            ):
                continue
            if require_terra and not any(
                b.get("terraforming_state") and b["terraforming_state"] not in ("", "Not terraformable")
                for b in body_list
            ):
                continue

        results.append({
            "id64":     row["id64"],
            "id":       str(row["id64"]),
            "name":     row["name"],
            "coords":   {"x": row["x"], "y": row["y"], "z": row["z"]},
            "distance": round(dist, 2),
            "main_star": row["main_star"],
            "needs_permit": bool(row["needs_permit"]),
            "population":           pop,
            "is_colonised":         is_col,
            "is_being_colonised":   being_col,
            "controlling_minor_faction": ctrl,
            "minor_faction_presences":  [],
            "government":  row["government"],
            "allegiance":  row["allegiance"],
            "primaryEconomy": row["economy"],
            "bodies":      body_list,
            "source": "local_db",
        })

    # Sort by distance for initial candidate list; final sort done in local_db_search
    results.sort(key=lambda s: s["distance"])

    warning = None
    if density_capped:
        warning = (
            f"Dense region detected: search scanned the maximum {RAW_ROW_CAP:,} candidate "
            f"systems near this location — results may be incomplete. "
            f"Try a smaller search radius (\u2264100 LY) near the galactic core."
        )

    return results, warning


def _count_body_types(bodies: list) -> dict:
    """Count body subtypes for filter matching — mirrors frontend countBodyTypes()."""
    from collections import defaultdict
    counts: dict = defaultdict(int)
    SUBTYPE_MAP = {
        # NOTE: Spansh galaxy dump uses these exact strings (confirmed from live API).
        # All entries must match exactly to avoid silent zero-counts.
        # \u2500\u2500 Terrestrial planets \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        "Earth-like world": "elw",
        "Water world": "ww",
        "Ammonia world": "ammonia",   # MUST match frontend BODY_SUBTYPE_MAP key 'ammonia'
        "High metal content world": "hmc",
        "Metal-rich body": "metalRich",
        "Rocky body": "rocky",
        "Rocky Ice world": "rockyIce",     # Spansh: lowercase 'w' confirmed live
        "Icy body": "icy",
        # \u2500\u2500 Gas giants \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        "Class I gas giant": "gasGiant",
        "Class II gas giant": "gasGiant",
        "Class III gas giant": "gasGiant",
        "Class IV gas giant": "gasGiant",
        "Class V gas giant": "gasGiant",
        "Gas giant with water-based life": "gasGiant",
        "Gas giant with ammonia-based life": "gasGiant",
        "Water giant": "gasGiant",         # Spansh confirmed \u2014 type='Planet', treat as gas giant
        "Helium-rich gas giant": "gasGiant",
        "Helium gas giant": "gasGiant",
        # \u2500\u2500 Stellar remnants \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        "Black Hole": "blackHoles",         # Spansh: 'Black Hole' (capital H)
        "Neutron Star": "neutron",          # Spansh: 'Neutron Star' (capital S)
        # White Dwarfs have spectral class suffixes in Spansh data:
        # 'White Dwarf (D) Star', 'White Dwarf (DA) Star', 'White Dwarf (DC) Star', 'White Dwarf (DQ) Star'
        # Handled below via substring match instead of exact SUBTYPE_MAP lookup.
    }
    for b in bodies:
        sub = (b.get("subtype") or "").strip()
        btype = (b.get("type") or "").strip()
        key = SUBTYPE_MAP.get(sub)
        if key:
            counts[key] += 1
        elif btype == "Star":
            # White Dwarfs have spectral suffixes: 'White Dwarf (DA) Star' etc.
            # Use substring match (mirrors frontend countBodyTypes via .includes('White Dwarf'))
            if "White Dwarf" in sub:
                counts["whiteDwarf"] += 1
            elif sub not in SUBTYPE_MAP:
                counts["otherStars"] += 1  # companion stars without a specific mapping

        if b.get("is_landable"):
            counts["landable"] += 1
            # walkable = landable + no atmosphere + not tidally locked
            # Mirrors frontend countBodyTypes (fixed in v3.28):
            #   if (b.is_landable && !(b.atmosphere||b.atmosphere_type) && !b.is_rotational_period_tidally_locked)
            atm = (b.get("atmosphere") or "").strip()
            is_tidal = bool(b.get("is_rotational_period_tidally_locked") or b.get("is_tidal_lock"))
            if (not atm or atm.lower() in ("", "no atmosphere", "none")) and not is_tidal:
                counts["walkable"] += 1

        # Count bodies with biological/geological signals.
        # Supports two body formats:
        #   - Normalized (from _spatial_search): has "signals" array AND "has_signals" int
        #   - Raw (legacy path): only "has_signals" int + "volcanism" proxy
        sigs = b.get("signals")
        if isinstance(sigs, list) and sigs:
            # Normalized format — use actual signal names
            for sig in sigs:
                if sig.get("name") == "Geological":
                    counts["geoSignal"] += 1
                elif sig.get("name") == "Biological":
                    counts["bioSignal"] += 1
        elif b.get("has_signals"):
            # Fallback: has_signals=1 flag only — use volcanism as geo proxy
            volc = (b.get("volcanism") or "").strip()
            if volc and volc not in ("", "No volcanism"):
                counts["geoSignal"] += 1
            else:
                counts["bioSignal"] += 1

        # Rings: support both normalized "rings" array and raw "ring_types" JSON string
        rings_list = b.get("rings")
        if isinstance(rings_list, list):
            counts["rings"] += len(rings_list)
        else:
            rt = b.get("ring_types")
            if rt:
                try:
                    rr = json.loads(rt) if isinstance(rt, str) else rt
                    counts["rings"] += len(rr) if isinstance(rr, list) else 1
                except Exception:
                    pass
    return dict(counts)


# ── Server-side rating (mirrors frontend rateSystem() exactly) ────────────────
def rate_system(sys: dict) -> dict:
    """
    Compute colonisation-suitability rating for a system dict.
    Mirrors rateSystem() in frontend/index.html — keep in sync.

    Components (max):
        starBonus      10 pts  — spectral class bonus
        slots          20 pts  — landable + orbital body count
        bodyQuality    25 pts  — ELW/WW/Ammonia + terraformable bonuses
        compactness    20 pts  — max planet distance to arrival
        signalQuality  15 pts  — bio/geo signals
        orbitalSafety  10 pts  — moon-of-moon proximity penalty
    Total max: 100 pts
    """
    bodies = sys.get("bodies") or []

    # Permit penalty
    if sys.get("needs_permit"):
        return {"total": 0, "slots": 0, "bodyQuality": 0,
                "compactness": 0, "signalQuality": 0,
                "orbitalSafety": 0, "starBonus": 0}

    # ── Star type bonus (10 pts) ──────────────────────────────────────────────
    main_star = (sys.get("main_star") or sys.get("mainStar") or "").upper().strip()
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

    # ── Slot score (20 pts) ──────────────────────────────────────────────────
    landable = sum(1 for b in bodies if b.get("type") == "Planet" and b.get("is_landable"))
    orbital  = (sum(1 for b in bodies if b.get("type") == "Planet" and not b.get("is_landable"))
                + sum(1 for b in bodies if b.get("type") == "Star"))
    if not bodies:
        slots = 10  # neutral midpoint — no Phase 2 data yet
    else:
        slots = min(20, round((min(landable, 10) / 10 + min(orbital, 10) / 10) * 10))

    # ── Body quality (25 pts) ────────────────────────────────────────────────
    body_quality = 0
    for b in bodies:
        sub  = (b.get("subtype") or "").strip()
        sigs = b.get("signals") or []
        has_geo = any(s.get("name") == "Geological"  for s in sigs)
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

    # ── Compactness (20 pts) ─────────────────────────────────────────────────
    planets = [b for b in bodies if b.get("type") == "Planet"]
    if not planets:
        compactness = 10  # neutral — no body data
    else:
        max_dist = max((b.get("distance_to_arrival") or 0) for b in planets)
        if   max_dist <= 500:    compactness = 20
        elif max_dist <= 1000:   compactness = 17
        elif max_dist <= 5000:   compactness = 13
        elif max_dist <= 20000:  compactness = 9
        elif max_dist <= 50000:  compactness = 6
        elif max_dist <= 250000: compactness = 3
        else:                    compactness = 0

    # ── Signal quality (15 pts) ──────────────────────────────────────────────
    bio_count  = sum(1 for b in bodies if any(s.get("name") == "Biological"  for s in (b.get("signals") or [])))
    geo_count  = sum(1 for b in bodies if any(s.get("name") == "Geological"  for s in (b.get("signals") or [])))
    both_sigs  = sum(1 for b in bodies if
                     any(s.get("name") == "Geological" for s in (b.get("signals") or [])) and
                     any(s.get("name") == "Biological"  for s in (b.get("signals") or [])))
    signal_quality = min(15,
        min(bio_count, 3) * 2 +
        min(geo_count, 3) * 2 +
        both_sigs * 3
    )

    # ── Orbital safety (10 pts) ──────────────────────────────────────────────
    close_pairs = sum(
        1 for b in bodies
        if any(p.get("type") == "Planet" for p in (b.get("parents") or []))
    )
    if   close_pairs == 0:  orbital_safety = 10
    elif close_pairs <= 2:  orbital_safety = 7
    elif close_pairs <= 5:  orbital_safety = 4
    else:                   orbital_safety = 1

    total = min(100, slots + body_quality + compactness + signal_quality + orbital_safety + star_bonus)
    return {
        "total":          total,
        "slots":          slots,
        "bodyQuality":    body_quality,
        "compactness":    compactness,
        "signalQuality":  signal_quality,
        "orbitalSafety":  orbital_safety,
        "starBonus":      star_bonus,
    }


# ── System detail ─────────────────────────────────────────────────────────────
def local_db_system(id64: int) -> Optional[dict]:
    """
    Return full system data from local DB, including bodies.
    Returns None if not found.
    Response shape mimics Spansh /system/{id64} → {"record": {...}}
    """
    with galaxy_conn() as conn:
        row = conn.execute("""
            SELECT s.id64, s.name, s.x, s.y, s.z, s.main_star, s.needs_permit,
                   c.population, c.is_colonised, c.is_being_colonised,
                   c.controlling_faction, c.state, c.government, c.allegiance, c.economy
            FROM systems s
            LEFT JOIN colonisation c ON c.id64 = s.id64
            WHERE s.id64 = ?
        """, (id64,)).fetchone()

        if not row:
            return None

        bodies = conn.execute(f"""
            SELECT id64, name, type, subtype, distance_to_arrival,
                   is_main_star, is_landable, {_bodies_tidal_col()}, has_signals, has_rings, ring_types,
                   atmosphere, volcanism, terraform_state,
                   mass, radius, surface_temp, surface_gravity,
                   estimated_mapping_value, estimated_scan_value, data
            FROM bodies
            WHERE system_id64 = ?
            ORDER BY distance_to_arrival
        """, (id64,)).fetchall()

    body_list = []
    for b in bodies:
        body_dict = dict(b)
        # Parse stored JSON data if available, then merge
        raw = body_dict.pop("data", None)
        if raw:
            try:
                extra = json.loads(raw)
                extra.update({k: v for k, v in body_dict.items() if v is not None})
                body_dict = extra
            except Exception:
                pass
        # ── Normalize DB column names → Spansh/frontend field names ──────────
        # terraform_state → terraforming_state  (Spansh API name)
        if "terraform_state" in body_dict and "terraforming_state" not in body_dict:
            body_dict["terraforming_state"] = body_dict.pop("terraform_state")
        elif "terraform_state" in body_dict:
            body_dict.pop("terraform_state")
        # surface_gravity → gravity  (Spansh API name)
        if "surface_gravity" in body_dict and "gravity" not in body_dict:
            body_dict["gravity"] = body_dict.pop("surface_gravity")
        elif "surface_gravity" in body_dict:
            body_dict.pop("surface_gravity")
        # surface_temp → surface_temperature  (frontend field name)
        if "surface_temp" in body_dict and "surface_temperature" not in body_dict:
            body_dict["surface_temperature"] = body_dict.pop("surface_temp")
        elif "surface_temp" in body_dict:
            body_dict.pop("surface_temp")
        # is_tidal_lock (int 0/1) → is_rotational_period_tidally_locked (bool)
        if "is_tidal_lock" in body_dict:
            if "is_rotational_period_tidally_locked" not in body_dict:
                body_dict["is_rotational_period_tidally_locked"] = bool(body_dict.pop("is_tidal_lock"))
            else:
                body_dict.pop("is_tidal_lock")
        # ring_types JSON → rings array of {type: "..."}
        rt = body_dict.pop("ring_types", None)
        if rt and "rings" not in body_dict:
            try:
                names = json.loads(rt) if isinstance(rt, str) else rt
                body_dict["rings"] = [{"type": t} for t in names if t]
            except Exception:
                body_dict["rings"] = []
        elif "rings" not in body_dict:
            body_dict["rings"] = []
        # has_signals int → signals array (volcanism proxy for geo/bio)
        if "signals" not in body_dict:
            if body_dict.get("has_signals"):
                volc = (body_dict.get("volcanism") or "").strip()
                if volc and volc not in ("", "No volcanism"):
                    body_dict["signals"] = [{"name": "Geological", "count": 1}]
                else:
                    body_dict["signals"] = [{"name": "Biological", "count": 1}]
            else:
                body_dict["signals"] = []
        body_list.append(body_dict)

    record = {
        "id64":        row["id64"],
        "id":          str(row["id64"]),
        "name":        row["name"],
        "coords":      {"x": row["x"], "y": row["y"], "z": row["z"]},
        "main_star":   row["main_star"],
        "needs_permit": bool(row["needs_permit"]),
        "population":  row["population"] or 0,
        "is_colonised": row["is_colonised"] or 0,
        "is_being_colonised": row["is_being_colonised"] or 0,
        "controlling_minor_faction": row["controlling_faction"],
        "government":  row["government"],
        "allegiance":  row["allegiance"],
        "primaryEconomy": row["economy"],
        "bodies":      body_list,
        "body_count":  len(body_list),
        "source":      "local_db",
    }
    return {"record": record}


# ── Autocomplete ──────────────────────────────────────────────────────────────
def local_db_autocomplete(q: str) -> list:
    """
    Fast prefix-search for system names.
    Returns list of {name, id64, coords} dicts (max 10).
    """
    if len(q) < 2:
        return []
    pattern = q + "%"
    with galaxy_conn() as conn:
        rows = conn.execute("""
            SELECT id64, name, x, y, z
            FROM systems
            WHERE name LIKE ?
            ORDER BY name
            LIMIT 10
        """, (pattern,)).fetchall()
    return [
        {
            "name": r["name"],
            "id64": r["id64"],
            "record": {"id64": r["id64"], "name": r["name"],
                       "x": r["x"], "y": r["y"], "z": r["z"]},
        }
        for r in rows
    ]


# ── Status ─────────────────────────────────────────────────────────────────────
def local_db_status() -> dict:
    """Return info about the local galaxy DB."""
    if not os.path.exists(GALAXY_DB):
        return {"available": False, "reason": "galaxy.db not found"}

    try:
        with galaxy_conn() as conn:
            sys_count = conn.execute("SELECT COUNT(*) FROM systems").fetchone()[0]
            col_count = conn.execute("SELECT COUNT(*) FROM colonisation").fetchone()[0]
            body_count = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='bodies'"
            ).fetchone()[0]
            if body_count:
                body_count = conn.execute("SELECT COUNT(*) FROM bodies").fetchone()[0]

            # Last EDDN update
            eddn_row = conn.execute(
                "SELECT value FROM import_meta WHERE key='eddn_last_seen'"
            ).fetchone()
            import_done = conn.execute(
                "SELECT value FROM import_meta WHERE key='systems_import_done'"
            ).fetchone()
            galaxy_done = conn.execute(
                "SELECT value FROM import_meta WHERE key='galaxy_import_done'"
            ).fetchone()
            eddn_msgs = conn.execute(
                "SELECT value FROM import_meta WHERE key='eddn_msg_count'"
            ).fetchone()
            delta_row = conn.execute(
                "SELECT value FROM import_meta WHERE key='delta_last_run'"
            ).fetchone()

        db_size_mb = os.path.getsize(GALAXY_DB) / 1_048_576

        # Refresh schema probe so status reflects any migrations applied since startup
        global _BODIES_COLS
        _BODIES_COLS = None
        cols = _probe_bodies_schema()
        has_tidal = "is_tidal_lock" in cols

        return {
            "available":            True,
            "systems_count":        sys_count,
            "colonisation_count":   col_count,
            "body_count":           body_count,
            "db_size_mb":           round(db_size_mb, 1),
            "systems_import_done":  import_done[0] if import_done else None,
            "galaxy_import_done":   galaxy_done[0] if galaxy_done else None,
            "eddn_last_seen":       eddn_row[0]    if eddn_row    else None,
            "eddn_msg_count":       int(eddn_msgs[0]) if eddn_msgs else 0,
            "delta_last_run":       delta_row[0]   if delta_row   else None,
            "max_search_radius_ly": int(MAX_SEARCH_RADIUS),
            "db_path":              GALAXY_DB,
            "has_tidal_lock_col":   has_tidal,      # False → run migrate_v3_28.sql
        }
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
