"""Disposable harness contracts without a Docker daemon or database."""
import hashlib
import json
import threading
from types import SimpleNamespace

import pytest

from scripts.operator.lib import f2d_evidence as evidence
from scripts.operator.lib import v3_purge_rehearsal_receipt as figures
from scripts.rehearsal import v3_derived_purge_rehearsal as harness
from scripts.rehearsal import v3_derived_purge_seed as seed


@pytest.mark.parametrize('scale,systems', [('tiny', 200), ('smoke', 100_000), ('one_percent', 2_000_000)])
def test_seed_uses_committed_generation_and_relation_proportions(scale, systems):
    proportion, counts = harness.seeding_proportions(scale)
    assert proportion == systems / 198_528_286
    assert counts['system_rating_vector']['ratings_v4_prod_p4_opt1'] == systems
    assert counts['system_search']['ratings_v4_prod_p4'] == 0
    assert counts['system_search']['ratings_v4_prod_p4_parallel_v1'] == 0
    assert counts['body_mechanics']['ratings_v4_prod_p4_opt1'] == round(577_709_320 * proportion)
    assert counts['economy_opportunity']['ratings_v4_prod_p4_opt1'] == round(740_001_532 * proportion)
    assert counts['system_rating_vector']['ratings_v4_prod_p4'] == max(1, round(4_938_000 * proportion))


@pytest.mark.parametrize('samples,expected', [([], 0), ([100], 0), ([100, 90, 110, 70], 40),
                                              ([100, 110, 120], 0), ([100, 95, 50, 90, 40], 60)])
def test_drawdown_conservatively_bounds_each_batch(samples, expected):
    assert harness.maximum_drawdown(samples) == expected


@pytest.mark.parametrize('bad', [[None], [-1], [1.5], [True]])
def test_drawdown_refuses_unknown_samples(bad):
    with pytest.raises(ValueError, match='invalid_free_bytes_sample'):
        harness.maximum_drawdown(bad)


def test_sql_data_bindings_do_not_interpolate_request_text():
    hostile = "x'); DROP DATABASE other; --"
    bound = harness.bind_sql('SELECT %(value)s, (n-1)%%%(systems)s::bigint;',
                             {'value': hostile, 'systems': 100})
    assert hostile not in bound
    assert hostile.encode().hex() in bound
    assert '(n-1)%convert_from' in bound
    assert '%(' not in bound
    with pytest.raises(ValueError, match='unbound_parameter'):
        harness.bind_sql('SELECT %(missing)s', {})


def test_seed_keeps_constraints_triggers_and_bounded_bulk_writes():
    sql = '\n'.join(value for value in vars(seed).values() if isinstance(value, str))
    assert 'DISABLE TRIGGER' not in sql
    assert 'session_replication_role' not in sql
    assert harness.SEED_BATCH_ROWS <= 100_000
    for statement in (seed.BODY, seed.ECONOMY, seed.VECTOR, seed.SEARCH):
        assert '%(first)s' in statement and '%(last)s' in statement
        bound = harness.bind_sql(statement, dict(first=1, last=10, systems=10, bodies=20, generation='uuid'))
        assert '%%' not in bound


def test_receipt_seals_raw_and_margin_figures_without_promoting_missing_crashes(tmp_path):
    proportion, counts = harness.seeding_proportions('tiny')
    raw = dict(deleted_rows=100, delete_seconds=1.0, batch_limit=10_000,
               batch_peak_bytes=0, rewrite_seconds=0.1, rewrite_peak_bytes=8192,
               heap_index_bytes=65536, autovacuum_budget_source='heap_plus_index_lower_bound')
    receipt = dict(schema_version=figures.SCHEMA, operation='v3-derived-purge-rehearsal',
                   status='success', source_git_sha='a'*40, scale='tiny',
                   **figures.code_identity(),
                   image_digest=harness.IMAGE, production_proportion=proportion,
                   row_counts=counts, lifecycle_receipt_sha256=hashlib.sha256(harness.RECEIPT_PATH.read_bytes()).hexdigest(),
                   settings={'autovacuum': 'on'}, gate_10_crash_rehearsal_passed=False,
                   crash_scenarios={name: {'passed': False} for name in harness.CRASH_SCENARIOS},
                   per_relation={relation: figures.relation_figures(
                       {**raw, 'deleted_rows': sum(counts[relation][key] for key in harness.controller.TARGETS)},
                       proportion) for relation in harness.RELATIONS})
    sealed = evidence.seal(receipt)
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(sealed))
    assert evidence.load_sealed(path) == sealed
    figures.validate(sealed, production=False)
    assert sealed['per_relation']['system_search']['margin_applied']['rewrite_peak_bytes'] > 8192
    with pytest.raises(ValueError):
        figures.validate(sealed, production=True)


def test_harness_has_no_external_target_or_credential_arguments():
    text = harness.Path(harness.__file__).read_text()
    assert "'--network', 'none'" in text
    assert "'POSTGRES_HOST_AUTH_METHOD=trust'" in text
    assert 'DATABASE_URL' not in text
    assert "'--host'" not in text
    assert '@sha256:' in harness.IMAGE
    assert len(harness.IMAGE.rsplit('@sha256:', 1)[1]) == 64


