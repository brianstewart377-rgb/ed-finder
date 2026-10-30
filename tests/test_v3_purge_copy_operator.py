"""Copy-and-drop operator contracts (019 route) over local SQL fakes; no database.

The PG18 counterparts live in tests/test_v3_purge_copy_operator_pg18.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
RELATIONS = ('system_search', 'economy_opportunity', 'body_mechanics', 'system_rating_vector')
PLAN = '6' * 64
PURGE = '49a0c00d-e722-4209-afd8-9d62b877e30a'


def _load(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def copy():
    return _load('scripts/operator/lib/v3_purge_copy.py', 'purge_copy_test')


@pytest.fixture
def controller():
    return _load('scripts/operator/lib/v3_generation_purge.py', 'purge_copy_controller_test')


# --- fixed SQL and per-phase bounds -----------------------------------------

def test_every_019_call_sets_its_own_statement_and_lock_timeout_first(copy):
    """F5: function-level SET statement_timeout never bounds the function's own
    call, so every 019 call runs inside SET LOCAL bounds in the same transaction."""
    calls = {
        'PREPARE_SQL': ('prepare', 'purge_copy_prepare('), 'CHUNK_SQL': ('chunk', 'purge_copy_chunk('),
        'BUILD_INDEXES_SQL': ('index_build', 'purge_copy_build_indexes('), 'VERIFY_SQL': ('verify', 'purge_copy_verify('),
        'SWAP_SQL': ('swap', 'purge_copy_swap('), 'SWAP_BACK_SQL': ('swap_back', 'purge_copy_swap_back('),
        'VALIDATE_FKS_SQL': ('validate_fks', 'purge_copy_validate_fks('), 'DROP_SQL': ('drop', 'purge_copy_drop('),
        'ABANDON_SQL': ('abandon', 'purge_copy_abandon('), 'RECORD_FAILURE_SQL': ('record_failure', 'purge_copy_record_failure('),
        'COMPLETE_SQL': ('complete', 'purge_copy_complete('), 'STATUS_SQL': ('read', 'purge_copy_status()'),
        'BACKUP_SKIP_SQL': ('read', 'purge_copy_backup_skip()'),
    }
    for name, (phase, function) in calls.items():
        sql = getattr(copy, name)
        settings = copy.phase_settings(phase)
        assert sql.startswith('SET ROLE v3_derived_purge_executor;')
        body = sql[sql.index('BEGIN'):]
        timeout = "SET LOCAL statement_timeout='%dms';" % settings['statement_timeout_ms']
        lock = "SET LOCAL lock_timeout='%dms';" % settings['lock_timeout_ms']
        assert timeout in body and lock in body
        assert body.index(timeout) < body.index(lock) < body.index(function), name
        assert body.rstrip().endswith('COMMIT;')
        if settings['temp_file_limit_kb'] is not None:
            assert "SET LOCAL temp_file_limit='%dkB';" % settings['temp_file_limit_kb'] in body
    read_only = {'STATUS_SQL', 'BACKUP_SKIP_SQL'}
    for name in calls:
        assert ('BEGIN READ ONLY;' in getattr(copy, name)) == (name in read_only)


def test_phase_table_is_reviewed_short_for_catalog_steps_and_bounded_for_long_ones(copy):
    long = {'index_build', 'vacuum_freeze', 'verify', 'validate_fks', 'recalibrate_count', 'recalibrate_analyze', 'preflight_scan'}
    for phase, (statement, lock, temp, is_long) in copy.PHASES.items():
        assert 1 <= statement <= copy.VERIFY_PHASE_MS
        assert 1 <= lock <= 5_000
        assert is_long == (phase in long)
        if phase == 'verify':
            # Owner decision 2026-10-30: verification alone is longer and has more temp space.
            assert (statement, temp) == (copy.VERIFY_PHASE_MS, copy.VERIFY_TEMP_FILE_LIMIT_KB)
        elif is_long:
            assert statement == copy.MAX_LONG_PHASE_MS
            assert temp in (None, copy.TEMP_FILE_LIMIT_KB)
        else:
            assert statement <= 45 * 60_000
    # F4: one swap/drop attempt is capped by its statement timeout, below the
    # API's 15 s read timeout, and asks for a sub-second lock wait.
    for phase in ('swap', 'swap_back', 'drop', 'abandon'):
        assert copy.PHASES[phase][0] <= 8_000 and copy.PHASES[phase][1] == copy.SWAP_LOCK_TIMEOUT_MS < 1000
    assert copy.MAX_LONG_PHASE_MS == 7_200_000
    assert copy.VERIFY_PHASE_MS == 19_200_000 and copy.VERIFY_TEMP_FILE_LIMIT_KB == 64 * 1024 ** 2
    assert len(copy.SWAP_BACKOFF_SECONDS) == copy.SWAP_MAX_ATTEMPTS
    with pytest.raises(ValueError, match='purge_copy_phase_invalid'):
        copy.phase_settings('invent')


def test_vacuum_is_throttled_outside_a_transaction_on_a_closed_staging_name(copy):
    for relation in RELATIONS:
        sql = copy.vacuum_sql(relation)
        assert sql.startswith('SET ROLE v3_derived_purge_executor;')
        assert 'BEGIN' not in sql
        assert "SET statement_timeout='7200000ms';" in sql
        assert "SET vacuum_cost_delay='10ms';" in sql and 'SET vacuum_cost_limit=1000;' in sql
        assert 'VACUUM (FREEZE, ANALYZE) v3_purge_staging.' + relation + ';' in sql
    with pytest.raises(ValueError, match='purge_relation_invalid'):
        copy.vacuum_sql('system_archetype')


def test_no_caller_text_or_identifier_enters_fixed_sql(copy):
    source = (ROOT / 'scripts/operator/lib/v3_purge_copy.py').read_text()
    for forbidden in ('session_replication_role', 'DISABLE TRIGGER', 'CASCADE', 'COPY FREEZE', 'TRUNCATE ',
                      '--password=', 'PGPASSWORD=', 'ssh-keyscan', 'DROP TABLE'):
        assert forbidden not in source
    # Every bound value is a psql hex-decoded variable, never an f-string.
    assert '%(relation)s' in copy.PREPARE_SQL and 'f"' not in source.split('def ')[0]
    assert 'pg_cancel_backend(' in copy.CANCEL_SQL and copy.CANCEL_SQL.count('pg_cancel_backend(') == 1
    assert 'a.usename=current_user' in copy.CANCEL_SQL and "a.state='active'" in copy.CANCEL_SQL
    assert 'SET ROLE' not in copy.CANCEL_SQL and 'SET ROLE' not in copy.PREFLIGHT_SQL
    assert copy.PREFLIGHT_SQL.startswith('BEGIN READ ONLY;') and copy.SEARCH_VIOLATIONS_SQL.startswith('BEGIN READ ONLY;')
    assert 'cfc25d36-3bc7-4011-a465-d6460eaaf826' in copy.SEARCH_VIOLATIONS_SQL


# --- pure gate arithmetic -------------------------------------------------------

def test_chunk_gate_is_floor_plus_one_and_a_half_times_measured_growth(copy):
    assert copy.chunk_gate_required(0) == 100_000_000_000
    assert copy.chunk_gate_required(900_000_000) == 100_000_000_000 + 1_350_000_000
    assert copy.chunk_gate_required(1) == 100_000_000_000 + 2
    with pytest.raises(ValueError, match='copy_reservation_invalid'):
        copy.chunk_gate_required(-1)


def test_long_phase_gate_counts_expected_index_size_temp_space_and_wal(copy):
    index = copy.expected_index_bytes(30_000_000_000, 397_000_000, 198_500_000)
    assert index == 15_000_000_000
    required = copy.long_phase_required('index_build', index_bytes=index, max_wal_size_bytes=32 * 1024 ** 3)
    assert required == 100_000_000_000 + 22_500_000_000 + 32 * 1024 ** 2 * 1024 + 32 * 1024 ** 3
    assert copy.long_phase_required('vacuum_freeze', max_wal_size_bytes=10) == 100_000_000_010
    assert copy.long_phase_required('verify', max_wal_size_bytes=0) == 100_000_000_000 + 64 * 1024 ** 3
    assert copy.long_phase_required('validate_fks', max_wal_size_bytes=0) == 100_000_000_000 + 32 * 1024 ** 3
    # A table smaller than its frozen count (stale reltuples) never shrinks the estimate.
    assert copy.expected_index_bytes(10, 1, 5) == 10
    with pytest.raises(ValueError, match='copy_index_estimate_invalid'):
        copy.expected_index_bytes(-1, 1, 1)


def test_wal_throttle_and_archive_lag_rules(copy):
    assert not copy.wal_throttle_needed(28 * 1024 ** 3, 32 * 1024 ** 3)
    assert copy.wal_throttle_needed(29 * 1024 ** 3, 32 * 1024 ** 3)
    with pytest.raises(ValueError, match='wal_measurement_invalid'):
        copy.wal_throttle_needed(1, 0)
    assert copy.archive_lag_segments({'archive_mode': 'on', 'current_segment': 100, 'archived_segment': 90}) == 10
    assert copy.archive_lag_segments({'archive_mode': 'always', 'current_segment': 5, 'archived_segment': 9}) == 0
    for lag in ({'archive_mode': 'off', 'current_segment': 1, 'archived_segment': 1},
                {'archive_mode': 'on', 'current_segment': 1, 'archived_segment': None},
                {'archive_mode': 'on', 'current_segment': '1', 'archived_segment': 1}):
        with pytest.raises(ValueError, match='wal_archive_lag_unknown'):
            copy.archive_lag_segments(lag)


def test_staging_freeze_assertion_rejects_a_plain_vacuum(copy):
    copy.staging_frozen({'staging_xid_age': 2000, 'staging_mxid_age': 5})
    for ages in ({'staging_xid_age': 1_000_001, 'staging_mxid_age': 0}, {'staging_xid_age': 0, 'staging_mxid_age': None},
                 {'staging_xid_age': 50_000_000, 'staging_mxid_age': 0}):
        with pytest.raises(ValueError, match='staging_relfrozenxid_not_frozen'):
            copy.staging_frozen(ages)


# --- ledger state and next step --------------------------------------------------

def _status(relations, *, completed=False):
    return {'requests': [{'copy_id': 'c' * 36, 'plan_sha256': PLAN, 'completed': completed, 'relations': relations}],
            'staging_relations': [], 'retired_relations': [], 'backup_skip': False}


def _state(**overrides):
    base = {'phase': None, 'phase_sequence': None, 'copy_position': 'none', 'failed': False, 'copy_started': None,
            'copy_started_at': None, 'verified': None, 'swapped': None, 'swapped_back': None, 'fk_validated': None,
            'rows_total': 0, 'chunks': 0, 'last_high': None, 'last_copy_at': None, 'staging_oid': None, 'retired_oid': None}
    return {**base, **overrides}


def test_relation_state_selects_the_reviewed_plan_and_fails_closed_on_shape(copy):
    status = _status({code: _state() for code in RELATIONS})
    assert copy.relation_state(status, PLAN, 'system_search')['copy_position'] == 'none'
    assert copy.relation_state(status, '7' * 64, 'system_search') is None
    status['requests'].append(dict(status['requests'][0]))
    with pytest.raises(ValueError, match='purge_copy_status_invalid'):
        copy.relation_state(status, PLAN, 'system_search')
    with pytest.raises(ValueError, match='purge_copy_status_invalid'):
        copy.relation_state({'requests': [{'plan_sha256': PLAN, 'relations': {'system_search': {'copy_position': 'elsewhere'}}}]},
                            PLAN, 'system_search')
    with pytest.raises(ValueError, match='purge_copy_status_invalid'):
        copy.relation_state({}, PLAN, 'system_search')


@pytest.mark.parametrize(('state', 'frozen', 'staging', 'expected'), [
    (None, 10, None, 'prepare'),
    (_state(copy_position='none'), 10, None, 'prepare'),
    (_state(copy_position='staged', phase='COPY_STARTED', rows_total=0), 10, None, 'chunk'),
    (_state(copy_position='staged', phase='CHUNK_COPIED', rows_total=9), 10, None, 'chunk'),
    (_state(copy_position='staged', phase='CHUNK_COPIED', rows_total=10), 10, None, 'index_build'),
    (_state(copy_position='staged', phase='CHUNK_COPIED', rows_total=10), None, None, 'refuse:copy_frozen_survivors_unknown'),
    (_state(copy_position='staged', phase='INDEXES_BUILT', last_copy_at='2026-10-27T10:00:00+00:00'), 10,
     {'staging_present': True, 'last_vacuum': None, 'last_analyze': None}, 'vacuum_freeze'),
    (_state(copy_position='staged', phase='INDEXES_BUILT', last_copy_at='2026-10-27T10:00:00+00:00'), 10,
     {'staging_present': True, 'last_vacuum': '2026-10-27T09:00:00+00:00', 'last_analyze': '2026-10-27T11:00:00+00:00'}, 'vacuum_freeze'),
    (_state(copy_position='staged', phase='INDEXES_BUILT', last_copy_at='2026-10-27T10:00:00+00:00'), 10,
     {'staging_present': True, 'last_vacuum': '2026-10-27T11:00:00+00:00', 'last_analyze': '2026-10-27T11:00:00+00:00'}, 'verify'),
    (_state(copy_position='staged', phase='INDEXES_BUILT'), 10, None, 'refuse:copy_staging_observation_invalid'),
    (_state(copy_position='staged', phase='SWAPPED_BACK', fk_validated=9), 10, None, 'verify'),
    # Codex 4379797650: a committed swap-back whose FK validation was interrupted
    # is finished by swap-back-R, never re-verified past NOT VALID child FKs.
    (_state(copy_position='staged', phase='SWAPPED_BACK'), 10, None, 'refuse:swap_back_fk_validation_pending'),
    (_state(copy_position='staged', phase='VERIFIED'), 10, None, 'done'),
    (_state(copy_position='staged', phase='VERIFIED', failed=True), 10, None, 'refuse:copy_relation_failed_stop_requires_owner_review'),
    (_state(copy_position='swapped', phase='SWAPPED'), 10, None, 'refuse:copy_relation_already_swapped'),
    (_state(copy_position='dropped', phase='DROPPED'), 10, None, 'refuse:copy_relation_already_swapped'),
    ({**_state(copy_position='staged', phase='VERIFIED'), 'completed': True}, 10, None, 'refuse:purge_copy_already_complete'),
    (_state(copy_position='staged', phase='FAILED_STOP'), 10, None, 'refuse:copy_phase_unknown'),
])
def test_next_step_follows_the_019_ledger(copy, state, frozen, staging, expected):
    assert copy.next_step(state, frozen, staging) == expected


def test_sqlstate_classification_separates_integrity_from_interruption(copy):
    assert copy.classify_sqlstate('P0001') == 'integrity'
    assert copy.classify_sqlstate('23514') == 'integrity'
    assert copy.classify_sqlstate('55P03') == 'retryable'
    assert copy.classify_sqlstate('57014') == 'retryable'
    assert copy.classify_sqlstate('53100') == 'resource'
    assert copy.classify_sqlstate(None) == 'unknown'


def test_failure_and_abandon_evidence_shapes(copy):
    evidence = copy.failure_evidence('copy_verify_integrity_failed', 'verify', 'P0001', {'abandoned': True, 'x': 1})
    assert evidence == {'condition': 'copy_verify_integrity_failed', 'phase': 'verify', 'integrity_failed': True,
                        'sqlstate': 'P0001', 'x': 1}
    assert copy.failure_evidence('bad text;', 'chunk', 'nope')['condition'] == 'copy_phase_failed'
    assert copy.failure_evidence('x', 'chunk', 'nope')['sqlstate'] is None
    assert copy.abandon_evidence('owner_abandon', '42', {'pid': 1})['integrity_failed'] is False
    with pytest.raises(ValueError, match='purge_copy_abandon_reason_invalid'):
        copy.abandon_evidence('free_space', None, None)


# --- preflight evaluation (F6/F9/F10) ---------------------------------------------

def _observed(relation='system_search', **changes):
    ages = [{'relation_code': code, 'scope': scope, 'xid_age': 1000, 'mxid_age': 10,
             'xid_limit': 200_000_000, 'mxid_limit': 400_000_000}
            for code in RELATIONS for scope in ('heap', 'toast')]
    base = {'relation': relation,
            'dependents': ['view:v3_app.system_search'] if relation == 'system_search' else [],
            'expected_dependents': ['view:v3_app.system_search'] if relation == 'system_search' else [],
            'disabled_triggers': [], 'commented_triggers': [], 'dependent_views_with_options': [],
            'clustered_indexes': [], 'invalid_indexes': 0, 'live_shape_ok': True,
            'not_valid_checks': ['c1', 'c2'] if relation == 'system_search' else [], 'staging_exists': False,
            'ages': ages}
    return {**base, **changes}


def test_preflight_passes_a_clean_search_relation_with_a_violation_scan(copy):
    result = copy.evaluate_preflight(_observed(), violations={'constraints': 2, 'violations': {'c1': 0, 'c2': 0}},
                                     relation='system_search')
    assert result['passed'] is True
    assert result['checks']['survivor_violations'] == {'c1': 0, 'c2': 0}
    resumed = copy.evaluate_preflight(_observed(), violations=None, relation='system_search')
    assert resumed['checks']['survivor_violations'] == 'not_scanned'
    other = copy.evaluate_preflight(_observed('body_mechanics'), violations=None, relation='body_mechanics')
    assert other['passed'] is True


@pytest.mark.parametrize(('changes', 'violations', 'code'), [
    ({'dependents': ['view:v3_app.system_search', 'other:a rule']}, None, 'copy_preflight_dependents_unexpected'),
    ({'dependents': []}, None, 'copy_preflight_dependents_unexpected'),
    ({'disabled_triggers': ['t']}, None, 'copy_preflight_disabled_trigger'),
    ({'commented_triggers': ['t']}, None, 'copy_preflight_commented_trigger'),
    ({'dependent_views_with_options': ['v3_app.system_search']}, None, 'copy_preflight_view_options'),
    ({'clustered_indexes': ['system_search_pkey']}, None, 'copy_preflight_clustered_index'),
    ({'invalid_indexes': 1}, None, 'copy_preflight_live_shape_outside_contract'),
    ({'live_shape_ok': False}, None, 'copy_preflight_live_shape_outside_contract'),
    ({}, {'constraints': 2, 'violations': {'c1': 0, 'c2': 3}}, 'copy_preflight_survivor_check_violations'),
    ({}, {'constraints': 1, 'violations': {'c1': 0}}, 'copy_preflight_observation_invalid'),
    ({}, {'constraints': 2, 'violations': {'c1': 0, 'c9': 0}}, 'copy_preflight_observation_invalid'),
    ({'relation': 'body_mechanics'}, None, 'copy_preflight_observation_invalid'),
    ({'ages': []}, None, 'copy_preflight_observation_invalid'),
])
def test_preflight_refuses_each_listed_condition(copy, changes, violations, code):
    with pytest.raises(ValueError, match=code):
        copy.evaluate_preflight(_observed(**changes), violations=violations, relation='system_search')


def test_preflight_refuses_a_live_table_near_its_freeze_limit(copy):
    observed = _observed()
    observed['ages'][5]['xid_age'] = 160_000_000  # 80% of 200M on a non-Search heap
    with pytest.raises(ValueError, match='copy_preflight_freeze_age_unsafe'):
        copy.evaluate_preflight(observed, violations=None, relation='system_search')
    observed = _observed('economy_opportunity')
    observed['not_valid_checks'] = ['unexpected']
    with pytest.raises(ValueError, match='copy_preflight_not_valid_check_outside_search'):
        copy.evaluate_preflight(observed, violations=None, relation='economy_opportunity')


# --- planner statistics recalibration (F7) --------------------------------------

def test_n_distinct_recalibration_sql_is_a_validated_negative_fraction(copy):
    assert copy.n_distinct_fraction(746_000_000, 198_500_000) == 0.266086
    sql = copy.recalibrate_alter_sql(0.266086)
    assert 'ALTER TABLE v3_derived.economy_opportunity ALTER COLUMN system_id64 SET (n_distinct = -0.266086);' in sql
    assert sql.startswith('BEGIN;') and 'SET ROLE' not in sql and "SET LOCAL statement_timeout='60000ms';" in sql
    for bad in (0.0, 1.5, -0.1, float('nan'), 1):
        with pytest.raises(ValueError, match='n_distinct_fraction_invalid'):
            copy.recalibrate_alter_sql(bad)
    for rows, distinct in ((0, 1), (10, 11), ('10', 1), (10, 0)):
        with pytest.raises(ValueError, match='n_distinct_counts_invalid'):
            copy.n_distinct_fraction(rows, distinct)


def test_chunk_read_plan_requires_a_nested_loop_over_the_opportunity_pkey(copy):
    good = [{'Plan': {'Node Type': 'Aggregate', 'Plans': [{'Node Type': 'Nested Loop', 'Plans': [
        {'Node Type': 'Index Scan', 'Index Name': 'system_rating_vector_chunk'},
        {'Node Type': 'Index Scan', 'Index Name': 'economy_opportunity_pkey'}]}]}}]
    assert copy.chunk_read_plan_ok(good)
    hash_join = json.loads(json.dumps(good).replace('Nested Loop', 'Hash Join'))
    assert not copy.chunk_read_plan_ok(hash_join)
    seq = json.loads(json.dumps(good).replace('Index Scan', 'Seq Scan'))
    assert not copy.chunk_read_plan_ok(seq)
    assert not copy.chunk_read_plan_ok(None) and not copy.chunk_read_plan_ok([{}])


# --- modes ----------------------------------------------------------------------

def test_mode_parsing_is_closed(copy):
    assert copy.relation_for_mode('copy-system-search') == ('copy', 'system_search')
    assert copy.relation_for_mode('swap-back-economy-opportunity') == ('swap_back', 'economy_opportunity')
    assert copy.relation_for_mode('swap-economy-opportunity') == ('swap', 'economy_opportunity')
    assert copy.relation_for_mode('preflight-body-mechanics') == ('preflight', 'body_mechanics')
    for mode in ('copy-system_search', 'delete-system-search', 'copy-system-archetype', 'copy-', 'swap-back-'):
        with pytest.raises(ValueError, match='purge_copy_mode_invalid'):
            copy.relation_for_mode(mode)
    assert copy.is_disabled('delete-system-search') and copy.is_disabled('rewrite-body-mechanics')
    assert not copy.is_disabled('abort-relation-system-search')


def test_controller_closed_mode_list_and_disabled_reason(controller, copy):
    assert controller.DISABLED_REASON == copy.DISABLED_REASON
    assert len(controller.MODES) == 34 and not set(controller.DISABLED_MODES) & set(controller.MODES)
    assert controller.is_copy_mode('copy-system-search') and not controller.is_copy_mode('complete')
    receipt = controller.receipt('preflight-system-search')
    assert receipt['read_only'] is True
    assert controller.receipt('copy-system-search')['read_only'] is False
    for key in ('copy_status', 'copy_steps', 'swap_attempts', 'finder_smoke', 'n_distinct_recalibration',
                'wal_phase_bytes', 'phase_timeouts', 'backup_age_hours', 'copy_state_hours', 'copy_preflight'):
        assert key in receipt and receipt[key] is None


def test_script_identity_binds_the_copy_modules(controller):
    source = (ROOT / 'scripts/operator/lib/v3_generation_purge.py').read_text()
    for relative in ('scripts/operator/lib/v3_purge_copy.py', 'scripts/operator/lib/v3_purge_copy_dispatch.py'):
        assert "'" + relative + "'" in source
    monitor = (ROOT / 'scripts/operator/lib/v3_purge_rewrite_monitor.py').read_text()
    assert 'v3_purge_copy.py' in monitor and 'v3_purge_copy_dispatch.py' in monitor


# --- status guidance (F16) ----------------------------------------------------------

def test_copy_next_mode_walks_the_relation_order(controller):
    progress = {'requests': [{'purge_id': PURGE, 'plan_sha256': PLAN}]}
    proven = {'status': 'proven'}
    def status(**positions):
        relations = {code: {'copy_position': 'none', 'failed': False, 'phase': None} for code in RELATIONS}
        for code, value in positions.items():
            relations[code].update(value)
        return _status(relations)
    assert controller.copy_next_mode(status(), progress, None)['mode'] == 'verify-system-archetype-empty'
    assert controller.copy_next_mode(status(), progress, proven) == {'mode': 'preflight-system-search', 'implemented': True}
    assert controller.copy_next_mode(status(system_search={'copy_position': 'staged', 'phase': 'CHUNK_COPIED'}), progress, proven)['mode'] == 'copy-system-search'
    assert controller.copy_next_mode(status(system_search={'copy_position': 'staged', 'phase': 'VERIFIED'}), progress, proven)['mode'] == 'swap-system-search'
    assert controller.copy_next_mode(status(system_search={'copy_position': 'swapped', 'phase': 'SWAPPED', 'fk_validated': 7}),
                                     progress, proven)['mode'] == 'drop-system-search'
    # A committed swap or swap-back whose FK validation never ran resumes in
    # its own mode; drop-R and copy-R would refuse.
    assert controller.copy_next_mode(status(system_search={'copy_position': 'swapped', 'phase': 'SWAPPED'}), progress, proven) == {
        'mode': 'swap-system-search', 'implemented': True, 'reason': 'swap_fk_validation_pending'}
    assert controller.copy_next_mode(status(system_search={'copy_position': 'staged', 'phase': 'SWAPPED_BACK'}), progress, proven) == {
        'mode': 'swap-back-system-search', 'implemented': True, 'reason': 'swap_back_fk_validation_pending'}
    assert controller.copy_next_mode(status(system_search={'copy_position': 'staged', 'phase': 'SWAPPED_BACK', 'fk_validated': 8}),
                                     progress, proven)['mode'] == 'copy-system-search'
    assert controller.copy_next_mode(status(system_search={'copy_position': 'dropped'}), progress, proven)['mode'] == 'preflight-economy-opportunity'
    assert controller.copy_next_mode(status(system_search={'copy_position': 'staged', 'failed': True}), progress, proven) == {
        'mode': 'status', 'reason': 'copy_failed_stop_owner_review_system_search'}
    everything = status(**{code: {'copy_position': 'dropped'} for code in RELATIONS})
    assert controller.copy_next_mode(everything, progress, proven) == {'mode': 'complete', 'implemented': True}
    everything['requests'][0]['completed'] = True
    assert controller.copy_next_mode(everything, progress, proven) == {'mode': 'status', 'reason': 'completed'}


def test_hours_since_handles_missing_and_naive_timestamps(copy):
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    assert copy.hours_since('2026-10-26T12:00:00+00:00', now) == 24.0
    assert copy.hours_since(None, now) is None
    assert copy.hours_since('2026-10-26T12:00:00', now) is None
    assert copy.hours_since('garbage', now) is None


# --- Finder smoke -----------------------------------------------------------------

class _Response:
    def __init__(self, status, body):
        self.status = status
        self._body = body
    def read(self, _n):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return False


def test_finder_smoke_is_read_only_and_fails_closed(copy):
    seen = []
    def opener(health_body=b'{"status":"ok","database":"connected"}', fail=None):
        class Opener:
            def open(self, request, timeout):
                seen.append((request.get_method(), request.full_url, request.data))
                path = request.full_url.removeprefix(copy.API_ORIGIN)
                if path == fail:
                    return _Response(503, b'{}')
                return _Response(200, health_body if path == '/api/health' else b'{"items":[]}')
        return Opener()
    result = copy.finder_smoke(opener=opener())
    assert result['passed'] is True
    assert [method for method, _url, _data in seen] == ['GET', 'GET', 'POST']
    assert all(url.startswith('http://127.0.0.1:58080/api/') for _m, url, _d in seen)
    assert json.loads(seen[2][2]) == {'galaxy_wide': True, 'sort_by': 'development', 'from': 0, 'size': 1}
    with pytest.raises(ValueError, match='finder_smoke_failed'):
        copy.finder_smoke(opener=opener(fail='/api/local/search'))
    with pytest.raises(ValueError, match='finder_smoke_failed'):
        copy.finder_smoke(opener=opener(health_body=b'{"status":"degraded","database":"connected"}'))
    with pytest.raises(ValueError, match='finder_smoke_origin_invalid'):
        copy.finder_smoke('https://ed-finder.app', opener=opener())


# --- dispatch-level contracts over fakes ------------------------------------------------

def _dispatch():
    return _load('scripts/operator/lib/v3_purge_copy_dispatch.py', 'purge_copy_dispatch_test')


def test_retrying_swap_bounds_attempts_and_records_the_stall(copy):
    dispatch = _dispatch()
    report = {}
    outcomes = iter(['database_lock_timeout', 'database_statement_timeout', 'ok'])
    clock = iter(range(0, 100, 1))
    sleeps = []
    def query(sql, params=None, *, write=False):
        assert sql == copy.SWAP_SQL and write
        outcome = next(outcomes)
        if outcome != 'ok':
            raise RuntimeError(outcome)
        return {'event': 7}
    runtime = SimpleNamespace(query=query)
    result = dispatch._retrying(None, copy, runtime, report, phase='swap', sql=copy.SWAP_SQL, params={},
                                clock=lambda: next(clock), sleep=sleeps.append)
    assert result == {'event': 7}
    assert [a['outcome'] for a in report['swap_attempts']] == ['database_lock_timeout', 'database_statement_timeout', 'committed']
    assert sleeps == [copy.SWAP_BACKOFF_SECONDS[0], copy.SWAP_BACKOFF_SECONDS[1]]
    assert report['measured_stall_seconds'] == 1
    # Exhaustion after the reviewed maximum; a non-timeout failure never retries.
    always = SimpleNamespace(query=lambda *a, **k: (_ for _ in ()).throw(RuntimeError('database_lock_timeout')))
    with pytest.raises(ValueError, match='swap_lock_attempts_exhausted'):
        dispatch._retrying(None, copy, always, {}, phase='swap', sql=copy.SWAP_SQL, params={},
                           clock=lambda: 0, sleep=lambda _: None)
    other = SimpleNamespace(query=lambda *a, **k: (_ for _ in ()).throw(RuntimeError('bounded_command_failed')))
    with pytest.raises(ValueError, match='^drop_failed$'):
        dispatch._retrying(None, copy, other, {}, phase='drop', sql=copy.DROP_SQL, params={},
                           clock=lambda: 0, sleep=lambda _: pytest.fail('no retry'))


CONTROLDATA = ("pg_control version number:            1800\n"
               "Latest checkpoint location:           1/2A000060\n"
               "Latest checkpoint's REDO location:    1/2A000028\n"
               "Latest checkpoint's REDO WAL file:    00000001000000010000002A\n")


def test_wal_wait_throttles_on_wal_since_the_last_checkpoint_and_archive_lag(copy, controller):
    """pg_wal's directory keeps recycled segments up to about max_wal_size after
    a write burst and an idle server skips checkpoints, so the soft limit is
    measured from the latest checkpoint's REDO point, never the directory."""
    dispatch = _dispatch()
    stop = SimpleNamespace(is_set=lambda: False)
    samples = iter([(40 * 1024 ** 3, 300), (20 * 1024 ** 3, 300), (20 * 1024 ** 3, 10)])
    current = {}
    def measure_wal(runtime, directory):
        current['wal'], current['lag'] = next(samples)
        # A full directory of recycled segments never throttles on its own.
        return {'bytes': 64 * 1024 ** 3, 'archive_mode': 'on', 'archiver': {'failed_count': 0, 'last_failed_time': None,
                                                                            'last_archived_time': None}, 'slots': []}
    controller.measure_wal = measure_wal
    docker_calls = []
    def docker(*argv, **kwargs):
        docker_calls.append(argv)
        return CONTROLDATA
    def query(sql, params=None, *, write=False):
        if sql == copy.WAL_DELTA_SQL:
            assert params == {'before_lsn': '1/2A000028', 'after_lsn': '1/90000000'}
            return {'bytes': current['wal']}
        assert sql == copy.WAL_LAG_SQL
        return {'archive_mode': 'on', 'current_segment': 1000, 'archived_segment': 1000 - current['lag'],
                'wal_lsn': '1/90000000'}
    report = {'wal_before': {'archive_mode': 'on', 'archiver': {'failed_count': 0, 'last_failed_time': None,
                                                             'last_archived_time': None}, 'slots': []}}
    runtime = SimpleNamespace(query=query, docker=docker, deadline=float('inf'))
    sleeps = []
    clock = iter(range(0, 1000, 5))
    result = dispatch._wait(controller, copy, runtime, {'data_directory': '/d'}, report, controller_alive=lambda: None,
                            stop=stop, max_wal_size=32 * 1024 ** 3, lag_segments=16,
                            clock=lambda: next(clock), sleep=sleeps.append)
    assert len(sleeps) == 2 and result['archive_lag_segments'] == 10
    assert result['wal_since_checkpoint_bytes'] == 20 * 1024 ** 3 and result['wal_directory_bytes'] == 64 * 1024 ** 3
    assert docker_calls[0] == ('exec', '--user', 'postgres', '--env', 'LC_ALL=C', controller.CONTAINER,
                               'pg_controldata', '-D', '/d')
    # Exhaustion refuses rather than starting a chunk against a lagging archiver.
    stuck = iter([(40 * 1024 ** 3, 300)] * 1000)
    def stuck_wal(runtime, directory):
        current['wal'], current['lag'] = next(stuck)
        return {'bytes': 1, 'archive_mode': 'on', 'archiver': {
            'failed_count': 0, 'last_failed_time': None, 'last_archived_time': None}, 'slots': []}
    controller.measure_wal = stuck_wal
    far = iter(range(0, 10_000, 100))
    with pytest.raises(ValueError, match='wal_archive_lag_wait_exhausted'):
        dispatch._wait(controller, copy, runtime, {'data_directory': '/d'}, report, controller_alive=lambda: None,
                       stop=stop, max_wal_size=32 * 1024 ** 3, lag_segments=16, clock=lambda: next(far), sleep=lambda _: None)
    with pytest.raises(ValueError, match='copy_stop_requested'):
        dispatch._wait(controller, copy, runtime, {'data_directory': '/d'}, report, controller_alive=lambda: None,
                       stop=SimpleNamespace(is_set=lambda: True), max_wal_size=1, lag_segments=16)


