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
| `has_biologicals`            | `s.has_biologicals = $n` (explicit true/false)    |
| `has_geologicals`            | `s.has_geologicals = $n` (explicit true/false)    |
| `main_star_class_in`         | `s.main_star_class IN ($n, ...)`                  |
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

## Economy-picked ranking (not yet supported — fail closed)

`system_search` / `system_archetype*` carry no per-economy potential column
today (no `economy_potential`/`potential_score` projection exists yet, and
`PROFILE_SPEC["primary_score_rule"]["economy"]` names an aspirational
`potential_score` field that has no backing relation). Rather than silently
rank a requested economy by the overall `best_colony_potential` — which
returns results that look economy-tuned but are not — a non-None
`picked_economy` **raises `ValueError`** in `_build_common`. The HTTP layer
(`local_search.local_db_search_v3`) rejects a concrete economy with a 422
before ever calling the builder, so the only economy value that reaches a
successful query is "no pick".

    TODO(F2c/F3 follow-up): once a per-economy potential projection exists
    (tracked as a future Finder derived-data task), branch picked_economy
    onto its real column and lift both the builder guard and the 422.

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

from typing import Any, Final

from .profile import BODY_COUNT_COLUMNS, HARD_FILTER_KEYS

# Body-count range filters map 1:1 onto a `v3_app.system_search` integer
# column: `<col>_min` -> `s.<col> >= $n`, `<col>_max` -> `s.<col> <= $n`.
# `BODY_COUNT_COLUMNS` (in `profile.py`) is the single source of truth for
# which columns exist; both bounds are supported for every one.
_BODY_COUNT_COLUMN_SET: frozenset[str] = frozenset(BODY_COUNT_COLUMNS)
_COUNT_BOUND_OPS: tuple[tuple[str, str], ...] = (("_min", ">="), ("_max", "<="))


def _count_filter_column(key: str) -> tuple[str, str] | None:
    """Resolve a `<col>_min` / `<col>_max` hard-filter key to its
    `(column, comparison_operator)`, or `None` if `key` is not a body-count
    range filter. Non-count keys that merely contain "min"/"max" (e.g.
    `min_development_score`, `max_distance_ly`) do not end in `_min`/`_max`
    over a known count column, so they fall through to their own branches.
    """
    for suffix, op in _COUNT_BOUND_OPS:
        if key.endswith(suffix) and key[: -len(suffix)] in _BODY_COUNT_COLUMN_SET:
            return key[: -len(suffix)], op
    return None


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


