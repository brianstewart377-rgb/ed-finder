#!/usr/bin/env python3
'''Build, reconcile, and receipt the V3 spatial density pyramid (#2a/#2b).

This module:

- registers the versioned `spatial_pyramid_version` cell-size ladder into
  `v3_spatial.cell_level` (idempotent);
- resolves the canonical relation schema for a `v3_spatial.spatial_generation`
  (`canonical_schema_for_spatial`) and counts its systems
  (`canonical_system_count`);
- aggregates each registered level's occupied cells, from the canonical
  `{gen}.systems` catalogue only, into `v3_spatial.cell_summary`
  (`build_level`/`build_all_levels`) -- pure density, no derived/rating
  fields; and
- enforces the reconciliation truth gate (`reconcile`) and assembles the
  sanitized validation receipt (`build_receipt`).

The spatial pyramid is decoupled from the ratings `derived_generation`
lifecycle: it is keyed to its own `v3_spatial.spatial_generation`, itself
keyed to a canonical generation (`sql/v3/migrations/012_v3_spatial_pyramid_decouple.sql`).
Registering the pyramid as a product, transitioning it BUILDING -> READY, and
publishing it via `v3_spatial.publish_spatial_pyramid` are separate concerns,
out of scope here (Task 4).
'''
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re

SCHEMA_NAME = re.compile(r'v3_gen_[a-z][a-z0-9_]{0,30}\Z')

PYRAMID_VERSION = 'pyramid_v1'


@dataclass(frozen=True)
class CellLevel:
    level: int
    cell_size_ly: float
    intended_scale: str
    target_count_min: int | None = None
    target_count_max: int | None = None


# Coarse (whole galaxy) -> fine (local). Sizes are a deterministic starting
# ladder recorded in docs/development/v3-spatial-density-pyramid-design.md;
# Task 7 benchmarks the exact sizes/level count against real data before this
# ladder is treated as final. Level choice at query time comes from semantic
# scale + visible volume + target budget, not this module.
CELL_LEVELS = [
    CellLevel(0, 2560.0, 'wide'),
    CellLevel(1, 1280.0, 'wide'),
    CellLevel(2, 640.0, 'regional'),
    CellLevel(3, 320.0, 'regional'),
    CellLevel(4, 160.0, 'local'),
    CellLevel(5, 80.0, 'local'),
    CellLevel(6, 40.0, 'local'),
]


def register_cell_levels(conn, version: str = PYRAMID_VERSION) -> None:
    '''Idempotently register `CELL_LEVELS` under `version` in
    `v3_spatial.cell_level`. Safe to call repeatedly (e.g. on every builder
    run): existing rows for `(version, level)` are left untouched.
    '''
    for lvl in CELL_LEVELS:
        conn.execute(
            '''INSERT INTO v3_spatial.cell_level
                 (spatial_pyramid_version, level, cell_size_ly, intended_scale,
                  target_count_min, target_count_max)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT (spatial_pyramid_version, level) DO NOTHING''',
            (version, lvl.level, lvl.cell_size_ly, lvl.intended_scale,
             lvl.target_count_min, lvl.target_count_max),
        )


def canonical_schema_for_spatial(conn, spatial_generation_id) -> str:
    '''Resolve the canonical relation schema for a spatial generation via its
    canonical_generation_id. Validated against SCHEMA_NAME to keep the schema
    safe to interpolate as an identifier.'''
    row = conn.execute(
        '''SELECT cg.relation_schema
             FROM v3_spatial.spatial_generation sg
             JOIN v3_meta.canonical_generation cg
               ON cg.generation_id = sg.canonical_generation_id
            WHERE sg.spatial_generation_id = %s''',
        (spatial_generation_id,),
    ).fetchone()
    if row is None:
        raise ValueError('unknown spatial generation')
    schema = row[0]
    if not isinstance(schema, str) or not SCHEMA_NAME.fullmatch(schema):
        raise ValueError('unsafe canonical generation relation schema')
    return schema


