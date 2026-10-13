"""Pure SQL-builder tests for the wide-row F2d ranking paths."""

from copy import deepcopy
from pathlib import Path
import re
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from edfinder_api.ranking.profile import ARCHETYPE_KEYS, PROFILE_SPEC  # noqa: E402
from edfinder_api.ranking.ranking_sql import (  # noqa: E402
    ARCHETYPE_COLUMNS,
    build_count_query,
    build_ranked_query,
)

LEGACY = (
    "mv_archetype_rankings",
    "system_archetype_scores",
    "system_archetype_traits",
    "FROM systems",
    "public.",
)


def _picked_page(key="paradise", floor=60, limit=50, offset=0):
    return build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=key,
        picked_economy=None,
        hard_filters={},
        reference_coords=None,
        min_score=floor,
        limit=limit,
        offset=offset,
    )


def _picked_count(key="paradise", floor=60):
    return build_count_query(
        PROFILE_SPEC,
        picked_archetype=key,
        picked_economy=None,
        hard_filters={},
        reference_coords=None,
        min_score=floor,
    )


def _assert_no_legacy(sql):
    for token in LEGACY:
        assert token not in sql


def test_column_map_is_derived_from_hashed_spec_for_all_eight_keys():
    assert ARCHETYPE_COLUMNS == PROFILE_SPEC["archetype_columns"]
    assert tuple(ARCHETYPE_COLUMNS) == ARCHETYPE_KEYS
    for key, columns in ARCHETYPE_COLUMNS.items():
        assert columns["score"] == f"{key}_score"
        assert columns["tier"] == f"{key}_tier"
        assert f"{key}_confidence_ppm / 1000000.0" in columns["confidence"]
        assert columns["weighted_key"] == f"{key}_weighted_e4"


@pytest.mark.parametrize("floor", [60, 76, 88])
def test_picked_floor_is_server_literal_and_uses_matching_columns(floor):
    sql, params = _picked_page("mining_hub", floor)
    assert f"ar.mining_hub_score >= {floor}" in sql
    assert "ar.mining_hub_weighted_e4" in sql
    assert "fetch.mining_hub_tier AS selected_archetype_tier" in sql
    assert "fetch.mining_hub_confidence_ppm / 1000000.0" in sql
    assert floor not in params


@pytest.mark.parametrize("floor", [0, 59, 70, 100, None, "60 OR true"])
def test_no_other_floor_can_produce_sql(floor):
    if floor is None:
        # None intentionally means the server default, never user input.
        sql, _ = _picked_page(floor=floor)
        assert "paradise_score >= 60" in sql
    else:
        with pytest.raises(ValueError):
            _picked_page(floor=floor)


def test_picked_page_has_all_four_bounded_stages_and_three_orders():
    sql, params = _picked_page(limit=50, offset=75)
    assert sql.count("v3_app.system_archetype") == 2
    assert "FROM v3_app.system_archetype ar" in sql
    assert "LIMIT 10000" in sql
    assert sql.count("ORDER BY") == 3
    assert "ORDER BY ar.paradise_weighted_e4 DESC" in sql
    assert sql.count("selected_archetype_weighted_e4 DESC") == 2
    assert "JOIN v3_app.system_search" in sql
    assert "JOIN v3_app.system_archetype fetch" in sql
    assert params == [50, 75]
    _assert_no_legacy(sql)


def test_picked_count_has_fixed_sentinel_and_no_order():
    sql, params = _picked_count(floor=88)
    assert "paradise_score >= 88" in sql
    assert "LIMIT 10001" in sql
    assert "ORDER BY" not in sql
    assert params == []


def test_unknown_and_adversarial_archetype_keys_never_reach_sql():
    for key in ("unknown", "paradise; DROP TABLE systems", 'paradise"'):
        with pytest.raises(ValueError):
            _picked_page(key=key)