def _build_common(
    builder: _ParamBuilder,
    *,
    picked_archetype: str | None,
    picked_economy: str | None,  # accepted, not yet used — see module docstring's economy-pick TODO
    hard_filters: dict[str, Any],
    reference_coords: tuple[float, float, float] | None,
) -> tuple[list[str], list[str], str, str, str]:
    """Build the joins, WHERE clauses and score expressions shared by both
    `build_ranked_query` and `build_count_query`.

    This is the single place hard filters are translated into predicates —
    both callers go through it so the count and the ranked page can never
    drift onto different filter semantics. Returns
    `(joins, where_clauses, primary_score_expr, confidence_expr, uncertainty_expr)`;
    each caller assembles its own final SQL text (a ranked SELECT with
    ORDER BY/LIMIT/OFFSET, or a bare COUNT(*)) from these pieces.

    `confidence_expr` is the *raw* confidence factor that feeds the
    uncertainty modifier (`a.confidence` for a picked archetype, else
    `sum.archetype_confidence`). It is exposed as its own selectable
    expression so a response can echo the confidence badge by selecting the
    real column directly, rather than dividing `uncertainty_factor` back out
    by `completeness` (which is undefined at completeness=0 and conflates the
    per-archetype judgement confidence with the general data-completeness
    fraction).
    """

    if picked_economy:
        # No per-economy potential projection exists yet (the
        # `PROFILE_SPEC["primary_score_rule"]["economy"]` `potential_score`
        # field has no backing `system_search`/`system_archetype*` column).
        # Silently ranking a requested economy by the overall
        # `best_colony_potential` returned results that *looked* economy-tuned
        # but were not. Fail closed here so no caller can reach that path;
        # `local_search.local_db_search_v3` rejects a picked economy with a
        # 422 before it ever calls the builder.
        raise ValueError(
            "picked_economy is not supported by the V3 ranking profile yet: "
            "no per-economy potential projection exists "
            f"(requested economy={picked_economy!r})."
        )

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
        confidence_expr = "a.confidence"
    else:
        # No-pick ranking: the F2b no-pick primary score. (A concrete
        # `picked_economy` never reaches here — it is rejected above.)
        primary_score_expr = "sum.best_colony_potential"
        confidence_expr = "sum.archetype_confidence"

    uncertainty_expr = f"{confidence_expr} * s.completeness"

    where_clauses: list[str] = []

    for key, value in hard_filters.items():
        if key not in HARD_FILTER_KEYS:
            # Unknown/typo'd/future key: ignore safely rather than erroring.
            continue

        count_filter = _count_filter_column(key)
        if count_filter is not None:
            column, op = count_filter
            param = builder.add(int(value))
            where_clauses.append(f"s.{column} {op} {param}")
        elif key == "has_rings":
            param = builder.add(bool(value))
            where_clauses.append(f"s.has_rings = {param}")
        elif key == "has_biologicals":
            param = builder.add(bool(value))
            where_clauses.append(f"s.has_biologicals = {param}")
        elif key == "has_geologicals":
            param = builder.add(bool(value))
            where_clauses.append(f"s.has_geologicals = {param}")
        elif key == "main_star_class_in":
            placeholders = ", ".join(builder.add(v) for v in value)
            where_clauses.append(f"s.main_star_class IN ({placeholders})")
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
        elif key == "min_distance_ly":
            if reference_coords is None:
                # No reference point to measure distance from: safely ignored,
                # like max_distance_ly above.
                continue
            distance_expr = _distance_expr(builder, reference_coords)
            param = builder.add(float(value))
            where_clauses.append(f"{distance_expr} >= {param}")
        # Every HARD_FILTER_KEYS member is handled above; nothing falls
        # through silently for a *known* key.

    return joins, where_clauses, primary_score_expr, confidence_expr, uncertainty_expr


# Ordering modes `build_ranked_query` supports. Callers (the search router)
# reject any other `sort_by` with a 422 rather than silently ignoring it.
SORT_SCORE: Final[str] = "score"
SORT_DISTANCE: Final[str] = "distance"
SUPPORTED_SORTS: Final[frozenset[str]] = frozenset({SORT_SCORE, SORT_DISTANCE})


