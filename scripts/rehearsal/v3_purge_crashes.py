"""Crash the real purge action only inside separately marked disposable fixtures.

A scenario passes only after its interruption point was observed, the published
payload fingerprints and catalog remain intact, and real action redispatch has
resolved the ledger without another rewrite. No synthetic pass or timing-only
assumption can satisfy gate 10. Fresh fixtures prevent one scenario hiding a
previous scenario's damage. Crash fixtures use smoke proportions, with two million survivor vectors for
external mid-rewrite interruptions, alongside the separate one-percent journey.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from scripts.operator.lib import f2d_evidence as evidence
from scripts.operator.lib import v3_generation_purge as controller
from scripts.operator.lib.v3_purge_rehearsal_receipt import CRASH_SCENARIOS

RELATION = 'system_rating_vector'
MODE = 'system-rating-vector'
POLL_SECONDS = 0.05
OBSERVATION_SECONDS = 120
RELATIONS = tuple(controller.RELATIONS.values())

# All relation identifiers come from the committed relation enum. Generation
# identifiers remain bound data. Counts plus independent row-hash sums protect
# every survivor column, beyond merely checking cardinality after a crash.
PUBLISHED_SQL = 'SELECT jsonb_build_object(' + ','.join(
    "'" + relation + "',(SELECT jsonb_build_object('rows',count(*),'fingerprint',"
    "COALESCE(sum(hashtextextended(to_jsonb(t)::text,0)::numeric),0)::text) "
    'FROM v3_derived.' + relation + ' t WHERE derived_generation_id=%(published)s::uuid)'
    for relation in RELATIONS) + ');'
STATE_SQL = """SELECT jsonb_build_object(
 'oid',c.oid,'relfilenode',c.relfilenode,'kind',c.relkind,
 'catalog_relations',(SELECT count(*) FROM pg_class x JOIN pg_namespace n ON n.oid=x.relnamespace
    WHERE n.nspname='v3_derived' AND x.relname='system_rating_vector'),
 'target_rows',(SELECT count(*) FROM v3_derived.system_rating_vector
    WHERE derived_generation_id<>%(published)s::uuid),
 'invalid_indexes',(SELECT count(*) FROM pg_index WHERE indrelid=c.oid AND (NOT indisvalid OR NOT indisready)),
 'invalid_foreign_keys',(SELECT count(*) FROM pg_constraint WHERE conrelid=c.oid AND contype='f' AND NOT convalidated),
 'invalid_triggers',(SELECT count(*) FROM pg_trigger WHERE tgrelid=c.oid AND tgenabled<>'O'),
 'last_analyze',(SELECT last_analyze FROM pg_stat_all_tables WHERE relid=c.oid),
 'last_rewrite_start',(SELECT max(created_at) FROM v3_meta.derived_generation_purge_event
    WHERE relation_code='system_rating_vector' AND event_kind='REWRITE_STARTED'),
 'rewrite_starts',(SELECT count(*) FROM v3_meta.derived_generation_purge_event
    WHERE relation_code='system_rating_vector' AND event_kind='REWRITE_STARTED'),
 'rewrite_verifications',(SELECT count(*) FROM v3_meta.derived_generation_purge_event
    WHERE relation_code='system_rating_vector' AND event_kind='REWRITE_VERIFIED'),
 'monitor_cancellations',(SELECT count(*) FROM v3_meta.derived_generation_purge_event
    WHERE relation_code='system_rating_vector' AND event_kind='REWRITE_CANCEL_REQUESTED'
      AND operational_payload->>'condition'='controller_loss' AND operational_payload->'signalled'='true'::jsonb),
 'committed_rows',(SELECT COALESCE(sum(rows_affected),0) FROM v3_meta.derived_generation_purge_event
    WHERE relation_code='system_rating_vector' AND event_kind='BATCH_COMMITTED'),
 'postmaster_started',pg_postmaster_start_time())
 FROM pg_class c WHERE c.oid='v3_derived.system_rating_vector'::regclass;"""
PROGRESS_SQL = """SELECT COALESCE((SELECT jsonb_build_object('pid',pid,'phase',phase,
 'heap_blks_scanned',heap_blks_scanned,'heap_tuples_written',heap_tuples_written)
 FROM pg_stat_progress_cluster WHERE relid='v3_derived.system_rating_vector'::regclass
 AND command='VACUUM FULL'),'{}'::jsonb);"""
SLEEP_SQL = """SELECT jsonb_build_object('sleeping',EXISTS(SELECT 1 FROM pg_stat_activity
 WHERE datname=current_database() AND wait_event='PgSleep' AND pid<>pg_backend_pid()));"""


def _json(harness, sql):
    return json.loads(harness.sql(sql, {'published': controller.PUBLISHED_ID}))


def snapshot(harness):
    return {'published': _json(harness, PUBLISHED_SQL),
            'pointers': json.loads(harness.sql(controller.POINTER_IDENTITIES_SQL)),
            'relation': _json(harness, STATE_SQL)}


def assert_intact(before, after):
    """One whole catalog identity and exact survivor content must survive."""
    if before['published'] != after['published'] or before['pointers'] != after['pointers']:
        raise ValueError('crash_published_payload_or_pointer_changed')
    relation = after['relation']
    if (relation['oid'] != before['relation']['oid'] or relation['catalog_relations'] != 1
            or relation['kind'] != 'r' or type(relation['relfilenode']) is not int
            or relation['relfilenode'] <= 0 or any(relation[key] for key in
            ('invalid_indexes', 'invalid_foreign_keys', 'invalid_triggers'))):
        raise ValueError('crash_half_swapped_or_invalid_relation')
    return 'old' if relation['relfilenode'] == before['relation']['relfilenode'] else 'new'


def assert_recovered(before, recovered, repeated):
    assert_intact(before, recovered)
    assert_intact(before, repeated)
    relation, retry = recovered['relation'], repeated['relation']
    if (relation['target_rows'] != 0 or relation['rewrite_verifications'] != 1
            or relation['relfilenode'] == before['relation']['relfilenode']
            or relation['last_analyze'] is None or relation['last_rewrite_start'] is None
            or relation['last_analyze'] <= relation['last_rewrite_start']):
        raise ValueError('crash_recovery_not_verified_or_analyzed')
    if any(relation[key] != retry[key] for key in ('relfilenode', 'rewrite_starts', 'rewrite_verifications')):
        raise ValueError('crash_recovery_double_rewrite')


def _wait(probe, process, *, reason):
    deadline = time.monotonic() + OBSERVATION_SECONDS
    while time.monotonic() < deadline:
        observed = probe()
        if observed:
            return observed
        if process.poll() is not None:
            raise RuntimeError(reason)
        time.sleep(POLL_SECONDS)
    raise RuntimeError(reason)


def _kill(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=30)


def _prepare(harness, *, delete_vector):
    harness.start()
    harness.migrate()
    harness.seed()
    report, path, *_ = harness.action('plan')
    harness.plan = (path, report['content_sha256'])
    harness.action('authorize')
    report, path, *_ = harness.action('verify-system-archetype-empty')
    harness.verification = (path, report['content_sha256'])
    for name in controller.RELATIONS:
        if name == MODE:
            if delete_vector:
                _delete_all(harness, name)
            break
        _delete_all(harness, name)
        harness.action('rewrite-' + name)


def _delete_all(harness, name):
    relation = controller.RELATIONS[name]
    for _ in range(1000):
        harness.action('delete-' + name)
        remaining = int(harness.sql('SELECT count(*) FROM v3_derived.' + relation +
                                   ' WHERE derived_generation_id<>%(published)s::uuid;',
                                   {'published': controller.PUBLISHED_ID}))
        if remaining == 0:
            return
    raise RuntimeError('crash_delete_dispatch_bound_exceeded')


def _active_rewrite(harness):
    progress = _json(harness, PROGRESS_SQL)
    # Presence in the progress view alone includes initialization. Observe
    # tuples already copied so a crash during real physical work is proven.
    copied = progress.get('heap_tuples_written')
    return progress if type(copied) is int and copied > 0 else False


def _interrupt(harness, scenario, process, marker):
    if scenario in ('batch_client_before_commit', 'batch_client_after_commit', 'wrapper_after_rewrite_commit'):
        def ready():
            if not marker.exists():
                return False
            payload = json.loads(marker.read_text())
            pid = payload.get('pid')
            try:
                owned = type(pid) is int and pid > 0 and os.getpgid(pid) == process.pid
            except ProcessLookupError:
                owned = False
            return payload if payload.get('scenario') == scenario and owned else False
        _wait(ready, process, reason='crash_fault_point_not_observed')
        if scenario.startswith('batch_client_'):
            _wait(lambda: _json(harness, SLEEP_SQL).get('sleeping'), process,
                  reason='crash_batch_commit_boundary_not_observed')
        # Kill the wrapper first so its finally blocks cannot resolve the
        # interruption. Before COMMIT its live psql client is then killed too.
        _kill(process)
        if scenario.startswith('batch_client_') or scenario == 'wrapper_after_rewrite_commit':
            harness.docker('exec', harness.container, 'killall', '-KILL', 'psql')
        return {'observed_fault_point': scenario,
                'batch_client_state': ('killed_before_commit' if scenario == 'batch_client_before_commit'
                                       else 'killed_after_commit' if scenario == 'batch_client_after_commit'
                                       else 'rewrite_client_killed_after_commit')}
    progress = _wait(lambda: _active_rewrite(harness), process,
                     reason='crash_active_rewrite_not_observed')
    if scenario == 'rewrite_monitor_cancel':
        Path(str(marker) + '.trigger').write_text('observed-active-rewrite\n')
    elif scenario == 'rewrite_terminate_backend':
        result = harness.sql(
            "SELECT COALESCE((SELECT pg_terminate_backend(pid) FROM pg_stat_progress_cluster "
            "WHERE pid=%(pid)s::integer AND relid='v3_derived.system_rating_vector'::regclass "
            "AND command='VACUUM FULL'),false);", {'pid': progress['pid']})
        if result != 't':
            raise RuntimeError('crash_backend_termination_failed')
    elif scenario == 'rewrite_postgres_restart':
        harness.docker('restart', '--time', '0', harness.container)
    else:
        raise ValueError('unknown_crash_scenario')
    try:
        process.wait(timeout=180)
    except subprocess.TimeoutExpired:
        _kill(process)
        raise RuntimeError('crash_wrapper_did_not_exit') from None
    if scenario == 'rewrite_postgres_restart':
        deadline = time.monotonic() + 120
        while True:
            try:
                harness.sql('SELECT 1;')
                break
            except (RuntimeError, OSError, subprocess.SubprocessError):
                if time.monotonic() >= deadline:
                    raise RuntimeError('crash_postgres_restart_not_ready') from None
                time.sleep(0.2)
    return {'observed_active_rewrite': progress, 'wrapper_returncode': process.returncode}


def configure_fixture(harness, scenario):
    # Add only survivor vectors for a useful physical-copy observation window.
    # Their build_chunk parents are seeded from this count; other payloads may
    # remain sparse. The main measured fixture and target proportions never
    # change. Tiny CI checks deliberately keep their original bounded dataset.
    harness.counts = deepcopy(harness.counts)
    if scenario.startswith('rewrite_') and harness.scale != 'tiny':
        published = harness.counts[RELATION][controller.PUBLISHED_KEY]
        harness.counts[RELATION][controller.PUBLISHED_KEY] = max(2_000_000, published)
    return deepcopy(harness.counts)


def run_scenario(harness, scenario):
    if scenario not in CRASH_SCENARIOS:
        raise ValueError('unknown_crash_scenario')
    is_batch = scenario.startswith('batch_client_')
    fixture_counts = configure_fixture(harness, scenario)
    _prepare(harness, delete_vector=not is_batch)
    before = snapshot(harness)
    marker = harness.output / 'fault-ready.json'
    # A private directory is required by the separately admitted runtime hooks.
    harness.output.chmod(0o700)
    environment = {**harness.environment, 'ED_PURGE_REHEARSAL_FAULT': scenario,
                   'ED_PURGE_REHEARSAL_FAULT_FILE': str(marker.resolve())}
    mode = ('delete-' if is_batch else 'rewrite-') + MODE
    with (harness.output / 'interrupted-action.json').open('w') as output:
        process = subprocess.Popen(harness.action_argv(mode), env=environment, stdout=output,
                                   stderr=subprocess.DEVNULL, start_new_session=True, text=True)
        try:
            interruption = _interrupt(harness, scenario, process, marker)
        finally:
            if process.poll() is None:
                _kill(process)
    interrupted = snapshot(harness)
    state = assert_intact(before, interrupted)
    if scenario == 'batch_client_before_commit' and interrupted['relation']['target_rows'] != before['relation']['target_rows']:
        raise ValueError('crash_uncommitted_batch_changed_rows')
    if scenario == 'batch_client_after_commit':
        removed = before['relation']['target_rows'] - interrupted['relation']['target_rows']
        if not 0 < removed <= harness.plan_batch_limit(RELATION):
            raise ValueError('crash_committed_batch_not_atomic')
    if scenario == 'rewrite_monitor_cancel' and interrupted['relation']['monitor_cancellations'] < 1:
        raise ValueError('crash_monitor_did_not_cancel_active_rewrite')
    if scenario == 'wrapper_after_rewrite_commit' and state != 'new':
        raise ValueError('crash_committed_rewrite_not_swapped')
    if (scenario == 'rewrite_postgres_restart' and interrupted['relation']['postmaster_started']
            == before['relation']['postmaster_started']):
        raise ValueError('crash_postgres_not_restarted')
    # Use the actual restore dispatcher, then the actual matching phase. No
    # ledger row is synthesized or patched by this orchestration module.
    harness.action('restore-services')
    if is_batch:
        _delete_all(harness, MODE)
    harness.action('rewrite-' + MODE)
    recovered = snapshot(harness)
    harness.action('rewrite-' + MODE)
    repeated = snapshot(harness)
    assert_recovered(before, recovered, repeated)
    if is_batch and recovered['relation']['committed_rows'] != before['relation']['target_rows']:
        raise ValueError('crash_delete_double_counted_or_incomplete')
    harness.action('complete')
    return {'passed': True, 'crash_scale': harness.scale,
            'crash_fixture_row_counts': fixture_counts,
            'observed_relation_state_after_interruption': state, **interruption,
            'before': before, 'after_interruption': interrupted, 'recovered': recovered,
            'redispatched': repeated, 'published_fingerprints_unchanged': True,
            'recovered_analyze_verified': True, 'no_double_rewrite': True}


def run_crashes(harness_factory, scale, run_id, output):
    """Always record all six outcomes; any unobserved/failing scenario closes gate10."""
    results = {}
    crash_scale = 'tiny' if scale == 'tiny' else 'smoke'
    for index, scenario in enumerate(CRASH_SCENARIOS):
        fixture = harness_factory(crash_scale, run_id, Path(output) / 'crashes' / f'{index:02d}-{scenario}')
        result = {'passed': False, 'crash_scale': crash_scale, 'reason': 'not_completed'}
        try:
            result = run_scenario(fixture, scenario)
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            code = str(exc)
            result['reason'] = (code if re.fullmatch('[a-z][a-z0-9_]{0,127}', code)
                                else 'crash_scenario_failed_or_interruption_not_observed')
        finally:
            if hasattr(fixture, 'counts'):
                result['crash_fixture_row_counts'] = deepcopy(fixture.counts)
            try:
                fixture.cleanup()
                result['cleanup_verified'] = True
            except (ValueError, RuntimeError, OSError, subprocess.SubprocessError):
                result.update(passed=False, cleanup_verified=False, reason='crash_fixture_cleanup_failed')
        results[scenario] = result
        (fixture.output / 'crash-result.json').write_text(evidence.canonical_json(evidence.seal(result)) + '\n')
    return results
