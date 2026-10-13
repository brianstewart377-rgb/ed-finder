"""DB-free identity tests for the F2d ranking profile."""

from copy import deepcopy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from edfinder_api.ranking.profile import (  # noqa: E402
    ACCEPTED_ARCHETYPE_SCORE_FLOORS,
    ARCHETYPE_KEYS,
    ARCHETYPE_SCORE_FLOOR_DEFAULT,
    PROFILE_SPEC,
    RANKING_COUNT_SENTINEL,
    RANKING_OFFSET_PLUS_LIMIT_MAX,
    RANKING_VERSION,
    RANKING_VERSIONS,
    RANKING_WINDOW_LIMIT,
    STORED_WEIGHTED_KEY_EXPRESSION,
    ranking_sha256,
    resolve,
)


EXPECTED_RANKING_SHA256 = "ec3533063f422f5859a26baf422974f9d330466f2ad675505fac2743bbca89e4"


def test_version_registry_and_pinned_digest():
    assert RANKING_VERSION == "v3-colony-potential-2"
    assert RANKING_VERSIONS[RANKING_VERSION] is PROFILE_SPEC
    assert resolve(RANKING_VERSION) is PROFILE_SPEC
    assert ranking_sha256() == PROFILE_SPEC["ranking_sha256"]
    assert ranking_sha256() == EXPECTED_RANKING_SHA256


def test_unknown_version_fails_closed():
    with pytest.raises(KeyError):
        resolve("not-a-ranking-version")


def test_wide_column_map_is_complete_and_explicit():
    columns = PROFILE_SPEC["archetype_columns"]
    assert tuple(columns) == ARCHETYPE_KEYS
    for key, mapped in columns.items():
        assert mapped == {
            "score": f"{key}_score",
            "tier": f"{key}_tier",
            "confidence": (
                f"({key}_confidence_ppm / 1000000.0)::double precision"
            ),
            "weighted_key": f"{key}_weighted_e4",
        }


def test_floor_window_count_and_tie_contract():
    assert ARCHETYPE_SCORE_FLOOR_DEFAULT == 60
    assert ACCEPTED_ARCHETYPE_SCORE_FLOORS == (60, 76, 88)
    assert PROFILE_SPEC["archetype_score_floor"] == {
        "default": 60,
        "accepted": [60, 76, 88],
    }
    assert RANKING_WINDOW_LIMIT == 10_000
    assert RANKING_OFFSET_PLUS_LIMIT_MAX == 10_000
    assert RANKING_COUNT_SENTINEL == 10_001
    assert PROFILE_SPEC["ranking_window"] == {
        "limit": 10_000,
        "offset_plus_limit_max": 10_000,
        "page_limit_min": 1,
        "page_limit_max": 500,
        "offset_min": 0,
        "offset_max": 9_999,
        "count_sentinel": 10_001,
        "is_truncated_rule": "qualifying = 10001",
        "total_rule": "min(qualifying, 10000)",
    }
    assert PROFILE_SPEC["tie_break"] == ["system_id64"]


def test_stored_weighted_key_expression_is_verbatim():
    assert STORED_WEIGHTED_KEY_EXPRESSION == (
        "((<key>_score::bigint * <key>_confidence_ppm * completeness_ppm) "
        "+ 50000000) / 100000000"
    )
    assert (
        PROFILE_SPEC["stored_weighted_key_expression"]
        == STORED_WEIGHTED_KEY_EXPRESSION
    )


def test_picked_filter_rejection_set_is_hashed():
    assert PROFILE_SPEC["picked_archetype_rejected_filters"] == [
        "galaxy_region",
        "max_distance_ly",
        "has_elw",
        "min_slots",
        "max_contamination",
    ]
    assert PROFILE_SPEC["picked_archetype_filter_rejection_reason"] == (
        "archetype ranking is unfiltered in the initial product; "
        "filter in Any mode or drop the filter"
    )


