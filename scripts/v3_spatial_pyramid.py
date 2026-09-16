#!/usr/bin/env python3
'''Build, reconcile, and receipt the V3 spatial density pyramid (#2a).

This module:

- registers the versioned `spatial_pyramid_version` cell-size ladder into
  `v3_spatial.cell_level` (idempotent);
- resolves whether a given derived generation's aggregation should read the
  cheap `v3_derived.system_search` projection or fall back to the canonical
  `{gen}.systems` catalogue, per the source rule in
  `docs/development/v3-spatial-density-pyramid-design.md`;
- aggregates each registered level's occupied cells into
  `v3_spatial.cell_summary` (`build_level`/`build_all_levels`); and
- enforces the reconciliation truth gate (`reconcile`) and assembles the
  sanitized validation receipt (`build_receipt`).

Publication (governed lifecycle + rollback) and the API read path are later
tasks in this same effort, not implemented here.
'''
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Literal

SCHEMA_NAME = re.compile(r'v3_gen_[a-z][a-z0-9_]{0,30}\Z')

PYRAMID_VERSION = 'pyramid_v1'

# Mirrors scripts/v3_system_search.py's PRODUCT_CODE naming convention
# (lower_snake_case product name, matching v3_meta.derived_product's
# `product_code ~ '^[a-z][a-z0-9_]{0,62}$'` CHECK).
PRODUCT_CODE = 'spatial_pyramid'


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


def _canonical_schema(conn, derived_generation_id) -> str:
    '''Resolve the canonical relation schema for a derived generation, the
    same way `apps/api/src/edfinder_api/v3_schema.py` resolves the currently
    published one, but pinned to the specific derived generation rather than
    "whatever is current" -- the pyramid always aggregates a named, pinned
    generation, never a moving target.
    '''
    row = conn.execute(
        '''SELECT cg.relation_schema
             FROM v3_meta.derived_generation dg
             JOIN v3_meta.canonical_generation cg
               ON cg.generation_id = dg.canonical_generation_id
            WHERE dg.derived_generation_id = %s''',
        (derived_generation_id,),
    ).fetchone()
    if row is None:
        raise ValueError('unknown derived generation')
    schema = row[0]
    if not isinstance(schema, str) or not SCHEMA_NAME.fullmatch(schema):
        raise ValueError('unsafe canonical generation relation schema')
    return schema


def resolve_source(conn, derived_generation_id) -> Literal['system_search', 'canonical']:
    '''Pick the cheap `system_search` aggregation source when it is provably
    complete for this generation (its row count matches the canonical
    `{gen}.systems` count exactly), else fall back to the canonical catalogue.

    This is a cheap pre-check, not the truth gate: the pyramid build's
    reconciliation step (Sigma system_count == canonical count) is the hard,
    self-verifying enforcement regardless of which source is chosen here.
    '''
    from psycopg import sql

    schema = _canonical_schema(conn, derived_generation_id)

    search_count = conn.execute(
        '''SELECT count(*) FROM v3_derived.system_search
            WHERE derived_generation_id = %s''',
        (derived_generation_id,),
    ).fetchone()[0]

    canonical_count = conn.execute(
        sql.SQL('SELECT count(*) FROM {}.systems').format(sql.Identifier(schema)),
    ).fetchone()[0]

    if int(search_count) == int(canonical_count):
        return 'system_search'
    return 'canonical'


_CELL_SUMMARY_INSERT_FROM_SYSTEM_SEARCH = '''
INSERT INTO v3_spatial.cell_summary
  (derived_generation_id, spatial_pyramid_version, level, cell_key,
   origin_x_ly, origin_y_ly, origin_z_ly, system_count,
   centroid_x_ly, centroid_y_ly, centroid_z_ly,
   landable_count, station_count, biological_system_count,
   terraformable_system_count, representative_system_id64)
SELECT %(gen)s, %(ver)s, %(lvl)s,
       floor(x_ly/%(sz)s)::bigint || '.' || floor(y_ly/%(sz)s)::bigint
           || '.' || floor(z_ly/%(sz)s)::bigint,
       floor(x_ly/%(sz)s)*%(sz)s, floor(y_ly/%(sz)s)*%(sz)s, floor(z_ly/%(sz)s)*%(sz)s,
       count(*), avg(x_ly), avg(y_ly), avg(z_ly),
       coalesce(sum(landable_count),0), coalesce(sum(station_count),0),
       count(*) FILTER (WHERE has_biologicals),
       count(*) FILTER (WHERE has_terraformable),
       min(system_id64)
  FROM v3_derived.system_search
 WHERE derived_generation_id = %(gen)s
 GROUP BY 4,5,6,7
'''


def _build_level_canonical(conn, *, derived_generation_id, version, level, cell_size_ly) -> int:
    '''Canonical-catalogue aggregation fallback, used when `resolve_source`
    finds `v3_derived.system_search` incomplete for a generation.

    Not implemented in this task: Task 3's reconciliation gate and the
    `system_search` path above are what this effort exercises first. A real
    implementation needs a `{schema}.systems` (+ bodies/stations) join
    equivalent to `v3_system_search.py`'s `projection_query_sql`, scoped to
    the pinned canonical schema for `derived_generation_id` -- not invented
    here per the task brief.
    '''
    raise NotImplementedError('canonical-source cell aggregation is not implemented yet (TODO)')


