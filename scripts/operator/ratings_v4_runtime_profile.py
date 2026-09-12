#!/usr/bin/env python3
"""Observe the existing Ratings V4 processes for two minutes; never attach/modify.

Stream JSONL to the protected workflow artifact. Only standard-library, Docker
inspection, readable procfs/cgroup counters, and short READ ONLY SQL are used.
Missing OS permissions remain missing; there is no privileged fallback.
"""
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

HOST = 'ed-finder-prod'
FQDN = 'nb79a3d.mevnode.com'
GENERATION = 'ratings_v4_prod_p4_opt1'
DATABASE = 'edfinder_v3_phase4c_full_20260827_r5'
CONTAINERS = {
    'ratings': 'edfinder-ratings-v4-prod-p4-opt1',
    'postgres': 'edfinder-v3-phase4c-full-20260827_r5-postgres',
    'search': 'edfinder-v3-system-search-p4-opt1',
}
DURATION_SECONDS = 120
INTERVAL_SECONDS = 2

ACTIVITY_SQL = """
SELECT json_build_object(
  'observed_at',clock_timestamp(),
  'activity',COALESCE((SELECT json_agg(x) FROM (
    SELECT pid,backend_type,host(client_addr) AS client_addr,state,wait_event_type,wait_event,
           CASE WHEN state='active' THEN
             extract(epoch FROM clock_timestamp()-query_start) END AS active_seconds,
           CASE WHEN state IS DISTINCT FROM 'active' THEN 'not_active'
                WHEN query IS NULL THEN 'unavailable'
                WHEN query ~* '^COPY' AND query LIKE '%system_rating_vector%' THEN 'copy_vectors'
                WHEN query ~* '^COPY' AND query LIKE '%body_mechanics%' THEN 'copy_mechanics'
                WHEN query ~* '^COPY' AND query LIKE '%economy_opportunity%' THEN 'copy_opportunities'
                WHEN query ~* '^COMMIT' THEN 'commit'
                WHEN query LIKE '%system_search%' THEN 'search'
                WHEN query LIKE '%build_chunk%' THEN 'chunk_receipt'
                WHEN query LIKE '%derived_generation%' THEN 'generation_check'
                WHEN query LIKE '%body_signal_current%' THEN 'canonical_signals'
                WHEN query LIKE '%rings%' THEN 'canonical_rings'
                WHEN query LIKE '%bodies%' THEN 'canonical_bodies'
                WHEN query LIKE '%systems%' THEN 'canonical_systems'
                ELSE 'other' END AS query_kind
      FROM pg_stat_activity
     WHERE datname=current_database() AND pid<>pg_backend_pid()
     ORDER BY pid
  ) x),'[]'::json),
  'copy',COALESCE((SELECT json_agg(x) FROM (
    SELECT pid,relid::regclass::text AS relation,command,type,
           bytes_processed,bytes_total,tuples_processed
      FROM pg_stat_progress_copy WHERE datname=current_database()
  ) x),'[]'::json)
)::text
"""

TOTALS_SQL = """
SELECT json_build_object(
 'observed_at',clock_timestamp(),
 'generation',(SELECT json_build_object(
     'id',g.derived_generation_id,'state',g.lifecycle_state,
     'expected_systems',g.expected_systems,
     'ratings_chunks',(SELECT count(*) FROM v3_derived.build_chunk b
                       WHERE b.derived_generation_id=g.derived_generation_id),
     'ratings_systems',(SELECT COALESCE(sum(b.systems),0) FROM v3_derived.build_chunk b
                        WHERE b.derived_generation_id=g.derived_generation_id),
     'search_systems',(SELECT COALESCE(sum(b.systems),0) FROM v3_derived.search_build_chunk b
                       WHERE b.derived_generation_id=g.derived_generation_id))
   FROM v3_meta.derived_generation g WHERE g.generation_key='ratings_v4_prod_p4_opt1'),
 'database',(SELECT to_jsonb(d) FROM pg_stat_database d WHERE datname=current_database()),
 'wal',(SELECT to_jsonb(w) FROM pg_stat_wal w),
 'checkpointer',(SELECT to_jsonb(c) FROM pg_stat_checkpointer c),
 'io',(SELECT json_agg(i) FROM pg_stat_io i),
 'settings',(SELECT json_object_agg(name,setting) FROM pg_settings WHERE name IN (
     'server_version','track_io_timing','track_wal_io_timing','track_activities',
     'shared_buffers','work_mem','jit','max_parallel_workers_per_gather'))
)::text
"""