def test_local_search_contract_is_explicit():
    contract = PROFILE_SPEC["local_search_contract"]
    assert contract["request_bounds"] == {
        "from_min": 0,
        "size_min": 1,
        "from_plus_size_max": 10_000,
    }
    assert contract["count"] == {
        "cap": 10_000,
        "sentinel_rule": "cap + 1",
        "total_rule": "min(qualifying, cap)",
        "total_is_capped_rule": "qualifying > cap",
        "applies_to": ["galaxy-wide", "anchored"],
    }
    assert contract["galaxy_wide_any"]["rejection_rule"] == (
        "reject any hard filter"
    )
    assert contract["galaxy_wide_any"]["reason"] == (
        "pick an anchor area or remove the filter"
    )
    anchored = contract["anchored_any"]
    assert anchored["intrinsic_radius_key"] == "max_distance_ly"
    assert anchored["intrinsic_radius_is_hard_filter"] is False
    assert anchored["min_distance_ly_is_hard_filter"] is True
    assert anchored["nearest_first_sort"] == "distance"
    assert anchored["score_sort"] == "development"
    assert anchored["request_radius_default_ly"] == 500
    assert anchored["route_max_radius_setting"] == "MAX_SEARCH_RADIUS"
    assert anchored["route_max_radius_default_ly"] == 10_000
    assert anchored["restricted_radius_cap_ly"] == 500
    assert anchored["restricted_radius_reason"] == (
        "reduce the radius, sort by distance, or remove the filter"
    )


@pytest.mark.parametrize(
    ("field", "mutation"),
    [
        ("archetype_columns", lambda value: {**value, "paradise": {**value["paradise"], "score": "wrong"}}),
        ("archetype_score_floor", lambda value: {**value, "default": 76}),
        (
            "archetype_score_floor",
            lambda value: {**value, "accepted": [60, 76]},
        ),
        ("stored_weighted_key_expression", lambda value: value + " "),
        ("ranking_window", lambda value: {**value, "limit": 9_999}),
        ("ranking_window", lambda value: {**value, "offset_plus_limit_max": 9_999}),
        ("ranking_window", lambda value: {**value, "count_sentinel": 10_002}),
        ("ranking_window", lambda value: {**value, "page_limit_min": 2}),
        ("ranking_window", lambda value: {**value, "page_limit_max": 499}),
        ("ranking_window", lambda value: {**value, "offset_min": 1}),
        ("ranking_window", lambda value: {**value, "offset_max": 9_998}),
        ("ranking_window", lambda value: {**value, "is_truncated_rule": "wrong"}),
        ("ranking_window", lambda value: {**value, "total_rule": "wrong"}),
        ("picked_archetype_rejected_filters", lambda value: value[:-1]),
        (
            "picked_archetype_filter_rejection_reason",
            lambda value: value + ".",
        ),
        ("tie_break", lambda _value: ["distance", "system_id64"]),
    ],
)
def test_each_f2d_ranking_decision_changes_digest(field, mutation):
    changed = deepcopy(PROFILE_SPEC)
    changed[field] = mutation(changed[field])
    assert ranking_sha256(changed) != PROFILE_SPEC["ranking_sha256"]


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("request_bounds", "from_min"), 1),
        (("request_bounds", "size_min"), 2),
        (("request_bounds", "from_plus_size_max"), 9_999),
        (("count", "cap"), 9_999),
        (("count", "sentinel_rule"), "cap"),
        (("count", "total_rule"), "qualifying"),
        (("count", "total_is_capped_rule"), "qualifying >= cap"),
        (("count", "applies_to"), ["galaxy-wide"]),
        (("galaxy_wide_any", "rejected_hard_filters"), []),
        (("galaxy_wide_any", "rejection_rule"), "allow"),
        (("galaxy_wide_any", "reason"), "different reason"),
        (("anchored_any", "intrinsic_radius_key"), "min_distance_ly"),
        (("anchored_any", "intrinsic_radius_is_hard_filter"), True),
        (("anchored_any", "min_distance_ly_is_hard_filter"), False),
        (("anchored_any", "other_filter_rule"), "allow"),
        (("anchored_any", "nearest_first_sort"), "development"),
        (("anchored_any", "score_sort"), "distance"),
        (("anchored_any", "request_radius_default_ly"), 501),
        (("anchored_any", "route_max_radius_setting"), "OTHER_SETTING"),
        (("anchored_any", "route_max_radius_default_ly"), 9_999),
        (
            ("anchored_any", "unfiltered_nearest_first_radius_rule"),
            "capped at 500",
        ),
        (("anchored_any", "restricted_request_rule"), "hard filters only"),
        (("anchored_any", "restricted_radius_cap_ly"), 501),
        (("anchored_any", "restricted_radius_reason"), "different reason"),
    ],
)
def test_each_local_search_contract_element_changes_digest(path, replacement):
    changed = deepcopy(PROFILE_SPEC)
    target = changed["local_search_contract"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    assert ranking_sha256(changed) != PROFILE_SPEC["ranking_sha256"]


def test_profile_is_json_serialisable():
    import json

    json.dumps(PROFILE_SPEC)
