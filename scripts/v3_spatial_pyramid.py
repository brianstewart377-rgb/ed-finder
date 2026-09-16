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
