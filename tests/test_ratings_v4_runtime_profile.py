from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.operator import ratings_v4_runtime_profile as profile  # noqa: E402
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402


def test_proc_stat_handles_comm_parentheses_and_linux_field_offsets():
    fields = ['S', '17'] + ['0'] * 19 + ['12']
    fields[11], fields[12], fields[19] = '150', '50', '123456'
    row = profile.parse_stat('42 (worker (encoder)) ' + ' '.join(fields))
    assert row == {'comm': 'worker (encoder)', 'state': 'S', 'ppid': 17,
                   'cpu_ticks': 200, 'start_ticks': 123456, 'rss_pages': 12}


def test_cpu_rates_are_one_core_percent_and_reject_pid_reuse():
    before = [{'pid': 42, 'cpu_ticks': 100, 'start_ticks': 9}]
    after = [{'pid': 42, 'namespace_pid': 1, 'comm': 'python',
              'cpu_ticks': 300, 'start_ticks': 9}]
    assert profile.process_rates(before, after, 2, 100)[0]['one_core_cpu_percent'] == 100
    after[0]['start_ticks'] = 10
    assert profile.process_rates(before, after, 2, 100) == []


def test_permission_denial_is_recorded_without_a_fallback(tmp_path, monkeypatch):
    def denied(self):
        raise PermissionError('fixture')
    monkeypatch.setattr(Path, 'read_text', denied)
    missing = set()
    assert profile.optional_read(tmp_path / 'stat', missing) is None
    assert len(missing) == 1
    assert next(iter(missing)).endswith(':PermissionError')


def test_cgroup_path_cannot_escape_host_cgroup_tree(monkeypatch):
    monkeypatch.setattr(profile, 'optional_read', lambda *_: '0::/../../tmp\n')
    with pytest.raises(ValueError, match='unexpected cgroup path'):
        profile.cgroup_directory(1, set())


def test_database_observations_use_fresh_read_only_bounded_transactions(monkeypatch):
    commands = []
    monkeypatch.setattr(profile, 'command', lambda args: commands.append(args) or '{"ok":true}')
    assert profile.database_query(profile.ACTIVITY_SQL) == {'ok': True}
    args = commands[0]
    statement = args[args.index('--command') + 1]
    assert statement.startswith("BEGIN READ ONLY; SET LOCAL statement_timeout='5s';")
    assert "SET LOCAL lock_timeout='1s';" in statement
    assert statement.endswith('; COMMIT;')
    assert 'ON_ERROR_STOP=1' in args
    assert profile.CONTAINERS['postgres'] in args
    assert 'query_kind' in statement
    assert 'host(client_addr) AS client_addr' in statement
    assert 'SELECT * FROM pg_stat_activity' not in statement


def test_profile_workflow_has_fixed_request_and_trusted_read_only_implementation():
    path = ROOT / '.github/workflows/ratings-v4-production-profile.yml'
    source = path.read_text()
    workflow = yaml.load(source, Loader=yaml.BaseLoader)
    job = workflow['jobs']['profile']
    assert job['environment'] == 'ed-new-operator'
    assert job['timeout-minutes'] == '8'
    assert workflow['concurrency']['cancel-in-progress'] == 'false'
    assert '.github/ratings-v4-profile-requests/*.json' in source
    assert '{"operation": "ratings-v4-runtime-profile"}' in source
    assert 'ref: main' in source
    assert 'timeout 210s python3.14 -' in source
    assert 'trusted-main/scripts/operator/ratings_v4_runtime_profile.py' in source
    assert '"profiler_sha256"' in source
    assert 'always()' in source


def test_observation_queries_execute_on_postgresql18_catalogs():
    with canonical_database() as (connection, _, _, _):
        for name in ('003_ratings_v4_derived.sql', '004_v3_search_spatial_clusters.sql',
                     '006_v3_derived_product_lifecycle.sql'):
            connection.execute((ROOT / 'sql/v3/migrations' / name).read_text())
        with connection.transaction():
            connection.execute('SET TRANSACTION READ ONLY')
            activity = connection.execute(profile.ACTIVITY_SQL).fetchone()[0]
            totals = connection.execute(profile.TOTALS_SQL).fetchone()[0]
        # SQL explicitly returns text for the standalone psql transport.
        import json
        assert isinstance(json.loads(activity)['activity'], list)
        data = json.loads(totals)
        assert data['generation'] is None
        assert data['database']['datname'].startswith('v4_test_')
        assert isinstance(data['io'], list)


def test_cpu_summary_retains_processes_between_endpoints_and_separates_pid_reuse():
    def process(pid, start, cpu):
        return {'pid': pid, 'start_ticks': start, 'cpu_ticks': cpu,
                'namespace_pid': pid, 'comm': 'python'}
    inventories = [
        [process(1, 10, 0)],
        [process(1, 10, 100), process(2, 20, 10)],
        [process(2, 20, 110), process(1, 30, 50)],
        [process(1, 30, 150)],
    ]
    frames = [{'elapsed_seconds': index, 'processes': {'ratings': rows}}
              for index, rows in enumerate(inventories)]
    result = profile.process_cpu_summary(frames, 'ratings', 100)
    by_identity = {(row['pid'], row['start_ticks']): row for row in result}
    assert set(by_identity) == {(1, 10), (2, 20), (1, 30)}
    for row in result:
        assert row['observed_cpu_seconds'] == 1
        assert row['observed_seconds'] == 1
        assert row['one_core_cpu_percent'] == pytest.approx(100 / 3)


def test_identity_change_receipt_distinguishes_restart_limits_and_exit():
    original = {'ratings': {'id': 'a', 'pid': 1, 'started_at': 'before',
                            'running': True, 'nano_cpus': 16, 'memory': 64}}
    assert not any(profile.identity_changes(original, original).values())
    for key, value, expected in (
        ('pid', 2, 'worker_restarted'), ('started_at', 'after', 'worker_restarted'),
        ('id', 'b', 'worker_restarted'), ('memory', 32, 'resource_limits_changed'),
        ('running', False, 'running_state_changed'),
    ):
        after = {'ratings': dict(original['ratings'], **{key: value})}
        changes = profile.identity_changes(original, after)
        assert changes[expected] is True
        assert sum(changes.values()) == 1


def test_search_generation_must_match_ratings():
    identities = {role: {'generation': profile.GENERATION} for role in ('ratings', 'search')}
    profile.verify_generations(identities)
    identities['search']['generation'] = 'stale_generation'
    with pytest.raises(ValueError, match='search worker generation mismatch'):
        profile.verify_generations(identities)


def test_unreadable_descriptor_does_not_prevent_observing_other_descriptors(monkeypatch):
    monkeypatch.setattr(Path, 'iterdir', lambda self: iter([self / '1', self / '2']))
    def link(path):
        if path.name == '1':
            raise PermissionError('fixture')
        return '/retained/galaxy.json.gz'
    monkeypatch.setattr(profile.os, 'readlink', link)
    monkeypatch.setattr(profile, 'optional_read', lambda *_: 'pos: 123\n')
    missing = set()
    assert profile.source_position(42, missing) == [123]
    assert missing == {'/proc/42/fd/1:PermissionError'}
