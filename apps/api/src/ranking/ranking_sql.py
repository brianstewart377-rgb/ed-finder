"""V3 Finder ranking-profile SQL builder (F2c, Task 2).

Pure, DB-free parameterized-SQL assembly for the ranking profile defined in
`edfinder_api.ranking.profile`. This module holds **SQL construction only**:
no database connection, no execution, and no literal values ever land in the
returned SQL text — every value is bound through an asyncpg `$n` placeholder
and returned alongside the SQL in a positional `params` list.

## Relations read

- `v3_app.system_search` (`s`) — the F1 Finder projection: exact coordinates,
  body/feature counts (`sql/v3/migrations/004_v3_search_spatial_clusters.sql`,
  `010_v3_system_search_body_type_counts.sql`), and the `confidence` /
  `completeness` facts the uncertainty modifier reads.
- `v3_app.system_archetype_summary` (`sum`) — the F2b no-pick primary score
  (`best_colony_potential`) plus `archetype_confidence`
  (`sql/v3/migrations/011_v3_system_archetype.sql`).
- `v3_app.system_archetype` (`a`) — only joined when `picked_archetype` is
  set, restricted to that one `archetype_key` in the join condition (not a
  WHERE filter, so the LEFT JOIN still yields a row — with a NULL score —
  for a system that was never scored for that archetype).

All three are already generation-pinned views (`v3_app.*` joins
`v3_meta.current_derived_generation`), so this module never adds its own
generation predicate — the caller resolves and echoes the pinned generation
separately (the `ratings_v4.py` `_current()` pattern), matching the F2c/F3
design.

## Hard-filter key convention

The canonical key set is `edfinder_api.ranking.profile.HARD_FILTER_KEYS`
(fixed by Task 1). This module is the single place that maps each key to its
real `v3_app.system_search` (or cross-relation) predicate:

| key                        | column / expression                              |
|-----------------------------|--------------------------------------------------|
| `elw_count_min`             | `s.elw_count >= $n`                              |
| `ww_count_min`               | `s.ww_count >= $n`                                |
| `terraformable_count_min`    | `s.terraformable_count >= $n`                     |
| `landable_count_min`         | `s.landable_count >= $n`                          |
| `has_rings`                  | `s.has_rings = $n` (explicit true/false)          |
| `min_development_score`      | `<primary_score_expr> >= $n` (see below)          |
| `max_distance_ly`            | `<distance_expr> <= $n` (needs `reference_coords`)|
| `galaxy_region`              | `s.galaxy_region_id = $n`                         |

`min_development_score` has no dedicated `system_search` column — V2's
`local_search.py` filtered the same *computed* colony/development score it
ranked by (`ctx.finder_score_expr`), not a stored column. This module mirrors
that: the filter reuses the same `primary_score_expr` the ORDER BY uses
(`a.archetype_score` when `picked_archetype`, else
`sum.best_colony_potential`), so "minimum development score" always means
"minimum on whichever score this query is actually ranking by."

`max_distance_ly` needs a Euclidean reference point. Without
`reference_coords` there is nothing to measure distance from, so the filter
is **safely ignored** rather than raising — consistent with "ignore unknown
keys safely" for a key that is known but inapplicable to this call. Any
`hard_filters` key outside `HARD_FILTER_KEYS` (typos, future/removed keys) is
ignored the same way.

## Economy-picked ranking (documented gap)

`system_search` / `system_archetype*` carry no per-economy potential column
today (no `economy_potential`/`potential_score` projection exists yet, and
`PROFILE_SPEC["primary_score_rule"]["economy"]` names an aspirational
`potential_score` field that has no backing relation). Rather than invent a
column, `picked_economy` currently **falls back to the same no-pick primary
score** (`sum.best_colony_potential`). This is a deliberate placeholder:

    TODO(F2c/F3 follow-up): once a per-economy potential projection exists
    (tracked as a future Finder derived-data task), branch picked_economy
    onto its real column instead of the best_colony_potential fallback.

## Uncertainty modifier

`PROFILE_SPEC["uncertainty"]["factor_expr"]` is `confidence * completeness`.
`system_archetype` carries a per-archetype `confidence` but no
`completeness` counterpart; `system_search` is the only relation with both
facts. So the modifier is built as:

- archetype-picked: `a.confidence * s.completeness` — the archetype's own
  judgement confidence, scaled by the system's general data completeness.
  No `COALESCE` fallback is needed: when the LEFT JOIN finds no row for the
  picked archetype, `a.archetype_score` (the primary score) is already
  NULL, so the `primary_score * uncertainty_factor` ORDER BY term is NULL
  either way and `NULLS LAST` places it after every scored system.
- no-pick / economy-picked: `sum.archetype_confidence * s.completeness`.

See docs/superpowers/plans/2026-09-27-v3-finder-f2c-f3-ranking.md (Task 2)
and docs/superpowers/specs/2026-09-27-v3-finder-f2c-f3-ranking-design.md.
"""

from __future__ import annotations

from typing import Any

from .profile import HARD_FILTER_KEYS

