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


@pytest.mark.parametrize('scale,systems', [('tiny', 200), ('smoke', 300_000), ('one_percent', 2_000_000)])
def test_seed_uses_committed_generation_and_relation_proportions(scale, systems):
    # Below about 200,000 systems the opportunity swap's plan proof cannot hold
    # (a hash join over the small table is genuinely cheaper); smoke and the
    # crash fixtures must stay above it.
    assert harness.SCALE_SYSTEMS['smoke'] >= 200_000
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


def _raw(counts, relation):
    return dict(copied_rows=counts[relation]['ratings_v4_prod_p4_parallel_v1'],
                target_rows=sum(counts[relation][key] for key in harness.controller.TARGETS),
                live_bytes_before=65536, copy_bytes=counts[relation]['ratings_v4_prod_p4_parallel_v1'] * 600,
                copy_peak_bytes=8192, temp_file_peak_bytes=0, temp_file_written_bytes=0, freed_bytes=40000,
                swap_attempts=1, finder_reads_during_swap=12, filesystem_sample_count=30,
                copy_seconds=0.5, index_build_seconds=0.1, vacuum_freeze_seconds=0.1, verify_seconds=0.1,
                fk_validation_seconds=0.05, swap_lock_hold_seconds=0.2, finder_read_stall_seconds=0.3,
                drop_seconds=0.1, wal_bytes={'chunk': 10, 'index_build': 1, 'vacuum_freeze': 1, 'verify': 0,
                                             'validate_fks': 0, 'drop': 1})


def test_receipt_seals_raw_and_margin_figures_without_promoting_missing_crashes(tmp_path):
    proportion, counts = harness.seeding_proportions('tiny')
    receipt = dict(schema_version=figures.SCHEMA, operation='v3-derived-purge-rehearsal', route=figures.ROUTE,
                   status='success', source_git_sha='a'*40, scale='tiny',
                   **figures.code_identity(),
                   image_digest=harness.IMAGE, production_proportion=proportion,
                   row_counts=counts, survivor_products=figures.expected_survivor_products(proportion),
                   lifecycle_receipt_sha256=hashlib.sha256(harness.RECEIPT_PATH.read_bytes()).hexdigest(),
                   settings={'autovacuum': 'on'}, gate_10_crash_rehearsal_passed=False,
                   crash_scenarios={name: {'passed': False} for name in harness.CRASH_SCENARIOS},
                   per_relation={relation: figures.relation_figures(_raw(counts, relation), proportion)
                                 for relation in harness.RELATIONS})
    sealed = evidence.seal(receipt)
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(sealed))
    assert evidence.load_sealed(path) == sealed
    figures.validate(sealed, production=False)
    assert sealed['per_relation']['system_search']['margin_applied']['copy_peak_bytes'] > 8192
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


def test_action_executes_real_entrypoint_and_preserves_sealed_statement_measurements(tmp_path):
    instance = harness.Harness('tiny', 'action-test', tmp_path)
    report = evidence.seal({'status': 'success', 'statement_durations': [
        {'statement_sha256': 'a' * 64, 'kind': 'query', 'duration_seconds': 0.1}]})
    calls = []
    def command(arguments, **kwargs):
        calls.append(arguments)
        return SimpleNamespace(returncode=0, stdout=json.dumps(report))
    instance.command = command
    outcome = instance.action('plan')
    assert outcome['report'] == report
    assert evidence.load_sealed(outcome['path']) == report
    assert calls[0][:3] == ['bash', str(harness.ROOT / 'scripts/operator/actions/v3-derived-generation-purge.sh'), 'plan']
    assert calls[0][-4:] == ['--rehearsal-container', instance.container, '--rehearsal-token', instance.token]
    assert instance.statements[0]['duration_seconds'] == 0.1
    assert instance.statements[-1]['kind'] == 'action_wall_clock'


class _ObserverLogins:
    """Fake `docker exec -i ... psql` observer logins speaking one line per query.

    Records when each login starts relative to the action's own process, and
    any one-shot psql login made through Harness.docker while it runs.
    """

    def __init__(self, instance, monkeypatch, *, answers=None):
        self.running = threading.Event()
        self.users = []
        self.during_action = []
        self.statements = []
        self.answered_during_action = threading.Event()
        self.closed = []
        logins = self
        answers = answers or {harness.TEMP_SAMPLE_SQL: '4096'}

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
                statement = text.rstrip('\n')
                assert statement in answers, statement
                logins.statements.append(statement)
                if logins.running.is_set():
                    logins.answered_during_action.set()
                self.answers.put(answers[statement] + '\n')

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
                return '7'
            raise AssertionError('unexpected docker call')

        instance.docker = docker


