"""Crash the real copy-and-drop action only inside separately marked fixtures.

Every scenario runs on economy_opportunity, the relation whose swap also
recalibrates and restores planner statistics, after system_search has been
copied, swapped and dropped through the real action. A scenario passes only
after its interruption point was observed, the published payload fingerprints
and pointers stayed intact, the ledger and catalog agreed at the interruption,
real action redispatch resumed from the ledger (never repeating committed
work), and every relation then finished through drop and complete. No ledger
row is synthesized or patched here. Fresh fixtures prevent one scenario hiding
a previous scenario's damage; crash fixtures use smoke proportions (tiny in
CI) alongside the separate one-percent journey.
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

RELATION = 'economy_opportunity'
MODE = 'economy-opportunity'
POLL_SECONDS = 0.05
OBSERVATION_SECONDS = 180
ORPHAN_SECONDS = 180
RELATIONS = tuple(controller.RELATIONS.values())
# Interruptions that kill the action's process group and its psql clients.
KILLED = ('copy_chunk_client_killed', 'swap_committed_client_killed',
          'swap_back_committed_client_killed', 'drop_committed_client_killed')
# Faults the action itself marks (runtime.fault); the others need no marker.
MARKED = KILLED + ('copy_postgres_restart', 'index_build_backend_terminated', 'verify_watchdog_cancel')
FAULT_MODES = {
    'copy_chunk_client_killed': 'copy-', 'copy_postgres_restart': 'copy-',
    'index_build_backend_terminated': 'copy-', 'verify_watchdog_cancel': 'copy-',
    'swap_committed_client_killed': 'swap-', 'swap_back_committed_client_killed': 'swap-back-',
    'drop_committed_client_killed': 'drop-',
}
PHASE_FUNCTIONS = {'copy_chunk_client_killed': 'purge_copy_chunk', 'copy_postgres_restart': 'purge_copy_chunk',
                   'index_build_backend_terminated': 'purge_copy_build_indexes',
                   'verify_watchdog_cancel': 'purge_copy_verify'}

# All relation identifiers come from the committed relation enum. Generation
# identifiers remain bound data. Counts plus independent row-hash sums protect
# every survivor column, beyond merely checking cardinality after a crash.
PUBLISHED_SQL = 'SELECT jsonb_build_object(' + ','.join(
    "'" + relation + "',(SELECT jsonb_build_object('rows',count(*),'fingerprint',"
    "COALESCE(sum(hashtextextended(to_jsonb(t)::text,0)::numeric),0)::text) "
    'FROM v3_derived.' + relation + ' t WHERE derived_generation_id=%(published)s::uuid)'
    for relation in RELATIONS) + ');'
# The copy ledger and catalog for the scenario relation, read by the observer
# (catalog lookups by name, so absent staging/retired tables read as null).
STATE_SQL = """SELECT jsonb_build_object(
 'events',(SELECT COALESCE(jsonb_agg(jsonb_build_object('kind',event_kind,'sequence',event_sequence,
    'abandoned',operational_payload->'abandoned') ORDER BY event_sequence),'[]'::jsonb)
    FROM v3_meta.derived_purge_copy_event WHERE relation_code='economy_opportunity'),
 'completed',EXISTS(SELECT 1 FROM v3_meta.derived_purge_copy_event WHERE event_kind='COMPLETED'),
 'rows_total',(SELECT rows_total FROM v3_meta.derived_purge_copy_event WHERE relation_code='economy_opportunity'
    AND event_kind='CHUNK_COPIED' ORDER BY event_sequence DESC LIMIT 1),
 'tables',(SELECT COALESCE(jsonb_object_agg(n.nspname,c.oid::bigint),'{}'::jsonb) FROM pg_class c
    JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relname='economy_opportunity'
    AND n.nspname IN ('v3_derived','v3_purge_staging','v3_retired')),
 'invalid_indexes',(SELECT count(*) FROM pg_index WHERE indrelid='v3_derived.economy_opportunity'::regclass
    AND (NOT indisvalid OR NOT indisready)),
 'not_valid_foreign_keys',(SELECT count(*) FROM pg_constraint WHERE contype='f' AND NOT convalidated
    AND (conrelid='v3_derived.economy_opportunity'::regclass OR confrelid='v3_derived.economy_opportunity'::regclass)),
 'live_attoptions',(SELECT to_jsonb(attoptions) FROM pg_attribute
    WHERE attrelid='v3_derived.economy_opportunity'::regclass AND attname='system_id64'),
 'target_rows',(SELECT count(*) FROM v3_derived.economy_opportunity WHERE derived_generation_id<>%(published)s::uuid),
 'postmaster_started',pg_postmaster_start_time());"""
ORPHAN_SQL = """SELECT jsonb_build_object('backends',(SELECT count(*) FROM pg_stat_activity
 WHERE datname=current_database() AND pid<>pg_backend_pid() AND state IS DISTINCT FROM 'idle'
 AND (wait_event='PgSleep' OR query ~ 'v3_meta[.]purge_copy_')));"""
# The paused phase statement itself (the action's own login, the fixed pause).
PAUSED_SQL = """SELECT COALESCE((SELECT jsonb_build_object('pid',pid) FROM pg_stat_activity
 WHERE datname=current_database() AND state='active' AND wait_event='PgSleep'
 AND query ~ %(function)s ORDER BY backend_start DESC LIMIT 1),'{}'::jsonb);"""
COMMITTED_SLEEP_SQL = """SELECT jsonb_build_object('sleeping',EXISTS(SELECT 1 FROM pg_stat_activity
 WHERE datname=current_database() AND wait_event='PgSleep' AND pid<>pg_backend_pid()
 AND query ~ 'purge_rehearsal'));"""
TERMINATE_SQL = """SELECT COALESCE((SELECT pg_terminate_backend(pid) FROM pg_stat_activity
 WHERE pid=%(pid)s::integer AND datname=current_database() AND query ~ 'v3_meta[.]purge_copy_build_indexes[(]'),false);"""

# The controller's read_sql() wrapper first assumes the purge executor role,
# which the read-only observer cannot (and must not) do. The observer already
# reads these catalog tables; drop only that role prefix and keep the bounded
# transaction.
_EXECUTOR_PREFIX = ('SET ROLE v3_derived_purge_executor; '
                    'SET default_transaction_read_only=off; ')
if not controller.POINTER_IDENTITIES_SQL.startswith(_EXECUTOR_PREFIX + 'BEGIN READ ONLY; '):
    raise ValueError('pointer_identity_sql_shape_changed')
POINTER_OBSERVATION_SQL = controller.POINTER_IDENTITIES_SQL[len(_EXECUTOR_PREFIX):]


def _json(harness, sql, parameters=None):
    return json.loads(harness.observe(sql, {'published': controller.PUBLISHED_ID, **(parameters or {})}))


def snapshot(harness):
    return {'published': _json(harness, PUBLISHED_SQL),
            'pointers': json.loads(harness.observe(POINTER_OBSERVATION_SQL)),
            'relation': _json(harness, STATE_SQL)}


def kinds(state):
    return [event['kind'] for event in state['relation']['events']]


def assert_intact(before, after):
    """Survivor content and pointers never change; the catalog agrees with the
    ledger's position at every observation (019's own position rule)."""
    if before['published'] != after['published'] or before['pointers'] != after['pointers']:
        raise ValueError('crash_published_payload_or_pointer_changed')
    relation = after['relation']
    events = [kind for kind in kinds(after) if kind != 'FK_VALIDATED']
    position = 'none'
    for kind in events:
        if kind == 'COPY_STARTED':
            position = 'staged'
        elif kind == 'SWAPPED':
            position = 'swapped'
        elif kind == 'SWAPPED_BACK':
            position = 'staged'
        elif kind == 'DROPPED':
            position = 'dropped'
    abandoned = [event for event in relation['events'] if event['kind'] == 'FAILED_STOP']
    if abandoned and events[-1] == 'FAILED_STOP':
        if abandoned[-1].get('abandoned') is not True:
            raise ValueError('crash_unexpected_failed_stop')
        position = 'none'
    tables = set(relation['tables'])
    expected = {'none': {'v3_derived'}, 'dropped': {'v3_derived'},
                'staged': {'v3_derived', 'v3_purge_staging'},
                'swapped': {'v3_derived', 'v3_retired'}}[position]
    if tables != expected or relation['invalid_indexes']:
        raise ValueError('crash_ledger_and_catalog_disagree')
    return position


def _wait(probe, process, *, reason, seconds=OBSERVATION_SECONDS):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        observed = probe()
        if observed:
            return observed
        if process is not None and process.poll() is not None:
            raise RuntimeError(reason)
        time.sleep(POLL_SECONDS)
    raise RuntimeError(reason)


def _psql_clients(harness):
    # docker top requires a PID column; the command follows it.
    listing = harness.docker('top', harness.container, '-eo', 'pid,args').splitlines()
    if not listing or listing[0].split()[:2] != ['PID', 'COMMAND']:
        raise RuntimeError('crash_container_process_listing_unknown')
    return [line for line in listing[1:] if len(line.split()) > 1 and Path(line.split()[1]).name == 'psql']


def _wait_no_psql_client(harness):
    deadline = time.monotonic() + 30
    while _psql_clients(harness):
        if time.monotonic() >= deadline:
            raise RuntimeError('crash_psql_client_survived')
        time.sleep(POLL_SECONDS)


def _wait_no_orphan(harness):
    """Redispatch only after the interrupted backend has exited; while it holds
    019's copy lock the action refuses (competing_purge_copy_backend_active)."""
    _wait(lambda: _json(harness, ORPHAN_SQL)['backends'] == 0, None,
          reason='crash_orphaned_backend_survived', seconds=ORPHAN_SECONDS)


