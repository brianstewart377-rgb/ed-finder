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
        body_filters {key: {min, max}}   body type counts (requires Phase 2 bodies table)
        require_bio  bool                require biological signals
        require_geo  bool                require geological signals
        require_terra bool               require terraformable bodies
        star_types   [str]               allowed main star types
        min_rating   int                 minimum colonisation rating (0-100)

    Sort: always distance ascending (same as Spansh default).
    Pagination: from + size.
    No 10k cap — returns ALL matching systems.
    """
    t0 = time.time()

    # Parse request
    filters        = body.get("filters", {})
    ref_coords     = body.get("reference_coords", {})
    size           = min(int(body.get("size", 50_000)), 100_000)  # No 10k cap!
    from_idx       = int(body.get("from", 0))

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

    # Body filters (active after Phase 2 import)
    body_filters = body.get("body_filters", {})   # {key: {min, max}}
    require_bio   = body.get("require_bio", False)
    require_geo   = body.get("require_geo", False)
    require_terra = body.get("require_terra", False)
    star_types    = body.get("star_types", [])     # e.g. ["K", "G", "F"]
    min_rating    = int(body.get("min_rating", 0))

    systems = _spatial_search(rx, ry, rz, min_dist, max_dist, require_empty,
                              body_filters, require_bio, require_geo,
                              require_terra, star_types, min_rating)

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
      2. Fetch systems from those cells (fast index lookup)
      3. Compute exact Euclidean distance and filter
      4. JOIN colonisation table to exclude inhabited systems when require_empty=True
      5. Optionally JOIN bodies table to apply body filters (Phase 2)
      6. Return sorted by distance asc, enriched with colonisation + body data
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

    # Check if bodies table exists (Phase 2)
    with galaxy_conn() as conn:
        has_bodies = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bodies'"
        ).fetchone() is not None

    use_body_filters = has_bodies and (body_filters or require_bio or require_geo or require_terra)
    # Always fetch bodies when Phase 2 data exists — rateSystem() and body pill display
    # both need populated bodies[] even on normal (no-filter) searches.
    always_fetch_bodies = has_bodies

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

        # Inhabited heuristic
        inhabited = bool(is_col or being_col or ctrl or pop > 0)
        if require_empty and inhabited:
            continue

        # Star type filter (uses main_star field e.g. "K", "G", "F (White Dwarf)")
        if star_types:
            main = (row["main_star"] or "").split()[0]  # first token = spectral class
            if main not in star_types:
                continue

        dist = math.sqrt(dist_sq)

        # Body data — fetch whenever Phase 2 exists so rateSystem() gets real data
        body_list = []
        if always_fetch_bodies:
            with galaxy_conn() as bconn:
                brows = bconn.execute("""
                    SELECT type, subtype, distance_to_arrival,
                           is_landable, has_signals, has_rings, ring_types,
                           atmosphere, volcanism, terraform_state,
                           surface_gravity, estimated_mapping_value, estimated_scan_value
                    FROM bodies WHERE system_id64 = ?
                    ORDER BY distance_to_arrival
                """, (row["id64"],)).fetchall()
            # Normalize column names to match Spansh API field names expected by frontend
            for b in brows:
                bd = dict(b)
                # terraform_state → terraforming_state (Spansh field name)
                bd["terraforming_state"] = bd.pop("terraform_state", None)
                # surface_gravity → gravity (Spansh field name)
                bd["gravity"] = bd.pop("surface_gravity", None)
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
                # The DB stores a single 0/1 flag; volcanism is used as geo proxy.
                # Build a minimal signals array so frontend hasSignal() works:
                #   - has_signals=1 + volcanism present → Geological
                #   - has_signals=1 + no volcanism → Biological
                # (Best approximation without a full signals table)
                if bd.get("has_signals"):
                    volc = (bd.get("volcanism") or "").strip()
                    if volc and volc not in ("", "No volcanism"):
                        bd["signals"] = [{"name": "Geological", "count": 1}]
                    else:
                        bd["signals"] = [{"name": "Biological", "count": 1}]
                else:
                    bd["signals"] = []
                body_list.append(bd)

            # Apply body-type slider filters when requested
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
            # NOTE: has_signals=1 covers ANY signal type; volcanism is the geo proxy.
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

    # Sort by distance
    results.sort(key=lambda s: s["distance"])
    return results


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
            # walkable = landable with no atmosphere (can use SRV)
            atm = (b.get("atmosphere") or "").strip()
            if not atm or atm.lower() in ("", "no atmosphere", "none"):
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