def _running_command(logins, report=None):
    def command(*arguments, **kwargs):
        logins.running.set()
        try:
            assert logins.answered_during_action.wait(timeout=5), 'no sample while the action ran'
        finally:
            logins.running.clear()
        return SimpleNamespace(returncode=0, stdout=json.dumps(evidence.seal(report or {'status': 'success'})))
    return command


def test_copy_sampling_opens_its_observer_login_before_the_action_and_none_during_it(tmp_path, monkeypatch):
    instance = harness.Harness('tiny', 'observer-login-test', tmp_path)
    instance.free_bytes = lambda: 1_000_000
    monkeypatch.setattr(harness, 'SAMPLE_SECONDS', 0.001)
    logins = _ObserverLogins(instance, monkeypatch)
    instance.command = _running_command(logins)
    outcome = instance.action('copy-economy-opportunity', measure=True)
    assert outcome['report']['status'] == 'success' and len(outcome['free_bytes_samples']) >= 3
    assert set(outcome['temp_file_bytes_samples']) == {4096}
    assert logins.during_action == []
    # One observer login, opened before and closed after the action.
    assert logins.users == [harness.OBSERVER_USER] and logins.closed == [False]
    receipt = json.loads((tmp_path / '001-copy-economy-opportunity-samples.json').read_text())
    assert len(receipt['free_bytes_samples']) >= 3 and set(receipt['temp_file_bytes_samples']) == {4096}


def test_swap_reader_measures_finder_read_latency_on_its_own_login(tmp_path, monkeypatch):
    instance = harness.Harness('tiny', 'reader-test', tmp_path)
    monkeypatch.setattr(harness, 'READ_INTERVAL_SECONDS', 0.001)
    statement = harness.FINDER_READS['system_rating_vector']
    logins = _ObserverLogins(instance, monkeypatch, answers={statement: '25'})
    instance.command = _running_command(logins)
    outcome = instance.action('swap-system-rating-vector', reader=statement)
    assert outcome['finder_read_seconds'] and all(value >= 0 for value in outcome['finder_read_seconds'])
    assert logins.users == [harness.OBSERVER_USER] and logins.during_action == []
    assert set(logins.statements) == {statement}
    for relation, read in harness.FINDER_READS.items():
        assert read.endswith(';') and '\n' not in read and ('v3_app.' in read or harness.controller.PUBLISHED_ID in read)


def test_an_unmeasured_action_opens_no_observer_login(tmp_path, monkeypatch):
    instance = harness.Harness('tiny', 'observer-none-test', tmp_path)
    logins = _ObserverLogins(instance, monkeypatch)
    instance.command = lambda *_args, **_kwargs: SimpleNamespace(
        returncode=0, stdout=json.dumps(evidence.seal({'status': 'success'})))
    instance.action('drop-economy-opportunity')
    assert logins.users == []


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
        instance.action('copy-system-search', measure=True)


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


def test_a_stopped_copy_dispatch_is_never_treated_as_progress(tmp_path):
    instance = harness.Harness('tiny', 'stopped-test', tmp_path)
    sealed = evidence.seal({'status': 'stopped', 'failures': ['copy_verify_interrupted'],
                            'result': 'copy_verified_ready_for_swap'})
    instance.command = lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=json.dumps(sealed))
    with pytest.raises(RuntimeError, match='real_action_refused_copy_system_search'):
        instance.copy_until_verified('system-search')
    assert instance.refused_action['failures'] == ['copy_verify_interrupted']


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


