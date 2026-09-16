#!/usr/bin/env python3
'''Register the V3 spatial density pyramid's cell-level ladder + choose a
generation's aggregation source.

This is the first, foundational piece of the V3 spatial density pyramid
(#2a): it does not build `v3_spatial.cell_summary` yet (that is a later task
in this same effort). It only:

- registers the versioned `spatial_pyramid_version` cell-size ladder into
  `v3_spatial.cell_level` (idempotent), and
- resolves whether a given derived generation's aggregation should read the
  cheap `v3_derived.system_search` projection or fall back to the canonical
  `{gen}.systems` catalogue, per the source rule in
  `docs/development/v3-spatial-density-pyramid-design.md`.

The reconciliation gate (a later task) is the ultimate enforcement of pyramid
correctness; this module only picks the cheap path when it is provably safe.
'''
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

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