# Count-minimum hard filters that map 1:1 onto a `v3_app.system_search`
# integer column via `column >= $n`.
_COUNT_MIN_FILTER_COLUMNS: dict[str, str] = {
    "elw_count_min": "elw_count",
    "ww_count_min": "ww_count",
    "terraformable_count_min": "terraformable_count",
    "landable_count_min": "landable_count",
}


class _ParamBuilder:
    """Accumulates positional asyncpg params and mints `$n` placeholders."""

    def __init__(self) -> None:
        self.params: list[Any] = []

    def add(self, value: Any) -> str:
        self.params.append(value)
        return f"${len(self.params)}"


def _distance_expr(builder: _ParamBuilder, reference_coords: tuple[float, float, float]) -> str:
    rx, ry, rz = reference_coords
    x_param = builder.add(float(rx))
    y_param = builder.add(float(ry))
    z_param = builder.add(float(rz))
    return (
        "sqrt("
        f"(s.x_ly - {x_param}) ^ 2 + "
        f"(s.y_ly - {y_param}) ^ 2 + "
        f"(s.z_ly - {z_param}) ^ 2"
        ")"
    )


def build_ranked_query(
    spec: dict[str, Any],
    *,
    picked_archetype: str | None,
    picked_economy: str | None,
    hard_filters: dict[str, Any],
    reference_coords: tuple[float, float, float] | None,
    limit: int,
    offset: int,
) -> tuple[str, list[Any]]:
    """Build a parameterized, generation-agnostic ranked SELECT.

    Returns `(sql, params)` where `sql` uses only `$1..$n` placeholders (no
    literal values) and `params` is the matching positional argument list
    for asyncpg. Pure — never opens a database connection.

    `spec` is accepted (rather than reading the module-level `PROFILE_SPEC`
    directly) so callers can pass a resolved `RANKING_VERSIONS[version]` for
    a future non-default profile without this function changing shape; the
    current implementation only depends on the fixed `HARD_FILTER_KEYS`
    contract and `uncertainty`/`tie_break` field names within `spec`.
    """

    builder = _ParamBuilder()

    joins = ["LEFT JOIN v3_app.system_archetype_summary sum ON sum.system_id64 = s.system_id64"]

    if picked_archetype:
        archetype_param = builder.add(picked_archetype)
        joins.append(
            "LEFT JOIN v3_app.system_archetype a "
            f"ON a.system_id64 = s.system_id64 AND a.archetype_key = {archetype_param}"
        )
        primary_score_expr = "a.archetype_score"
        # No COALESCE fallback needed: when the LEFT JOIN finds no matching
        # archetype row, `a.archetype_score` is already NULL, so the
        # `primary_score_expr * uncertainty_expr` ORDER BY term is NULL
        # either way and `NULLS LAST` sorts it after every scored system.
        uncertainty_expr = "a.confidence * s.completeness"
    else:
        # No pick and economy-pick both fall back to best_colony_potential
        # today — see the module docstring's "Economy-picked ranking" TODO.
        primary_score_expr = "sum.best_colony_potential"
        uncertainty_expr = "sum.archetype_confidence * s.completeness"

    where_clauses: list[str] = []

    for key, value in hard_filters.items():
        if key not in HARD_FILTER_KEYS:
            # Unknown/typo'd/future key: ignore safely rather than erroring.
            continue

        if key in _COUNT_MIN_FILTER_COLUMNS:
            column = _COUNT_MIN_FILTER_COLUMNS[key]
            param = builder.add(int(value))
            where_clauses.append(f"s.{column} >= {param}")
        elif key == "has_rings":
            param = builder.add(bool(value))
            where_clauses.append(f"s.has_rings = {param}")
        elif key == "min_development_score":
            param = builder.add(int(value))
            where_clauses.append(f"{primary_score_expr} >= {param}")
        elif key == "galaxy_region":
            param = builder.add(int(value))
            where_clauses.append(f"s.galaxy_region_id = {param}")
        elif key == "max_distance_ly":
            if reference_coords is None:
                # Known key, but no reference point to measure distance
                # from in this call: safely ignored (see module docstring).
                continue
            distance_expr = _distance_expr(builder, reference_coords)
            param = builder.add(float(value))
            where_clauses.append(f"{distance_expr} <= {param}")
        # Every HARD_FILTER_KEYS member is handled above; nothing falls
        # through silently for a *known* key.

    order_terms = [f"({primary_score_expr}) * ({uncertainty_expr}) DESC NULLS LAST"]
    if reference_coords is not None:
        tie_break_distance_expr = _distance_expr(builder, reference_coords)
        order_terms.append(f"{tie_break_distance_expr} ASC")
    order_terms.append("s.system_id64 ASC")

    limit_param = builder.add(int(limit))
    offset_param = builder.add(int(offset))

    where_sql = f"WHERE {' AND '.join(where_clauses)}\n" if where_clauses else ""
    joins_sql = "\n".join(joins)

    sql = (
        "SELECT s.*, "
        f"({primary_score_expr}) AS primary_score, "
        f"({uncertainty_expr}) AS uncertainty_factor\n"
        "FROM v3_app.system_search s\n"
        f"{joins_sql}\n"
        f"{where_sql}"
        f"ORDER BY {', '.join(order_terms)}\n"
        f"LIMIT {limit_param} OFFSET {offset_param}"
    )

    return sql, builder.params