def canonical_system_count(conn, spatial_generation_id) -> int:
    from psycopg import sql
    schema = canonical_schema_for_spatial(conn, spatial_generation_id)
    return int(conn.execute(
        sql.SQL('SELECT count(*) FROM {}.systems').format(sql.Identifier(schema)),
    ).fetchone()[0])


def build_level(conn, *, spatial_generation_id, version, level, cell_size_ly) -> int:
    '''Aggregate one level's occupied cells from the canonical {gen}.systems
    catalogue into v3_spatial.cell_summary (insert-only). Pure density:
    system_count = COUNT(*); representative = system nearest the cell
    data-centroid (tiebreak min(id64)). Returns rows inserted.'''
    from psycopg import sql
    schema = canonical_schema_for_spatial(conn, spatial_generation_id)
    stmt = sql.SQL('''
        INSERT INTO v3_spatial.cell_summary
          (spatial_generation_id, spatial_pyramid_version, level, cell_key,
           origin_x_ly, origin_y_ly, origin_z_ly, system_count,
           centroid_x_ly, centroid_y_ly, centroid_z_ly, representative_system_id64)
        WITH pts AS (
            SELECT id64, x_ly, y_ly, z_ly,
                   floor(x_ly/%(sz)s)::bigint AS ix,
                   floor(y_ly/%(sz)s)::bigint AS iy,
                   floor(z_ly/%(sz)s)::bigint AS iz
              FROM {schema}.systems
        ), agg AS (
            SELECT ix, iy, iz, count(*) AS n,
                   avg(x_ly) AS cx, avg(y_ly) AS cy, avg(z_ly) AS cz
              FROM pts GROUP BY ix, iy, iz
        ), rep AS (
            SELECT DISTINCT ON (p.ix, p.iy, p.iz)
                   p.ix, p.iy, p.iz, p.id64
              FROM pts p JOIN agg a USING (ix, iy, iz)
             ORDER BY p.ix, p.iy, p.iz,
                   ((p.x_ly-a.cx)^2 + (p.y_ly-a.cy)^2 + (p.z_ly-a.cz)^2),
                   p.id64
        )
        SELECT %(gen)s, %(ver)s, %(lvl)s,
               a.ix || '.' || a.iy || '.' || a.iz,
               a.ix*%(sz)s, a.iy*%(sz)s, a.iz*%(sz)s,
               a.n, a.cx, a.cy, a.cz, r.id64
          FROM agg a JOIN rep r USING (ix, iy, iz)
    ''').format(schema=sql.Identifier(schema))
    cur = conn.execute(stmt, {
        'gen': spatial_generation_id, 'ver': version, 'lvl': level, 'sz': cell_size_ly,
    })
    return cur.rowcount


def build_all_levels(conn, *, spatial_generation_id, version: str = PYRAMID_VERSION) -> dict[int, int]:
    '''Build every registered `CELL_LEVELS` level for `spatial_generation_id`,
    returning a `level -> occupied cell count` map.
    '''
    counts: dict[int, int] = {}
    for lvl in CELL_LEVELS:
        counts[lvl.level] = build_level(
            conn, spatial_generation_id=spatial_generation_id, version=version,
            level=lvl.level, cell_size_ly=lvl.cell_size_ly,
        )
    return counts


class ReconciliationError(Exception):
    '''Raised by `reconcile` when a level's aggregated `Σ system_count` does not
    exactly match the canonical system count. This is the pyramid's truth gate:
    it must fail closed on any mismatch -- there is no partial-credit pass.
    '''


