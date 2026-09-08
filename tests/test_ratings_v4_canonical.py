from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.ratings_v4 import opportunities_from_facts, rate_system_facts
from domain.ratings_v4_canonical import (
    adapt_canonical_export, canonical_lineage, load_source_fixture,
)


FIXTURES = Path(__file__).parent / 'fixtures' / 'ratings_v4_sources'


@pytest.fixture(scope='module')
def originals():
    return load_source_fixture(FIXTURES)


@pytest.fixture
def source(originals):
    return deepcopy(originals)


def relation(canonical, name):
    return next(item['rows'] for item in canonical['extras'] if item['relation'] == name)


def body_fact(facts, body):
    return next(item for item in facts[body['system_id64']].bodies
                if item.candidate_id == str(body['body_pk']))


def physical_body(canonical):
    return next(row for row in canonical['bodies'] if row['body_type_id'] == 2)


def admitted_metadata(metadata):
    metadata['generation_id'] = 'test-generation'
    extra = deepcopy({key: metadata[key] for key in ('run', 'artifact', 'source')})
    extra['run']['source_run_id'] = '00000000-0000-0000-0000-000000000002'
    extra['run']['artifact_id'] = extra['artifact']['artifact_id'] = '00000000-0000-0000-0000-000000000003'
    extra['artifact']['content_sha256'] = '\\x' + 'a' * 64
    metadata['generation_inputs'] = [
        {'input': {'generation_id': metadata['generation_id'], 'input_ordinal': ordinal,
                   'source_id': item['run']['source_id'], 'source_run_id': item['run']['source_run_id'],
                   'artifact_id': item['run']['artifact_id'], 'input_role': 'TEST_FIXTURE'},
         **{key: item[key] for key in ('run', 'artifact', 'source')}}
        for ordinal, item in enumerate((metadata, extra))]
    return extra


@pytest.mark.parametrize('table', ['systems', 'bodies', 'rings', 'body_signal_current'])
def test_each_canonical_relation_accepts_admitted_runs_and_preserves_provenance(source, table):
    canonical, metadata, subtypes = source
    extra = admitted_metadata(metadata)
    rows = canonical[table] if table in canonical else relation(canonical, table)
    baseline = adapt_canonical_export(*source)
    for row in rows:
        row['source_run_id'] = extra['run']['source_run_id']
    facts = adapt_canonical_export(*source)
    # Every economy's score and evidence remain unchanged when only lineage changes.
    for identifier, system in facts.items():
        assert {key: value.potential_score for key, value in rate_system_facts(system).items()} == {
            key: value.potential_score for key, value in rate_system_facts(baseline[identifier]).items()}
    serialized = json.dumps({key: asdict(value) for key, value in facts.items()})
    assert extra['run']['source_run_id'] in serialized
    assert 'a' * 64 in serialized
    assert canonical_lineage(*source)['canonical_generation_inputs'] == metadata['generation_inputs']
    rows[0]['source_run_id'] = 'unregistered'
    with pytest.raises(ValueError, match='unregistered source run'):
        adapt_canonical_export(*source)


@pytest.mark.parametrize('fault', ['empty', 'missing_coordinator', 'duplicate_run', 'duplicate_ordinal',
                                 'generation', 'source', 'artifact', 'partial', 'private', 'quarantined',
                                 'hash', 'row_source'])
def test_invalid_admitted_manifests_fail_closed(source, fault):
    canonical, metadata, _ = source
    extra = admitted_metadata(metadata)
    entries = metadata['generation_inputs']
    if fault == 'empty':
        entries.clear()
    elif fault == 'missing_coordinator':
        entries.pop(0)
    elif fault == 'duplicate_run':
        entries.append(deepcopy(entries[1]))
    elif fault == 'duplicate_ordinal':
        entries[1]['input']['input_ordinal'] = 0
    elif fault == 'generation':
        entries[1]['input']['generation_id'] = 'another-generation'
    elif fault in {'source', 'artifact'}:
        entries[1]['input'][fault + '_id'] = 'wrong'
    elif fault == 'partial':
        extra['run']['run_state'] = 'PARTIAL'
    elif fault == 'private':
        extra['run']['trust_zone'] = 'PRIVATE'
    elif fault == 'quarantined':
        extra['artifact']['quarantine_state'] = 'QUARANTINED'
    elif fault == 'hash':
        extra['artifact']['content_sha256'] = 'bad'
    else:
        canonical['bodies'][0]['source_run_id'] = extra['run']['source_run_id']
        canonical['bodies'][0]['source_id'] = -1
    with pytest.raises(ValueError):
        adapt_canonical_export(*source)