def build_level(conn, *, derived_generation_id, version, level, cell_size_ly, source) -> int:
    '''Aggregate one pyramid level's occupied cells into `v3_spatial.cell_summary`
    with a single set-based INSERT...SELECT...GROUP BY, scoped to
    `derived_generation_id`. `cell_summary` is insert-only (immutable once
    written by migration 004's triggers): this never updates existing rows.

    Returns the number of cell rows inserted (one per occupied cell).
    '''
    if source == 'system_search':
        cur = conn.execute(
            _CELL_SUMMARY_INSERT_FROM_SYSTEM_SEARCH,
            {
                'gen': derived_generation_id,
                'ver': version,
                'lvl': level,
                'sz': cell_size_ly,
            },
        )
        return cur.rowcount
    if source == 'canonical':
        return _build_level_canonical(
            conn, derived_generation_id=derived_generation_id, version=version,
            level=level, cell_size_ly=cell_size_ly,
        )
    raise ValueError(f'unknown aggregation source {source!r}')


def build_all_levels(conn, *, derived_generation_id, version: str = PYRAMID_VERSION, source) -> dict[int, int]:
    '''Build every registered `CELL_LEVELS` level for `derived_generation_id`,
    returning a `level -> occupied cell count` map.
    '''
    counts: dict[int, int] = {}
    for lvl in CELL_LEVELS:
        counts[lvl.level] = build_level(
            conn, derived_generation_id=derived_generation_id, version=version,
            level=lvl.level, cell_size_ly=lvl.cell_size_ly, source=source,
        )
    return counts


class ReconciliationError(Exception):
    '''Raised by `reconcile` when a level's aggregated `Σ system_count` does not
    exactly match the canonical system count. This is the pyramid's truth gate:
    it must fail closed on any mismatch, including a level that is short only
    because its source (`system_search` or the canonical fallback) was itself
    incomplete when the level was built -- there is no partial-credit pass.
    '''


