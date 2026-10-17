#!/usr/bin/env python3
"""Read-only, fail-closed entry fence for governed production mutators.

No caller text enters SQL. The CLI is also streamed from trusted main for actions
without a checkout. A missing lease file is free; this probe never creates it.
Only migration apply may supply a previously authenticated bootstrap decision.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
from typing import Callable

LEASE = Path('/run/lock/edfinder-v3-derived-purge.lock')
CONTAINER = 'edfinder-v3-phase4c-full-20260827_r5-postgres'
DATABASE_USER = 'edfinder_v3'
DATABASE_NAME = 'edfinder_v3_phase4c_full_20260827_r5'
MAX_OUTPUT = 2 * 1024 * 1024
PRESENCE_SQL = """BEGIN READ ONLY;
SET LOCAL statement_timeout='10s';
SELECT json_build_object('database',current_database(),
 'read_only',current_setting('transaction_read_only'),
 'ledger_present',to_regclass('v3_meta.derived_generation_purge_event') IS NOT NULL);
COMMIT;"""
# Use 016's own resolver, including its same-plan/request/relation scoping and
# verified=true rule for writer-fence restoration. FAILED_STOP closes a rewrite
# per design 4.2; integrity failures independently remain a refusal below.
STATE_SQL = """BEGIN READ ONLY;
SET LOCAL statement_timeout='10s';
SET LOCAL lock_timeout='5s';
WITH scopes AS MATERIALIZED (
 SELECT DISTINCT purge_id,relation_code,event_kind
 FROM v3_meta.derived_generation_purge_event
 WHERE event_kind IN ('BATCH_STARTED','REWRITE_STARTED','SERVICES_QUIESCED',
                     'WRITER_FENCE_ENABLED','AUTOVACUUM_DISABLED')
), resolved AS MATERIALIZED (
 SELECT v3_meta.purge_open_event(purge_id,relation_code,event_kind,
  CASE event_kind
   WHEN 'BATCH_STARTED' THEN ARRAY['BATCH_COMMITTED','BATCH_ROLLED_BACK']
   WHEN 'REWRITE_STARTED' THEN ARRAY['REWRITE_VERIFIED','REWRITE_ROLLED_BACK','FAILED_STOP']
   WHEN 'SERVICES_QUIESCED' THEN ARRAY['SERVICES_RESTORED']
   WHEN 'WRITER_FENCE_ENABLED' THEN ARRAY['WRITER_FENCE_RESTORED']
   WHEN 'AUTOVACUUM_DISABLED' THEN ARRAY['AUTOVACUUM_RESTORED'] END) AS e
 FROM scopes
), unresolved AS (
 SELECT DISTINCT (e).event_sequence,(e).purge_id,(e).relation_code,(e).event_kind
 FROM resolved WHERE (e).event_sequence IS NOT NULL
 UNION
 SELECT event_sequence,purge_id,relation_code,event_kind
 FROM v3_meta.derived_generation_purge_event
 WHERE event_kind='FAILED_STOP' AND failure_evidence->'integrity_failed'='true'::jsonb
)
SELECT json_build_object('database',current_database(),
 'read_only',current_setting('transaction_read_only'),
 'unresolved',COALESCE((SELECT json_agg(u ORDER BY event_sequence) FROM unresolved u),'[]'::json));
COMMIT;"""
KINDS = frozenset(('BATCH_STARTED', 'REWRITE_STARTED', 'SERVICES_QUIESCED',
                   'WRITER_FENCE_ENABLED', 'AUTOVACUUM_DISABLED', 'FAILED_STOP'))


class PurgeStateError(ValueError):
    def __init__(self, report: dict):
        self.report = report
        super().__init__(','.join(report['failures']))


def lease_state(path: Path = LEASE) -> str:
    """Probe the same inode as the purge controller without changing the host."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return 'free'
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError('lease is not regular')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 'held'
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        return 'free'
    finally:
        os.close(descriptor)


def _read(executor: Callable[[str], str], sql: str) -> dict:
    body = executor(sql)
    if not isinstance(body, str) or len(body.encode()) > MAX_OUTPUT:
        raise ValueError('purge query output invalid')
    value = json.loads(body)
    if (not isinstance(value, dict) or value.get('database') != DATABASE_NAME
            or value.get('read_only') != 'on'):
        raise ValueError('purge query identity invalid')
    return value


def check(executor: Callable[[str], str], *, bootstrap: bool = False,
          lease_held_by_caller: bool = False) -> dict:
    report = {'status': 'clear', 'failures': [], 'lease': 'unknown',
              'ledger_present': None, 'unresolved': [], 'bootstrap': False}
    try:
        # Only the purge controller uses this after acquiring this very inode.
        # All existing mutator callers continue to probe the lease themselves.
        report['lease'] = 'held_by_caller' if lease_held_by_caller else lease_state()
        if report['lease'] == 'held':
            report['failures'].append('purge_host_lease_held')
    except (OSError, ValueError):
        report['failures'].append('purge_host_lease_query_failed')
    try:
        presence = _read(executor, PRESENCE_SQL)
        if type(presence.get('ledger_present')) is not bool:
            raise ValueError('invalid ledger presence')
        report['ledger_present'] = presence['ledger_present']
        if not presence['ledger_present']:
            if bootstrap:
                report['bootstrap'] = True
            else:
                report['failures'].append('purge_ledger_absent')
        else:
            state = _read(executor, STATE_SQL)
            records = state.get('unresolved')
            if not isinstance(records, list) or any(
                not isinstance(row, dict) or row.get('event_kind') not in KINDS
                or type(row.get('event_sequence')) is not int
                or not isinstance(row.get('purge_id'), str)
                for row in records
            ):
                raise ValueError('invalid unresolved records')
            report['unresolved'] = records
            report['failures'].extend('purge_unresolved_' + kind
                                      for kind in sorted({row['event_kind'] for row in records}))
    except Exception:
        # Do not leak command output, environment, or database error text.
        report['failures'].append('purge_state_query_failed')
    if report['failures']:
        report['status'] = 'refused'
        raise PurgeStateError(report)
    return report


def docker_query(sql: str) -> str:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('DOCKER_', 'PG'))}
    env['DOCKER_HOST'] = 'unix:///var/run/docker.sock'
    result = subprocess.run(
        ['docker', '--context', 'default', 'exec', CONTAINER, 'psql', '-X', '--no-psqlrc',
         '--no-password', '--username', DATABASE_USER, '--dbname', DATABASE_NAME,
         '--host', '/var/run/postgresql', '--tuples-only', '--no-align', '--quiet',
         '--set', 'ON_ERROR_STOP=1', '--command', sql],
        env=env, capture_output=True, text=True, check=True, timeout=20,
    )
    return result.stdout.strip()


def main() -> int:
    if platform.python_implementation() != 'CPython' or sys.version_info[:2] != (3, 14):
        print(json.dumps({'status': 'refused', 'failures': ['purge_python314_required']}))
        return 78
    try:
        report = check(docker_query)
    except PurgeStateError as exc:
        print(json.dumps(exc.report, sort_keys=True))
        return 78
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