def build_ranked_query(
    spec: dict[str, Any],
    *,
    picked_archetype: str | None,
    picked_economy: str | None,
    hard_filters: dict[str, Any],
    reference_coords: tuple[float, float, float] | None,
    limit: int,
    offset: int,
    sort: str = SORT_SCORE,
) -> tuple[str, list[Any]]:
    """Build a parameterized, generation-agnostic ranked SELECT.

    Returns `(sql, params)` where `sql` uses only `$1..$n` placeholders (no
    literal values) and `params` is the matching positional argument list
    for asyncpg. Pure — never opens a database connection.

    `sort` selects the primary ordering:
    - `SORT_SCORE` (default): weighted score (`primary_score * uncertainty`)
      DESC, then nearest-distance, then `system_id64` — the ranking profile's
      canonical order.
    - `SORT_DISTANCE`: nearest reference distance ASC first, then weighted
      score DESC, then `system_id64`. Requires `reference_coords`; without a
      reference there is nothing to measure distance from, so it falls back to
      score order. Any value outside `SUPPORTED_SORTS` is the caller's error
      (the router 422s before calling this).

    `spec` is accepted (rather than reading the module-level `PROFILE_SPEC`
    directly) so callers can pass a resolved `RANKING_VERSIONS[version]` for
    a future non-default profile without this function changing shape; the
    current implementation only depends on the fixed `HARD_FILTER_KEYS`
    contract and `uncertainty`/`tie_break` field names within `spec`.

    See `build_count_query` for the matching `COUNT(*)` query over the same
    WHERE clause — the two share `_build_common` so a page's filter and its
    total can never drift apart. (Sort order does not affect a count, so
    `build_count_query` takes no `sort`.)
    """

    builder = _ParamBuilder()
    joins, where_clauses, primary_score_expr, confidence_expr, uncertainty_expr = _build_common(
        builder,
        picked_archetype=picked_archetype,
        picked_economy=picked_economy,
        hard_filters=hard_filters,
        reference_coords=reference_coords,
    )

    score_term = f"({primary_score_expr}) * ({uncertainty_expr}) DESC NULLS LAST"
    distance_term = (
        f"{_distance_expr(builder, reference_coords)} ASC"
        if reference_coords is not None
        else None
    )

    if sort == SORT_DISTANCE and distance_term is not None:
        # Nearest-first: distance ASC primary, weighted score as tie-break.
        order_terms = [distance_term, score_term]
    else:
        # Canonical ranking order: weighted score primary, distance tie-break.
        order_terms = [score_term]
        if distance_term is not None:
            order_terms.append(distance_term)
    order_terms.append("s.system_id64 ASC")

    limit_param = builder.add(int(limit))
    offset_param = builder.add(int(offset))

    where_sql = f"WHERE {' AND '.join(where_clauses)}\n" if where_clauses else ""
    joins_sql = "\n".join(joins)

    sql = (
        "SELECT s.*, "
        f"({primary_score_expr}) AS primary_score, "
        f"({confidence_expr}) AS ranking_confidence, "
        f"({uncertainty_expr}) AS uncertainty_factor, "
        # The system's ACTUAL no-pick summary facts (always joined via `sum`),
        # aliased so a response can report the real primary/secondary archetype
        # and overall best potential rather than inventing them from the
        # selected archetype (finding #20). NULL for a system with no summary.
        "sum.primary_archetype AS summary_primary_archetype, "
        "sum.secondary_archetype AS summary_secondary_archetype, "
        "sum.best_colony_potential AS summary_best_colony_potential, "
        "sum.archetype_confidence AS summary_archetype_confidence\n"
        "FROM v3_app.system_search s\n"
        f"{joins_sql}\n"
        f"{where_sql}"
        f"ORDER BY {', '.join(order_terms)}\n"
        f"LIMIT {limit_param} OFFSET {offset_param}"
    )

    return sql, builder.params


def build_count_query(
    spec: dict[str, Any],
    *,
    picked_archetype: str | None,
    picked_economy: str | None,
    hard_filters: dict[str, Any],
    reference_coords: tuple[float, float, float] | None,
) -> tuple[str, list[Any]]:
    """Build the `COUNT(*)` companion to `build_ranked_query`'s SELECT.

    Uses exactly the same joins and WHERE predicates as `build_ranked_query`
    (via the shared `_build_common` helper) for the same arguments, so the
    reported total can never drift from what the page actually filtered on.
    Carries no ORDER BY, no tie-break distance params, and no LIMIT/OFFSET —
    none of those affect a row count. Pure — never opens a database
    connection.
    """

    builder = _ParamBuilder()
    joins, where_clauses, _primary_score_expr, _confidence_expr, _uncertainty_expr = _build_common(
        builder,
        picked_archetype=picked_archetype,
        picked_economy=picked_economy,
        hard_filters=hard_filters,
        reference_coords=reference_coords,
    )

    where_sql = f"WHERE {' AND '.join(where_clauses)}\n" if where_clauses else ""
    joins_sql = "\n".join(joins)

    sql = (
        "SELECT count(*)\n"
        "FROM v3_app.system_search s\n"
        f"{joins_sql}\n"
        f"{where_sql}"
    ).rstrip()

    return sql, builder.params
