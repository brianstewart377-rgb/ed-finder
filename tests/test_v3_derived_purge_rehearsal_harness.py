"""Disposable harness contracts without a Docker daemon or database."""
import hashlib
import json
import queue
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
    # Post-go-live: the surviving generation holds one published Search row per
    # system, as production does, alongside the same count of archetype rows.
    assert counts['system_search']['ratings_v4_prod_p4_parallel_v1'] == systems
    assert counts['system_search']['ratings_v4_prod_p4_opt1'] == systems
    assert figures.expected_survivor_products(proportion) == {'system_search': systems, 'system_archetype': systems}
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
    for statement in (seed.BODY, seed.ECONOMY, seed.VECTOR, seed.SEARCH, seed.ARCHETYPE):
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
                   row_counts=counts, survivor_products=figures.expected_survivor_products(proportion),
                   lifecycle_receipt_sha256=hashlib.sha256(harness.RECEIPT_PATH.read_bytes()).hexdigest(),
                   settings={'autovacuum': 'on'}, gate_10_crash_rehearsal_passed=False,
                   crash_scenarios={name: {'passed': False} for name in harness.CRASH_SCENARIOS},
                   per_relation={relation: figures.relation_figures(
                       {**raw, 'deleted_rows': sum(counts[relation][key] for key in harness.controller.TARGETS)},
                       proportion) for relation in harness.RELATIONS})
    search = receipt['per_relation']['system_search']
    search['survivor_target_split'] = figures.search_split_figures(dict(
        survivor_rows=counts['system_search']['ratings_v4_prod_p4_parallel_v1'],
        target_rows=search['raw']['deleted_rows'], heap_index_bytes_before_delete=65536,
        survivor_heap_index_bytes_after_rewrite=200 * 8192, governed_rewrite_seconds=0.1,
        governed_rewrite_peak_bytes=8192, survivor_rewrite_seconds=0.05, survivor_rewrite_peak_bytes=4096,
        target_delete_seconds=1.0), proportion)
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


class _ObserverLogins:
    """Fake `docker exec -i ... psql` observer logins speaking one line per query.

    Records when each login starts relative to the action's own process, and
    any one-shot psql login made through Harness.docker while it runs.
    """

    def __init__(self, instance, monkeypatch):
        self.running = threading.Event()
        self.users = []
        self.during_action = []
        # Set by any batch-ledger sample taken while the action runs.
        self.answered_during_action = threading.Event()
        self.closed = []
        logins = self

        class Process:
            def __init__(self, argv, **kwargs):
                assert argv[:5] == ['docker', '--context', 'default', 'exec', '-i']
                assert argv[5] == instance.container and argv[6] == 'psql'
                logins.users.append(argv[argv.index('-U') + 1])
                if logins.running.is_set():
                    logins.during_action.append(argv)
                self.answers = queue.Queue()
                self.stdin = SimpleNamespace(write=self.write, flush=lambda: None, close=self.close)
                self.stdout = iter(self.answers.get, None)
                self.returncode = None

            def write(self, text):
                assert text == harness.BATCH_LEDGER_SQL + '\n'
                if logins.running.is_set():
                    logins.answered_during_action.set()
                self.answers.put('7\n')

            def close(self):
                logins.closed.append(logins.running.is_set())
                self.answers.put(None)

            def wait(self, timeout=None):
                self.returncode = 0
                return 0

            def kill(self):
                pass

        monkeypatch.setattr(harness.subprocess, 'Popen', Process)

        def docker(*arguments, **kwargs):
            if 'psql' in arguments:
                logins.users.append(arguments[arguments.index('-U') + 1])
                if logins.running.is_set():
                    logins.during_action.append(arguments)
                    logins.answered_during_action.set()
                return '7'
            raise AssertionError('unexpected docker call')

        instance.docker = docker


def test_delete_sampling_starts_no_database_login_while_the_action_runs(tmp_path, monkeypatch):
    # 016 refuses a batch (P0001 'competing writing transaction') while any
    # other client backend has state NULL, which is how a login looks while it
    # starts. Smoke run 40032512857 stopped on exactly that: the sampler's own
    # per-sample observer logins raced delete-economy-opportunity's batches.
    instance = harness.Harness('tiny', 'observer-login-test', tmp_path)
    instance.free_bytes = lambda: 1_000_000
    monkeypatch.setattr(harness, 'SAMPLE_SECONDS', 0.001)
    logins = _ObserverLogins(instance, monkeypatch)

    def command(*arguments, **kwargs):
        logins.running.set()
        try:
            assert logins.answered_during_action.wait(timeout=5), 'no batch sample while the action ran'
        finally:
            logins.running.clear()
        return SimpleNamespace(returncode=0, stdout=json.dumps(evidence.seal({'status': 'success'})))

    instance.command = command
    report, _, _, _, count = instance.action('delete-economy-opportunity', measure=True)
    assert report['status'] == 'success' and count >= 3
    assert logins.during_action == []
    # One observer login, opened before and closed after the action.
    assert logins.users == [harness.OBSERVER_USER]
    assert logins.closed == [False]
    receipt = json.loads((tmp_path / '001-delete-economy-opportunity-filesystem-samples.json').read_text())
    assert len(receipt['batch_event_and_free_bytes_samples']) >= 3
    assert {event for event, _ in receipt['batch_event_and_free_bytes_samples']} == {7}