@pytest.mark.parametrize('text', ['', "Latest checkpoint's REDO location:    garbage\n",
                                  CONTROLDATA + CONTROLDATA, None])
def test_wal_since_checkpoint_fails_closed_without_one_redo_location(copy, controller, text):
    dispatch = _dispatch()
    runtime = SimpleNamespace(docker=lambda *a, **k: text, query=lambda *a, **k: pytest.fail('no delta without REDO'))
    with pytest.raises(ValueError, match='wal_checkpoint_redo_unknown'):
        dispatch._wal_since_checkpoint(controller, copy, runtime, {'data_directory': '/d'}, '1/0')


def test_dispatch_refuses_quiesce_mode_acknowledgement_and_unknown_modes(controller):
    dispatch = _dispatch()
    with pytest.raises(ValueError, match='quiesce_mode_not_authorized_option_b_only'):
        dispatch.dispatch(controller, 'copy-system-search', None, {}, None, None, writer_mode='quiesce')
    with pytest.raises(ValueError, match='acknowledgement_not_admitted'):
        dispatch.dispatch(controller, 'copy-system-search', None, {}, None, None, acknowledge_failed_stop=5)


def test_controller_routes_copy_modes_and_complete_to_the_copy_dispatch(controller, monkeypatch):
    routed = []
    monkeypatch.setattr(controller, '_load', lambda name, path=None: SimpleNamespace(
        dispatch=lambda c, mode, *args, **kwargs: routed.append((name, mode))))
    for mode in ('copy-system-search', 'swap-body-mechanics', 'preflight-system-rating-vector', 'complete',
                 'abandon-economy-opportunity', 'drop-system-search', 'swap-back-system-search'):
        controller.execute(mode, None, {}, None)
    assert routed == [('v3_purge_copy_dispatch', mode) for mode in (
        'copy-system-search', 'swap-body-mechanics', 'preflight-system-rating-vector', 'complete',
        'abandon-economy-opportunity', 'drop-system-search', 'swap-back-system-search')]
    for mode in ('delete-system-search', 'rewrite-system-search'):
        with pytest.raises(ValueError, match=controller.DISABLED_REASON):
            controller.execute(mode, None, {}, None)