def emit(kind, **data):
    print(json.dumps({'kind': kind, 'utc': datetime.now(timezone.utc).isoformat(),
                      **data}, sort_keys=True), flush=True)


def command(args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=8, check=False)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed ({result.returncode}): {result.stderr[:400]}')
    return result.stdout.strip()


def database_query(query):
    # A new connection/transaction gives each observation a fresh stats snapshot.
    result = command([
        'docker', 'exec', CONTAINERS['postgres'], 'psql',
        '-X', '--no-psqlrc', '--no-password', '--quiet', '--tuples-only', '--no-align',
        '--set', 'ON_ERROR_STOP=1', '--username', 'edfinder_v3', '--dbname', DATABASE,
        '--command', "BEGIN READ ONLY; SET LOCAL statement_timeout='5s'; "
        "SET LOCAL lock_timeout='1s'; " + query + '; COMMIT;',
    ])
    return json.loads(result)


def optional_read(path, missing):
    try:
        return path.read_text()
    except (OSError, UnicodeError) as exc:
        missing.add(f'{path}:{type(exc).__name__}')
        return None


def parse_stat(source):
    # comm may itself contain spaces and parentheses.
    prefix, _, suffix = source.rpartition(')')
    fields = suffix.split()  # Starts with field 3 (state).
    return {
        'comm': prefix.split('(', 1)[1], 'state': fields[0], 'ppid': int(fields[1]),
        'cpu_ticks': int(fields[11]) + int(fields[12]),
        'start_ticks': int(fields[19]), 'rss_pages': int(fields[21]),
    }


def numeric_lines(source):
    if source is None:
        return None
    return {parts[0].rstrip(':'): int(parts[1]) for line in source.splitlines()
            if len(parts := line.split()) == 2 and parts[1].isdigit()}


def process_snapshot(pid, missing):
    base = Path('/proc') / str(pid)
    raw = optional_read(base / 'stat', missing)
    if raw is None:
        return None
    row = {'pid': pid, **parse_stat(raw)}
    row['io'] = numeric_lines(optional_read(base / 'io', missing))
    row['wchan'] = (optional_read(base / 'wchan', missing) or '').strip()
    status = optional_read(base / 'status', missing) or ''
    namespaces = next((s.split()[1:] for s in status.splitlines() if s.startswith('NSpid:')), [])
    row['namespace_pid'] = int(namespaces[-1]) if namespaces else None
    return row


def container_info(name):
    # Explicit selected fields: no environment, arguments, mounts or credentials.
    template = ('{"id":{{json .Id}},"pid":{{.State.Pid}},'
                '"running":{{.State.Running}},"started_at":{{json .State.StartedAt}},'
                '"nano_cpus":{{.HostConfig.NanoCpus}},"memory":{{.HostConfig.Memory}},'
                '"ips":"{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",'
                '"generation":{{json (index .Config.Labels "ed-finder.generation-key")}},'
                '"source_sha":{{json (index .Config.Labels "ed-finder.source-sha")}},'
                '"encoder_workers":{{json (index .Config.Labels "ed-finder.encoder-workers")}}}')
    info = json.loads(command(['docker', 'inspect', '--format', template, name]))
    info['ips'] = info['ips'].split()
    return info


def process_ids(name):
    rows = command(['docker', 'top', name, '-eo', 'pid']).splitlines()[1:]
    return [int(row.strip()) for row in rows]


def cgroup_directory(pid, missing):
    source = optional_read(Path('/proc') / str(pid) / 'cgroup', missing) or ''
    unified = next((row[3:] for row in source.splitlines() if row.startswith('0::')), None)
    if unified is None:
        return None
    root = Path('/sys/fs/cgroup')
    candidate = root / unified.lstrip('/')
    if '..' in Path(unified).parts or not candidate.resolve().is_relative_to(root):
        raise ValueError('unexpected cgroup path')
    return candidate


