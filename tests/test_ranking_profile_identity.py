"""F2c Task 1: identity + drift-guard tests for the V3 ranking profile.

Pure, DB-free — the profile module must not touch a database or emit SQL.
See docs/superpowers/plans/2026-09-27-v3-finder-f2c-f3-ranking.md (Task 1).
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from edfinder_api.ranking.profile import (  # noqa: E402
    RANKING_VERSION,
    PROFILE_SPEC,
    RANKING_VERSIONS,
    ranking_sha256,
    resolve,
)


def test_version_and_registry():
    assert RANKING_VERSION == "v3-colony-potential-1"
    assert RANKING_VERSION in RANKING_VERSIONS
    assert resolve(RANKING_VERSION) is PROFILE_SPEC


def test_unknown_version_raises():
    try:
        resolve("does-not-exist")
    except KeyError:
        pass
    else:
        raise AssertionError("resolve() should raise KeyError for an unknown version")


def test_ranking_sha_is_stable_and_matches_recorded():
    # the recorded sha in the spec must equal the sha recomputed from the live spec
    assert ranking_sha256() == PROFILE_SPEC["ranking_sha256"]
    # stable across repeated calls (deterministic canonicalisation)
    assert ranking_sha256() == ranking_sha256()


def test_tier_thresholds_match_projection_contract():
    assert PROFILE_SPEC["tier_thresholds"] == {"S": 88, "A": 76, "B": 60, "C": 45}


def test_tie_break_is_distance_then_system_id64():
    assert PROFILE_SPEC["tie_break"] == ["distance", "system_id64"]


def test_primary_score_rule_covers_archetype_economy_and_none():
    rule = PROFILE_SPEC["primary_score_rule"]
    assert set(rule) == {"archetype", "economy", "none"}
    assert "archetype_score" in rule["archetype"]
    assert "potential_score" in rule["economy"]
    assert "best_colony_potential" in rule["none"]


def test_uncertainty_factor_is_confidence_times_completeness():
    uncertainty = PROFILE_SPEC["uncertainty"]
    assert "confidence" in uncertainty["factor_expr"]
    assert "completeness" in uncertainty["factor_expr"]
    assert uncertainty["confidence_range"] == [0.0, 1.0]
    assert uncertainty["completeness_range"] == [0.0, 1.0]


def test_hard_filter_keys_present():
    keys = PROFILE_SPEC["hard_filter_keys"]
    for expected in (
        "elw_count_min",
        "terraformable_count_min",
        "has_rings",
        "min_development_score",
        "max_distance_ly",
        "galaxy_region",
    ):
        assert expected in keys


def test_archetype_keys_are_the_eight_v3_native_archetypes():
    assert set(PROFILE_SPEC["archetype_keys"]) == {
        "paradise",
        "mining_hub",
        "manufacturing_hub",
        "megacomplex",
        "research_hub",
        "stronghold",
        "population_capital",
        "flexible",
    }


def test_spec_is_json_serialisable():
    import json

    json.dumps(PROFILE_SPEC)


def test_mutated_spec_hash_differs_from_recorded():
    # Drift guard: hashing an arbitrary spec that differs from the recorded
    # one must not collide with the recorded sha. This proves the guard
    # would actually catch a silent definition change, not just echo itself.
    mutated = dict(PROFILE_SPEC)
    mutated["tier_thresholds"] = {**PROFILE_SPEC["tier_thresholds"], "S": 99}
    assert ranking_sha256(mutated) != PROFILE_SPEC["ranking_sha256"]


def test_mutated_uncertainty_hash_differs_from_recorded():
    mutated = dict(PROFILE_SPEC)
    mutated["uncertainty"] = {**PROFILE_SPEC["uncertainty"], "confidence_range": [0.0, 2.0]}
    assert ranking_sha256(mutated) != PROFILE_SPEC["ranking_sha256"]