def test_rewrite_sampling_opens_no_observer_login(tmp_path, monkeypatch):
    instance = harness.Harness('tiny', 'observer-rewrite-test', tmp_path)
    instance.free_bytes = lambda: 1_000_000
    logins = _ObserverLogins(instance, monkeypatch)
    instance.command = lambda *_args, **_kwargs: SimpleNamespace(
        returncode=0, stdout=json.dumps(evidence.seal({'status': 'success'})))
    instance.action('rewrite-economy-opportunity', measure=True)
    assert logins.users == []


def test_sampling_survives_application_session_recycle(tmp_path, monkeypatch):
    # The single sampling login is the observer role, never the application
    # role whose sessions the writer fence recycles mid-action.
    instance = harness.Harness('tiny', 'observer-test', tmp_path)
    instance.free_bytes = lambda: 1_000_000
    monkeypatch.setattr(harness, 'SAMPLE_SECONDS', 0.001)
    logins = _ObserverLogins(instance, monkeypatch)

    def command(*arguments, **kwargs):
        logins.running.set()
        try:
            assert logins.answered_during_action.wait(timeout=5), 'no concurrent sample observed'
        finally:
            logins.running.clear()
        return SimpleNamespace(returncode=0, stdout=json.dumps(evidence.seal({'status': 'success'})))

    instance.command = command
    report, _, _, _, count = instance.action('delete-system-search', measure=True)
    assert report['status'] == 'success' and count >= 3
    assert logins.users == [harness.OBSERVER_USER]
    assert harness.OBSERVER_USER != harness.USER


def test_dead_observer_session_stops_sampling(tmp_path, monkeypatch):
    instance = harness.Harness('tiny', 'observer-dead-test', tmp_path)
    instance.free_bytes = lambda: 1_000_000
    monkeypatch.setattr(harness, 'OBSERVER_QUERY_SECONDS', 1)

    class Dead:
        def __init__(self, argv, **kwargs):
            self.stdin = SimpleNamespace(write=lambda text: None, flush=lambda: None, close=lambda: None)
            self.stdout = iter(())

        def wait(self, timeout=None):
            return 3

    monkeypatch.setattr(harness.subprocess, 'Popen', Dead)
    instance.command = lambda *_args, **_kwargs: pytest.fail('action must not start without a sampling session')
    with pytest.raises(RuntimeError, match='^observer_session_failed$'):
        instance.action('delete-system-search', measure=True)


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


def test_seed_publishes_survivor_products_through_015_after_base_publication(tmp_path):
    instance = harness.Harness('tiny', 'seed-order-test', tmp_path)
    executed = []
    def sql(statement, parameters=None):
        executed.append((statement, dict(parameters or {})))
        if statement == seed.SURVIVOR_PUBLICATION:
            rows = instance.counts['system_search'][harness.controller.PUBLISHED_KEY]
            return json.dumps({'products': {code: {'version': version, 'state': 'READY', 'status': 'VERIFIED',
                                                   'expected_rows': rows, 'published': True}
                                            for code, version in seed.SURVIVOR_PRODUCTS},
                               'audit_rows': 2, 'search_rows': rows, 'archetype_rows': rows,
                               'app_search_rows': rows, 'app_archetype_rows': rows})
        if statement.startswith('SELECT COALESCE(json_object_agg'):
            relation = statement.split('FROM v3_derived.')[1].split()[0]
            identities = {key: value[0] for key, value in harness.controller.TARGETS.items()}
            identities[harness.controller.PUBLISHED_KEY] = harness.controller.PUBLISHED_ID
            return json.dumps({identities[key]: count for key, count in instance.counts[relation].items() if count})
        return ''
    instance.sql = sql
    instance.seed()
    order = [statement for statement, _ in executed]
    published = harness.controller.PUBLISHED_ID
    survivor_search = [index for index, (statement, parameters) in enumerate(executed)
                       if statement == seed.SEARCH and parameters.get('generation') == published]
    base_publish = order.index(seed.PUBLISH)
    products_publish = order.index(seed.PUBLISH_PRODUCTS)
    # Survivor Search and archetype rows are written only after the base is
    # PUBLISHED, and the products are published only after both are READY.
    assert survivor_search and min(survivor_search) > base_publish
    archetype = [index for index, statement in enumerate(order) if statement == seed.ARCHETYPE]
    assert archetype and min(archetype) > base_publish and max(archetype) < products_publish
    ready = [index for index, (statement, parameters) in enumerate(executed) if statement == seed.PRODUCT_READY]
    assert [executed[index][1]['product'] for index in ready] == ['system_search', 'system_archetype']
    assert max(ready) < products_publish < order.index(seed.SURVIVOR_PUBLICATION)
    registered = [parameters for statement, parameters in executed if statement == seed.SURVIVOR_PRODUCT]
    assert [(item['product'], item['version'], item['rows']) for item in registered] == [
        ('system_search', 'v3-system-search-2', 200), ('system_archetype', 'v3-archetype-4', 200)]
    # The opt1 target keeps its own unpublished v3-system-search-1 product.
    assert [parameters['generation'] for statement, parameters in executed if statement == seed.SEARCH_PRODUCT] == [
        harness.controller.TARGETS['ratings_v4_prod_p4_opt1'][0]]


