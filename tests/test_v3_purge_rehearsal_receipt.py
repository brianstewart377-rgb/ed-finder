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


RAW = {'copied_rows': 1, 'target_rows': 0, 'live_bytes_before': 4_000_000_000, 'copy_bytes': 1,
       'copy_peak_bytes': 201, 'temp_file_peak_bytes': 30, 'temp_file_written_bytes': 50, 'freed_bytes': 3_000,
       'swap_attempts': 1, 'finder_reads_during_swap': 40, 'filesystem_sample_count': 100,
       'copy_seconds': 20.0, 'index_build_seconds': 2.0, 'vacuum_freeze_seconds': 3.0, 'verify_seconds': 4.0,
       'fk_validation_seconds': 1.0, 'swap_lock_hold_seconds': 0.25, 'finder_read_stall_seconds': 0.5,
       'drop_seconds': 0.1,
       'wal_bytes': {'chunk': 1000, 'index_build': 100, 'vacuum_freeze': 50, 'verify': 0, 'validate_fks': 10, 'drop': 1}}


def example_raw(counts, relation, **updates):
    """Copy-route measurements consistent with the seeded counts."""
    raw = deepcopy(RAW)
    raw['copied_rows'] = counts[relation]['ratings_v4_prod_p4_parallel_v1']
    raw['target_rows'] = sum(counts[relation][key] for key in ('ratings_v4_prod_p4', 'ratings_v4_prod_p4_opt1'))
    # Search copies as wide as the 2026-10-24 rehearsal's survivors (514 B/row).
    raw['copy_bytes'] = raw['copied_rows'] * 514
    raw.update(updates)
    return raw


def example_receipt(**updates):
    proportion = 0.01
    counts = tool.expected_row_counts(proportion)
    per_relation = {relation: tool.relation_figures(example_raw(counts, relation), proportion)
                    for relation in tool.RELATIONS}
    body = {'schema_version': tool.SCHEMA, 'operation': 'v3-derived-purge-rehearsal', 'route': tool.ROUTE,
            **tool.code_identity(),
            'status': 'success', 'source_git_sha': 'a' * 40, 'scale': 'one_percent',
            'production_proportion': proportion,
            'image_digest': 'postgres:18@sha256:' + 'b' * 64,
            'settings': {'autovacuum': 'on', 'archive_mode': 'on', 'wal_level': 'replica'},
            'row_counts': counts, 'survivor_products': tool.expected_survivor_products(proportion),
            'per_relation': per_relation, 'cleanup_verified': True, 'failures': [],
            'crash_scenarios': {name: {'passed': True} for name in tool.CRASH_SCENARIOS},
            'gate_10_crash_rehearsal_passed': True,
            'lifecycle_receipt_sha256': hashlib.sha256(tool.LIFECYCLE_RECEIPT.read_bytes()).hexdigest()}
    body.update(updates)
    return tool._evidence().seal(body)


def _resealed(mutate):
    value = example_receipt()
    body = {key: item for key, item in value.items() if key != 'content_sha256'}
    mutate(body)
    return tool._evidence().seal(body)


def write_receipt(tmp_path, value):
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(value))
    return path


def test_math_scales_whole_relation_work_and_keeps_rates_and_swap_figures_raw():
    value = example_receipt()
    measured = value['per_relation']['system_search']
    raw = measured['raw']
    production = measured['production']
    assert production['copy_rows_per_second'] == raw['copied_rows'] / 20.0
    assert production['copy_seconds'] == 2000.0 and production['index_build_seconds'] == 200.0
    assert production['vacuum_freeze_seconds'] == 300.0 and production['verify_seconds'] == 400.0
    assert production['fk_validation_seconds'] == 100.0
    assert production['long_phase_seconds_max'] == 400.0 and production['long_phase_fits_reviewed_timeout'] is True
    assert production['copy_peak_bytes'] == 20100
    assert production['required_free_bytes_before_copy'] == 100_000_000_000 + 30150
    assert production['temp_file_peak_bytes'] == 3000 and production['temp_file_written_bytes'] == 5000
    assert production['wal_bytes'] == {'chunk': 100_000, 'index_build': 10_000, 'vacuum_freeze': 5000,
                                       'verify': 0, 'validate_fks': 1000, 'drop': 100}
    # A swap moves catalog entries, not rows: its lock hold and the reader
    # stall are not multiplied by the scale.
    assert production['swap_lock_hold_seconds'] == 0.25 and production['finder_read_stall_seconds'] == 0.5
    assert measured['margin_applied'] == {'copy_peak_bytes': 30150, 'temp_file_peak_bytes': 4500}
    assert tool.validate(value) is value


