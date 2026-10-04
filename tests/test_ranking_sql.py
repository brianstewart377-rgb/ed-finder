"""F2c Task 2: parameterized-SQL builder tests for the V3 ranking profile.

Pure, DB-free — `build_ranked_query` only assembles a SQL string + a params
list; it never opens a connection. See
docs/superpowers/plans/2026-09-27-v3-finder-f2c-f3-ranking.md (Task 2).
"""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from edfinder_api.ranking.profile import PROFILE_SPEC  # noqa: E402
from edfinder_api.ranking.ranking_sql import build_count_query, build_ranked_query  # noqa: E402

LEGACY_RELATIONS = (
    "mv_archetype_rankings",
    "system_archetype_scores",
    "system_archetype_traits",
    "cluster_summary",
    "public.",
    " ratings ",
)


def _assert_no_legacy(sql: str) -> None:
    for token in LEGACY_RELATIONS:
        assert token not in sql, f"legacy relation token {token!r} leaked into SQL"
    # No bare `systems` table reference before the first real v3 relation.
    assert "systems" not in sql.split("v3_app.system_search")[0]


def test_archetype_pick_orders_by_that_archetype_score():
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype="mining_hub",
        picked_economy=None,
        hard_filters={"min_development_score": 60, "elw_count_min": 1},
        reference_coords=(0.0, 0.0, 0.0),
        limit=24,
        offset=0,
    )
    assert "v3_app.system_archetype" in sql
    _assert_no_legacy(sql)
    assert "ORDER BY" in sql
    assert "a.archetype_score" in sql
    # uncertainty modifier present in the ordering expression
    assert "confidence" in sql.lower() and "completeness" in sql.lower()
    # every value is a param, not a literal
    assert "60" not in sql
    assert "$" in sql
    assert 60 in params
    assert 1 in params
    assert "mining_hub" in params


def test_no_pick_orders_by_best_colony_potential():
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={},
        reference_coords=None,
        limit=10,
        offset=0,
    )
    assert "best_colony_potential" in sql
    _assert_no_legacy(sql)
    assert "a.archetype_score" not in sql
    assert 10 in params
    assert 0 in params


def test_economy_pick_is_rejected_not_silently_ranked_by_overall():
    # A concrete economy has no per-economy potential projection yet, so the
    # builder MUST fail closed rather than silently rank by overall colony
    # potential (which returned results that looked economy-tuned but were not).
    import pytest

    for builder_fn in (build_ranked_query, build_count_query):
        with pytest.raises(ValueError):
            if builder_fn is build_ranked_query:
                builder_fn(
                    PROFILE_SPEC,
                    picked_archetype=None,
                    picked_economy="extraction",
                    hard_filters={},
                    reference_coords=None,
                    limit=10,
                    offset=0,
                )
            else:
                builder_fn(
                    PROFILE_SPEC,
                    picked_archetype=None,
                    picked_economy="extraction",
                    hard_filters={},
                    reference_coords=None,
                )


def test_hard_filters_are_where_not_order():
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"has_rings": True, "terraformable_count_min": 2},
        reference_coords=None,
        limit=10,
        offset=0,
    )
    where = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert "terraformable_count" in where
    assert "has_rings" in where
    order_by = sql.split("ORDER BY", 1)[1]
    assert "terraformable_count" not in order_by
    assert True in params
    assert 2 in params


def test_galaxy_region_hard_filter_maps_to_region_id_column():
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"galaxy_region": 5},
        reference_coords=None,
        limit=10,
        offset=0,
    )
    where = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert "galaxy_region_id" in where
    assert 5 in params


def test_max_distance_ly_requires_reference_coords_and_is_ignored_without_it():
    # Known-but-inapplicable key without a reference point is safely ignored,
    # not an error and not a stray literal.
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"max_distance_ly": 50.0},
        reference_coords=None,
        limit=10,
        offset=0,
    )
    assert 50.0 not in params


def test_max_distance_ly_filters_when_reference_coords_present():
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"max_distance_ly": 50.0},
        reference_coords=(1.0, 2.0, 3.0),
        limit=10,
        offset=0,
    )
    where = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert "x_ly" in where
    assert 50.0 in params


