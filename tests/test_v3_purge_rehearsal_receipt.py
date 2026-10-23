"""Sealed disposable measurements are plan inputs only after scale/crash gates."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('rehearsal_receipt_test', ROOT / 'scripts/operator/lib/v3_purge_rehearsal_receipt.py')
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)


def example_receipt(**updates):
    raw = {'deleted_rows': 100_000, 'delete_seconds': 10.0, 'batch_limit': 1000,
           'batch_peak_bytes': 101, 'rewrite_seconds': 2.0, 'rewrite_peak_bytes': 201,
           'heap_index_bytes': 1000}
    proportion = 0.01
    counts = tool.expected_row_counts(proportion)
    per_relation = {}
    for relation in tool.RELATIONS:
        measured = dict(raw)
        measured['deleted_rows'] = sum(counts[relation][key] for key in ('ratings_v4_prod_p4', 'ratings_v4_prod_p4_opt1'))
        measured['delete_seconds'] = measured['deleted_rows'] / 10_000
        per_relation[relation] = tool.relation_figures(measured, proportion)
    per_relation['system_search']['survivor_target_split'] = tool.search_split_figures(
        example_split(per_relation['system_search']['raw'], counts), proportion)
    body = {'schema_version': tool.SCHEMA, 'operation': 'v3-derived-purge-rehearsal',
            **tool.code_identity(),
            'status': 'success', 'source_git_sha': 'a' * 40, 'scale': 'one_percent',
            'production_proportion': proportion,
            'image_digest': 'postgres:18@sha256:' + 'b' * 64,
            'settings': {'autovacuum': 'on', 'archive_mode': 'off', 'wal_level': 'replica'},
            'row_counts': counts, 'survivor_products': tool.expected_survivor_products(proportion),
            'per_relation': per_relation, 'cleanup_verified': True, 'failures': [],
            'crash_scenarios': {name: {'passed': True} for name in tool.CRASH_SCENARIOS},
            'gate_10_crash_rehearsal_passed': True,
            'lifecycle_receipt_sha256': hashlib.sha256(tool.LIFECYCLE_RECEIPT.read_bytes()).hexdigest()}
    body.update(updates)
    return tool._evidence().seal(body)


def example_split(raw, counts, **updates):
    """Measured survivor/target Search figures consistent with the relation raw."""
    survivors = counts['system_search']['ratings_v4_prod_p4_parallel_v1']
    split = dict(survivor_rows=survivors, target_rows=raw['deleted_rows'],
                 heap_index_bytes_before_delete=raw['heap_index_bytes'],
                 survivor_heap_index_bytes_after_rewrite=survivors * 555,
                 governed_rewrite_seconds=raw['rewrite_seconds'], governed_rewrite_peak_bytes=raw['rewrite_peak_bytes'],
                 survivor_rewrite_seconds=1.5, survivor_rewrite_peak_bytes=150,
                 target_delete_seconds=raw['delete_seconds'])
    split.update(updates)
    return split


def write_receipt(tmp_path, value):
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(value))
    return path


def test_math_scales_relation_work_but_preserves_batch_reservation_and_rate():
    value = example_receipt()
    measured = value['per_relation']['system_search']
    assert measured['production'] == {
        'rows_per_second': 10_000.0, 'rewrite_allowance_seconds': 400,
        'batch_limit': 1000, 'batch_peak_bytes': 101, 'rewrite_peak_bytes': 20100,
        'statement_timeout_ms': 400_000, 'autovacuum_budget_bytes': 150_000,
        'autovacuum_budget_source': 'heap_plus_index_lower_bound'}
    assert measured['margin_applied'] == {
        'batch_peak_bytes': 152, 'rewrite_peak_bytes': 30150, 'autovacuum_budget_bytes': 150_000}
    assert tool.validate(value) is value


def test_valid_reviewed_receipt_authenticates_and_binds_plan_without_double_margin(tmp_path):
    value = example_receipt()
    loaded = tool.load_reviewed(write_receipt(tmp_path, value), value['content_sha256'])
    plan = {'snapshot': {'retained': 'preserved'}, 'delete': {'stale': 'replaced'}}
    assert tool.apply_to_plan(plan, loaded) is plan
    for relation in tool.RELATIONS:
        assert plan['delete'][relation]['batch_peak_bytes'] == 101
        assert plan['delete'][relation]['rows_per_second_source'] == 'reviewed_rehearsal:' + value['content_sha256']
        assert plan['rewrite'][relation] == {'rewrite_peak_bytes': 20100, 'statement_timeout_ms': 400_000}
    assert plan['snapshot'] == {'retained': 'preserved'}
    assert plan['rehearsal']['gate_10_crash_rehearsal_passed'] is True
    for field, identity in tool.code_identity().items():
        assert plan['rehearsal'][field] == identity


def test_receipt_records_the_exact_action_script_identity():
    from scripts.operator.lib import v3_generation_purge as controller
    assert tool.code_identity()['script_sha256'] == controller.script_identity()
    assert tool.code_identity()['migration_set_identity'] == controller.schema_identity.migration_set_identity(
        controller.schema_identity.derive_entries())


@pytest.mark.parametrize('field', ('script_sha256', 'rehearsal_script_sha256', 'migration_set_identity'))
def test_reviewed_receipt_refuses_changed_executed_code_or_migrations(tmp_path, field):
    stale = ('sha256:' if field == 'migration_set_identity' else '') + '0' * 64
    value = example_receipt(**{field: stale})
    with pytest.raises(ValueError, match='rehearsal_' + field + '_mismatch'):
        tool.load_reviewed(write_receipt(tmp_path, value), value['content_sha256'])
    with pytest.raises(ValueError, match='rehearsal_' + field + '_mismatch'):
        tool.apply_to_plan({}, value)


@pytest.mark.parametrize('relative', tool.HARNESS_FILES)
def test_harness_identity_covers_every_executed_harness_file(monkeypatch, relative):
    before = tool.code_identity()
    original = Path.read_bytes
    def read_bytes(path):
        data = original(path)
        return data + b'\n# changed executed harness' if path == tool.ROOT / relative else data
    monkeypatch.setattr(Path, 'read_bytes', read_bytes)
    after = tool.code_identity()
    assert before['script_sha256'] == after['script_sha256']
    assert before['migration_set_identity'] == after['migration_set_identity']
    assert before['rehearsal_script_sha256'] != after['rehearsal_script_sha256']


@pytest.mark.parametrize('scale', ('smoke', 'tiny'))
def test_smoke_is_evidence_but_never_production_authority(tmp_path, scale):
    value = example_receipt(scale=scale)
    assert tool.validate(value, production=False) is value
    with pytest.raises(ValueError, match='production_scale_required'):
        tool.load_reviewed(write_receipt(tmp_path, value), value['content_sha256'])


def test_false_crash_gate_is_never_production_authority(tmp_path):
    value = example_receipt(gate_10_crash_rehearsal_passed=False, crash_scenarios={})
    assert tool.validate(value, production=False) is value
    with pytest.raises(ValueError, match='crash_gate_not_passed'):
        tool.load_reviewed(write_receipt(tmp_path, value), value['content_sha256'])


@pytest.mark.parametrize('scenario', tool.CRASH_SCENARIOS)
def test_all_crash_scenarios_required_even_if_top_gate_claims_success(scenario):
    value = example_receipt()
    value['crash_scenarios'][scenario]['passed'] = False
    with pytest.raises(ValueError, match='crash_scenarios_incomplete'):
        tool.validate(value)


def test_gate_10_requires_verification_transaction_failure_in_addition_to_old_scenarios():
    value = example_receipt()
    del value['crash_scenarios']['rewrite_verified_transaction_failure']
    with pytest.raises(ValueError, match='crash_scenarios_incomplete'):
        tool.validate(value)


def test_seal_binds_measurements_and_explicit_reviewed_digest(tmp_path):
    value = example_receipt()
    path = write_receipt(tmp_path, value)
    with pytest.raises(ValueError, match='expected_sha256_mismatch'):
        tool.load_reviewed(path, 'c' * 64)
    value['per_relation']['system_search']['raw']['batch_peak_bytes'] += 1
    write_receipt(tmp_path, value)
    with pytest.raises(ValueError, match='seal_invalid'):
        tool.load_reviewed(path, value['content_sha256'])


def test_apply_refuses_an_unsealed_in_memory_receipt():
    value = example_receipt()
    value['source_git_sha'] = 'c' * 40
    with pytest.raises(ValueError, match='seal_invalid'):
        tool.apply_to_plan({}, value)


@pytest.mark.parametrize(('field', 'invalid'), (
    ('deleted_rows', 0), ('deleted_rows', True), ('batch_limit', 100001),
    ('delete_seconds', float('nan')), ('rewrite_seconds', float('inf')),
    ('rewrite_seconds', 0), ('batch_peak_bytes', -1), ('batch_peak_bytes', 1_000_000_000),
    ('heap_index_bytes', 0), ('rewrite_peak_bytes', True),
))
def test_invalid_measurements_refused(field, invalid):
    raw = deepcopy(example_receipt()['per_relation']['system_search']['raw'])
    raw[field] = invalid
    with pytest.raises(ValueError, match='rehearsal_'):
        tool.relation_figures(raw, .01)


@pytest.mark.parametrize(('field', 'invalid'), (
    ('schema_version', 'different'), ('source_git_sha', 'main'),
    ('script_sha256', None), ('rehearsal_script_sha256', 'missing'),
    ('migration_set_identity', '0' * 64),
    ('image_digest', 'postgres:18'), ('settings', {'autovacuum': 'off'}),
    ('production_proportion', .0005), ('lifecycle_receipt_sha256', 'd' * 64),
    ('row_counts', {}), ('per_relation', {}), ('gate_10_crash_rehearsal_passed', 1),
))
def test_schema_identity_and_proportion_binding_refuse(field, invalid):
    value = example_receipt(**{field: invalid})
    with pytest.raises(ValueError, match='rehearsal_'):
        tool.validate(value)


def test_margin_and_scaled_figures_cannot_be_edited_without_matching_raw_math():
    value = example_receipt()
    value['per_relation']['system_search']['production']['batch_peak_bytes'] = 152
    with pytest.raises(ValueError, match='derived_figures_mismatch'):
        tool.validate(value)


def test_real_plan_consumes_validated_receipt_before_database_sealing(monkeypatch):
    from tests.test_v3_derived_generation_purge_operator import _action_tool, _successful_phase
    module = _action_tool()
    report, runtime, _plan, _calls = _successful_phase(module, monkeypatch, 'plan')
    value = example_receipt()
    module.execute('plan', runtime, report, rehearsal=value)
    reviewed = report['reviewed_plan']
    assert reviewed['delete']['system_search']['rows_per_second'] == 10_000
    assert reviewed['rewrite']['body_mechanics']['statement_timeout_ms'] == 400_000
    assert report['rehearsal_receipt_sha256'] == value['content_sha256']


@pytest.mark.parametrize('arguments', (
    ['plan', '--rehearsal-receipt=missing'],
    ['plan', '--rehearsal-receipt-sha256=' + 'f' * 64],
    ['status', '--rehearsal-receipt=missing', '--rehearsal-receipt-sha256=' + 'f' * 64],
    ['authorize', '--rehearsal-receipt=missing', '--rehearsal-receipt-sha256=' + 'f' * 64],
))
def test_cli_receipt_pair_is_plan_only_and_refused_before_runtime(monkeypatch, capsys, arguments):
    from tests.test_v3_derived_generation_purge_operator import _action_tool
    module = _action_tool()
    monkeypatch.setattr(module, 'Runtime', lambda *_: pytest.fail('must refuse before runtime'))
    assert module.main(arguments) == 1
    assert 'rehearsal_arguments_not_admitted_for_mode' in json.loads(capsys.readouterr().out)['failures']


def test_cli_loads_reviewed_receipt_then_passes_it_to_real_plan_dispatch(monkeypatch, tmp_path, capsys):
    from tests.test_v3_derived_generation_purge_operator import _action_tool
    module = _action_tool()
    value = example_receipt()
    path = write_receipt(tmp_path, value)
    calls = []
    class Runtime:
        def __init__(self, report):
            calls.append('runtime')
        def guard(self):
            calls.append('guard')
    def execute(mode, runtime, report, **kwargs):
        assert mode == 'plan'
        assert kwargs['rehearsal'] == value
        report['status'] = 'success'
        calls.append('execute')
    monkeypatch.setattr(module, 'Runtime', Runtime)
    monkeypatch.setattr(module, 'execute', execute)
    assert module.main(['plan', '--rehearsal-receipt=' + str(path),
                        '--rehearsal-receipt-sha256=' + value['content_sha256']]) == 0
    assert calls == ['runtime', 'guard', 'execute']
    assert json.loads(capsys.readouterr().out)['status'] == 'success'


def test_cli_invalid_seal_refuses_before_any_host_or_database_access(monkeypatch, tmp_path, capsys):
    from tests.test_v3_derived_generation_purge_operator import _action_tool
    module = _action_tool()
    value = example_receipt()
    value['settings']['autovacuum'] = 'off'
    path = write_receipt(tmp_path, value)
    monkeypatch.setattr(module, 'Runtime', lambda *_: pytest.fail('must authenticate before runtime'))
    assert module.main(['plan', '--rehearsal-receipt=' + str(path),
                        '--rehearsal-receipt-sha256=' + value['content_sha256']]) == 1
    assert json.loads(capsys.readouterr().out)['failures'] == ['rehearsal_seal_invalid']


@pytest.mark.parametrize('field', ('script_sha256', 'rehearsal_script_sha256', 'migration_set_identity'))
def test_cli_stale_rehearsal_refuses_before_any_host_or_database_access(monkeypatch, tmp_path, capsys, field):
    from tests.test_v3_derived_generation_purge_operator import _action_tool
    module = _action_tool()
    stale = ('sha256:' if field == 'migration_set_identity' else '') + '0' * 64
    value = example_receipt(**{field: stale})
    path = write_receipt(tmp_path, value)
    monkeypatch.setattr(module, 'Runtime', lambda *_: pytest.fail('must bind identities before runtime'))
    assert module.main(['plan', '--rehearsal-receipt=' + str(path),
                        '--rehearsal-receipt-sha256=' + value['content_sha256']]) == 1
    assert json.loads(capsys.readouterr().out)['failures'] == ['rehearsal_' + field + '_mismatch']


def test_counts_must_match_committed_receipt_proportions():
    value = example_receipt()
    value['row_counts']['system_search']['ratings_v4_prod_p4_opt1'] += 1
    with pytest.raises(ValueError, match='row_counts_proportion_mismatch'):
        tool.validate(value)


def test_actual_deleted_counts_must_match_seeded_targets():
    value = example_receipt()
    value['per_relation']['body_mechanics']['raw']['deleted_rows'] += 1
    with pytest.raises(ValueError, match='deleted_rows_mismatch'):
        tool.validate(value)


def test_cleanup_must_be_verified_before_production_import():
    value = example_receipt(cleanup_verified=False)
    with pytest.raises(ValueError, match='cleanup_not_verified'):
        tool.validate(value)


@pytest.mark.parametrize('raw', (None, [], 'unknown'))
def test_malformed_raw_measurements_refuse_with_finite_validation_error(raw):
    value = example_receipt()
    value['per_relation']['system_search']['raw'] = raw
    with pytest.raises(ValueError, match='measurement_invalid'):
        tool.validate(value)


def _bound_plan():
    value = example_receipt()
    plan = {'snapshot': {}, 'delete': {}}
    tool.apply_to_plan(plan, value)
    return plan


def test_plan_binding_accepts_exactly_the_applied_one_percent_figures():
    plan = _bound_plan()
    assert tool.require_plan_binding(plan) is plan['rehearsal']


@pytest.mark.parametrize('mutation', (
    'no_binding', 'smoke_scale', 'crash_gate_false', 'digest_invalid',
    'fallback_throughput', 'missing_relation', 'missing_allowance', 'missing_rewrite_peak',
    'missing_rewrite_section',
))
def test_plan_binding_refuses_a_plan_that_could_authorize_but_never_delete(mutation):
    plan = _bound_plan()
    if mutation == 'no_binding':
        del plan['rehearsal']
    elif mutation == 'smoke_scale':
        plan['rehearsal']['scale'] = 'smoke'
    elif mutation == 'crash_gate_false':
        plan['rehearsal']['gate_10_crash_rehearsal_passed'] = False
    elif mutation == 'digest_invalid':
        plan['rehearsal']['content_sha256'] = 'F' * 64
    elif mutation == 'fallback_throughput':
        plan['delete']['body_mechanics']['rows_per_second_source'] = 'conservative_fallback'
    elif mutation == 'missing_relation':
        del plan['delete']['system_rating_vector']
    elif mutation == 'missing_allowance':
        del plan['delete']['system_search']['rewrite_allowance_seconds']
    elif mutation == 'missing_rewrite_peak':
        del plan['rewrite']['economy_opportunity']['rewrite_peak_bytes']
    else:
        del plan['rewrite']
    with pytest.raises(ValueError, match='plan_rehearsal_figures_required'):
        tool.require_plan_binding(plan)


# Post-go-live survivor Search population (ROADMAP step P reopened gate 1).

def test_expected_counts_include_published_survivor_search_and_archetype_rows():
    proportion = 2_000_000 / 198_528_286
    counts = tool.expected_row_counts(proportion)
    assert counts['system_search'] == {'ratings_v4_prod_p4': 0, 'ratings_v4_prod_p4_opt1': 2_000_000,
                                       'ratings_v4_prod_p4_parallel_v1': 2_000_000}
    assert tool.expected_survivor_products(proportion) == {'system_search': 2_000_000,
                                                           'system_archetype': 2_000_000}
    # Every other relation is still bound to the committed receipt unchanged.
    assert counts['system_rating_vector']['ratings_v4_prod_p4_parallel_v1'] == 2_000_000


def test_search_split_separates_survivor_and_target_work_and_extrapolates_admission():
    value = example_receipt()
    split = value['per_relation']['system_search']['survivor_target_split']
    proportion = value['production_proportion']
    survivors = value['row_counts']['system_search']['ratings_v4_prod_p4_parallel_v1']
    assert split['survivor'] == {'rows': survivors, 'heap_index_bytes': survivors * 555,
                                 'bytes_per_row': 555.0, 'rewrite_seconds': 1.5, 'rewrite_peak_bytes': 150}
    assert split['target']['rows'] == value['per_relation']['system_search']['raw']['deleted_rows']
    assert split['target']['rewrite_seconds'] == 0.5
    assert split['target']['rewrite_peak_bytes'] == 51
    production = split['production']
    assert production['survivor_rows'] == round(survivors / proportion)
    assert production['rewrite_peak_bytes'] == value['per_relation']['system_search']['production']['rewrite_peak_bytes']
    assert production['rewrite_peak_margin_bytes'] == tool.margin_bytes(production['rewrite_peak_bytes'])
    assert production['required_free_bytes_before_rewrite'] == 100_000_000_000 + production['rewrite_peak_margin_bytes']
    assert production['survivor_rewrite_seconds'] == 1.5 / proportion
    assert production['target_rewrite_seconds'] == 0.5 / proportion
    assert production['reference_bytes_per_row'] == pytest.approx(175e9 / (2 * 198_528_286))


def test_v1_or_zero_survivor_receipt_is_refused(tmp_path):
    with pytest.raises(ValueError, match='rehearsal_schema_invalid'):
        tool.validate(example_receipt(schema_version='ed-finder/derived-purge-rehearsal/v1'))
    zero = example_receipt(survivor_products={'system_search': 0, 'system_archetype': 0})
    with pytest.raises(ValueError, match='rehearsal_survivor_population_mismatch'):
        tool.load_reviewed(write_receipt(tmp_path, zero), zero['content_sha256'])
    counts = deepcopy(example_receipt()['row_counts'])
    counts['system_search']['ratings_v4_prod_p4_parallel_v1'] = 0
    with pytest.raises(ValueError, match='rehearsal_row_counts_proportion_mismatch'):
        tool.validate(example_receipt(row_counts=counts))


def _with_split(mutate):
    value = example_receipt()
    body = {key: item for key, item in value.items() if key != 'content_sha256'}
    mutate(body['per_relation']['system_search'], body)
    return tool._evidence().seal(body)


def test_missing_or_forged_search_split_is_refused():
    with pytest.raises(ValueError, match='rehearsal_search_split_missing'):
        tool.validate(_with_split(lambda figure, _: figure.pop('survivor_target_split')))
    def forge(figure, _):
        figure['survivor_target_split']['production']['required_free_bytes_before_rewrite'] = 1
    with pytest.raises(ValueError, match='rehearsal_search_split_mismatch'):
        tool.validate(_with_split(forge))


@pytest.mark.parametrize('field,value', [('target_rows', 1), ('survivor_rows', 1),
                                         ('governed_rewrite_seconds', 9.0), ('target_delete_seconds', 9.0),
                                         ('heap_index_bytes_before_delete', 1)])
def test_search_split_must_bind_to_the_measured_relation(field, value):
    def mutate(figure, body):
        raw = dict(figure['survivor_target_split']['raw'], **{field: value})
        figure['survivor_target_split'] = tool.search_split_figures(raw, body['production_proportion'])
    with pytest.raises(ValueError, match='rehearsal_search_split_unbound'):
        tool.validate(_with_split(mutate))


def test_plan_peak_must_be_the_larger_of_governed_and_survivor_only_peaks(tmp_path):
    def larger_control(figure, body):
        raw = dict(figure['survivor_target_split']['raw'], survivor_rewrite_peak_bytes=999)
        figure['survivor_target_split'] = tool.search_split_figures(raw, body['production_proportion'])
    with pytest.raises(ValueError, match='rehearsal_search_split_unbound'):
        tool.validate(_with_split(larger_control))
    def carried(figure, body):
        larger_control(figure, body)
        figure.update(tool.relation_figures(dict(figure['raw'], rewrite_peak_bytes=999), body['production_proportion']))
    value = _with_split(carried)
    plan = tool.apply_to_plan({}, tool.load_reviewed(write_receipt(tmp_path, value), value['content_sha256']))
    assert plan['rewrite']['system_search']['rewrite_peak_bytes'] == math.ceil(999 / value['production_proportion'])


def test_survivor_rows_narrower_than_production_are_refused():
    def narrow(figure, body):
        raw = dict(figure['survivor_target_split']['raw'])
        raw['survivor_heap_index_bytes_after_rewrite'] = raw['survivor_rows'] * 400
        figure['survivor_target_split'] = tool.search_split_figures(raw, body['production_proportion'])
    with pytest.raises(ValueError, match='rehearsal_search_survivor_width_unrepresentative'):
        tool.validate(_with_split(narrow), production=False)


@pytest.mark.parametrize('field', ('survivor_rows', 'target_rows', 'survivor_heap_index_bytes_after_rewrite'))
def test_search_split_requires_present_survivors_and_targets(field):
    raw = example_split(example_receipt()['per_relation']['system_search']['raw'],
                        tool.expected_row_counts(0.01), **{field: 0})
    with pytest.raises(ValueError, match='rehearsal_search_survivors_absent'):
        tool.search_split_figures(raw, 0.01)