def test_picked_path_rejects_filters_instead_of_filtering_the_window():
    with pytest.raises(ValueError):
        build_ranked_query(
            PROFILE_SPEC,
            picked_archetype="paradise",
            picked_economy=None,
            hard_filters={"galaxy_region": 7},
            reference_coords=None,
            min_score=60,
            limit=50,
            offset=0,
        )


def test_no_user_value_is_interpolated_into_picked_sql():
    sql, params = _picked_page(limit=417, offset=283)
    assert "417" not in sql and "283" not in sql
    assert params == [417, 283]
    # The only bare numeric literals are the hashed, server-owned floor,
    # window and confidence-scale constants.
    numbers = {int(value) for value in re.findall(r"(?<!\$)\b\d+\b", sql)}
    assert numbers <= {60, 10000, 1000000, 0}


def test_no_pick_keeps_summary_join_and_canonical_order():
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={},
        reference_coords=None,
        limit=50,
        offset=0,
    )
    assert "v3_app.system_archetype_summary" in sql
    assert "sum.weighted_potential DESC NULLS LAST" in sql
    assert "s.system_id64 ASC" in sql
    assert "LIMIT 10000" in sql
    assert params == [50, 0]
    _assert_no_legacy(sql)


def test_count_cap_means_cap_plus_one_sentinel():
    sql, params = build_count_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={},
        reference_coords=None,
        cap=10_000,
    )
    assert "LIMIT $1" in sql
    assert params == [10_001]


def test_anchored_nearest_first_has_knn_order_inside_limit_radius_outside():
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"max_distance_ly": 10_000.0},
        reference_coords=(1.0, 2.0, 3.0),
        sort="distance",
        limit=50,
        offset=75,
    )
    inner, outer = sql.split(") nearest", 1)
    assert "s.position_ly <@ cube(" in inner
    assert "ORDER BY s.position_ly <->" in inner
    assert "sum.weighted_potential DESC NULLS LAST, s.system_id64 ASC" in inner
    assert "LIMIT $5" in inner
    assert "nearest.distance_ly <= $4" in outer
    assert params == [1.0, 2.0, 3.0, 10_000.0, 125, 50, 75]


def test_anchored_nearest_first_count_uses_knn_sentinel_inside_radius():
    sql, params = build_count_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={"max_distance_ly": 500.0},
        reference_coords=(1.0, 2.0, 3.0),
        sort="distance",
        cap=10_000,
    )
    inner, outer = sql.split(") nearest", 1)
    assert "ORDER BY s.position_ly <->" in inner
    assert "LIMIT $5" in inner
    assert "nearest.distance_ly <= $4" in outer
    assert params[-1] == 10_001


def test_anchored_filters_remain_parameterized():
    marker = "unlikely-star-class-marker"
    sql, params = build_ranked_query(
        PROFILE_SPEC,
        picked_archetype=None,
        picked_economy=None,
        hard_filters={
            "max_distance_ly": 500.0,
            "min_distance_ly": 25.0,
            "main_star_class_in": [marker],
            "has_biologicals": True,
        },
        reference_coords=(0.0, 0.0, 0.0),
        sort="distance",
        limit=50,
        offset=0,
    )
    assert marker not in sql
    assert marker in params and 25.0 in params and True in params


def test_page_window_bound_fails_closed_in_builder():
    with pytest.raises(ValueError):
        _picked_page(limit=2, offset=9_999)
    with pytest.raises(ValueError):
        _picked_page(limit=501, offset=0)


@pytest.mark.parametrize(
    "field",
    [
        "archetype_columns",
        "archetype_score_floor",
        "stored_weighted_key_expression",
        "ranking_window",
        "picked_archetype_rejected_filters",
        "picked_archetype_filter_rejection_reason",
        "local_search_contract",
        "tie_break",
    ],
)
def test_builder_rejects_mutated_hashed_contract(field):
    changed = deepcopy(PROFILE_SPEC)
    changed[field] = None
    with pytest.raises(ValueError):
        build_ranked_query(
            changed,
            picked_archetype=None,
            picked_economy=None,
            hard_filters={},
            reference_coords=None,
            limit=10,
            offset=0,
        )