def test_container_and_volume_have_token_and_workflow_cleanup_labels(tmp_path):
    instance = harness.Harness('tiny', 'test-123', tmp_path)
    calls = []
    instance.docker = lambda *args, **kwargs: calls.append(args) or ''
    instance.command = lambda *args, **kwargs: type('Result', (), {'returncode': 0})()
    instance.sql = lambda *args, **kwargs: None
    instance.start()
    for arguments in calls[:2]:
        assert 'edfinder.purge-rehearsal=' + instance.token in arguments
        assert 'io.ed-finder.purge-rehearsal=true' in arguments
        assert 'io.ed-finder.purge-rehearsal.run-id=test-123' in arguments
    assert harness.re.fullmatch('edfinder-purge-rehearsal-[a-f0-9]{32}', instance.container)
    assert instance.volume == instance.container + '-data'
    assert '--hostname' in calls[1] and instance.container in calls[1]


def test_readiness_waits_for_the_final_server_over_loopback_tcp(tmp_path):
    # initdb's temporary server answers only on the Unix socket; probing over
    # 127.0.0.1 cannot mistake it for the restarted final server.
    instance = harness.Harness('tiny', 'ready-test', tmp_path)
    probes = []
    instance.docker = lambda *args, **kwargs: ''
    instance.sql = lambda *args, **kwargs: None
    def command(arguments, **kwargs):
        probes.append(arguments)
        return SimpleNamespace(returncode=0 if len(probes) > 2 else 2)
    instance.command = command
    harness.time.sleep, original = (lambda _seconds: None), harness.time.sleep
    try:
        instance.start()
    finally:
        harness.time.sleep = original
    assert probes == [['docker', '--context', 'default', 'exec', instance.container,
                       'pg_isready', '-h', '127.0.0.1', '-p', '5432',
                       '-U', harness.USER, '-d', harness.DATABASE]] * 3


def test_batch_growth_uses_boundaries_without_counting_accumulated_prior_wal():
    observations = [(1, 1000), (1, 900), (2, 850), (2, 800), (3, 750), (3, 700)]
    assert harness.batch_peak_growth(observations) == 150


def test_action_executes_real_entrypoint_and_preserves_sealed_statement_measurements(tmp_path):
    instance = harness.Harness('tiny', 'action-test', tmp_path)
    report = evidence.seal({'status': 'success', 'statement_durations': [
        {'statement_sha256': 'a' * 64, 'kind': 'query', 'duration_seconds': 0.1}]})
    calls = []
    def command(arguments, **kwargs):
        calls.append(arguments)
        return SimpleNamespace(returncode=0, stdout=json.dumps(report))
    instance.command = command
    actual, path, *_ = instance.action('plan')
    assert actual == report
    assert evidence.load_sealed(path) == report
    assert calls[0][:3] == ['bash', str(harness.ROOT / 'scripts/operator/actions/v3-derived-generation-purge.sh'), 'plan']
    assert calls[0][-4:] == ['--rehearsal-container', instance.container, '--rehearsal-token', instance.token]
    assert instance.statements[0]['duration_seconds'] == 0.1
    assert instance.statements[-1]['kind'] == 'action_wall_clock'


def test_sampling_survives_application_session_recycle(tmp_path, monkeypatch):
    instance = harness.Harness('tiny', 'observer-test', tmp_path)
    recycling = threading.Event()
    sampled_during_recycle = threading.Event()
    observed_users = []
    instance.free_bytes = lambda: 1_000_000
    monkeypatch.setattr(harness, 'SAMPLE_SECONDS', 0.001)

    def docker(*arguments, **kwargs):
        user = arguments[arguments.index('-U') + 1]
        observed_users.append(user)
        if recycling.is_set():
            if user == harness.USER:
                raise RuntimeError('application_session_recycled')
            sampled_during_recycle.set()
        return '1'

    def command(*arguments, **kwargs):
        recycling.set()
        assert sampled_during_recycle.wait(timeout=5), 'no concurrent sample observed'
        recycling.clear()
        return SimpleNamespace(returncode=0, stdout=json.dumps(evidence.seal({'status': 'success'})))

    instance.docker = docker
    instance.command = command
    report, _, _, _, count = instance.action('delete-system-search', measure=True)
    assert report['status'] == 'success' and count >= 3
    assert observed_users and set(observed_users) == {harness.OBSERVER_USER}
    assert harness.OBSERVER_USER != harness.USER


def test_cleanup_unknown_inspect_requires_successful_absence_probe(tmp_path):
    instance = harness.Harness('tiny', 'cleanup-test', tmp_path)
    instance.command = lambda *_args, **_kwargs: type('Result', (), {'returncode': 1})()
    def unavailable(*_args, **_kwargs):
        raise RuntimeError('daemon_unavailable')
    instance.docker = unavailable
    with pytest.raises(RuntimeError, match='daemon_unavailable'):
        instance.cleanup()