def _ready(harness):
    deadline = time.monotonic() + 120
    while True:
        try:
            harness.observe('SELECT 1;')
            return
        except (RuntimeError, OSError, subprocess.SubprocessError):
            if time.monotonic() >= deadline:
                raise RuntimeError('crash_postgres_restart_not_ready') from None
            time.sleep(0.2)


def _kill(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=30)


def _route(harness, name):
    """One relation through the real action: preflight, copy, swap, drop."""
    harness.action('preflight-' + name)
    harness.copy_until_verified(name)
    harness.action('swap-' + name)
    harness.action('drop-' + name)


def _prepare(harness):
    harness.start()
    harness.migrate()
    harness.seed()
    harness.authorize()
    _route(harness, 'system-search')


def _finish(harness):
    """Every remaining relation through drop, then 019's COMPLETED."""
    for name in ('body-mechanics', 'system-rating-vector'):
        _route(harness, name)
    harness.action('complete')


def _marker(marker, scenario, process):
    if not marker.exists():
        return False
    payload = json.loads(marker.read_text())
    pid = payload.get('pid')
    try:
        owned = type(pid) is int and pid > 0 and os.getpgid(pid) == process.pid
    except ProcessLookupError:
        owned = False
    return payload if payload.get('scenario') == scenario and owned else False


