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
from edfinder_api.ranking.ranking_sql import build_ranked_query  # noqa: E402

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


def test_economy_pick_falls_back_to_best_colony_potential():
    sql, _ = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy="extraction",
        hard_filters={},
        reference_coords=None,
        limit=10,
        offset=0,
    )
    assert "best_colony_potential" in sql
    _assert_no_legacy(sql)


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