def test_cleanup_refuses_resource_remaining_after_failed_inspect(tmp_path):
    instance = harness.Harness('tiny', 'cleanup-test', tmp_path)
    instance.command = lambda *_args, **_kwargs: type('Result', (), {'returncode': 1})()
    instance.docker = lambda *_args, **_kwargs: instance.container
    with pytest.raises(RuntimeError, match='cleanup_resource_still_present'):
        instance.cleanup()


@pytest.mark.parametrize('missing', (None, 'integrity_failed', 'runner_state', 'writer_restore', 'failed_stop_recorded'))
def test_only_a_proven_nonintegrity_budget_stop_can_resume(tmp_path, missing):
    instance = harness.Harness('tiny', 'resume-test', tmp_path)
    report = dict(status='stopped', failures=['delete_wall_clock_budget_exhausted'],
                  integrity_failed=False, runner_state={'loop_exited': True},
                  writer_restore={'verified': True}, failed_stop_recorded=[1, 2])
    if missing:
        del report[missing]
    sealed = evidence.seal(report)
    instance.command = lambda *_args, **_kwargs: type('Result', (), {
        'returncode': 1, 'stdout': json.dumps(sealed)})()
    if missing:
        with pytest.raises(RuntimeError, match='real_action_refused'):
            instance.action('delete-system-search', allow_partial_delete=True)
    else:
        observed, *_ = instance.action('delete-system-search', allow_partial_delete=True)
        assert observed['status'] == 'stopped'
        assert observed['failures'] == ['delete_wall_clock_budget_exhausted']
        with pytest.raises(RuntimeError, match='real_action_refused'):
            instance.action('delete-system-search')


def test_refused_action_records_its_own_identifier_failure_codes(tmp_path):
    instance = harness.Harness('tiny', 'refused-test', tmp_path)
    sealed = evidence.seal({'status': 'stopped', 'failures': [
        'bounded_command_failed', 'purge_unresolved_AUTOVACUUM_DISABLED,purge_unresolved_WRITER_FENCE_ENABLED',
        'SELECT secret FROM t', {'not': 'a code'}, 'x' * 121]})
    instance.command = lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=json.dumps(sealed))
    with pytest.raises(RuntimeError, match='real_action_refused_plan'):
        instance.action('plan')
    assert instance.refused_action == {'mode': 'plan', 'report': '001-plan.json', 'failures': [
        'bounded_command_failed', 'purge_unresolved_AUTOVACUUM_DISABLED,purge_unresolved_WRITER_FENCE_ENABLED']}



@pytest.mark.parametrize(('crash_passed', 'cleanup_fails', 'status', 'phase'), [
    (True, False, 'success', None),
    (False, False, 'stopped', 'crash_scenarios'),
    (True, True, 'stopped', 'cleanup'),
])
def test_every_stopped_outcome_records_its_phase(tmp_path, monkeypatch, capsys,
                                                 crash_passed, cleanup_fails, status, phase):
    from scripts.rehearsal import v3_purge_crashes as crashes
    for name in ('start', 'migrate', 'seed'):
        monkeypatch.setattr(harness.Harness, name, lambda self: None)
    monkeypatch.setattr(harness.Harness, 'sql', lambda self, *args, **kwargs: '{}')
    monkeypatch.setattr(harness.Harness, 'journey', lambda self: {})
    calls = []
    def cleanup(self):
        calls.append(1)
        if cleanup_fails and len(calls) > 1:
            raise RuntimeError('cleanup')
    monkeypatch.setattr(harness.Harness, 'cleanup', cleanup)
    monkeypatch.setattr(crashes, 'run_crashes', lambda *args: {
        name: {'passed': crash_passed} for name in harness.CRASH_SCENARIOS})
    monkeypatch.setattr(harness.figures, 'validate', lambda *args, **kwargs: None)
    code = harness.main(['--scale', 'tiny', '--run-id', 'phase-test', '--output-dir', str(tmp_path)])
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == (0 if status == 'success' else 1)
    assert summary['status'] == status
    assert summary['stopped_phase'] == phase
    sealed = evidence.load_sealed(tmp_path / 'rehearsal-receipt.json')
    assert sealed.get('stopped_phase') == phase


@pytest.mark.parametrize(('mode', 'plan', 'verification'), [
    ('plan', False, False), ('status', False, True), ('authorize', True, False),
    ('verify-system-archetype-empty', True, False), ('complete', True, True),
    ('delete-system-search', True, True), ('rewrite-system-search', True, True),
    ('abort-relation-system-search', True, True), ('restore-services', True, True),
])
def test_action_arguments_match_controller_admission(tmp_path, mode, plan, verification):
    # The controller refuses plan arguments for status/plan, and verification
    # arguments for authorize/verify (plan_/verification_arguments_not_admitted).
    instance = harness.Harness('tiny', 'argv-test', tmp_path)
    instance.plan = (tmp_path / 'plan.json', 'a' * 64)
    instance.verification = (tmp_path / 'verify.json', 'b' * 64)
    argv = instance.action_argv(mode)
    assert ('--plan' in argv) is plan and ('--plan-sha256' in argv) is plan
    assert ('--verification' in argv) is verification
    assert ('--verification-sha256' in argv) is verification