def test_cli_preflight_is_plan_only_and_holds_no_backup_lock(controller, monkeypatch, capsys):
    monkeypatch.setattr(controller, 'authenticated_plan', lambda *a, **k: {'reviewed_plan': {}})
    monkeypatch.setattr(controller.Runtime, 'guard', lambda self: None)
    monkeypatch.setattr(controller.Runtime, 'state', lambda self, **kwargs: {'unresolved': [], 'failures': [], 'copy_ledger_present': True})
    monkeypatch.setattr(controller.Runtime, 'backup_lock', lambda self: pytest.fail('preflight must not hold the backup schedule lock'))
    from contextlib import contextmanager
    @contextmanager
    def lease(self):
        yield
    monkeypatch.setattr(controller.Runtime, 'lease', lease)
    seen = []
    monkeypatch.setattr(controller, 'execute', lambda mode, runtime, report, plan=None, **kwargs: seen.append((mode, kwargs.get('verification'))) or report.update(status='success'))
    assert controller.main(['preflight-system-search', '--plan=unused', '--plan-sha256=' + '1' * 64]) == 0
    assert seen == [('preflight-system-search', None)]
    assert controller.main(['preflight-system-search', '--plan=unused', '--plan-sha256=' + '1' * 64,
                            '--verification=unused', '--verification-sha256=' + '2' * 64]) == 1
    assert json.loads(capsys.readouterr().out.splitlines()[-1])['failures'] == ['verification_arguments_not_admitted_for_mode']