def cgroup_snapshot(directory, missing):
    if directory is None:
        return {'available': False}
    return {name: optional_read(directory / name, missing) for name in (
        'cpu.stat', 'cpu.max', 'cpu.pressure', 'memory.current', 'memory.events',
        'memory.pressure', 'io.stat', 'io.pressure',
    )}


def host_snapshot(missing):
    stat = optional_read(Path('/proc/stat'), missing) or ''
    cpu = next((list(map(int, line.split()[1:9])) for line in stat.splitlines()
                if line.startswith('cpu ')), None)
    disks = {}
    for line in (optional_read(Path('/proc/diskstats'), missing) or '').splitlines():
        fields = line.split()
        if len(fields) >= 14 and not fields[2].startswith(('loop', 'ram', 'zram')):
            disks[fields[2]] = list(map(int, fields[3:14]))
    memory = {parts[0].rstrip(':'): int(parts[1])
              for line in (optional_read(Path('/proc/meminfo'), missing) or '').splitlines()
              if len(parts := line.split()) == 3 and parts[2] == 'kB'}
    return {'cpu_ticks': cpu, 'disks': disks, 'memory_kib': memory,
            'pressure': {name: optional_read(Path('/proc/pressure') / name, missing)
                         for name in ('cpu', 'memory', 'io')}}


def source_position(pid, missing):
    directory = Path('/proc') / str(pid) / 'fd'
    positions = []
    try:
        for fd in directory.iterdir():
            try:
                target = os.readlink(fd)
                if target.endswith('/galaxy.json.gz'):
                    raw = optional_read(directory.parent / 'fdinfo' / fd.name, missing)
                    positions.append(numeric_lines(raw).get('pos') if raw else None)
            except FileNotFoundError:
                pass  # Descriptors may close while being observed.
            except OSError as exc:
                missing.add(f'{fd}:{type(exc).__name__}')
    except OSError as exc:
        missing.add(f'{directory}:{type(exc).__name__}')
    return positions


def process_rates(before, after, seconds, ticks_per_second):
    result = []
    prior = {row['pid']: row for row in before}
    for row in after:
        old = prior.get(row['pid'])
        if old is None or old['start_ticks'] != row['start_ticks']:
            continue
        delta = row['cpu_ticks'] - old['cpu_ticks']
        if delta < 0:
            continue
        result.append({'pid': row['pid'], 'namespace_pid': row['namespace_pid'],
                       'start_ticks': row['start_ticks'], 'cpu_ticks_delta': delta,
                       'comm': row['comm'], 'one_core_cpu_percent':
                           100 * delta / ticks_per_second / seconds})
    return result


def process_cpu_summary(frames, role, ticks_per_second):
    """Retain matched interval deltas even for processes absent at an endpoint.

    CPU outside a process's observed intervals is unknown. Cgroup counters provide
    the full container total, including lifetimes shorter than the sample cadence.
    """
    totals = {}
    seconds = frames[-1]['elapsed_seconds'] - frames[0]['elapsed_seconds']
    for before, after in zip(frames, frames[1:], strict=False):
        interval = after['elapsed_seconds'] - before['elapsed_seconds']
        for row in process_rates(before['processes'][role], after['processes'][role],
                                 interval, ticks_per_second):
            key = row['pid'], row['start_ticks']
            total = totals.setdefault(key, {
                'pid': row['pid'], 'namespace_pid': row['namespace_pid'],
                'start_ticks': row['start_ticks'], 'comm': row['comm'],
                'observed_cpu_seconds': 0, 'observed_seconds': 0,
            })
            total['observed_cpu_seconds'] += row['cpu_ticks_delta'] / ticks_per_second
            total['observed_seconds'] += interval
    return [dict(row, one_core_cpu_percent=100 * row['observed_cpu_seconds'] / seconds)
            for row in totals.values()]


def identity_changes(before, after):
    def changed(keys):
        return any(after[role][key] != info[key] for role, info in before.items()
                   for key in keys)
    return {
        'worker_restarted': changed(('id', 'pid', 'started_at')),
        'running_state_changed': changed(('running',)),
        'resource_limits_changed': changed(('nano_cpus', 'memory')),
    }


