"""F3 slice 2: pure (no DB) tests for `edfinder_api.ranking.rerank`.

The rerank blend is deliberately outside the hashed ranking-profile identity
(its weights are per request), so this module also pins that adding it left
`ranking_sha256` untouched -- the deployed-image attestation in
`deploy/v3-production/target-authority.json` is keyed on that digest.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import get_args

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from edfinder_api.models import ArchetypeKey  # noqa: E402
from edfinder_api.ranking.profile import (  # noqa: E402
    ARCHETYPE_KEYS,
    PROFILE_SPEC,
    ranking_sha256,
)
from edfinder_api.ranking.rerank import (  # noqa: E402
    RERANK_ID_LIMIT,
    WEIGHTED_E4_SCALE,
    archetype_entry,
    build_system_archetype_detail_query,
    equal_weights,
    rerank_rows,
    single_archetype_weights,
    tier_for,
    validate_id64s,
    validate_weights,
)


def _row(system_id64: int, **overrides):
    """A wide row shaped like `v3_app.system_archetype`, all fits at zero."""
    row = {'system_id64': system_id64, 'primary_archetype': 'flexible',
           'secondary_archetype': None, 'best_colony_potential': 0,
           'completeness_ppm': 1_000_000}
    for key in ARCHETYPE_KEYS:
        row[f'{key}_score'] = 0
        row[f'{key}_tier'] = 'D'
        row[f'{key}_confidence_ppm'] = 1_000_000
        row[f'{key}_weighted_e4'] = 0
    row.update(overrides)
    return row


def test_rerank_module_does_not_change_the_hashed_profile_identity():
    assert ranking_sha256() == PROFILE_SPEC['ranking_sha256']
    assert 'rerank' not in json.dumps(PROFILE_SPEC)
    target_authority = json.loads(
        (ROOT / 'deploy/v3-production/target-authority.json').read_text()
    )
    attested = target_authority['accepted_release_schema_compatibility']['ranking_sha256']
    assert ranking_sha256() == attested


def test_models_archetype_key_literal_matches_profile_keys():
    assert get_args(ArchetypeKey) == ARCHETYPE_KEYS


def test_tier_thresholds_match_profile_contract():
    assert [tier_for(s) for s in (100, 88, 87, 76, 75, 60, 59, 45, 44, 0)] == [
        'S', 'S', 'A', 'A', 'B', 'B', 'C', 'C', 'D', 'D',
    ]


def test_weight_helpers_cover_every_key_exactly():
    equal = equal_weights()
    assert set(equal) == set(ARCHETYPE_KEYS)
    assert sum(equal.values()) == pytest.approx(1.0)
    single = single_archetype_weights('mining_hub')
    assert single['mining_hub'] == 1.0
    assert sum(single.values()) == 1.0
    with pytest.raises(ValueError):
        single_archetype_weights('refinery_industrial')


@pytest.mark.parametrize('bad', (
    {},                                                    # missing keys
    {**equal_weights(), 'purity': 0.5},                    # legacy dimension
    {key: 0.0 for key in ARCHETYPE_KEYS},                  # all zero
    {**equal_weights(), 'paradise': 1.5},                  # out of range
    {**equal_weights(), 'paradise': -0.1},
    {**equal_weights(), 'paradise': float('nan')},
))
def test_validate_weights_rejects_bad_blends(bad):
    with pytest.raises(ValueError):
        validate_weights(bad)


def test_validate_id64s_dedupes_preserves_order_and_bounds():
    assert validate_id64s([3, 1, 3, 2]) == [3, 1, 2]
    with pytest.raises(ValueError):
        validate_id64s([])
    with pytest.raises(ValueError):
        validate_id64s([-1])
    with pytest.raises(ValueError):
        validate_id64s([2**63])
    with pytest.raises(ValueError):
        validate_id64s(list(range(RERANK_ID_LIMIT + 1)))
    assert len(validate_id64s(list(range(RERANK_ID_LIMIT)))) == RERANK_ID_LIMIT


def test_detail_query_is_parameterized_and_reads_only_v3_views():
    sql, params = build_system_archetype_detail_query(PROFILE_SPEC, id64s=[7, 7, 9])
    assert params == [[7, 9]]
    assert 'v3_app.system_search' in sql and 'v3_app.system_archetype' in sql
    assert '$1::bigint[]' in sql
    lowered = sql.lower()
    for term in ('system_archetype_scores', 'system_archetype_traits',
                 'mv_archetype_rankings', ' from systems ', 'public.'):
        assert term not in lowered
    # No literal values leak into the statement.
    assert '7' not in sql and '9' not in sql
    for key in ARCHETYPE_KEYS:
        for suffix in ('_score', '_tier', '_weighted_e4', '_confidence_ppm'):
            assert f'a.{key}{suffix}' in sql
    with pytest.raises(ValueError):
        build_system_archetype_detail_query(
            {**PROFILE_SPEC, 'archetype_columns': {}}, id64s=[1],
        )


def test_archetype_entry_reads_stored_values_verbatim():
    row = _row(1, paradise_score=91, paradise_tier='S',
               paradise_confidence_ppm=750_000, paradise_weighted_e4=682_500)
    assert archetype_entry(row, 'paradise') == {
        'score': 91, 'tier': 'S', 'confidence': 0.75, 'weighted_e4': 682_500,
    }


def test_rerank_orders_by_weighted_blend_then_id64():
    # weighted_e4 = score * confidence * completeness (e4 units). System 20 has
    # the higher raw paradise score but thin evidence; 10 is better observed.
    rows = [
        _row(20, paradise_score=90, paradise_weighted_e4=450_000,
             paradise_confidence_ppm=500_000, completeness_ppm=1_000_000,
             best_colony_potential=90),
        _row(10, paradise_score=80, paradise_weighted_e4=800_000,
             paradise_confidence_ppm=1_000_000, best_colony_potential=80),
        _row(30, paradise_score=80, paradise_weighted_e4=800_000,
             paradise_confidence_ppm=1_000_000, best_colony_potential=80),
    ]
    out = rerank_rows(rows, weights=single_archetype_weights('paradise'),
                      picked_archetype='paradise')
    assert [r['id64'] for r in out] == [10, 30, 20]       # ties -> id64 ASC
    assert out[0]['reranked_score'] == 800_000 // WEIGHTED_E4_SCALE == 80
    assert out[2]['reranked_score'] == 45
    assert out[0]['tier'] == 'A' and out[2]['tier'] == 'C'
    assert out[2]['original_score'] == 90.0             # raw picked score, not the blend
    assert out[2]['confidence'] == 0.5
    assert out[0]['completeness'] == 1.0


def test_rerank_blend_is_normalised_by_weight_sum_and_ignores_zero_weights():
    row = _row(1, paradise_weighted_e4=1_000_000, mining_hub_weighted_e4=0,
               mining_hub_confidence_ppm=0, best_colony_potential=55)
    half = rerank_rows([row], weights={**{k: 0.0 for k in ARCHETYPE_KEYS},
                                       'paradise': 0.2, 'mining_hub': 0.2},
                       picked_archetype=None)[0]
    assert half['reranked_score'] == 50                    # (1e6*0.2 + 0*0.2) / 0.4 / 1e4
    assert half['confidence'] == 0.5
    assert half['original_score'] == 55.0                  # no pick -> best_colony_potential
    only = rerank_rows([row], weights=single_archetype_weights('paradise'),
                       picked_archetype=None)[0]
    assert only['reranked_score'] == 100


def test_rerank_rejects_unknown_pick_and_bad_weights():
    with pytest.raises(ValueError):
        rerank_rows([_row(1)], weights=equal_weights(), picked_archetype='trade_logistics')
    with pytest.raises(ValueError):
        rerank_rows([_row(1)], weights={k: 0.0 for k in ARCHETYPE_KEYS}, picked_archetype=None)
