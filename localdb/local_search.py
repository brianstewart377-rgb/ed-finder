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
def _open_galaxy_db() -> sqlite3.Connection:
    conn = sqlite3.connect(GALAXY_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-65536")    # 64 MB per connection
    conn.execute("PRAGMA mmap_size=536870912")  # 512 MB mmap
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
        (all other filters are client-side, same as Spansh path)

    Sort: always distance ascending (same as Spansh default).
    Pagination: from + size.
    """
    t0 = time.time()

    # Parse request
    filters        = body.get("filters", {})
    ref_coords     = body.get("reference_coords", {})
    size           = min(int(body.get("size", 500)), 10_000)
    from_idx       = int(body.get("from", 0))
    sort_dirs      = body.get("sort", [{"distance": {"direction": "asc"}}])

    rx = float(ref_coords.get("x", 0))
    ry = float(ref_coords.get("y", 0))
    rz = float(ref_coords.get("z", 0))

    # Distance filter
    dist_filter = filters.get("distance", {})
    min_dist    = float(dist_filter.get("min", 0))
    max_dist    = float(dist_filter.get("max", 500))

    # Population filter — key improvement over Spansh
    pop_filter = filters.get("population", {})
    pop_val    = pop_filter.get("value")
    pop_cmp    = pop_filter.get("comparison", "equal")
    require_empty = (pop_val == 0 and pop_cmp == "equal")

    systems = _spatial_search(rx, ry, rz, min_dist, max_dist, require_empty)

    # Apply pagination
    total    = len(systems)
    page     = systems[from_idx: from_idx + size]
    elapsed  = round((time.time() - t0) * 1000)

    log.debug("local_db_search: %d total, returning %d (from=%d) in %dms",
              total, len(page), from_idx, elapsed)

    return {
        "results": page,
        "count":   len(page),
        "total":   total,
        "source":  "local_db",
        "query_ms": elapsed,
    }


def _spatial_search(
    rx: float, ry: float, rz: float,
    min_dist: float, max_dist: float,
    require_empty: bool,
) -> List[dict]:
    """
    Use spatial grid cells to find candidate systems, then filter by exact distance.

    Strategy:
      1. Calculate which grid cells fall within [min_dist-cell, max_dist+cell]
      2. Fetch systems from those cells (fast index lookup)
      3. Compute exact Euclidean distance and filter
      4. JOIN colonisation table to exclude inhabited systems when require_empty=True
      5. Return sorted by distance asc, enriched with colonisation data
    """
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

        if has_grid:
            # Fast path: use spatial grid
            rows = conn.execute("""
                SELECT s.id64, s.name, s.x, s.y, s.z, s.main_star, s.needs_permit,
                       c.population, c.is_colonised, c.is_being_colonised,
                       c.controlling_faction, c.state, c.government, c.allegiance, c.economy
                FROM spatial_grid sg
                JOIN systems s ON s.id64 = sg.id64
                LEFT JOIN colonisation c ON c.id64 = s.id64
                WHERE sg.cx BETWEEN ? AND ?
                  AND sg.cy BETWEEN ? AND ?
                  AND sg.cz BETWEEN ? AND ?
            """, (cx_min, cx_max, cy_min, cy_max, cz_min, cz_max)).fetchall()
        else:
            # Fallback: bounding-box scan (slower on large DB)
            rows = conn.execute("""
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
                  rz - max_dist - cell, rz + max_dist + cell)).fetchall()

    results = []
    for row in rows:
        dx = row["x"] - rx
        dy = row["y"] - ry
        dz = row["z"] - rz
        dist_sq = dx*dx + dy*dy + dz*dz

        if dist_sq < min_dist_sq or dist_sq > max_dist_sq:
            continue

        pop     = row["population"] or 0
        is_col  = row["is_colonised"] or 0
        being_col = row["is_being_colonised"] or 0
        ctrl    = row["controlling_faction"]

        # Inhabited heuristic: same as client-side passesBodyFilters
        inhabited = bool(is_col or being_col or ctrl or pop > 0)
        if require_empty and inhabited:
            continue

        dist = math.sqrt(dist_sq)

        results.append({
            "id64":     row["id64"],
            "id":       str(row["id64"]),
            "name":     row["name"],
            "coords":   {"x": row["x"], "y": row["y"], "z": row["z"]},
            "distance": round(dist, 2),
            "main_star": row["main_star"],
            "needs_permit": bool(row["needs_permit"]),
            # Colonisation data — always fresh from EDDN
            "population":           pop,
            "is_colonised":         is_col,
            "is_being_colonised":   being_col,
            "controlling_minor_faction": ctrl,
            "minor_faction_presences":  [],   # not stored at row level; fetched on demand
            "government":  row["government"],
            "allegiance":  row["allegiance"],
            "primaryEconomy": row["economy"],
            # Source tag so frontend can show "Local DB" badge
            "source": "local_db",
        })

    # Sort by distance
    results.sort(key=lambda s: s["distance"])
    return results


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

        bodies = conn.execute("""
            SELECT id64, name, type, subtype, distance_to_arrival,
                   is_main_star, is_landable, has_signals, has_rings, ring_types,
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
        if body_dict.get("ring_types"):
            try:
                body_dict["rings"] = [{"type": t} for t in json.loads(body_dict["ring_types"])]
            except Exception:
                pass
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

        db_size_mb = os.path.getsize(GALAXY_DB) / 1_048_576

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
            "db_path":              GALAXY_DB,
        }
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