def test_workflow_and_action_source_contracts():
    workflow = (ROOT / '.github/workflows/v3-production-derived-purge.yml').read_text()
    for prefix in ('preflight-', 'copy-', 'swap-', 'swap-back-', 'drop-', 'abandon-'):
        for relation in ('system-search', 'economy-opportunity', 'body-mechanics', 'system-rating-vector'):
            assert '          - ' + prefix + relation + '\n' in workflow
    assert '          - delete-' not in workflow and '          - rewrite-' not in workflow
    assert "startsWith(inputs.mode, 'copy-')" in workflow and "startsWith(inputs.mode, 'drop-')" in workflow
    assert 'ssh-keyscan' not in workflow
    dispatch_source = (ROOT / 'scripts/operator/lib/v3_purge_copy_dispatch.py').read_text()
    assert 'start_new_session' not in dispatch_source and 'nohup' not in dispatch_source
    assert 'monitor.start_copy(' in dispatch_source
    assert re.search(r"'vacuum_freeze'.*'verify'", dispatch_source, re.S)
    # Every long phase runs through the single watchdog/progress runner.
    assert dispatch_source.count('_long_phase(c, copy, runtime, report, phase=') >= 6


# --- plan figures for the copy route ----------------------------------------------

def _figures(copy, peak=111_800_000_000):
    return {code: {'copy_peak_bytes': peak, 'required_free_bytes_before_copy': copy.FLOOR_BYTES + (3 * peak + 1) // 2,
                   'copy_rows_per_second': 5000.0, 'long_phase_seconds_max': 1200.0,
                   'long_phase_fits_reviewed_timeout': True} for code in RELATIONS}