@pytest.mark.parametrize(('mode', 'plan', 'verification', 'wall_clock'), [
    ('plan', False, False, False), ('status', False, True, False), ('authorize', True, False, False),
    ('verify-system-archetype-empty', True, False, False), ('complete', True, True, False),
    ('preflight-system-search', True, False, False), ('copy-system-search', True, True, True),
    ('swap-economy-opportunity', True, True, False), ('swap-back-body-mechanics', True, True, False),
    ('drop-system-rating-vector', True, True, False), ('abandon-economy-opportunity', True, True, False),
])
def test_action_arguments_match_controller_admission(tmp_path, mode, plan, verification, wall_clock):
    # The controller refuses plan arguments for status/plan, verification
    # arguments for authorize/verify/preflight, and a wall clock outside copy.
    instance = harness.Harness('tiny', 'argv-test', tmp_path)
    instance.plan = (tmp_path / 'plan.json', 'a' * 64)
    instance.verification = (tmp_path / 'verify.json', 'b' * 64)
    argv = instance.action_argv(mode)
    assert ('--plan' in argv) is plan and ('--plan-sha256' in argv) is plan
    assert ('--verification' in argv) is verification
    assert ('--verification-sha256' in argv) is verification
    assert ('--wall-clock-seconds' in argv) is wall_clock
    if wall_clock:
        assert argv[argv.index('--wall-clock-seconds') + 1] == str(harness.COPY_WALL_CLOCK_SECONDS)


def test_migrate_applies_the_whole_manifest_then_observer_and_temp_file_grants(tmp_path):
    instance = harness.Harness('tiny', 'migrate-test', tmp_path)
    executed = []
    instance.sql = lambda statement, parameters=None: executed.append((statement, parameters)) or ''
    instance.migrate()
    names = [parameters['name'] for statement, parameters in executed if parameters and 'name' in parameters]
    manifest = [line.split()[1] for line in (harness.ROOT / 'sql/v3/migration-manifest.txt').read_text().splitlines()
                if line.strip() and not line.startswith('#')]
    assert names == manifest and harness.COPY_MIGRATION in names and harness.controller.MIGRATION in names
    assert [statement for statement, _ in executed[-2:]] == [harness.OBSERVER_SETUP, harness.EXECUTOR_PARAMETER_SETUP]
    assert 'GRANT pg_monitor TO edfinder_purge_observer' in harness.OBSERVER_SETUP
    assert 'v3_app' in harness.OBSERVER_SETUP and 'INSERT' not in harness.OBSERVER_SETUP
    assert harness.EXECUTOR_PARAMETER_SETUP == 'GRANT SET ON PARAMETER temp_file_limit TO v3_derived_purge_executor;'


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
        if statement == harness.ARCHIVED_SQL:
            return 't'
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
    # 019's verify recounts per-chunk receipts: each generation's are written
    # while it is still BUILDING (before FINALIZE), and the survivor Search
    # product's receipts before it is READY.
    receipts = [index for index, statement in enumerate(order) if statement == seed.CHUNK_RECEIPTS]
    finalized = [index for index, statement in enumerate(order) if statement == seed.FINALIZE]
    assert len(receipts) == 3 and len(finalized) == 2
    assert all(any(receipt < final for receipt in receipts) for final in finalized)
    search_receipts = [index for index, (statement, parameters) in enumerate(executed)
                       if statement == seed.SEARCH_CHUNK_RECEIPTS]
    assert len(search_receipts) == 1 and executed[search_receipts[0]][1] == {
        'generation': published, 'version': 'v3-system-search-2'}
    assert max(survivor_search) < search_receipts[0] < min(ready)
    # Each receipt join analyses its freshly inserted inputs first; unanalysed,
    # the build-receipt join ran for more than 30 minutes at 200,000 systems.
    for statement in (seed.CHUNK_RECEIPTS, seed.SEARCH_CHUNK_RECEIPTS):
        assert statement.startswith(seed.RECEIPT_STATISTICS)
    assert seed.RECEIPT_STATISTICS.startswith('ANALYZE ') and seed.RECEIPT_STATISTICS.count(';') == 1
    # Production's planner statistics, then a completed archive segment.
    assert base_publish < order.index(seed.PLANNER_STATISTICS) < order.index(harness.ARCHIVER_SQL)
    assert order[-1] == harness.ARCHIVED_SQL


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