def test_unknown_hard_filter_key_is_ignored_safely():
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"not_a_real_key": 999},
        reference_coords=None,
        limit=10,
        offset=0,
    )
    assert 999 not in params
    assert "not_a_real_key" not in sql


def test_no_literal_values_only_placeholders():
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype="paradise",
        picked_economy=None,
        hard_filters={
            "elw_count_min": 3,
            "ww_count_min": 2,
            "landable_count_min": 1,
            "min_development_score": 70,
            "has_rings": False,
        },
        reference_coords=(10.0, 20.0, 30.0),
        limit=15,
        offset=5,
    )
    # Bare numeric literals (not part of a `$n` placeholder, and not the
    # fixed `^ 2` squaring exponent in the Euclidean distance expression)
    # must never appear in the emitted SQL text.
    sql_without_exponents = sql.replace("^ 2", "")
    bare_numbers = {int(m) for m in re.findall(r"(?<!\$)\b\d+\b", sql_without_exponents)}
    assert bare_numbers == set(), f"found bare numeric literal(s) in SQL: {bare_numbers}"
    placeholder_count = sql.count("$")
    assert placeholder_count >= len(params)


def test_tie_break_is_distance_then_system_id64_when_reference_present():
    sql, _ = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={},
        reference_coords=(0.0, 0.0, 0.0),
        limit=10,
        offset=0,
    )
    order_by = sql.split("ORDER BY", 1)[1]
    assert "system_id64" in order_by


def test_limit_and_offset_are_parameterized():
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={},
        reference_coords=None,
        limit=24,
        offset=48,
    )
    assert "LIMIT" in sql and "OFFSET" in sql
    assert "24" not in sql and "48" not in sql
    assert 24 in params and 48 in params


def test_has_biologicals_and_geologicals_hard_filters():
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"has_biologicals": True, "has_geologicals": True},
        reference_coords=None,
        limit=10,
        offset=0,
    )
    where = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert "has_biologicals" in where
    assert "has_geologicals" in where
    assert params.count(True) >= 2


def test_main_star_class_in_hard_filter():
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"main_star_class_in": ["K", "M"]},
        reference_coords=None,
        limit=10,
        offset=0,
    )
    where = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert "main_star_class IN" in where
    assert "K" in params and "M" in params


# --- body-count range filters (finding #7: min AND max, every column) --------


def test_every_body_count_column_supports_min_and_max_bounds():
    from edfinder_api.ranking.profile import BODY_COUNT_COLUMNS

    for col in BODY_COUNT_COLUMNS:
        sql, params = build_ranked_query(
            PROFILE_SPEC,
            picked_archetype=None,
            picked_economy=None,
            hard_filters={f"{col}_min": 2, f"{col}_max": 9},
            reference_coords=None,
            limit=10,
            offset=0,
        )
        where = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
        assert f"s.{col} >=" in where, f"{col} min not enforced"
        assert f"s.{col} <=" in where, f"{col} max not enforced"
        assert 2 in params and 9 in params


def test_body_count_max_zero_is_a_real_constraint_not_dropped():
    # "0 ELW bodies" is a meaningful exclusion filter, not a no-op. A `max` of
    # zero must produce `s.elw_count <= $n` with 0 bound (finding #7 dropped it).
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"elw_count_max": 0},
        reference_coords=None,
        limit=10,
        offset=0,
    )
    where = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert "s.elw_count <=" in where
    assert 0 in params


def test_body_count_max_filter_shared_by_ranked_and_count_queries():
    hard_filters = {"ammonia_count_max": 3, "ww_count_min": 1}
    ranked_sql, ranked_params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters=hard_filters,
        reference_coords=None,
        limit=10,
        offset=0,
    )
    count_sql, count_params = build_count_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters=hard_filters,
        reference_coords=None,
    )
    for sql in (ranked_sql, count_sql):
        where = sql.split("WHERE", 1)[1]
        assert "s.ammonia_count <=" in where
        assert "s.ww_count >=" in where
    # count params are the WHERE-clause prefix of the ranked params
    assert count_params == ranked_params[: len(count_params)]