def reconcile(conn, *, spatial_generation_id, version: str, canonical_count: int) -> dict:
    '''Verify every built level's `Σ system_count` in `v3_spatial.cell_summary`
    exactly equals `canonical_count`, per
    `docs/development/v3-spatial-density-pyramid-design.md` ("Reconciliation +
    validation receipt"). Every occupied cell at a level partitions the full set
    of systems present at build time, so a level's cell-count sum is exactly the
    number of distinct systems that level was built from; any deviation from
    `canonical_count` means the build was incomplete, the wrong generation was
    aggregated, or `canonical_count` itself is stale -- all fail-closed cases.

    Raises `ReconciliationError` naming the offending level, the expected count,
    and the actual sum on the first mismatch found. Returns
    `{'per_level_system_sum': {level: sum, ...}, 'canonical_count': canonical_count}`
    on success.

    This is the truth gate, so it must not be satisfiable by verifying nothing:
    before checking any sums, it fetches the set of levels *expected* to exist
    for `version` from `v3_spatial.cell_level` and raises `ReconciliationError`
    if that expected set is empty (nothing registered for this version -- there
    is nothing to reconcile against) or if any expected level is missing from
    `per_level_system_sum` (e.g. wrong generation/version was aggregated, or a
    build wrote zero rows) rather than silently treating an absent level as
    "nothing to sum".
    '''
    expected_levels = {
        int(level)
        for (level,) in conn.execute(
            '''SELECT level FROM v3_spatial.cell_level
                WHERE spatial_pyramid_version=%s''',
            (version,),
        ).fetchall()
    }
    if not expected_levels:
        raise ReconciliationError(
            f'no levels registered for version {version!r} -- cannot reconcile'
        )

    rows = conn.execute(
        '''SELECT level, sum(system_count)
             FROM v3_spatial.cell_summary
            WHERE spatial_generation_id=%s AND spatial_pyramid_version=%s
            GROUP BY level''',
        (spatial_generation_id, version),
    ).fetchall()
    per_level_system_sum = {int(level): int(total) for level, total in rows}

    missing_levels = sorted(expected_levels - set(per_level_system_sum))
    if missing_levels:
        raise ReconciliationError(
            f'level(s) {missing_levels} registered for version {version!r} but '
            f'absent from cell_summary for spatial_generation_id={spatial_generation_id!r} '
            '-- wrong generation/version, or a build that wrote nothing'
        )

    for level in sorted(per_level_system_sum):
        actual = per_level_system_sum[level]
        if actual != canonical_count:
            raise ReconciliationError(
                f'level {level}: expected system_count sum {canonical_count}, got {actual}'
            )
    return {
        'per_level_system_sum': per_level_system_sum,
        'canonical_count': canonical_count,
    }


def build_receipt(conn, *, spatial_generation_id, version: str,
                   canonical_count: int, per_level: dict[int, int]) -> dict:
    '''Assemble the sanitized validation receipt the design doc calls for:
    per-level cell + system counts, reconciliation result, pyramid version,
    generation ids, and a DB-sourced coverage timestamp. No secrets are read or
    included -- every value here is a count, id, version string, or timestamp.

    `per_level` is the `level -> occupied cell count` map `build_all_levels`
    returns. Reconciliation is re-run here (against `canonical_count`) rather
    than trusted from a prior call, so a receipt can never be produced for a
    build that does not actually reconcile: this raises `ReconciliationError`
    (propagated from `reconcile`) instead of emitting a receipt claiming success.
    Coverage is read via `SELECT now()` rather than `datetime.now()` so the
    receipt reflects DB time and this module has no wall-clock side effect at
    import time.

    The `spatial_generation` row lookup runs before reconciliation and raises
    `ValueError` (mirroring `canonical_schema_for_spatial`'s convention) if the
    generation id is unresolvable, rather than silently emitting a receipt with
    `canonical_generation_id`/`coverage_at` set to `None`. It is checked first
    so an unknown generation id is reported as exactly that, not masked behind
    `reconcile`'s (also fail-closed) "missing level" error for a generation
    that was never built at all.

    There is only one aggregation source now (the canonical catalogue), so
    `source` is always `'canonical-catalogue'` -- unlike the derived-keyed
    predecessor of this module, there is no `system_search`/`canonical`
    resolver choice to record.
    '''
    row = conn.execute(
        '''SELECT sg.canonical_generation_id, now()
             FROM v3_spatial.spatial_generation sg
            WHERE sg.spatial_generation_id = %s''',
        (spatial_generation_id,),
    ).fetchone()
    if row is None:
        raise ValueError('unknown spatial generation')
    canonical_generation_id, coverage_at = row

    reconciliation = reconcile(
        conn, spatial_generation_id=spatial_generation_id, version=version,
        canonical_count=canonical_count,
    )

    system_sums = reconciliation['per_level_system_sum']
    per_level_report = {
        level: {
            'cell_count': per_level.get(level),
            'system_count_sum': system_sums.get(level),
        }
        for level in sorted(set(per_level) | set(system_sums))
    }

    return {
        'spatial_generation_id': str(spatial_generation_id),
        'canonical_generation_id': str(canonical_generation_id) if canonical_generation_id else None,
        'spatial_pyramid_version': version,
        'source': 'canonical-catalogue',
        'canonical_count': canonical_count,
        'per_level': per_level_report,
        'reconciliation': 'passed',
        'coverage_at': coverage_at,
    }