def test_journey_copies_each_relation_in_019_order_and_records_copy_figures(tmp_path, monkeypatch):
    instance = harness.Harness('tiny', 'journey-test', tmp_path)
    instance.plan = (tmp_path / 'plan.json', 'c' * 64)
    modes = []
    dispatches = {}
    def action(mode, *, measure=False, reader=None):
        modes.append((mode, measure, reader))
        report = {'content_sha256': 'c' * 64, 'status': 'success'}
        free, temp, reads = [], [], []
        if mode.startswith('copy-'):
            relation = harness.controller.RELATIONS[mode.removeprefix('copy-')]
            dispatches[relation] = dispatches.get(relation, 0) + 1
            first = dispatches[relation] == 1
            report.update(copy_chunk_statement_seconds=0.4 if first else None,
                          copy_steps=[] if first else [{'phase': 'index_build', 'seconds': 0.1},
                                                       {'phase': 'vacuum_freeze', 'seconds': 0.2},
                                                       {'phase': 'verify', 'seconds': 0.3}],
                          wal_phase_bytes={'chunk': 100} if first else {'index_build': 5, 'vacuum_freeze': 6, 'verify': 0},
                          copy_state_after={'rows_total': instance.counts[relation]['ratings_v4_prod_p4_parallel_v1']},
                          result='copy_in_progress' if first else 'copy_verified_ready_for_swap')
            free, temp = ([1000, 900] if first else [900, 700, 950]), ([0, 0] if first else [0, 64, 0])
        elif mode.startswith('swap-'):
            report.update(swap_attempts=[{'attempt': 1}], measured_stall_seconds=0.2,
                          copy_steps=[{'phase': 'swap'}, {'phase': 'validate_fks', 'seconds': 0.05}],
                          wal_phase_bytes={'validate_fks': 2})
            reads = [0.01, 0.4, 0.02]
        elif mode.startswith('drop-'):
            report.update(measured_stall_seconds=0.1, wal_phase_bytes={'drop': 1})
        elif mode == 'plan' or mode == 'verify-system-archetype-empty':
            pass
        return {'report': report, 'path': tmp_path / (mode + '.json'), 'duration': 1.0,
                'free_bytes_samples': free, 'temp_file_bytes_samples': temp, 'finder_read_seconds': reads}
    def sql(statement, parameters=None):
        if statement == harness.RELATION_BYTES_SQL:
            return {'v3_derived': '65536', 'v3_purge_staging': None, 'v3_retired': '40000'}[
                parameters['relation'].split('.')[0]] or str(
                    instance.counts[parameters['relation'].split('.')[1]]['ratings_v4_prod_p4_parallel_v1'] * 600)
        if statement == harness.TEMP_WRITTEN_SQL:
            return '0'
        relation = next((name for name, query in harness.TARGET_ROWS_SQL.items() if query == statement), None)
        if relation is not None:
            # Targets remain until the drop; afterwards the live table holds none.
            dropped = any(mode == 'drop-' + relation.replace('_', '-') for mode, *_ in modes)
            return '0' if dropped else str(sum(instance.counts[relation][key] for key in harness.controller.TARGETS))
        raise AssertionError(statement[:60])
    monkeypatch.setattr(instance, 'action', action)
    monkeypatch.setattr(instance, 'sql', sql)
    measurements = instance.journey()
    order = [mode for mode, *_ in modes if not mode.startswith(('plan', 'authorize', 'verify-'))]
    expected = []
    for name in harness.controller.RELATIONS:
        expected += ['preflight-' + name, 'copy-' + name, 'copy-' + name, 'swap-' + name, 'drop-' + name]
    assert order == expected + ['complete']
    assert all(measure for mode, measure, _ in modes if mode.startswith('copy-'))
    assert [reader for mode, _, reader in modes if mode.startswith('swap-')] == [
        harness.FINDER_READS[relation] for relation in harness.RELATIONS]
    vector = measurements['system_rating_vector']['raw']
    assert vector['copy_peak_bytes'] == 300 and vector['temp_file_peak_bytes'] == 64
    assert vector['copy_dispatches'] == 2 and vector['finder_read_stall_seconds'] == 0.4
    assert vector['wal_bytes'] == {'chunk': 100, 'index_build': 5, 'vacuum_freeze': 6, 'verify': 0,
                                   'validate_fks': 2, 'drop': 1}
    assert vector['copy_seconds'] == 0.4 and vector['verify_seconds'] == 0.3 and vector['fk_validation_seconds'] == 0.05
    # The receipt validator accepts exactly these recorded figures.
    receipt = dict(schema_version=figures.SCHEMA, operation='v3-derived-purge-rehearsal', route=figures.ROUTE,
                   status='stopped', source_git_sha='a' * 40, scale='tiny', **figures.code_identity(),
                   image_digest=harness.IMAGE, production_proportion=instance.proportion, row_counts=instance.counts,
                   survivor_products=instance.survivors, settings={'autovacuum': 'on'},
                   gate_10_crash_rehearsal_passed=False, crash_scenarios={}, per_relation=measurements)
    assert figures.validate(receipt, production=False) is receipt