def test_min_development_score_not_mistaken_for_a_count_min_filter():
    # `min_development_score` contains "min" but is NOT a `<col>_min` count
    # filter — it must still map to the primary-score expression, not a
    # bogus `s.min_development_sc >= n` column predicate.
    sql, _ = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"min_development_score": 55},
        reference_coords=None,
        limit=10,
        offset=0,
    )
    where = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert "best_colony_potential" in where
    assert "min_development_sc" not in where


# --- distance range + sort (findings #14, #15) -------------------------------


def test_min_distance_ly_emits_lower_bound_when_reference_present():
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"min_distance_ly": 100.0, "max_distance_ly": 500.0},
        reference_coords=(0.0, 0.0, 0.0),
        limit=10,
        offset=0,
    )
    where = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert ">= $" in where and "<= $" in where, "annulus needs both bounds"
    assert 100.0 in params and 500.0 in params


def test_min_distance_ly_ignored_without_reference():
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"min_distance_ly": 100.0},
        reference_coords=None,
        limit=10,
        offset=0,
    )
    assert 100.0 not in params


def test_min_distance_shared_by_ranked_and_count():
    hard_filters = {"min_distance_ly": 50.0, "max_distance_ly": 400.0}
    ref = (1.0, 2.0, 3.0)
    _, ranked_params = build_ranked_query(
        PROFILE_SPEC, picked_archetype=None, picked_economy=None,
        hard_filters=hard_filters, reference_coords=ref, limit=10, offset=0,
    )
    count_sql, count_params = build_count_query(
        PROFILE_SPEC, picked_archetype=None, picked_economy=None,
        hard_filters=hard_filters, reference_coords=ref,
    )
    assert count_params == ranked_params[: len(count_params)]
    assert 50.0 in count_params and 400.0 in count_params


def test_sort_distance_orders_distance_first_then_score():
    sql, _ = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={},
        reference_coords=(0.0, 0.0, 0.0),
        limit=10,
        offset=0,
        sort="distance",
    )
    order_by = sql.split("ORDER BY", 1)[1]
    # first ordering term is the distance expression (ASC), score comes after.
    # No-pick ranks by the precomputed, indexable weighted_potential (#335).
    first_term = order_by.split(",")[0]
    assert "sqrt(" in first_term and "ASC" in first_term
    assert order_by.index("sqrt(") < order_by.index("weighted_potential")


def test_sort_score_is_default_and_orders_score_first():
    sql, _ = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={},
        reference_coords=(0.0, 0.0, 0.0),
        limit=10,
        offset=0,
    )
    order_by = sql.split("ORDER BY", 1)[1]
    assert order_by.index("weighted_potential") < order_by.index("sqrt(")


def test_sort_distance_without_reference_falls_back_to_score_order():
    sql, _ = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={},
        reference_coords=None,
        limit=10,
        offset=0,
        sort="distance",
    )
    order_by = sql.split("ORDER BY", 1)[1]
    assert "sqrt(" not in order_by  # no reference -> no distance term at all
    assert "weighted_potential" in order_by


# --- build_count_query -------------------------------------------------------


def test_build_count_query_has_no_order_limit_offset():
    sql, params = build_count_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"has_rings": True},
        reference_coords=None,
    )
    assert "ORDER BY" not in sql
    assert "LIMIT" not in sql
    assert "OFFSET" not in sql
    assert "count(" in sql.lower()
    _assert_no_legacy(sql)
    assert True in params


def test_build_count_query_placeholder_count_matches_params():
    sql, params = build_count_query(
        PROFILE_SPEC,
        picked_archetype="mining_hub",
        picked_economy=None,
        hard_filters={"min_development_score": 60, "elw_count_min": 1},
        reference_coords=(1.0, 2.0, 3.0),
    )
    placeholder_indices = {int(m) for m in re.findall(r"\$(\d+)", sql)}
    assert placeholder_indices == set(range(1, len(params) + 1))