def mark_pyramid_ready(conn, *, spatial_generation_id, version: str, receipt: dict) -> None:
    '''Transition the spatial_generation BUILDING/VALIDATING -> READY, storing
    the VERIFIED validation receipt + its sha. Requires an already-reconciled
    build_receipt (receipt['reconciliation'] == 'passed') with a positive
    canonical_count. Idempotent: a no-op when the row is already READY with a
    matching validation receipt. Parameterised SQL only.'''
    if not isinstance(receipt, dict) or receipt.get('reconciliation') != 'passed':
        raise ValueError('mark_pyramid_ready requires a reconciled build_receipt (reconciliation == "passed")')
    canonical_count = receipt.get('canonical_count')
    if not isinstance(canonical_count, int) or isinstance(canonical_count, bool) or canonical_count <= 0:
        raise ValueError('receipt canonical_count must be a positive integer')

    row = conn.execute(
        '''SELECT lifecycle_state, pyramid_version
             FROM v3_spatial.spatial_generation WHERE spatial_generation_id=%s''',
        (spatial_generation_id,),
    ).fetchone()
    if row is None:
        raise ValueError('unknown spatial generation')
    state, existing_version = row
    if existing_version != version:
        raise ValueError('spatial generation pyramid_version differs from build version')
    if state == 'READY':
        return  # idempotent no-op
    if state not in ('BUILDING', 'VALIDATING'):
        raise ValueError(f'spatial generation cannot become READY from state {state!r}')

    validation_receipt = {**receipt, 'status': 'VERIFIED'}
    validation_sha = _digest(validation_receipt)
    with conn.transaction():
        updated = conn.execute(
            '''UPDATE v3_spatial.spatial_generation
                  SET lifecycle_state='READY', validation_receipt=%s::jsonb,
                      validation_sha256=%s, validated_at=now()
                WHERE spatial_generation_id=%s
                  AND lifecycle_state IN ('BUILDING','VALIDATING')''',
            (_json(validation_receipt), validation_sha, spatial_generation_id),
        ).rowcount
        if updated != 1:
            raise ValueError('spatial generation READY transition failed')


def spatial_pyramid_for_current(conn) -> tuple | None:
    '''Return (spatial_generation_id, pyramid_version, canonical_generation_id,
    expected_systems, validated_at) for the currently published spatial
    generation, or None. Mirrors the API read exactly.'''
    row = conn.execute(
        '''SELECT c.spatial_generation_id, sg.pyramid_version,
                  sg.canonical_generation_id, sg.expected_systems, sg.validated_at
             FROM v3_spatial.current_spatial_generation c
             JOIN v3_spatial.spatial_generation sg USING (spatial_generation_id)
            WHERE sg.lifecycle_state='PUBLISHED' ''',
    ).fetchone()
    if row is None:
        return None
    return tuple(row)


def _json(value) -> str:
    '''Deterministic JSON, mirroring `scripts/v3_system_search.py`'s `_json`:
    bytes-like values become hex, datetimes become UTC ISO-8601, and anything
    else not natively JSON-serializable (e.g. a `uuid.UUID`) falls back to
    `str()`. Keys are sorted and separators are compact so the same logical
    value always produces the same digest.
    '''
    def convert(item):
        if isinstance(item, (bytes, bytearray, memoryview)):
            return bytes(item).hex()
        if isinstance(item, datetime):
            return item.astimezone(timezone.utc).isoformat()
        return str(item)

    return json.dumps(
        value, default=convert, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False,
    )


def _digest(value) -> bytes:
    return hashlib.sha256(_json(value).encode()).digest()