def test_seed_refuses_unproven_survivor_publication(tmp_path):
    instance = harness.Harness('tiny', 'seed-refusal-test', tmp_path)
    def sql(statement, parameters=None):
        if statement == seed.SURVIVOR_PUBLICATION:
            return json.dumps({'products': {}, 'audit_rows': 0})
        if statement.startswith('SELECT COALESCE(json_object_agg'):
            relation = statement.split('FROM v3_derived.')[1].split()[0]
            identities = {key: value[0] for key, value in harness.controller.TARGETS.items()}
            identities[harness.controller.PUBLISHED_KEY] = harness.controller.PUBLISHED_ID
            return json.dumps({identities[key]: count for key, count in instance.counts[relation].items() if count})
        return ''
    instance.sql = sql
    with pytest.raises(ValueError, match='seed_survivor_publication_unproven'):
        instance.seed()


def test_journey_records_survivor_and_target_search_rewrite_separately(tmp_path, monkeypatch):
    instance = harness.Harness('tiny', 'journey-test', tmp_path)
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'reviewed_plan': {'delete': {relation: {'batch_limit': 10_000}
                                                             for relation in harness.RELATIONS}}}))
    remaining = {relation: sum(instance.counts[relation][key] for key in harness.controller.TARGETS)
                 for relation in harness.RELATIONS}
    current = {}
    def action(mode, *, measure=False, allow_partial_delete=False):
        report = {'content_sha256': 'c' * 64, 'statement_durations': []}
        if mode.startswith('delete-'):
            relation = harness.controller.RELATIONS[mode.removeprefix('delete-')]
            current['relation'] = relation
            report.update(rows_affected_this_run=remaining[relation], statement_durations=[
                {'kind': 'payload_batch', 'duration_seconds': 0.5}])
            remaining[relation] = 0
            return report, plan, 2.0, 100, 3
        if mode.startswith('rewrite-'):
            report['statement_durations'] = [{'kind': 'vacuum_full_analyze', 'duration_seconds': 0.4}]
            return report, plan, 0.6, 4096, 3
        return report, plan, 0.1, 0, 0
    sizes = iter([65536, 200 * 8192] + [65536] * 3)
    def sql(statement, parameters=None):
        if statement.startswith('SELECT pg_total_relation_size'):
            return str(next(sizes))
        if statement.startswith('SELECT count(*)'):
            return str(remaining[statement.split('FROM v3_derived.')[1].split()[0]])
        return ''
    monkeypatch.setattr(instance, 'action', action)
    monkeypatch.setattr(instance, 'sql', sql)
    # The survivor-only control rewrite measures a larger peak than the
    # governed one: the plan must carry the larger (fail-closed).
    monkeypatch.setattr(instance, 'survivor_control_rewrite', lambda: (0.3, 6000, 4))
    measurements = instance.journey()
    search = measurements['system_search']
    split = search['survivor_target_split']
    assert split['raw']['survivor_rows'] == instance.counts['system_search']['ratings_v4_prod_p4_parallel_v1'] == 200
    assert split['raw']['governed_rewrite_peak_bytes'] == 4096
    assert split['survivor']['rewrite_seconds'] == 0.3 and split['survivor']['rewrite_peak_bytes'] == 6000
    assert split['target']['rewrite_seconds'] == pytest.approx(0.1) and split['target']['rewrite_peak_bytes'] == 0
    assert search['raw']['rewrite_peak_bytes'] == 6000
    assert search['production']['rewrite_peak_bytes'] == split['production']['rewrite_peak_bytes']
    assert all('survivor_target_split' not in measurements[relation]
               for relation in harness.RELATIONS if relation != 'system_search')
    # The receipt validator accepts exactly these recorded figures.
    counts = instance.counts
    receipt = dict(schema_version=figures.SCHEMA, operation='v3-derived-purge-rehearsal', status='stopped',
                   source_git_sha='a' * 40, scale='tiny', **figures.code_identity(), image_digest=harness.IMAGE,
                   production_proportion=instance.proportion, row_counts=counts,
                   survivor_products=instance.survivors, settings={'autovacuum': 'on'},
                   gate_10_crash_rehearsal_passed=False, crash_scenarios={}, per_relation=measurements)
    assert figures.validate(receipt, production=False) is receipt