def test_plan_block_carries_free_space_before_each_copy_from_the_copy_rehearsal(copy):
    source = 'reviewed_rehearsal:' + 'a' * 64
    block = copy.plan_block(_figures(copy), source)
    search = block['relations']['system_search']
    assert search['required_free_bytes_before_copy'] == 100_000_000_000 + 167_700_000_000
    assert search['copy_peak_source'] == source and search['chunk_rows'] == 100_000
    assert search['rehearsal']['copy_rows_per_second'] == 5000.0
    assert block['source'] == source and set(block['phase_timeouts']) == set(copy.PHASES)
    assert block['swap_backoff_seconds'] == list(copy.SWAP_BACKOFF_SECONDS)
    reviewed = {'copy': block}
    assert copy.required_before_copy(reviewed, 'system_search') == 267_700_000_000
    with pytest.raises(ValueError, match='copy_plan_figures_missing'):
        copy.required_before_copy({'copy': {'relations': {}}}, 'system_search')
    with pytest.raises(ValueError, match='copy_plan_figures_missing'):
        copy.required_before_copy({'copy': {'relations': {'system_search': {'required_free_bytes_before_copy': 1}}}}, 'system_search')


def test_plan_block_refuses_unmeasured_or_inconsistent_figures(copy):
    source = 'reviewed_rehearsal:' + 'a' * 64
    with pytest.raises(ValueError, match='copy_plan_figures_missing'):
        copy.plan_block(None, source)
    for bad in ({}, {code: {} for code in RELATIONS}):
        with pytest.raises(ValueError, match='copy_plan_peak_not_measured'):
            copy.plan_block(bad, source)
    figures = _figures(copy)
    figures['body_mechanics']['required_free_bytes_before_copy'] -= 1
    with pytest.raises(ValueError, match='copy_plan_peak_not_measured'):
        copy.plan_block(figures, source)
    for invalid in ('reviewed_rehearsal:short', 'conservative_fallback', None):
        with pytest.raises(ValueError, match='copy_plan_source_invalid'):
            copy.plan_block(_figures(copy), invalid)
    # Only the disposable rehearsal seals a figure-less, floor-only block.
    bootstrap = copy.plan_block(None, copy.BOOTSTRAP_SOURCE)
    assert all(item['required_free_bytes_before_copy'] == copy.FLOOR_BYTES and 'rehearsal' not in item
               for item in bootstrap['relations'].values())


def test_plan_mode_seals_the_copy_block_through_the_reviewed_rehearsal():
    source = (ROOT / 'scripts/operator/lib/v3_generation_purge.py').read_text()
    plan_branch = source[source.index("if rehearsal is not None:"):]
    assert "_load('v3_purge_rehearsal_receipt').apply_to_plan(reviewed, rehearsal)" in plan_branch
    assert plan_branch.index('apply_to_plan(reviewed, rehearsal)') < plan_branch.index('transactions.seal_plan(runtime.query, reviewed)')
    receipt = (ROOT / 'scripts/operator/lib/v3_purge_rehearsal_receipt.py').read_text()
    assert "reviewed['copy'] = _load('v3_purge_copy').plan_block(figures, source)" in receipt


# --- the copy-R state machine over fakes ---------------------------------------------------

class _FakeBackend:
    def __init__(self, results):
        self.results = results
        self.identity = {'backend_pid': 4242, 'backend_start': '2026-10-27T10:00:00+00:00'}
        self.calls = []

    def query(self, sql, params=None, *, write=False):
        self.calls.append((sql, params, write))
        outcome = self.results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _copy_fixture(controller, copy, dispatch, monkeypatch, *, state, frozen, chunk_results, staging=None):
    from contextlib import contextmanager
    report = controller.receipt('copy-system-search')
    report.update(data_mount={'source': '/data', 'device': 1}, wal_before={}, script_sha256='2' * 64,
                  runner_state={'controller_run_id': '1'})
    reviewed = {'plan_sha256': PLAN, 'copy': {'relations': {'system_search': {'required_free_bytes_before_copy': 150_000_000_000}}}}
    status = _status({'system_search': state, **{code: _state() for code in RELATIONS if code != 'system_search'}})
    staging = staging or {'staging_present': state['copy_position'] == 'staged', 'staging_bytes': 100, 'wal_lsn': '0/10',
                          'max_wal_size_bytes': 32 * 1024 ** 3, 'live_index_bytes': 10, 'live_reltuples': 10,
                          'last_vacuum': None, 'last_analyze': None, 'xid_next': 1000, 'staging_xid_age': 5,
                          'staging_mxid_age': 1}
    writes = []
    def query(sql, params=None, *, write=False):
        if write:
            writes.append(sql)
        if sql == copy.STATUS_SQL:
            return json.loads(json.dumps(status))
        if sql == copy.REQUEST_SQL:
            return {'frozen_survivors': {'system_search': frozen}}
        if sql == copy.STAGING_SQL:
            return dict(staging)
        if sql == copy.PREPARE_SQL:
            status['requests'][0]['relations']['system_search'].update(
                copy_position='staged', phase='COPY_STARTED', rows_total=0, last_copy_at='2026-10-27T10:30:00+00:00')
            return {'event': 1}
        if sql == copy.WAL_DELTA_SQL:
            return {'bytes': 7}
        if sql == copy.RECORD_FAILURE_SQL:
            return {'event': 99}
        raise AssertionError(sql[:80])
    runtime = SimpleNamespace(query=query, deadline=float('inf'), report=report, status_workers=lambda: None,
                              workers=lambda: True)
    backend = _FakeBackend(list(chunk_results))
    @contextmanager
    def fake_backend(c, rt, timeout_ms, *, on_wait=None):
        yield backend
    phases = []
    def fake_long_phase(c, cp, rt, rep, *, phase, **kwargs):
        phases.append(phase)
        relation = status['requests'][0]['relations']['system_search']
        if phase == 'index_build':
            relation.update(phase='INDEXES_BUILT')
        elif phase == 'vacuum_freeze':
            staging.update(last_vacuum='2026-10-27T12:00:00+00:00', last_analyze='2026-10-27T12:00:00+00:00')
        elif phase == 'verify':
            relation.update(phase='VERIFIED')
        return {'event': 5}
    monkeypatch.setattr(dispatch, 'phase_backend', fake_backend)
    monkeypatch.setattr(dispatch, '_long_phase', fake_long_phase)
    monkeypatch.setattr(dispatch, '_measure', lambda *a, **k: {'filesystem_free_bytes': 10 ** 12})
    monkeypatch.setattr(dispatch, '_wait', lambda *a, **k: {})
    monkeypatch.setattr(dispatch, 'preflight', lambda *a, **k: {'passed': True})
    monkeypatch.setattr(controller, 'require_reviewed_migration_ledger', lambda *a, **k: None)
    monkeypatch.setattr(controller, 'survivor_gate', lambda *a, **k: None)
    stop = SimpleNamespace(is_set=lambda: False)
    return report, runtime, reviewed, status, backend, phases, writes, stop


def test_copy_dispatch_prepares_copies_and_runs_every_long_phase_in_order(controller, copy, monkeypatch):
    dispatch = _dispatch()
    chunks = [{'rows': 3, 'staging_bytes': 200, 'wal_lsn': '0/20'}, {'rows': 2, 'staging_bytes': 400, 'wal_lsn': '0/30'},
              {'rows': 0, 'staging_bytes': 400, 'wal_lsn': '0/30'}]
    report, runtime, reviewed, status, backend, phases, writes, stop = _copy_fixture(
        controller, copy, dispatch, monkeypatch, state=_state(), frozen=5, chunk_results=chunks)
    def advance(*args, **kwargs):
        relation = status['requests'][0]['relations']['system_search']
        result = chunks_iter.__next__()
        relation.update(phase='CHUNK_COPIED', rows_total=relation['rows_total'] + result['rows'],
                        last_copy_at='2026-10-27T11:00:00+00:00')
        return result
    chunks_iter = iter(json.loads(json.dumps(chunks)))
    backend.query = advance
    dispatch._copy(controller, copy, runtime, report, reviewed, [PURGE, PURGE], {'data_directory': '/d'}, [], 'system_search',
                   None, 5, runtime.query(copy.STAGING_SQL), controller_alive=lambda: None, stop=stop,
                   max_wal_size=32 * 1024 ** 3, wall_clock_seconds=600)
    assert copy.PREPARE_SQL in writes
    assert phases == ['index_build', 'vacuum_freeze', 'verify']
    assert report['result'] == 'copy_verified_ready_for_swap'
    assert report['next_admissible_mode'] == {'mode': 'swap-system-search', 'implemented': True}
    assert report['rows_affected_this_run'] == 5 and report['rows_remaining'] == {'system_search': 0}
    assert report['required_free_bytes_before_copy'] == 150_000_000_000
    assert report['copy_chunk_outcome'] == 'copy_rows_complete'


def test_copy_dispatch_defers_a_long_phase_that_no_longer_fits_the_job(controller, copy, monkeypatch):
    dispatch = _dispatch()
    state = _state(copy_position='staged', phase='CHUNK_COPIED', rows_total=5, last_copy_at='2026-10-27T10:30:00+00:00')
    report, runtime, reviewed, status, backend, phases, writes, stop = _copy_fixture(
        controller, copy, dispatch, monkeypatch, state=state, frozen=5, chunk_results=[])
    monkeypatch.setattr(dispatch, 'DISPATCH_BUDGET_SECONDS', 10)
    dispatch._copy(controller, copy, runtime, report, reviewed, [PURGE, PURGE], {'data_directory': '/d'}, [], 'system_search',
                   state, 5, runtime.query(copy.STAGING_SQL), controller_alive=lambda: None, stop=stop,
                   max_wal_size=32 * 1024 ** 3, wall_clock_seconds=5)
    assert phases == [] and writes == []
    assert report['result'] == 'copy_long_phase_deferred_to_next_dispatch'
    assert report['copy_next_step'] == 'index_build'
    assert report['next_admissible_mode'] == {'mode': 'copy-system-search', 'implemented': True}