def test_admitted_run_without_artifact_keeps_explicit_missing_hash(source):
    canonical, metadata, _ = source
    extra = admitted_metadata(metadata)
    extra['run']['artifact_id'] = None
    metadata['generation_inputs'][1]['artifact'] = None
    metadata['generation_inputs'][1]['input']['artifact_id'] = None
    body = physical_body(canonical)
    body['source_run_id'] = extra['run']['source_run_id']
    adapted = body_fact(adapt_canonical_export(*source), body)
    provenance = json.loads(adapted.feature_provenance['provenance'])
    assert provenance['source_run_id'] == extra['run']['source_run_id']
    assert provenance['artifact_sha256'] is None


def test_lossless_cohort_has_body_scoped_reserves_and_distinct_lineage(originals):
    facts = adapt_canonical_export(*originals)
    bodies = [body for system in facts.values() for body in system.bodies]
    assert len(facts) == 12
    assert len(originals[0]['bodies']) == 389
    assert len(bodies) == 360
    assert all(system.reserve_level is None for system in facts.values())
    assert all(system.body_inventory_complete for system in facts.values())
    assert all(body.reserve_scope == 'body' for body in bodies)
    assert sum(body.reserve_level is not None for body in bodies) == 46
    assert all(body.usable_ground_opportunity is None for body in bodies)
    assert all(body.feature_provenance['provenance'] for body in bodies)
    lineage = canonical_lineage(*originals)
    assert lineage['canonical_artifact_sha256'] == (
        'b4944ab5d7537d7e3c370d55bf92a887bebf36e6db0ba1159c072c7cdf9e9868')
    assert len(lineage['subtype_sources_normalized_sha256']) == 12
    for body in bodies:
        classification = json.loads(body.feature_provenance['body_class'])
        assert classification['field'] == 'subType'
        assert classification['source_normalized_sha256'] in (
            lineage['subtype_sources_normalized_sha256'].values())
        assert classification['canonical_join_provenance'] == body.feature_provenance['provenance']


def test_belts_follow_accepted_extraction_rule_but_keep_their_kind(originals):
    canonical = originals[0]
    rings = relation(canonical, 'rings')
    belt_body_ids = {row['body_pk'] for row in rings if row['kind'] == 'BELT'}
    ring_body_ids = {row['body_pk'] for row in rings if row['kind'] == 'RING'}
    body = next(row for row in canonical['bodies'] if row['body_pk'] in belt_body_ids - ring_body_ids)
    facts = adapt_canonical_export(*originals)
    adapted = body_fact(facts, body)
    assert adapted.rings is True
    assert all(observation['kind'] == 'BELT' for observation in
               json.loads(adapted.feature_provenance['rings'])['observations'])
    extraction = [opportunity for opportunity in opportunities_from_facts(facts[body['system_id64']])
                  if opportunity.candidate_id == adapted.candidate_id and opportunity.economy == 'Extraction']
    assert len(extraction) == 1 and extraction[0].modifier


@pytest.mark.parametrize('complete,expected', [(False, None), (True, False)])
def test_absent_signal_uses_body_coverage_not_full_galaxy_acquisition(source, complete, expected):
    canonical, metadata, subtypes = source
    body = physical_body(canonical)
    body['signals_complete'] = complete
    relation(canonical, 'body_signal_current')[:] = [row for row in relation(canonical, 'body_signal_current')
                                                  if row['body_pk'] != body['body_pk']]
    adapted = body_fact(adapt_canonical_export(canonical, metadata, subtypes), body)
    assert adapted.biologicals is expected
    assert adapted.geologicals is expected