def reconcile(conn, *, derived_generation_id, version: str, canonical_count: int) -> dict:
    '''Verify every built level's `Σ system_count` in `v3_spatial.cell_summary`
    exactly equals `canonical_count`, per
    `docs/development/v3-spatial-density-pyramid-design.md` ("Reconciliation +
    validation receipt"). Every occupied cell at a level partitions the full set
    of systems present at build time, so a level's cell-count sum is exactly the
    number of distinct systems that level was built from; any deviation from
    `canonical_count` means the source was incomplete, the wrong generation was
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
            WHERE derived_generation_id=%s AND spatial_pyramid_version=%s
            GROUP BY level''',
        (derived_generation_id, version),
    ).fetchall()
    per_level_system_sum = {int(level): int(total) for level, total in rows}

    missing_levels = sorted(expected_levels - set(per_level_system_sum))
    if missing_levels:
        raise ReconciliationError(
            f'level(s) {missing_levels} registered for version {version!r} but '
            f'absent from cell_summary for derived_generation_id={derived_generation_id!r} '
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


def build_receipt(conn, *, derived_generation_id, version: str, source: str,
                   canonical_count: int, per_level: dict[int, int]) -> dict:
    '''Assemble the sanitized validation receipt the design doc calls for: source
    path, per-level cell + system counts, reconciliation result, pyramid version,
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

    The `derived_generation` row lookup runs before reconciliation and raises
    `ValueError` (mirroring `_canonical_schema`'s convention) if the generation
    id is unresolvable, rather than silently emitting a receipt with
    `canonical_generation_id`/`coverage_at` set to `None`. It is checked first so
    an unknown generation id is reported as exactly that, not masked behind
    `reconcile`'s (also fail-closed, since Task 3's review fix) "missing level"
    error for a generation that was never built at all.
    '''
    row = conn.execute(
        '''SELECT dg.canonical_generation_id, now()
             FROM v3_meta.derived_generation dg
            WHERE dg.derived_generation_id = %s''',
        (derived_generation_id,),
    ).fetchone()
    if row is None:
        raise ValueError('unknown derived generation')
    canonical_generation_id, coverage_at = row

    reconciliation = reconcile(
        conn, derived_generation_id=derived_generation_id, version=version,
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
        'derived_generation_id': str(derived_generation_id),
        'canonical_generation_id': str(canonical_generation_id) if canonical_generation_id else None,
        'spatial_pyramid_version': version,
        'source': source,
        'canonical_count': canonical_count,
        'per_level': per_level_report,
        'reconciliation': 'passed',
        'coverage_at': coverage_at,
    }


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


def _pyramid_product(conn, derived_generation_id):
    return conn.execute(
        '''SELECT product_version,lifecycle_state,manifest,manifest_sha256,
                  expected_rows,validation_receipt,validation_sha256
             FROM v3_meta.derived_product
            WHERE derived_generation_id=%s AND product_code=%s''',
        (derived_generation_id, PRODUCT_CODE),
    ).fetchone()


def _pyramid_manifest(derived_generation_id, version: str) -> dict:
    return {
        'product_code': PRODUCT_CODE,
        'product_version': version,
        'derived_generation_id': str(derived_generation_id),
    }


def mark_pyramid_ready(conn, *, derived_generation_id, version: str, receipt: dict) -> None:
    '''Ensure the spatial-pyramid `v3_meta.derived_product` row exists for
    `derived_generation_id` and transition it `BUILDING -> READY`, storing the
    validation `receipt`.

    Mirrors exactly how `scripts/v3_system_search.py` registers its product
    (`register_product`) and transitions it to READY (`validate_product`):
    same `v3_meta.derived_product` columns, same idempotent
    insert-if-absent/verify-if-present manifest check, same
    `UPDATE ... WHERE lifecycle_state='BUILDING'` compare-and-swap into READY.
    There is no PUBLISHED state and no per-pyramid pointer here -- publication
    is generation-level (`v3_meta.current_derived_generation`, swapped by
    `v3_meta.publish_derived_generation`), out of scope for this function.

    `receipt` must be an already-reconciled `build_receipt` result (i.e.
    `receipt['reconciliation'] == 'passed'`) with a positive `canonical_count`
    -- this function stores a receipt, it does not re-run `reconcile` itself,
    but it refuses to mark a product READY from a receipt that never passed
    the truth gate.

    Idempotent: calling this again with an identical `(version, receipt)`
    once the product is already READY is a no-op. Parameterized SQL only.
    '''
    if not isinstance(receipt, dict) or receipt.get('reconciliation') != 'passed':
        raise ValueError('mark_pyramid_ready requires a reconciled build_receipt (reconciliation == "passed")')
    canonical_count = receipt.get('canonical_count')
    if not isinstance(canonical_count, int) or isinstance(canonical_count, bool) or canonical_count <= 0:
        raise ValueError('receipt canonical_count must be a positive integer')

    manifest = _pyramid_manifest(derived_generation_id, version)
    manifest_sha = _digest(manifest)

    existing = _pyramid_product(conn, derived_generation_id)
    if existing is None:
        with conn.transaction():
            conn.execute(
                '''INSERT INTO v3_meta.derived_product(
                       derived_generation_id,product_code,product_version,
                       manifest,manifest_sha256,expected_rows)
                   VALUES (%s,%s,%s,%s::jsonb,%s,%s)''',
                (
                    derived_generation_id, PRODUCT_CODE, version,
                    _json(manifest), manifest_sha, canonical_count,
                ),
            )
        existing = _pyramid_product(conn, derived_generation_id)

    if existing is None:
        raise ValueError('spatial pyramid product registration failed')
    if (
        existing[0] != version
        or existing[2] != manifest
        or bytes(existing[3]) != manifest_sha
    ):
        raise ValueError('existing spatial pyramid product manifest differs from current version/input')

    if existing[1] == 'READY':
        return  # idempotent no-op: already registered and READY

    if existing[1] != 'BUILDING':
        raise ValueError(f'spatial pyramid product cannot become READY from state {existing[1]!r}')

    validation_receipt = {**receipt, 'status': 'VERIFIED'}
    validation_sha = _digest(validation_receipt)

    with conn.transaction():
        updated = conn.execute(
            '''UPDATE v3_meta.derived_product
                  SET lifecycle_state='READY',validation_receipt=%s::jsonb,
                      validation_sha256=%s,validated_at=now()
                WHERE derived_generation_id=%s AND product_code=%s
                  AND lifecycle_state='BUILDING' ''',
            (_json(validation_receipt), validation_sha, derived_generation_id, PRODUCT_CODE),
        ).rowcount
        if updated != 1:
            raise ValueError('spatial pyramid product READY transition failed')


def pyramid_for_current_generation(conn) -> tuple | None:
    '''Return `(derived_generation_id, spatial_pyramid_version)` for the
    spatial pyramid belonging to the current *published* derived generation,
    or `None` if there is no current generation or its spatial-pyramid
    product is not READY.

    Resolves "current published derived generation" the exact way
    `apps/api/src/routers/ratings_v4.py:_current` does: join
    `v3_meta.current_derived_generation` to `v3_meta.derived_generation` and
    require `lifecycle_state='PUBLISHED'` (the atomic active pointer plus its
    generation-level PUBLISHED state -- there is no separate per-pyramid
    pointer or PUBLISHED state to check). That is additionally joined here to
    this generation's `v3_meta.derived_product` row for `PRODUCT_CODE`,
    requiring `lifecycle_state='READY'`.
    '''
    row = conn.execute(
        '''SELECT c.derived_generation_id, p.product_version
             FROM v3_meta.current_derived_generation c
             JOIN v3_meta.derived_generation d USING (derived_generation_id)
             JOIN v3_meta.derived_product p
               ON p.derived_generation_id = c.derived_generation_id
              AND p.product_code = %s
            WHERE d.lifecycle_state = 'PUBLISHED'
              AND p.lifecycle_state = 'READY' ''',
        (PRODUCT_CODE,),
    ).fetchone()
    if row is None:
        return None
    return (row[0], row[1])