def test_copy_dispatch_refuses_a_failed_or_swapped_relation_before_any_work(controller, copy, monkeypatch):
    dispatch = _dispatch()
    for state, code in ((_state(copy_position='staged', phase='VERIFIED', failed=True), 'copy_relation_failed_stop_requires_owner_review'),
                        (_state(copy_position='swapped', phase='SWAPPED'), 'copy_relation_already_swapped')):
        report, runtime, reviewed, status, backend, phases, writes, stop = _copy_fixture(
            controller, copy, dispatch, monkeypatch, state=state, frozen=5, chunk_results=[])
        with pytest.raises(ValueError, match=code):
            dispatch._copy(controller, copy, runtime, report, reviewed, [PURGE, PURGE], {'data_directory': '/d'}, [], 'system_search',
                           state, 5, runtime.query(copy.STAGING_SQL), controller_alive=lambda: None, stop=stop,
                           max_wal_size=32 * 1024 ** 3, wall_clock_seconds=5)
        assert writes == [] and phases == []


def test_chunk_integrity_failure_records_failed_stop_but_an_interruption_does_not(controller, copy, monkeypatch):
    dispatch = _dispatch()
    state = _state(copy_position='staged', phase='CHUNK_COPIED', rows_total=2)
    report, runtime, reviewed, status, backend, phases, writes, stop = _copy_fixture(
        controller, copy, dispatch, monkeypatch, state=state, frozen=5,
        chunk_results=[dispatch.PhaseBackendError('copy_phase_backend_failed', '23514')])
    with pytest.raises(ValueError, match='copy_chunk_integrity_failed'):
        dispatch._chunks(controller, copy, runtime, report, [PURGE, PURGE], {'data_directory': '/d'}, [], 'system_search',
                         state, 5, runtime.query(copy.STAGING_SQL), controller_alive=lambda: None, stop=stop,
                         max_wal_size=1, budget_seconds=60)
    assert writes == [copy.RECORD_FAILURE_SQL]
    assert report['failed_stop_recorded'] == 99 and report['integrity_failed'] is True
    assert report['failure_evidence']['sqlstate'] == '23514' and report['failure_evidence']['phase'] == 'chunk'
    report, runtime, reviewed, status, backend, phases, writes, stop = _copy_fixture(
        controller, copy, dispatch, monkeypatch, state=state, frozen=5,
        chunk_results=[dispatch.PhaseBackendError('copy_phase_backend_failed', '57014')])
    with pytest.raises(ValueError, match='copy_chunk_interrupted'):
        dispatch._chunks(controller, copy, runtime, report, [PURGE, PURGE], {'data_directory': '/d'}, [], 'system_search',
                         state, 5, runtime.query(copy.STAGING_SQL), controller_alive=lambda: None, stop=stop,
                         max_wal_size=1, budget_seconds=60)
    assert writes == [] and report.get('integrity_failed') is None
    assert report['copy_phase_failures'][0]['classification'] == 'retryable'


def test_chunk_loop_stops_at_its_wall_clock_budget_and_grows_the_reservation(controller, copy, monkeypatch):
    dispatch = _dispatch()
    state = _state(copy_position='staged', phase='CHUNK_COPIED', rows_total=0)
    report, runtime, reviewed, status, backend, phases, writes, stop = _copy_fixture(
        controller, copy, dispatch, monkeypatch, state=state, frozen=100,
        chunk_results=[{'rows': 1, 'staging_bytes': 2_000_000_100, 'wal_lsn': '0/20'}])
    clock = iter([0, 0, 0, 100, 100, 100, 100])
    measured = []
    monkeypatch.setattr(dispatch, '_measure', lambda c, cp, rt, i, rep, required: measured.append(required))
    dispatch._chunks(controller, copy, runtime, report, [PURGE, PURGE], {'data_directory': '/d'}, [], 'system_search',
                     state, 100, runtime.query(copy.STAGING_SQL), controller_alive=lambda: None, stop=stop,
                     max_wal_size=1, budget_seconds=60, clock=lambda: next(clock))
    assert report['copy_chunk_outcome'] == 'copy_wall_clock_budget_exhausted'
    assert report['rows_affected_this_run'] == 1 and report['rows_remaining'] == {'system_search': 99}
    assert measured == [copy.chunk_gate_required(copy.DEFAULT_CHUNK_RESERVATION_BYTES)]
    assert report['copy_chunk_reservation']['bytes'] == 2_000_000_007
    assert report['wal_phase_bytes'] == {'chunk': 7}


# --- swap, swap-back and drop resumption over fakes (Codex 4379797637/4379797650) ---

class _Ledger:
    """A fake owner runtime whose one relation follows 019's position rules."""

    def __init__(self, copy, relation, state, *, attoptions=None, retired=None):
        self.copy, self.relation = copy, relation
        self.state = _state(**state)
        self.attoptions, self.retired = attoptions, retired
        self.statements = []
        self.saved = []
        self.deadline = float('inf')
        self.report = {}

    def status(self):
        relations = {code: _state(copy_position='dropped') for code in RELATIONS}
        relations[self.relation] = dict(self.state)
        return _status(relations)

    def query(self, sql, params=None, *, write=False):
        copy = self.copy
        self.statements.append(sql)
        if sql == copy.STATUS_SQL:
            return json.loads(json.dumps(self.status()))
        if sql == copy.REQUEST_SQL:
            return {'frozen_survivors': {self.relation: 10}}
        if sql == copy.RECALIBRATE_STATS_SQL:
            return {'attoptions': self.attoptions, 'retired_attoptions': self.retired, 'reltuples': 10}
        if sql == copy.SWAP_SQL:
            self.state.update(copy_position='swapped', phase='SWAPPED', swapped=20, fk_validated=None)
            return {'event': 20}
        if sql in (copy.SWAP_BACK_SQL, copy.SWAP_BACK_OPPORTUNITY_SQL):
            if sql == copy.SWAP_BACK_OPPORTUNITY_SQL:
                self.attoptions = self.retired
            self.state.update(copy_position='staged', phase='SWAPPED_BACK', swapped_back=30, fk_validated=None)
            return {'event': 30}
        if sql == copy.DROP_SQL:
            self.state.update(copy_position='dropped', phase='DROPPED')
            return {'event': 40}
        if sql.startswith('BEGIN;\n') and 'SET (n_distinct = ' in sql:
            self.attoptions = ['n_distinct=' + sql.split('SET (n_distinct = ')[1].split(')')[0]]
            return {'n_distinct': float(self.attoptions[0].split('=')[1])}
        if sql == copy.RECALIBRATE_ANALYZE_SQL:
            raise AssertionError('ANALYZE must run on the long-phase backend, not the one-shot transport')
        if sql == copy.CHUNK_READ_PLAN_SQL:
            return [{'Plan': {'Node Type': 'Nested Loop', 'Plans': [
                {'Node Type': 'Index Scan', 'Index Name': 'economy_opportunity_pkey'}]}}]
        if sql == copy.WAL_LAG_SQL:
            return {'wal_lsn': '0/10'}
        if sql == copy.WAL_DELTA_SQL:
            return {'bytes': 3}
        raise AssertionError(sql[:80])


def _phase_fakes(controller, copy, dispatch, monkeypatch, ledger):
    phases = []
    def long_phase(c, cp, rt, rep, *, phase, **kwargs):
        phases.append(phase)
        if phase == 'validate_fks':
            ledger.state['fk_validated'] = 50
            return {'event': 50}
        if phase == 'recalibrate_count':
            return {'rows': 3_700, 'distinct_systems': 1_000}
        if phase == 'recalibrate_analyze':
            assert kwargs['sql'] == cp.RECALIBRATE_ANALYZE_SQL
            return {'analyzed': True}
        raise AssertionError(phase)
    monkeypatch.setattr(dispatch, '_long_phase', long_phase)
    monkeypatch.setattr(dispatch, '_measure', lambda *a, **k: None)
    monkeypatch.setattr(dispatch, '_wait', lambda *a, **k: None)
    monkeypatch.setattr(copy, 'finder_smoke', lambda *a, **k: {'passed': True})
    original = controller._load
    def load(name, path=None):
        if name == 'v3_purge_delete':
            return SimpleNamespace(save_host_state=lambda value, path=None: ledger.saved.append((value, path)),
                                   free_space=lambda *_: {'free_bytes': 1})
        return original(name, path) if path else original(name)
    monkeypatch.setattr(controller, '_load', load)
    report = {'reviewed_plan_sha256': PLAN, 'data_mount': {'source': '/data'}}
    return phases, report


def _run(dispatch, controller, copy, ledger, report, function):
    stop = SimpleNamespace(is_set=lambda: False)
    getattr(dispatch, function)(controller, copy, ledger, report, [PURGE, PURGE], {'data_directory': '/d'},
                                ledger.relation, copy.relation_state(ledger.status(), PLAN, ledger.relation),
                                controller_alive=lambda: None, stop=stop, max_wal_size=1)


def test_swap_back_of_the_opportunity_restores_the_retired_statistics_in_its_own_transaction(controller, copy, monkeypatch):
    dispatch = _dispatch()
    ledger = _Ledger(copy, 'economy_opportunity', dict(copy_position='swapped', phase='SWAPPED', verified=10,
                                                         swapped=20, fk_validated=21),
                     attoptions=['n_distinct=-0.270000'], retired=['n_distinct=-0.13'])
    phases, report = _phase_fakes(controller, copy, dispatch, monkeypatch, ledger)
    _run(dispatch, controller, copy, ledger, report, '_swap_back')
    assert copy.SWAP_BACK_OPPORTUNITY_SQL in ledger.statements and copy.SWAP_BACK_SQL not in ledger.statements
    assert report['n_distinct_restore']['before']['attoptions'] == ['n_distinct=-0.270000']
    assert report['n_distinct_restore']['after']['attoptions'] == ['n_distinct=-0.13']
    assert phases == ['validate_fks'] and report['result'] == 'swapped_back_live_restored'


