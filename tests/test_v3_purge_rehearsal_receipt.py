"""Sealed disposable measurements are plan inputs only after scale/crash gates."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
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
    body = {'schema_version': tool.SCHEMA, 'operation': 'v3-derived-purge-rehearsal',
            **tool.code_identity(),
            'status': 'success', 'source_git_sha': 'a' * 40, 'scale': 'one_percent',
            'production_proportion': proportion,
            'image_digest': 'postgres:18@sha256:' + 'b' * 64,
            'settings': {'autovacuum': 'on', 'archive_mode': 'off', 'wal_level': 'replica'},
            'row_counts': counts, 'per_relation': per_relation, 'cleanup_verified': True, 'failures': [],
            'crash_scenarios': {name: {'passed': True} for name in tool.CRASH_SCENARIOS},
            'gate_10_crash_rehearsal_passed': True,
            'lifecycle_receipt_sha256': hashlib.sha256(tool.LIFECYCLE_RECEIPT.read_bytes()).hexdigest()}
    body.update(updates)
    return tool._evidence().seal(body)


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