def _interrupt(harness, scenario, process, marker):
    """Observe the exact fault point, then interrupt there; returns evidence."""
    _wait(lambda: _marker(marker, scenario, process), process, reason='crash_fault_point_not_observed')
    if scenario in PHASE_FUNCTIONS:
        paused = _wait(lambda: _json(harness, PAUSED_SQL, {'function': 'v3_meta[.]' + PHASE_FUNCTIONS[scenario] + '[(]'})
                       or False, process, reason='crash_phase_statement_not_observed')
    else:
        paused = _wait(lambda: _json(harness, COMMITTED_SLEEP_SQL).get('sleeping'), process,
                       reason='crash_commit_boundary_not_observed')
    evidence_ = {'observed_fault_point': scenario}
    if scenario in KILLED:
        # Kill the wrapper first so its finally blocks cannot resolve the
        # interruption, then its psql client inside the container.
        _kill(process)
        harness.docker('exec', harness.container, 'killall', '-KILL', 'psql', check=False)
        _wait_no_psql_client(harness)
        evidence_['client_state'] = ('killed_before_commit' if scenario == 'copy_chunk_client_killed'
                                     else 'killed_after_commit')
    elif scenario == 'copy_postgres_restart':
        harness.docker('restart', '--time', '0', harness.container)
        evidence_['postgres_restarted'] = True
    elif scenario == 'index_build_backend_terminated':
        if harness.sql(TERMINATE_SQL, {'pid': paused['pid']}) != 't':
            raise RuntimeError('crash_backend_termination_failed')
        evidence_['terminated_backend'] = True
    elif scenario == 'verify_watchdog_cancel':
        # The independent watchdog cancels on controller loss; the trigger is
        # written only after the verify statement itself was observed active.
        Path(str(marker) + '.trigger').write_text('observed-active-verify\n')
        evidence_['watchdog_trigger'] = 'controller_loss'
    else:
        raise ValueError('unknown_crash_scenario')
    if process.poll() is None:
        try:
            process.wait(timeout=240)
        except subprocess.TimeoutExpired:
            _kill(process)
            raise RuntimeError('crash_wrapper_did_not_exit') from None
    evidence_['wrapper_returncode'] = process.returncode
    if scenario == 'copy_postgres_restart':
        _ready(harness)
    _wait_no_orphan(harness)
    return evidence_