@pytest.mark.parametrize('count,expected', [(0, False), (3, True)])
def test_explicit_signal_observation_survives_incomplete_scan(source, count, expected):
    canonical, metadata, subtypes = source
    body = physical_body(canonical)
    body['signals_complete'] = False
    rows = relation(canonical, 'body_signal_current')
    rows[:] = [row for row in rows if row['body_pk'] != body['body_pk']]
    rows.append({'body_pk': body['body_pk'], 'signal_type_id': 1, 'signal_count': count,
                 'source_run_id': metadata['run']['source_run_id'], 'observed_at': '2026-08-24T00:00:00Z'})
    adapted = body_fact(adapt_canonical_export(canonical, metadata, subtypes), body)
    assert adapted.biologicals is expected
    assert adapted.geologicals is None


def test_missing_inventory_coverage_leaves_ring_absence_and_catalogue_unknown(source):
    canonical, metadata, subtypes = source
    metadata['run']['is_complete_snapshot'] = False
    body = physical_body(canonical)
    relation(canonical, 'rings')[:] = [row for row in relation(canonical, 'rings')
                                     if row['body_pk'] != body['body_pk']]
    facts = adapt_canonical_export(canonical, metadata, subtypes)
    assert facts[body['system_id64']].body_inventory_complete is False
    assert body_fact(facts, body).rings is None


def test_complete_acquisition_does_not_establish_absent_ring_scan_evidence(source):
    canonical, metadata, subtypes = source
    body = physical_body(canonical)
    relation(canonical, 'rings')[:] = [row for row in relation(canonical, 'rings')
                                     if row['body_pk'] != body['body_pk']]
    facts = adapt_canonical_export(canonical, metadata, subtypes)
    assert facts[body['system_id64']].body_inventory_complete is True
    assert body_fact(facts, body).rings is None


def test_missing_subtype_retains_unknown_planet_class(source):
    canonical, metadata, _ = source
    body = physical_body(canonical)
    adapted = body_fact(adapt_canonical_export(canonical, metadata, ()), body)
    assert adapted.body_class == 'planet'
    assert adapted.feature_provenance['body_class'] == adapted.feature_provenance['provenance']


def test_newer_source_changes_only_subtype_and_records_its_hash(source):
    canonical, metadata, subtypes = source
    baseline = adapt_canonical_export(*source)
    source_body = next(row for payload in subtypes for row in payload['system']['bodies']
                       if row.get('reserveLevel') == 'Pristine')
    canonical_body = next(row for row in canonical['bodies'] if row['source_body_id64'] == source_body['id64'])
    source_body.update({'reserveLevel': 'Depleted', 'isLandable': False, 'rings': [],
                        'signals': {}, 'spectralClass': 'H', 'luminosity': 'III'})
    changed = adapt_canonical_export(canonical, metadata, subtypes)
    old, new = body_fact(baseline, canonical_body), body_fact(changed, canonical_body)
    assert old.reserve_level == new.reserve_level == 'pristine'
    assert old.rings == new.rings
    assert old.biologicals == new.biologicals
    assert old.geologicals == new.geologicals
    assert old.spectral_class == new.spectral_class
    assert old.luminosity_class == new.luminosity_class
    assert old.feature_provenance['body_class'] != new.feature_provenance['body_class']


@pytest.mark.parametrize('table', ['systems', 'bodies', 'rings', 'body_signal_current'])
def test_duplicate_canonical_identities_fail_even_when_identical(source, table):
    canonical, metadata, subtypes = source
    rows = canonical[table] if table in canonical else relation(canonical, table)
    rows.append(deepcopy(rows[0]))
    with pytest.raises(ValueError, match='duplicate'):
        adapt_canonical_export(canonical, metadata, subtypes)