def test_swap_back_of_other_relations_uses_the_plain_019_call(controller, copy, monkeypatch):
    dispatch = _dispatch()
    ledger = _Ledger(copy, 'body_mechanics', dict(copy_position='swapped', phase='SWAPPED', verified=10, swapped=20,
                                                    fk_validated=21))
    phases, report = _phase_fakes(controller, copy, dispatch, monkeypatch, ledger)
    _run(dispatch, controller, copy, ledger, report, '_swap_back')
    assert copy.SWAP_BACK_SQL in ledger.statements and copy.SWAP_BACK_OPPORTUNITY_SQL not in ledger.statements
    assert 'n_distinct_restore' not in report and phases == ['validate_fks']


@pytest.mark.parametrize(('fk_validated', 'phases', 'result'), [
    (None, ['validate_fks'], 'swapped_back_live_restored'), (31, [], 'swap_back_already_verified')])
def test_a_committed_swap_back_resumes_without_a_second_physical_swap_back(controller, copy, monkeypatch,
                                                                           fk_validated, phases, result):
    """Codex 4379797650: staged + SWAPPED_BACK (child FKs NOT VALID) is resumable."""
    dispatch = _dispatch()
    ledger = _Ledger(copy, 'economy_opportunity', dict(copy_position='staged', phase='SWAPPED_BACK', verified=10,
                                                         swapped=20, swapped_back=30, fk_validated=fk_validated),
                     attoptions=['n_distinct=-0.13'], retired=None)
    observed, report = _phase_fakes(controller, copy, dispatch, monkeypatch, ledger)
    _run(dispatch, controller, copy, ledger, report, '_swap_back')
    assert not {copy.SWAP_BACK_SQL, copy.SWAP_BACK_OPPORTUNITY_SQL} & set(ledger.statements)
    assert report['swap_back_resumed'] is True and observed == phases and report['result'] == result
    assert report['finder_smoke'] == {'passed': True}


@pytest.mark.parametrize('state', [dict(copy_position='staged', phase='VERIFIED'), dict(copy_position='none'),
                                   dict(copy_position='dropped', phase='DROPPED')])
def test_swap_back_refuses_anything_but_a_swapped_or_swapped_back_relation(controller, copy, monkeypatch, state):
    dispatch = _dispatch()
    ledger = _Ledger(copy, 'body_mechanics', state)
    _phase_fakes(controller, copy, dispatch, monkeypatch, ledger)
    with pytest.raises(ValueError, match='swapped_relation_required_for_swap_back'):
        _run(dispatch, controller, copy, ledger, {'reviewed_plan_sha256': PLAN}, '_swap_back')
    assert ledger.statements == []


def test_a_committed_forward_swap_resumes_fk_validation_and_recalibration(controller, copy, monkeypatch):
    dispatch = _dispatch()
    ledger = _Ledger(copy, 'economy_opportunity', dict(copy_position='swapped', phase='SWAPPED', verified=10, swapped=20),
                     attoptions=['n_distinct=-0.13'], retired=['n_distinct=-0.13'])
    phases, report = _phase_fakes(controller, copy, dispatch, monkeypatch, ledger)
    _run(dispatch, controller, copy, ledger, report, '_swap')
    assert copy.SWAP_SQL not in ledger.statements and report['swap_resumed'] is True
    assert phases == ['validate_fks', 'recalibrate_count', 'recalibrate_analyze'] and report['result'] == 'swap_verified'
    assert ledger.attoptions == ['n_distinct=-0.270270']
    assert report['next_admissible_mode'] == {'mode': 'drop-economy-opportunity', 'implemented': True}


def test_recalibration_ledgers_the_restore_value_first_and_is_idempotent(controller, copy, monkeypatch):
    dispatch = _dispatch()
    ledger = _Ledger(copy, 'economy_opportunity', dict(copy_position='swapped', phase='SWAPPED', verified=10, swapped=20,
                                                         fk_validated=21),
                     attoptions=['n_distinct=-0.13'], retired=['n_distinct=-0.13'])
    phases, report = _phase_fakes(controller, copy, dispatch, monkeypatch, ledger)
    order = []
    original_query = ledger.query
    def query(sql, params=None, *, write=False):
        if 'SET (n_distinct = ' in sql:
            order.append('alter')
        return original_query(sql, params, write=write)
    ledger.query = query
    original_save = ledger.saved.append
    ledger.saved = SimpleNamespace(append=lambda item: (order.append('saved'), original_save(item)))
    dispatch._recalibrate(controller, copy, ledger, report, [PURGE, PURGE], {'data_directory': '/d'}, 'economy_opportunity',
                          controller_alive=lambda: None, stop=SimpleNamespace(is_set=lambda: False), max_wal_size=1)
    assert order == ['saved', 'alter']
    record = report['n_distinct_recalibration']['host_state']
    assert record['live_attoptions_before'] == ['n_distinct=-0.13'] and record['retired_attoptions'] == ['n_distinct=-0.13']
    assert record['n_distinct_target'] == -0.27027 and record['already_set'] is False
    # Re-dispatched: the option already matches; no second ALTER, no new state.
    order.clear()
    report = {'reviewed_plan_sha256': PLAN}
    dispatch._recalibrate(controller, copy, ledger, report, [PURGE, PURGE], {'data_directory': '/d'}, 'economy_opportunity',
                          controller_alive=lambda: None, stop=SimpleNamespace(is_set=lambda: False), max_wal_size=1)
    assert order == [] and report['n_distinct_recalibration']['altered'] == {'n_distinct': -0.27027, 'already_set': True}
    assert report['n_distinct_recalibration']['host_state'] is None


def test_recalibration_refuses_when_the_option_did_not_take(controller, copy, monkeypatch):
    dispatch = _dispatch()
    ledger = _Ledger(copy, 'economy_opportunity', dict(copy_position='swapped', phase='SWAPPED', verified=10, swapped=20,
                                                         fk_validated=21), attoptions=None, retired=None)
    _phases, report = _phase_fakes(controller, copy, dispatch, monkeypatch, ledger)
    original_query = ledger.query
    ledger.query = lambda sql, params=None, *, write=False: (
        {'n_distinct': -0.27027} if 'SET (n_distinct = ' in sql else original_query(sql, params, write=write))
    with pytest.raises(ValueError, match='n_distinct_recalibration_not_applied'):
        dispatch._recalibrate(controller, copy, ledger, report, [PURGE, PURGE], {'data_directory': '/d'},
                              'economy_opportunity', controller_alive=lambda: None,
                              stop=SimpleNamespace(is_set=lambda: False), max_wal_size=1)


def test_a_committed_drop_is_reported_without_a_second_drop(controller, copy, monkeypatch):
    dispatch = _dispatch()
    ledger = _Ledger(copy, 'economy_opportunity', dict(copy_position='dropped', phase='DROPPED'))
    _phase_fakes(controller, copy, dispatch, monkeypatch, ledger)
    report = {'reviewed_plan_sha256': PLAN}
    dispatch._drop(controller, copy, ledger, report, [PURGE, PURGE], {'data_directory': '/d'}, 'economy_opportunity',
                   copy.relation_state(ledger.status(), PLAN, 'economy_opportunity'),
                   controller_alive=lambda: None, stop=SimpleNamespace(is_set=lambda: False), max_wal_size=1)
    assert ledger.statements == [] and report['result'] == 'retired_relation_already_dropped'
    assert report['next_admissible_mode'] == {'mode': 'copy-body-mechanics', 'implemented': True}


@pytest.mark.parametrize('relation', ['system_search', 'economy_opportunity', 'body_mechanics'])
@pytest.mark.parametrize('recalibration', ['verified', 'unverified'])
def test_opportunity_drop_reverifies_statistics_first(controller, copy, monkeypatch, relation, recalibration):
    """PR #894 review 4382332411: an interrupted swap-economy-opportunity could
    leave FK validation committed but the n_distinct recalibration and its
    plan proof unfinished. The opportunity drop re-runs the idempotent
    recalibration before it drops the retired table, and on failure drops
    nothing and sends the owner back to swap-R. Other relations never touch it."""
    dispatch = _dispatch()
    calls = []

    def recalibrate(*args, **kwargs):
        calls.append(args[6])
        if recalibration == 'unverified':
            raise ValueError('n_distinct_recalibration_plan_unverified')
    monkeypatch.setattr(dispatch, '_recalibrate', recalibrate)
    dropped = []
    monkeypatch.setattr(dispatch, '_measure', lambda *a, **k: {'filesystem_free_bytes': 1})
    monkeypatch.setattr(dispatch, '_retrying', lambda *a, **k: dropped.append(k['phase']) or {'event': 7})
    monkeypatch.setattr(copy, 'finder_smoke', lambda: {'ok': True})
    state = {'failed': False, 'copy_position': 'swapped', 'phase': 'SWAPPED', 'verified': 3, 'fk_validated': 5}
    runtime = SimpleNamespace(query=lambda sql, params=None, **k: {'wal_lsn': '0/1', 'bytes': 0})
    monkeypatch.setattr(controller, '_load', lambda name, path=None: SimpleNamespace(
        free_space=lambda path: {'free_bytes': 1}))
    controller.OBJECTS_SQL = getattr(controller, 'OBJECTS_SQL', 'SELECT 1')
    report = {'reviewed_plan_sha256': PLAN, 'data_mount': {'source': '/d'}}
    args = (controller, copy, runtime, report, [PURGE, PURGE], {'data_directory': '/d'}, relation, state)
    kwargs = dict(controller_alive=lambda: None, stop=SimpleNamespace(is_set=lambda: False), max_wal_size=1)
    if relation == 'economy_opportunity' and recalibration == 'unverified':
        with pytest.raises(ValueError, match='n_distinct_recalibration_plan_unverified'):
            dispatch._drop(*args, **kwargs)
        assert dropped == []
        assert report['next_admissible_mode']['mode'] == 'swap-economy-opportunity'
    else:
        dispatch._drop(*args, **kwargs)
        assert dropped == ['drop']
        assert report['result'] == 'retired_relation_dropped'
    assert calls == (['economy_opportunity'] if relation == 'economy_opportunity' else [])


