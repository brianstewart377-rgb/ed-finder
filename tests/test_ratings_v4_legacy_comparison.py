from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('ratings_v4_compare_legacy', ROOT / 'scripts/ratings_v4/compare_legacy.py')
assert SPEC and SPEC.loader
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


def _sources():
    body = {
        'body_pk': 11, 'system_id64': 1, 'source_body_id64': 101, 'is_main_star': True,
        'spectral_class': 'G2', 'is_landable': None, 'is_tidally_locked': None,
        'terraforming_state_id': None, 'signals_complete': False, 'distance_from_arrival_ls': None,
    }
    export = {
        'canonical_schema': 'v3_gen_test',
        'systems': [{'id64': 1, 'name': 'Test', 'loaded_body_count': 1, 'source_body_count': 1}],
        'bodies': [body],
        'extras': [
            {'schema': 'v3_vocab', 'relation': 'signal_type', 'rows': [
                {'signal_type_id': 1, 'public_code': 'saa_signaltype_biological'},
                {'signal_type_id': 2, 'public_code': 'saa_signaltype_geological'}]},
            {'schema': 'v3_vocab', 'relation': 'terraforming_state', 'rows': []},
            {'schema': 'v3_gen_test', 'relation': 'body_signal_current', 'rows': []},
            {'schema': 'v3_gen_test', 'relation': 'rings', 'rows': []},
        ],
    }
    dumps = {1: {'system': {'id64': 1, 'bodies': [{'id64': 101, 'subType': 'G (White-Yellow) Star'}]}}}
    return export, dumps