def test_build_count_query_params_are_a_prefix_of_ranked_query_params():
    """The CRITICAL regression this guards: `build_count_query`'s params must
    be exactly the WHERE-clause params -- no tie-break distance params, no
    limit/offset -- so the count query's `$n` placeholders always match the
    argument list a caller passes it."""
    hard_filters = {"min_development_score": 60, "elw_count_min": 1}
    reference_coords = (1.0, 2.0, 3.0)

    ranked_sql, ranked_params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype="mining_hub",
        picked_economy=None,
        hard_filters=hard_filters,
        reference_coords=reference_coords,
        limit=24,
        offset=0,
    )
    count_sql, count_params = build_count_query(
        PROFILE_SPEC,
        picked_archetype="mining_hub",
        picked_economy=None,
        hard_filters=hard_filters,
        reference_coords=reference_coords,
    )

    assert count_params == ranked_params[:len(count_params)]
    # ranked adds 3 tie-break distance params (reference_coords present) + 2
    # limit/offset params beyond the shared WHERE params.
    assert len(ranked_params) == len(count_params) + 5
    _assert_no_legacy(count_sql)


def test_build_count_query_without_reference_coords_matches_ranked_where_params():
    hard_filters = {"has_rings": True}

    ranked_sql, ranked_params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters=hard_filters,
        reference_coords=None,
        limit=10,
        offset=0,
    )
    count_sql, count_params = build_count_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters=hard_filters,
        reference_coords=None,
    )

    assert count_params == ranked_params[:len(count_params)]
    # No reference_coords means no tie-break distance params; only the
    # trailing limit/offset params (2) differ from the shared WHERE params.
    assert len(ranked_params) == len(count_params) + 2


def test_build_count_query_cap_wraps_in_bounded_subquery():
    """A galaxy-wide count must be bounded so it never scans the whole
    published generation: `cap` wraps the scan in a `LIMIT`ed subquery."""
    sql, params = build_count_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"has_rings": True},
        reference_coords=None,
        cap=10_000,
    )
    assert "count(*) from (" in sql.lower()
    assert "limit" in sql.lower()
    # The cap value is the last positional parameter.
    assert params[-1] == 10_000
    placeholder_indices = {int(m) for m in re.findall(r"\$(\d+)", sql)}
    assert placeholder_indices == set(range(1, len(params) + 1))
    _assert_no_legacy(sql)


def test_build_count_query_cap_appends_after_where_params():
    """The cap param is added last, so the shared WHERE params still line up
    with `build_ranked_query` as a prefix even when a cap is present."""
    hard_filters = {"min_development_score": 60, "elw_count_min": 1}

    _ranked_sql, ranked_params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters=hard_filters,
        reference_coords=None,
        limit=24,
        offset=0,
    )
    count_sql, count_params = build_count_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters=hard_filters,
        reference_coords=None,
        cap=10_000,
    )
    # Drop the trailing cap param: the remainder is exactly the shared WHERE
    # params, identical to the ranked query's leading WHERE params.
    where_only = count_params[:-1]
    assert where_only == ranked_params[:len(where_only)]
    assert count_params[-1] == 10_000


def test_build_count_query_without_cap_has_no_limit():
    """Distance-bounded (non galaxy-wide) counts stay exact: no cap, no LIMIT."""
    sql, params = build_count_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"has_rings": True},
        reference_coords=None,
    )
    assert "LIMIT" not in sql
    assert "from (" not in sql.lower()


# --- #335: default no-pick ranking uses the precomputed weighted_potential ---


def test_no_pick_default_orders_by_indexable_weighted_potential():
    """The default galaxy-wide, no-anchor Explore load (no reference coords)
    must ORDER BY the precomputed, single-column `sum.weighted_potential` so a
    cold-cache load is index-satisfiable, NOT by the cross-table
    `best_colony_potential * (confidence * completeness)` product that forces a
    full-generation sort (#335)."""
    sql, _ = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={},
        reference_coords=None,
        limit=24,
        offset=0,
    )
    order_by = sql.split("ORDER BY", 1)[1]
    assert "sum.weighted_potential" in order_by
    # The raw cross-table product must NOT be the ordering expression anymore.
    assert "* (" not in order_by.replace("sum.weighted_potential", "")
    # The score is still selectable for the response payload.
    assert "weighted_potential" in sql.split("FROM", 1)[0]