def configure_fixture(harness, scenario):
    # The fixture's proportions are the crash scale's own; nothing is added.
    harness.counts = deepcopy(harness.counts)
    return deepcopy(harness.counts)


def _faulted(harness, scenario):
    """Run the faulted dispatch in its own process group and interrupt it."""
    marker = harness.output / 'fault-ready.json'
    # A private directory is required by the separately admitted runtime hooks.
    harness.output.chmod(0o700)
    environment = {**harness.environment, 'ED_PURGE_REHEARSAL_FAULT': scenario,
                   'ED_PURGE_REHEARSAL_FAULT_FILE': str(marker.resolve())}
    mode = FAULT_MODES[scenario] + MODE
    report_path = harness.output / 'interrupted-action.json'
    with report_path.open('w') as output:
        process = subprocess.Popen(harness.action_argv(mode), env=environment, stdout=output,
                                   stderr=subprocess.DEVNULL, start_new_session=True, text=True)
        try:
            interruption = _interrupt(harness, scenario, process, marker)
        finally:
            if process.poll() is None:
                _kill(process)
    text = report_path.read_text().strip()
    return interruption, (json.loads(text) if text else None)


def _expect(condition, code):
    if not condition:
        raise ValueError(code)


def run_scenario(harness, scenario):
    if scenario not in CRASH_SCENARIOS:
        raise ValueError('unknown_crash_scenario')
    fixture_counts = configure_fixture(harness, scenario)
    _prepare(harness)
    before = snapshot(harness)
    frozen = harness.counts[RELATION][controller.PUBLISHED_KEY]
    result = {'passed': False, 'crash_scale': harness.scale, 'crash_fixture_row_counts': fixture_counts}
    harness.action('preflight-' + MODE)
    if scenario in ('copy_chunk_client_killed', 'copy_postgres_restart', 'index_build_backend_terminated',
                    'verify_watchdog_cancel'):
        interruption, interrupted_report = _faulted(harness, scenario)
        interrupted = snapshot(harness)
        position = assert_intact(before, interrupted)
        _expect(position == 'staged', 'crash_copy_position_not_staged')
        events = kinds(interrupted)
        if scenario in ('copy_chunk_client_killed', 'copy_postgres_restart'):
            # Exactly the committed chunk before the interrupted one.
            _expect(events.count('CHUNK_COPIED') == 1 and 'INDEXES_BUILT' not in events, 'crash_chunk_not_atomic')
            if scenario == 'copy_postgres_restart':
                _expect(interrupted['relation']['postmaster_started'] != before['relation']['postmaster_started'],
                        'crash_postgres_not_restarted')
        elif scenario == 'index_build_backend_terminated':
            _expect('INDEXES_BUILT' not in events, 'crash_index_build_committed')
        else:
            _expect(events[-1] == 'INDEXES_BUILT' and 'VERIFIED' not in events, 'crash_verify_committed')
            failures = (interrupted_report or {}).get('copy_phase_failures') or []
            _expect(bool(failures) and failures[-1].get('monitor_condition') == 'controller_loss'
                    and failures[-1].get('sqlstate') == '57014'
                    and (interrupted_report or {}).get('failures') == ['copy_verify_interrupted'],
                    'crash_watchdog_did_not_cancel_verify')
        result.update(interruption)
        harness.copy_until_verified(MODE)
        recovered = snapshot(harness)
        assert_intact(before, recovered)
        _expect(recovered['relation']['rows_total'] == frozen
                and kinds(recovered).count('COPY_STARTED') == 1 and kinds(recovered)[-1] == 'VERIFIED',
                'crash_copy_not_resumed_from_the_ledger')
        harness.action('swap-' + MODE)
        harness.action('drop-' + MODE)
    elif scenario == 'swap_committed_client_killed':
        harness.copy_until_verified(MODE)
        interruption, _report = _faulted(harness, scenario)
        interrupted = snapshot(harness)
        _expect(assert_intact(before, interrupted) == 'swapped' and kinds(interrupted)[-1] == 'SWAPPED',
                'crash_committed_swap_not_observed')
        status = harness.action('status')['report']
        _expect((status.get('next_admissible_mode') or {}).get('mode') == 'swap-' + MODE, 'crash_status_guidance_wrong')
        resumed = harness.action('swap-' + MODE)['report']
        _expect(resumed.get('swap_resumed') is True and kinds(snapshot(harness))[-1] == 'FK_VALIDATED',
                'crash_swap_not_resumed')
        result.update(interruption, status_next_mode=status['next_admissible_mode'])
        harness.action('drop-' + MODE)
    elif scenario == 'swap_back_committed_client_killed':
        harness.copy_until_verified(MODE)
        harness.action('swap-' + MODE)
        swapped = snapshot(harness)
        interruption, _report = _faulted(harness, scenario)
        interrupted = snapshot(harness)
        _expect(assert_intact(before, interrupted) == 'staged' and kinds(interrupted)[-1] == 'SWAPPED_BACK'
                and interrupted['relation']['tables']['v3_derived'] == before['relation']['tables']['v3_derived']
                and interrupted['relation']['live_attoptions'] == before['relation']['live_attoptions'],
                'crash_committed_swap_back_not_observed')
        status = harness.action('status')['report']
        _expect((status.get('next_admissible_mode') or {}).get('mode') == 'swap-back-' + MODE,
                'crash_status_guidance_wrong')
        resumed = harness.action('swap-back-' + MODE)['report']
        _expect(resumed.get('swap_back_resumed') is True and resumed.get('result') == 'swapped_back_live_restored',
                'crash_swap_back_not_resumed')
        result.update(interruption, status_next_mode=status['next_admissible_mode'],
                      recalibrated_attoptions=swapped['relation']['live_attoptions'])
        harness.copy_until_verified(MODE)
        harness.action('swap-' + MODE)
        harness.action('drop-' + MODE)
    elif scenario == 'swap_back_and_reswap':
        harness.copy_until_verified(MODE)
        harness.action('swap-' + MODE)
        swapped = snapshot(harness)
        back = harness.action('swap-back-' + MODE)['report']
        restored = snapshot(harness)
        _expect(back.get('result') == 'swapped_back_live_restored'
                and assert_intact(before, restored) == 'staged'
                and restored['relation']['tables']['v3_derived'] == before['relation']['tables']['v3_derived']
                and restored['relation']['live_attoptions'] == before['relation']['live_attoptions'],
                'crash_swap_back_did_not_restore_live')
        harness.copy_until_verified(MODE)
        harness.action('swap-' + MODE)
        reswapped = snapshot(harness)
        _expect(assert_intact(before, reswapped) == 'swapped'
                and reswapped['relation']['tables']['v3_derived'] == swapped['relation']['tables']['v3_derived']
                and reswapped['relation']['live_attoptions'] == swapped['relation']['live_attoptions'],
                'crash_reswap_differs_from_first_swap')
        result.update(observed_fault_point=scenario, swapped_attoptions=swapped['relation']['live_attoptions'],
                      restored_attoptions=restored['relation']['live_attoptions'])
        harness.action('drop-' + MODE)
    elif scenario == 'abandon_and_recopy':
        harness.copy_until_verified(MODE)
        harness.action('abandon-' + MODE)
        abandoned = snapshot(harness)
        _expect(assert_intact(before, abandoned) == 'none' and kinds(abandoned)[-1] == 'FAILED_STOP',
                'crash_abandon_left_staging')
        harness.action('preflight-' + MODE)
        harness.copy_until_verified(MODE)
        recopied = snapshot(harness)
        _expect(kinds(recopied).count('COPY_STARTED') == 2 and recopied['relation']['rows_total'] == frozen,
                'crash_recopy_not_fresh')
        result.update(observed_fault_point=scenario)
        harness.action('swap-' + MODE)
        harness.action('drop-' + MODE)
    elif scenario == 'drop_committed_client_killed':
        harness.copy_until_verified(MODE)
        harness.action('swap-' + MODE)
        interruption, _report = _faulted(harness, scenario)
        interrupted = snapshot(harness)
        _expect(assert_intact(before, interrupted) == 'dropped', 'crash_committed_drop_not_observed')
        again = harness.action('drop-' + MODE)['report']
        _expect(again.get('result') == 'retired_relation_already_dropped', 'crash_drop_not_idempotent')
        result.update(interruption)
    else:
        raise ValueError('unknown_crash_scenario')
    dropped = snapshot(harness)
    _expect(assert_intact(before, dropped) == 'dropped' and dropped['relation']['target_rows'] == 0
            and kinds(dropped).count('DROPPED') == 1, 'crash_relation_not_dropped_once')
    _finish(harness)
    final = snapshot(harness)
    assert_intact(before, final)
    _expect(final['relation']['completed'] is True, 'crash_purge_not_completed')
    for relation in RELATIONS:
        _expect(harness.number(harness_target_rows(relation)) == 0, 'crash_target_rows_remain')
    result.update(passed=True, before=before, after_interruption_or_steps=dropped, completed=final,
                  published_fingerprints_unchanged=True, resumed_without_repeating_committed_work=True)
    return result


def harness_target_rows(relation):
    if relation not in RELATIONS:
        raise ValueError('unknown_relation')
    return ('SELECT count(*) FROM v3_derived.' + relation
            + " WHERE derived_generation_id<>'" + controller.PUBLISHED_ID + "';")


def run_crashes(harness_factory, scale, run_id, output):
    """Record every outcome; any unobserved/failing scenario closes gate10."""
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
            if getattr(fixture, 'refused_action', None) is not None:
                result['refused_action'] = fixture.refused_action
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