def verify_generations(identities):
    for role in ('ratings', 'search'):
        if identities[role]['generation'] != GENERATION:
            raise ValueError(f'{role} worker generation mismatch')


def main():
    if len(sys.argv) != 1:
        raise ValueError('this fixed profiler accepts no arguments')
    if socket.gethostname() != HOST or command(['hostname', '-f']) != FQDN:
        raise ValueError('unexpected production host')
    if command(['docker', 'context', 'show']) != 'default':
        raise ValueError('unexpected docker context')
    endpoint = command(['docker', 'context', 'inspect', 'default',
                        '--format', '{{.Endpoints.docker.Host}}'])
    if endpoint != 'unix:///var/run/docker.sock':
        raise ValueError('docker context is not the local rootful socket')
    identities = {role: container_info(name) for role, name in CONTAINERS.items()}
    if any(not value['running'] for value in identities.values()):
        raise ValueError('expected existing Ratings, Search and PostgreSQL processes')
    verify_generations(identities)
    missing = set()
    groups = {role: cgroup_directory(info['pid'], missing) for role, info in identities.items()}
    ticks = os.sysconf('SC_CLK_TCK')
    emit('identity', containers=identities, duration_seconds=DURATION_SECONDS,
         interval_seconds=INTERVAL_SECONDS, clock_ticks_per_second=ticks,
         host_logical_cpus=os.cpu_count())
    before_totals = database_query(TOTALS_SQL)
    if before_totals['generation'] is None:
        raise ValueError('target Ratings generation is absent')
    emit('totals_before', data=before_totals)
    started = time.monotonic()
    process_frames = []
    sample = 0
    wait_counts = Counter()
    while True:
        pids = {role: process_ids(name) for role, name in CONTAINERS.items()}
        processes = {role: [row for pid in members
                           if (row := process_snapshot(pid, missing)) is not None]
                     for role, members in pids.items()}
        os_time = time.monotonic()
        frame = {'elapsed_seconds': os_time - started, 'processes': processes,
                 'cgroups': {role: cgroup_snapshot(path, missing) for role, path in groups.items()},
                 'host': host_snapshot(missing),
                 'source_compressed_positions': source_position(identities['ratings']['pid'], missing)}
        activity_started = time.monotonic()
        activity = database_query(ACTIVITY_SQL)
        frame['observer_query_seconds'] = time.monotonic() - activity_started
        for row in activity['activity']:
            roles = [role for role, info in identities.items() if row['client_addr'] in info['ips']]
            row['container_role'] = roles[0] if len(roles) == 1 else 'unattributed'
            wait_counts[(row['container_role'], row['state'], row['wait_event_type'],
                         row['wait_event'], row['query_kind'])] += 1
        frame['database'] = activity
        emit('sample', index=sample, **frame)
        process_frames.append({'elapsed_seconds': frame['elapsed_seconds'],
                               'processes': processes})
        sample += 1
        remaining = DURATION_SECONDS - (time.monotonic() - started)
        if remaining <= 0:
            break
        time.sleep(min(INTERVAL_SECONDS, remaining))
    after_totals = database_query(TOTALS_SQL)
    emit('totals_after', data=after_totals)
    end_identities = {role: container_info(name) for role, name in CONTAINERS.items()}
    changes = identity_changes(identities, end_identities)
    stable = not any(changes.values())
    seconds = process_frames[-1]['elapsed_seconds'] - process_frames[0]['elapsed_seconds']
    emit('summary', samples=sample, sample_seconds=seconds, identity_unchanged=stable,
         process_cpu={role: process_cpu_summary(process_frames, role, ticks)
                      for role in CONTAINERS},
         database_wait_samples=[{'role': key[0], 'state': key[1], 'type': key[2],
                                 'event': key[3], 'query_kind': key[4], 'count': value}
                                for key, value in wait_counts.items()],
         unavailable_counters=sorted(missing), **changes,
         configuration_changes_performed=False, database_writes_performed=False,
         schema_changes_performed=False, publication_performed=False)
    if not stable:
        raise ValueError('observed processes or resource limits changed during the profile')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        emit('error', error_type=type(exc).__name__, detail=str(exc))
        raise SystemExit(1) from None