def test_valid_reviewed_receipt_authenticates_and_seals_the_copy_block_without_double_margin(tmp_path):
    value = example_receipt()
    loaded = tool.load_reviewed(write_receipt(tmp_path, value), value['content_sha256'])
    plan = {'snapshot': {'retained': 'preserved'}, 'delete': {'kept': 'unused_by_the_copy_route'}}
    assert tool.apply_to_plan(plan, loaded) is plan
    source = 'reviewed_rehearsal:' + value['content_sha256']
    assert plan['copy']['source'] == source
    for relation in tool.RELATIONS:
        figures = plan['copy']['relations'][relation]
        assert figures['copy_peak_bytes'] == 20100 and figures['copy_peak_source'] == source
        assert figures['required_free_bytes_before_copy'] == 100_000_000_000 + 30150
        assert figures['rehearsal']['long_phase_fits_reviewed_timeout'] is True
    assert 'rewrite' not in plan and plan['delete'] == {'kept': 'unused_by_the_copy_route'}
    assert plan['snapshot'] == {'retained': 'preserved'}
    assert plan['rehearsal']['gate_10_crash_rehearsal_passed'] is True and plan['rehearsal']['route'] == 'copy_and_drop'
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


def test_gate_10_names_the_copy_route_crash_points():
    assert tool.CRASH_SCENARIOS == (
        'copy_chunk_client_killed', 'copy_postgres_restart', 'index_build_backend_terminated',
        'verify_watchdog_cancel', 'swap_committed_client_killed', 'swap_back_committed_client_killed',
        'swap_back_and_reswap', 'abandon_and_recopy', 'drop_committed_client_killed')
    value = example_receipt()
    del value['crash_scenarios']['swap_back_committed_client_killed']
    with pytest.raises(ValueError, match='crash_scenarios_incomplete'):
        tool.validate(value)


def test_seal_binds_measurements_and_explicit_reviewed_digest(tmp_path):
    value = example_receipt()
    path = write_receipt(tmp_path, value)
    with pytest.raises(ValueError, match='expected_sha256_mismatch'):
        tool.load_reviewed(path, 'c' * 64)
    value['per_relation']['system_search']['raw']['copy_peak_bytes'] += 1
    write_receipt(tmp_path, value)
    with pytest.raises(ValueError, match='seal_invalid'):
        tool.load_reviewed(path, value['content_sha256'])


def test_apply_refuses_an_unsealed_in_memory_receipt():
    value = example_receipt()
    value['source_git_sha'] = 'c' * 40
    with pytest.raises(ValueError, match='seal_invalid'):
        tool.apply_to_plan({}, value)


@pytest.mark.parametrize(('field', 'invalid'), (
    ('copied_rows', 0), ('copied_rows', True), ('copy_bytes', 0), ('swap_attempts', 0),
    ('finder_reads_during_swap', 0), ('copy_seconds', float('nan')), ('verify_seconds', float('inf')),
    ('index_build_seconds', 0), ('copy_peak_bytes', -1), ('temp_file_peak_bytes', 1.5),
    ('swap_lock_hold_seconds', -0.1), ('finder_read_stall_seconds', None), ('drop_seconds', 'fast'),
    ('wal_bytes', {'chunk': 1}), ('wal_bytes', None),
))
def test_invalid_measurements_refused(field, invalid):
    raw = deepcopy(example_receipt()['per_relation']['system_search']['raw'])
    raw[field] = invalid
    with pytest.raises(ValueError, match='rehearsal_'):
        tool.relation_figures(raw, .01)