def test_swap_back_of_the_opportunity_is_one_owner_transaction_restoring_only_n_distinct(copy):
    sql = copy.SWAP_BACK_OPPORTUNITY_SQL
    assert sql.startswith('SET default_transaction_read_only=off;\nBEGIN;\n') and sql.rstrip().endswith('COMMIT;')
    assert sql.count('BEGIN;') == 1 and sql.count('COMMIT;') == 1
    body = sql[sql.index('BEGIN;'):]
    assert body.index("SET LOCAL statement_timeout='8000ms';") < body.index('DO $restore$') < body.index(
        'SET LOCAL ROLE v3_derived_purge_executor;') < body.index("v3_meta.purge_copy_swap_back(%(purge_id)s::uuid,'economy_opportunity')")
    assert "WHERE attrelid='v3_retired.economy_opportunity'::regclass AND attname='system_id64'" in sql
    assert 'RESET (n_distinct, n_distinct_inherited)' in sql
    assert "IF o.option_name NOT IN ('n_distinct','n_distinct_inherited') THEN" in sql
    # The only identifiers are fixed; option text comes from the catalog via %I/%L.
    assert "format('ALTER TABLE v3_derived.economy_opportunity ALTER COLUMN system_id64 SET (%I = %L)'" in sql
    assert '%(relation)s' not in sql


def test_n_distinct_option_text_matches_the_alter_literal(copy):
    assert copy.n_distinct_option(0.13) == 'n_distinct=-0.130000'
    assert copy.attoptions_list(None) == [] and copy.attoptions_list(['b=1', 'a=2']) == ['a=2', 'b=1']
    with pytest.raises(ValueError, match='attoptions_observation_invalid'):
        copy.attoptions_list('n_distinct=-0.13')


# --- long phases see their backend only after it is set up (Codex 4379797609) ---

def test_long_phase_callback_never_runs_before_its_backend_exists(controller, copy, monkeypatch):
    from contextlib import contextmanager
    dispatch = _dispatch()
    monkeypatch.setattr(dispatch, 'PROGRESS_INTERVAL_SECONDS', 0)
    monkeypatch.setattr(dispatch, '_wait', lambda *a, **k: None)
    monkeypatch.setattr(dispatch, '_measure', lambda *a, **k: {'filesystem_free_bytes': 1})
    identity = {'backend_pid': 4242, 'backend_start': '2026-10-27T10:00:00+00:00'}
    observed = []
    @contextmanager
    def phase_backend(c, runtime, timeout_ms, *, on_wait=None):
        on_wait()  # the original defect: set-up queries ran the caller's callback
        backend = SimpleNamespace(identity=identity)
        def query(sql, params=None, *, write=False):
            for _ in range(3):
                on_wait()
            return {'event': 5}
        backend.query = query
        yield backend
    monkeypatch.setattr(dispatch, 'phase_backend', phase_backend)
    original = controller._load
    monitor = SimpleNamespace(start_copy=lambda *a, **k: 'unit', copy_condition=lambda unit: None, copy_detail=lambda unit: None)
    monkeypatch.setattr(controller, '_load', lambda name, path=None: monitor if name == 'v3_purge_rewrite_monitor'
                        else (original(name, path) if path else original(name)))
    def query(sql, params=None, *, write=False):
        if sql == copy.PROGRESS_SQL:
            observed.append(params)
            return {'activity': {'state': 'active'}}
        if sql == copy.TEMP_FILE_LIMIT_PRIVILEGE_SQL:
            return {'can_set_temp_file_limit': True}
        if sql == copy.WAL_LAG_SQL:
            return {'wal_lsn': '0/10'}
        if sql == copy.WAL_DELTA_SQL:
            return {'bytes': 0}
        raise AssertionError(sql[:80])
    runtime = SimpleNamespace(query=query, deadline=float('inf'), workers=lambda: True)
    report = {'runner_state': {}}
    result = dispatch._long_phase(controller, copy, runtime, report, phase='verify', sql=copy.VERIFY_SQL,
                                  params={'purge_id': PURGE, 'relation': 'system_search'}, relation='system_search',
                                  ids=[PURGE, PURGE], identity={'data_directory': '/d'}, controller_alive=lambda: None,
                                  stop=SimpleNamespace(is_set=lambda: False), required_bytes=1, max_wal_size=1)
    assert result == {'event': 5}
    assert observed and all(item == {'backend_pid': '4242', 'backend_start': '2026-10-27T10:00:00+00:00'}
                            for item in observed)
    assert report['copy_progress']['phase'] == 'verify' and report['copy_steps'][-1]['phase'] == 'verify'


def test_long_phase_admits_on_the_reservation_but_watches_only_the_floor(controller, copy, monkeypatch):
    """Admission needs floor + growth + temp + WAL; once running, the phase is
    meant to consume that reservation, so the watchdog guards only the floor
    (PR #894 review 4382256472). Holding the whole reservation at runtime would
    cancel a phase admitted with a little headroom as soon as it used it."""
    from contextlib import contextmanager
    dispatch = _dispatch()
    monkeypatch.setattr(dispatch, '_wait', lambda *a, **k: None)
    admitted = []
    monkeypatch.setattr(dispatch, '_measure', lambda c, copy_, runtime, identity, report, required:
                        admitted.append(required) or {'filesystem_free_bytes': required + 1})

    @contextmanager
    def phase_backend(c, runtime, timeout_ms, *, on_wait=None):
        yield SimpleNamespace(identity={'backend_pid': 1, 'backend_start': '2026-10-27T10:00:00+00:00'},
                              query=lambda sql, params=None, *, write=False: {'event': 9})
    monkeypatch.setattr(dispatch, 'phase_backend', phase_backend)
    watched = []
    monitor = SimpleNamespace(start_copy=lambda c, runtime, spec, identity, report: watched.append(spec) or 'unit',
                              copy_condition=lambda unit: None, copy_detail=lambda unit: None)
    original = controller._load
    monkeypatch.setattr(controller, '_load', lambda name, path=None: monitor if name == 'v3_purge_rewrite_monitor'
                        else (original(name, path) if path else original(name)))

    def query(sql, params=None, *, write=False):
        if sql == copy.TEMP_FILE_LIMIT_PRIVILEGE_SQL:
            return {'can_set_temp_file_limit': True}
        if sql == copy.WAL_LAG_SQL:
            return {'wal_lsn': '0/10'}
        if sql == copy.WAL_DELTA_SQL:
            return {'bytes': 0}
        return {}
    runtime = SimpleNamespace(query=query, deadline=float('inf'), workers=lambda: True)
    reservation = copy.long_phase_required('index_build', index_bytes=40_000_000_000,
                                           max_wal_size_bytes=32 * 1024 ** 3)
    assert reservation > copy.FLOOR_BYTES
    dispatch._long_phase(controller, copy, runtime, {'runner_state': {}}, phase='index_build',
                         sql=copy.VERIFY_SQL, params={'purge_id': PURGE, 'relation': 'system_search'},
                         relation='system_search', ids=[PURGE, PURGE], identity={'data_directory': '/d'},
                         controller_alive=lambda: None, stop=SimpleNamespace(is_set=lambda: False),
                         required_bytes=reservation, max_wal_size=32 * 1024 ** 3)
    assert admitted == [reservation]
    assert [spec['required_free_bytes'] for spec in watched] == [copy.FLOOR_BYTES]


def test_phase_backend_runs_its_set_up_queries_without_the_callback():
    source = (ROOT / 'scripts/operator/lib/v3_purge_copy_dispatch.py').read_text()
    setup = source[source.index('            backend = Backend()'):source.index('            yield backend')]
    assert setup.count('wait=_no_wait') == 2
    long_phase = source[source.index('def _long_phase('):source.index('def _retrying(')]
    assert "active['backend'] = backend" in long_phase and 'backend = active.get' in long_phase


# --- a still-running earlier copy backend refuses before any write -------------

@pytest.mark.parametrize(('observed', 'refused'), [
    ({'lock_holders': 0, 'copy_statements': 0}, False), ({'lock_holders': 1, 'copy_statements': 0}, True),
    ({'lock_holders': 0, 'copy_statements': 2}, True), ({'lock_holders': None, 'copy_statements': 0}, 'invalid'),
    (None, 'invalid')])
def test_competing_copy_backend_refuses_retryably(copy, observed, refused):
    dispatch = _dispatch()
    runtime = SimpleNamespace(query=lambda sql, params=None, **k: observed if sql == copy.COMPETING_COPY_SQL
                              else pytest.fail(sql[:40]))
    report = {}
    if refused is True:
        with pytest.raises(ValueError, match='competing_purge_copy_backend_active'):
            dispatch._require_no_competitor(copy, runtime, report)
        assert report['next_admissible_mode']['mode'] == 'status'
    elif refused == 'invalid':
        with pytest.raises(ValueError, match='competing_copy_observation_invalid'):
            dispatch._require_no_competitor(copy, runtime, report)
    else:
        dispatch._require_no_competitor(copy, runtime, report)
        assert report['competing_copy_backends'] == observed
    assert copy.COMPETING_COPY_SQL.startswith('BEGIN READ ONLY;') and 'objid=764019001' in copy.COMPETING_COPY_SQL
    source = (ROOT / 'scripts/operator/lib/v3_purge_copy_dispatch.py').read_text()
    body = source[source.index('def dispatch('):source.index('def _copy(')]
    assert body.index('_require_no_competitor(copy, runtime, report)') < body.index('_controller(c, report')