def test_original_functions_can_load_without_database_or_importer_side_effects(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    legacy = comparison.legacy_functions()
    assert legacy['RATING_VERSION'] == '3.4'
    assert 'psycopg' not in legacy and 'DB_DSN' not in legacy
    scores = {economy: 100 for economy in comparison.ECONOMIES}
    attenuated = legacy['attenuate_economy_scores'](scores)
    assert list(attenuated.values()) == [100, 100, 85, 70, 70, 70, 70]


def test_legacy_source_hash_is_stable_across_git_line_endings(tmp_path):
    source = tmp_path / 'source.py'
    source.write_bytes(b'first\nsecond\n')
    lf_hash = comparison.legacy_source_sha256(source)
    source.write_bytes(b'first\r\nsecond\r\n')
    assert comparison.legacy_source_sha256(source) == lf_hash


def test_unknown_source_values_remain_null_and_legacy_defaults_are_disclosed():
    export, dumps = _sources()
    report = comparison.build_report(export, dumps)
    row = report['systems'][0]
    body = row['bodies'][0]
    assert body['bio_signal_count'] is None
    assert body['is_landable'] is None
    assert body['distance_from_star'] is None
    assert body['has_rings'] is None
    assert row['legacy_default_counts']['bio_signal_count'] == 1
    assert row['v3_4']['counts']['bio'] == 0
    assert report['historical_production_scores'] is False


def test_numerical_signal_counts_and_explicit_known_absence_are_not_booleanized():
    export, dumps = _sources()
    export['bodies'][0]['signals_complete'] = True
    export['extras'][2]['rows'] = [{'body_pk': 11, 'signal_type_id': 2, 'signal_count': 24}]
    row = comparison.canonical_legacy_inputs(export, dumps)[0]
    assert row['bodies'][0]['geo_signal_count'] == 24
    assert row['bodies'][0]['bio_signal_count'] == 0
    assert not any(gap['field'].endswith('signal_count') for gap in row['legacy_defaulted_inputs'])


def test_belts_do_not_become_legacy_ring_rows():
    export, dumps = _sources()
    export['extras'][3]['rows'] = [{'body_pk': 11, 'system_id64': 1, 'kind': 'BELT'}]
    assert comparison.canonical_legacy_inputs(export, dumps)[0]['bodies'][0]['has_rings'] is None
    export['extras'][3]['rows'][0]['kind'] = 'RING'
    assert comparison.canonical_legacy_inputs(export, dumps)[0]['bodies'][0]['has_rings'] is True


@pytest.mark.parametrize('mutation', ['system', 'body', 'ring_owner', 'duplicate_signal'])
def test_source_identity_failures_are_rejected(mutation):
    export, dumps = _sources()
    if mutation == 'system':
        dumps[1]['system']['id64'] = 2
    elif mutation == 'body':
        dumps[1]['system']['bodies'][0]['id64'] = 999
    elif mutation == 'ring_owner':
        export['extras'][3]['rows'] = [{'body_pk': 11, 'system_id64': 2, 'kind': 'RING'}]
    else:
        signal = {'body_pk': 11, 'signal_type_id': 2, 'signal_count': 24}
        export['extras'][2]['rows'] = [signal, signal]
    with pytest.raises(ValueError):
        comparison.canonical_legacy_inputs(export, dumps)


def test_legacy_seven_economies_do_not_depend_on_fabricated_arrival_distances():
    bodies = [{'subtype': 'Earth-like world', 'is_terraformable': True, 'distance_from_star': None},
              {'subtype': 'Rocky body', 'is_landable': True, 'geo_signal_count': 24}]
    original = comparison.recompute_legacy(bodies, 'G')
    remote = deepcopy(bodies)
    for body in remote:
        body['distance_from_star'] = 999999
    moved = comparison.recompute_legacy(remote, 'G')
    assert original['pre_attenuation'] == moved['pre_attenuation']
    assert original['post_attenuation'] == moved['post_attenuation']
    assert original['counts']['tf_quality_acc'] != moved['counts']['tf_quality_acc']


def test_comparison_exposes_reversal_and_unknown_without_certifying_acceptance():
    old = {economy: 0 for economy in comparison.ECONOMIES}
    old.update(Agriculture=75, Tourism=100)
    current = dict(old, Agriculture=100, Tourism=75, Refinery=None)
    result = comparison.compare_scores({'post_attenuation': old}, current)
    assert result['major_deltas_for_review'] == ['Agriculture', 'Tourism']
    assert result['delta_from_v3_4_post_attenuation']['Refinery'] is None
    assert result['ordering_reversals_for_review'] == [
        {'economies': ['Agriculture', 'Tourism'], 'v3_4_gap': -25, 'v4_gap': 25}]
    assert result['review_status'] == 'requires_mechanics_review'


def test_reviewed_cohort_replays_exact_sources_and_covers_all_flagged_changes():
    sys.path.insert(0, str(ROOT / 'apps/api/src'))
    from domain.ratings_v4 import rate_system_facts
    from domain.ratings_v4_canonical import adapt_canonical_export, load_source_fixture

    canonical, metadata, sources = load_source_fixture(ROOT / 'tests/fixtures/ratings_v4_sources')
    facts = adapt_canonical_export(canonical, metadata, sources)
    scores = {str(system_id): {economy: rating.potential_score
                              for economy, rating in rate_system_facts(system).items()}
              for system_id, system in facts.items()}
    report = comparison.build_report(canonical, {source['system']['id64']: source for source in sources}, scores)
    reviewed = json.loads((ROOT / 'tests/fixtures/ratings_v4_legacy_comparison.json').read_text(encoding='utf-8'))
    assert reviewed['legacy_scorer_sha256'] == comparison.legacy_source_sha256()
    assert reviewed['legacy_scorer_hash_normalization'] == 'utf-8-lf'
    assert reviewed['historical_production_scores'] is False
    reviewed_rows = {row['system_id64']: row for row in reviewed['systems']}
    assert len(reviewed_rows) == len(report['systems']) == 12
    for row in report['systems']:
        accepted = reviewed_rows[row['system_id64']]
        assert accepted['name'] == row['name']
        assert accepted['v3_4_pre_attenuation'] == row['v3_4']['pre_attenuation']
        assert accepted['v3_4_post_attenuation'] == row['v3_4']['post_attenuation']
        assert accepted['v4_potential_score'] == row['comparison']['v4_potential_scores']
        assert accepted['delta'] == row['comparison']['delta_from_v3_4_post_attenuation']
        assert [flag['economy'] for flag in accepted['major_deltas']] == row['comparison']['major_deltas_for_review']
        assert [{key: flag[key] for key in ('economies', 'v3_4_gap', 'v4_gap')}
                for flag in accepted['ordering_reversals']] == row['comparison']['ordering_reversals_for_review']
        for flag in accepted['major_deltas'] + accepted['ordering_reversals']:
            assert flag['status'] == 'explained'
            assert flag['reason_codes']
            assert set(flag['reason_codes']) <= reviewed['reason_definitions'].keys()
    assert reviewed['review_counts'] == {
        'systems': 12, 'economy_pairs': 84, 'major_deltas': 44,
        'ordering_reversals': 73, 'unexplained_flags': 0,
    }