@pytest.mark.parametrize(('field', 'invalid'), (
    ('schema_version', 'different'), ('route', 'delete_and_rewrite'), ('source_git_sha', 'main'),
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
    value['per_relation']['system_search']['production']['required_free_bytes_before_copy'] = 100_000_000_000
    with pytest.raises(ValueError, match='derived_figures_mismatch'):
        tool.validate(value)


def test_real_plan_consumes_validated_receipt_before_database_sealing(monkeypatch):
    from tests.test_v3_derived_generation_purge_operator import _action_tool, _successful_phase
    module = _action_tool()
    report, runtime, _plan, _calls = _successful_phase(module, monkeypatch, 'plan')
    value = example_receipt()
    module.execute('plan', runtime, report, rehearsal=value)
    reviewed = report['reviewed_plan']
    assert reviewed['copy']['source'] == 'reviewed_rehearsal:' + value['content_sha256']
    assert reviewed['copy']['relations']['body_mechanics']['required_free_bytes_before_copy'] == 100_000_030_150
    assert 'rewrite' not in reviewed
    assert report['rehearsal_receipt_sha256'] == value['content_sha256']
    assert tool.require_plan_binding(reviewed) is reviewed['rehearsal']


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


@pytest.mark.parametrize(('field', 'code'), (('copied_rows', 'copied_rows_mismatch'),
                                           ('target_rows', 'target_rows_mismatch')))
def test_copied_and_target_counts_must_match_the_seed(field, code):
    def mutate(body):
        raw = dict(body['per_relation']['body_mechanics']['raw'])
        raw[field] += 1
        body['per_relation']['body_mechanics'] = tool.relation_figures(raw, body['production_proportion'])
    with pytest.raises(ValueError, match='rehearsal_' + code):
        tool.validate(_resealed(mutate))


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
    plan = {'snapshot': {}}
    tool.apply_to_plan(plan, value)
    return plan


def test_plan_binding_accepts_exactly_the_applied_one_percent_figures():
    plan = _bound_plan()
    assert tool.require_plan_binding(plan) is plan['rehearsal']


@pytest.mark.parametrize('mutation', (
    'no_binding', 'smoke_scale', 'crash_gate_false', 'digest_invalid', 'legacy_route',
    'bootstrap_source', 'other_receipt', 'missing_relation', 'floor_only', 'missing_copy_block',
    'relation_source',
))
def test_plan_binding_refuses_a_plan_that_could_authorize_but_never_copy(mutation):
    plan = _bound_plan()
    if mutation == 'no_binding':
        del plan['rehearsal']
    elif mutation == 'smoke_scale':
        plan['rehearsal']['scale'] = 'smoke'
    elif mutation == 'crash_gate_false':
        plan['rehearsal']['gate_10_crash_rehearsal_passed'] = False
    elif mutation == 'digest_invalid':
        plan['rehearsal']['content_sha256'] = 'F' * 64
    elif mutation == 'legacy_route':
        del plan['rehearsal']['route']
    elif mutation == 'bootstrap_source':
        plan['copy']['source'] = 'disposable_bootstrap_unmeasured'
    elif mutation == 'other_receipt':
        plan['rehearsal']['content_sha256'] = 'e' * 64
    elif mutation == 'missing_relation':
        del plan['copy']['relations']['system_rating_vector']
    elif mutation == 'floor_only':
        plan['copy']['relations']['economy_opportunity']['required_free_bytes_before_copy'] = 1
    elif mutation == 'relation_source':
        plan['copy']['relations']['system_search']['copy_peak_source'] = 'disposable_bootstrap_unmeasured'
    else:
        del plan['copy']
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


def test_v1_v2_or_zero_survivor_receipt_is_refused(tmp_path):
    for schema in ('ed-finder/derived-purge-rehearsal/v1', 'ed-finder/derived-purge-rehearsal/v2'):
        with pytest.raises(ValueError, match='rehearsal_schema_invalid'):
            tool.validate(example_receipt(schema_version=schema))
    zero = example_receipt(survivor_products={'system_search': 0, 'system_archetype': 0})
    with pytest.raises(ValueError, match='rehearsal_survivor_population_mismatch'):
        tool.load_reviewed(write_receipt(tmp_path, zero), zero['content_sha256'])
    counts = deepcopy(example_receipt()['row_counts'])
    counts['system_search']['ratings_v4_prod_p4_parallel_v1'] = 0
    with pytest.raises(ValueError, match='rehearsal_row_counts_proportion_mismatch'):
        tool.validate(example_receipt(row_counts=counts))


def test_the_committed_delete_and_rewrite_receipt_cannot_seal_a_copy_plan():
    """The 2026-10-24 receipt measured the disabled route (schema v2)."""
    committed = tool.ROOT / 'docs/operations/evidence/2026-10-24-v3-derived-purge-rehearsal-receipt-run-40074011789.json'
    value = json.loads(committed.read_text())
    assert value['schema_version'] == 'ed-finder/derived-purge-rehearsal/v2'
    with pytest.raises(ValueError, match='rehearsal_schema_invalid'):
        tool.load_reviewed(committed, value['content_sha256'])


def test_search_copy_narrower_than_production_is_refused():
    def narrow(body):
        raw = dict(body['per_relation']['system_search']['raw'])
        raw['copy_bytes'] = raw['copied_rows'] * 400
        body['per_relation']['system_search'] = tool.relation_figures(raw, body['production_proportion'])
    with pytest.raises(ValueError, match='rehearsal_search_survivor_width_unrepresentative'):
        tool.validate(_resealed(narrow), production=False)
    assert tool.production_search_bytes_per_row() == pytest.approx(175e9 / (2 * 198_528_286))


@pytest.mark.parametrize(('field', 'value', 'code'), (
    ('verify_seconds', 37.0, 'rehearsal_long_phase_exceeds_reviewed_timeout'),
    ('index_build_seconds', 36.01, 'rehearsal_long_phase_exceeds_reviewed_timeout'),
    ('finder_read_stall_seconds', 15.5, 'rehearsal_finder_stall_exceeds_api_timeout'),
))
def test_production_refuses_a_long_phase_or_swap_stall_outside_the_reviewed_bounds(field, value, code):
    def mutate(body):
        raw = dict(body['per_relation']['economy_opportunity']['raw'], **{field: value})
        body['per_relation']['economy_opportunity'] = tool.relation_figures(raw, body['production_proportion'])
    receipt = _resealed(mutate)
    # Smoke evidence still validates; production authority refuses.
    assert tool.validate(receipt, production=False) is receipt
    with pytest.raises(ValueError, match=code):
        tool.validate(receipt)
    # 2 x 36 s / 0.01 = 7200 s is exactly the reviewed envelope.
    def boundary(body):
        raw = dict(body['per_relation']['economy_opportunity']['raw'], verify_seconds=36.0)
        body['per_relation']['economy_opportunity'] = tool.relation_figures(raw, body['production_proportion'])
    assert tool.validate(_resealed(boundary))['status'] == 'success'