def test_duplicate_subtype_system_fails(source):
    canonical, metadata, subtypes = source
    with pytest.raises(ValueError, match='duplicate subtype system'):
        adapt_canonical_export(canonical, metadata, (*subtypes, subtypes[0]))


@pytest.mark.parametrize('mutation', ['duplicate', 'unknown_id', 'wrong_frontier', 'wrong_type'])
def test_ambiguous_subtype_joins_fail(source, mutation):
    canonical, metadata, subtypes = source
    rows = subtypes[0]['system']['bodies']
    if mutation == 'duplicate':
        rows.append(deepcopy(rows[0]))
    elif mutation == 'unknown_id':
        rows[0]['id64'] = 999999999999999999
    elif mutation == 'wrong_frontier':
        rows[0]['bodyId'] = 99999999
    else:
        rows[0]['type'] = 'Planet' if rows[0]['type'] == 'Star' else 'Star'
    with pytest.raises(ValueError, match='duplicate|unmatched|conflicting'):
        adapt_canonical_export(canonical, metadata, subtypes)


@pytest.mark.parametrize('mutation', ['partial_run', 'wrong_artifact', 'wrong_generation', 'wrong_row_run',
                                      'body_count', 'orphan_ring', 'negative_signal', 'invalid_boolean'])
def test_untrusted_or_inconsistent_canonical_evidence_fails(source, mutation):
    canonical, metadata, subtypes = source
    if mutation == 'partial_run':
        metadata['run']['run_state'] = 'PARTIAL'
    elif mutation == 'wrong_artifact':
        metadata['artifact']['artifact_id'] = 'wrong'
    elif mutation == 'wrong_generation':
        canonical['canonical_schema'] = 'v3_gen_other'
    elif mutation == 'wrong_row_run':
        canonical['bodies'][0]['source_run_id'] = 'wrong'
    elif mutation == 'body_count':
        canonical['systems'][0]['loaded_body_count'] += 1
    elif mutation == 'orphan_ring':
        relation(canonical, 'rings')[0]['body_pk'] = 999999999999999999
    elif mutation == 'negative_signal':
        relation(canonical, 'body_signal_current')[0]['signal_count'] = -1
    else:
        physical_body(canonical)['is_landable'] = 'false'
    with pytest.raises(ValueError):
        adapt_canonical_export(canonical, metadata, subtypes)


def test_conflicting_attached_reserves_fail(source):
    canonical, metadata, subtypes = source
    rings = relation(canonical, 'rings')
    observation = next(row for row in rings if row['reserve_type_id'] == 5)
    conflict = deepcopy(observation)
    conflict.update({'ring_pk': 999999999999999999, 'reserve_type_id': 1})
    rings.append(conflict)
    with pytest.raises(ValueError, match='conflicting attached reserve'):
        adapt_canonical_export(canonical, metadata, subtypes)


def test_missing_relation_cannot_silently_become_no_signals(source):
    canonical, metadata, subtypes = source
    canonical['extras'][:] = [row for row in canonical['extras'] if row['relation'] != 'body_signal_current']
    with pytest.raises(ValueError, match='missing canonical relation'):
        adapt_canonical_export(canonical, metadata, subtypes)


def test_real_cohort_ground_unknown_and_canonical_star_luminosity_preserved(originals):
    canonical = originals[0]
    facts = adapt_canonical_export(*originals)
    for row in canonical['bodies']:
        if row['body_type_id'] == 1:
            assert body_fact(facts, row).luminosity_class == row['luminosity_class']
    for system in facts.values():
        rating = rate_system_facts(system)['Refinery']
        if rating.potential_score:
            assert rating.specialisation_quality is None
            assert rating.specialisation_quality_min == 0
            assert rating.specialisation_quality_max > 0


def test_byte_tampering_is_rejected_before_any_fixture_is_used(tmp_path):
    manifest = json.loads((FIXTURES / 'manifest.json').read_bytes())
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    (tmp_path / 'canonical.json').write_bytes(b'{}')
    with pytest.raises(ValueError, match='fixture checksum mismatch'):
        load_source_fixture(tmp_path)