def test_picked_archetype_still_orders_by_weighted_float_product():
    """A picked archetype has no precomputed weighted column, so it keeps the
    exact `archetype_score * (confidence * completeness)` ordering (its filtered
    set is bounded by the #204 archetype index, not a full-generation sort)."""
    sql, _ = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype="mining_hub",
        picked_economy=None,
        hard_filters={},
        reference_coords=None,
        limit=24,
        offset=0,
    )
    order_by = sql.split("ORDER BY", 1)[1]
    assert "a.archetype_score" in order_by
    assert "completeness" in order_by
    assert "weighted_potential" not in order_by


# --- #265: distance radius uses an index-usable cube bounding predicate ------


def test_max_distance_adds_indexable_cube_bound_alongside_exact_check():
    """On a bounded-radius search the filter must include an index-usable
    `position_ly <@ cube(...)` bounding box (served by the GiST index on
    `v3_derived.system_search.position_ly`) in addition to the exact Euclidean
    `sqrt(...) <= r` check, so PostgreSQL does not scan the whole generation
    (#265)."""
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"max_distance_ly": 200.0},
        reference_coords=(10.0, 20.0, 30.0),
        limit=24,
        offset=0,
    )
    where = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert "position_ly" in where and "cube(" in where
    assert "<@" in where
    # The exact distance check is still present (cube box is a superset).
    assert "sqrt(" in where
    # Every value is still a bound parameter: no bare radius/coord literals.
    assert "200" not in sql
    assert 200.0 in params


def test_cube_bound_is_shared_by_count_query():
    """The count query shares the same indexable cube predicate (via
    `_build_common`) so page and total scan the same bounded set."""
    hard_filters = {"max_distance_ly": 150.0}
    ref = (1.0, 2.0, 3.0)
    count_sql, _ = build_count_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters=hard_filters,
        reference_coords=ref,
    )
    where = count_sql.split("WHERE", 1)[1]
    assert "position_ly" in where and "cube(" in where and "<@" in where


# --- #291: the builder consumes the hashed spec (identity can't drift) -------


def test_unsupported_uncertainty_factor_expr_fails_closed():
    """`ranking_sha256` hashes `uncertainty.factor_expr`; if the builder
    silently ignored it, a spec change could leave ordering unchanged (or a
    builder change could diverge from the hash). The builder must consume it
    and fail closed on an expression it does not implement (#291)."""
    import copy
    import pytest

    bad = copy.deepcopy(PROFILE_SPEC)
    bad["uncertainty"]["factor_expr"] = "confidence"  # not the implemented curve
    with pytest.raises(ValueError):
        build_ranked_query(
            bad,
            picked_archetype=None,
            picked_economy=None,
            hard_filters={},
            reference_coords=None,
            limit=10,
            offset=0,
        )


def test_unsupported_primary_score_rule_fails_closed():
    """`primary_score_rule` is hashed into ranking_sha256; the builder must
    consume it so changing a score expression cannot mint a new identity while
    executing identical hard-coded SQL (#162)."""
    import copy
    import pytest

    bad = copy.deepcopy(PROFILE_SPEC)
    bad["primary_score_rule"]["none"] = "system_archetype_summary.archetype_confidence"
    with pytest.raises(ValueError):
        build_ranked_query(
            bad,
            picked_archetype=None,
            picked_economy=None,
            hard_filters={},
            reference_coords=None,
            limit=10,
            offset=0,
        )


def test_unsupported_tie_break_fails_closed():
    import copy
    import pytest

    bad = copy.deepcopy(PROFILE_SPEC)
    bad["tie_break"] = ["system_id64", "distance"]  # reversed: not implemented
    with pytest.raises(ValueError):
        build_ranked_query(
            bad,
            picked_archetype=None,
            picked_economy=None,
            hard_filters={},
            reference_coords=(0.0, 0.0, 0.0),
            limit=10,
            offset=0,
        )


def test_default_spec_builds_after_identity_binding():
    """The live PROFILE_SPEC must still build cleanly once the builder consumes
    the hashed identity fields (regression guard for #291's fail-closed check)."""
    sql, _ = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={},
        reference_coords=None,
        limit=10,
        offset=0,
    )
    assert "ORDER BY" in sql
