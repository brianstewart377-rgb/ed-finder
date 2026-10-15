"""Governed purge controller: fixed SQL and sealed, bounded phase evidence.

The owner-only P2a read-only state probe is reused unchanged in substance;
progress also uses a fixed owner read to observe backend identities. Other
database sessions start by dropping to 016's executor capability.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HOST = 'ed-finder-prod'
FQDN = 'nb79a3d.mevnode.com'
CONTAINER = 'edfinder-v3-phase4c-full-20260827_r5-postgres'
DATABASE = 'edfinder_v3_phase4c_full_20260827_r5'
USER = APPLICATION_ROLE = 'edfinder_v3'
MIGRATION = '016_v3_governed_derived_purge.sql'
MIGRATION_SHA256 = '0919904cb12509082022ffdb27b7df30b8ed4b20a1b4ac2bb1e0e700778e0836'
LEASE = Path('/run/lock/edfinder-v3-derived-purge.lock')
BACKUP_SCHEDULE_LOCK = Path('/run/lock/edfinder-v3-pgbackrest-schedule.lock')
INSTALLED_WRAPPER = Path('/opt/ed-finder-v3-runtime/pgbackrest-operation.sh')
WRAPPER = ROOT / 'deploy/v3-production/backup/pgbackrest-operation.sh'
MAX_PLAN_AGE_SECONDS = 3600
MEASUREMENT_SECONDS = 5
MEASUREMENT_ATTEMPTS = 3
FREE_FLOOR_BYTES = 100_000_000_000
# Conservative planning horizon; P2b2 must replace it with the reviewed cadence
# and measured per-relation batch/rewrite bounds before opening any fence.
PLANNING_HORIZON_SECONDS = 86400
MAX_OUTPUT = 8 * 1024 * 1024
IMPLEMENTED = frozenset(('plan', 'status', 'authorize', 'verify-system-archetype-empty', 'complete'))
RELATIONS = {
    'system-search': 'system_search',
    'economy-opportunity': 'economy_opportunity',
    'body-mechanics': 'body_mechanics',
    'system-rating-vector': 'system_rating_vector',
}
TARGETS = {
    'ratings_v4_prod_p4': ('49a0c00d-e722-4209-afd8-9d62b877e30a', 'BUILDING'),
    'ratings_v4_prod_p4_opt1': ('403b2d43-820c-414a-ad57-0d4de0ca3e82', 'VALIDATING'),
}
PUBLISHED_ID = 'cfc25d36-3bc7-4011-a465-d6460eaaf826'
PUBLISHED_KEY = 'ratings_v4_prod_p4_parallel_v1'


def _load(name, path=None):
    spec = importlib.util.spec_from_file_location(name, path or Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


evidence = _load('f2d_evidence')
purge_state = _load('v3_purge_state')
schema_identity = _load('v3_schema_identity', ROOT / 'scripts/operator/v3_schema_identity.py')


def classify_mode(mode):
    if mode in IMPLEMENTED or mode == 'restore-services' or any(
            mode == prefix + relation for prefix in ('delete-', 'abort-relation-') for relation in RELATIONS):
        return mode
    if mode == 'restore-services' or any(
        mode == prefix + relation
        for prefix in ('delete-', 'rewrite-', 'abort-relation-') for relation in RELATIONS
    ):
        raise ValueError('mode_not_implemented_until_p2b2b')
    raise ValueError('unknown_mode')


def receipt(mode):
    """A stable superset of design 4.2; unobserved evidence is always null."""
    result = dict.fromkeys((
        'result', 'workflow_run_id', 'source_git_sha', 'script_sha256',
        'migration_live_sha256', 'migration_set_identity', 'migration_verified',
        'host', 'fqdn', 'container', 'database', 'postgresql_version', 'data_mount',
        'purge_id', 'reviewed_plan_sha256', 'targets', 'pointers_before', 'pointers_after',
        'workers', 'relation', 'batch_limit', 'rows_affected_this_run',
        'rows_affected_cumulative', 'rows_remaining', 'survivors_before', 'survivors_after',
        'fk_check', 'relation_bytes_before', 'relation_bytes_after',
        'filesystem_before', 'filesystem_after', 'wal_before', 'wal_after',
        'wal_byte_delta', 'archive_status', 'replication_slots', 'checkpoint_counters',
        'temp_bytes', 'backend_state', 'runner_state', 'rewrite_started_at',
        'rewrite_completed_at', 'transaction_outcome', 'competing_writer_wait',
        'writer_fence', 'autovacuum', 'purge_state', 'progress', 'next_admissible_mode',
        'skipped_scheduled_backups', 'installed_wrapper_sha256', 'expected_wrapper_sha256',
        'pointer_identities', 'extra_payload_counts', 'autovacuum_ages',
        'system_archetype_verification', 'relation_probes',
    ))
    result.update(
        schema_version='ed-finder/derived-generation-purge/v1',
        operation='v3-derived-generation-purge', phase=mode, status='stopped', failures=[],
        created_at=datetime.now(timezone.utc).isoformat(),
        migration_expected_sha256=MIGRATION_SHA256,
        read_only=mode in ('plan', 'status', 'verify-system-archetype-empty'),
        lock_timeout='5s', statement_timeout='45min', wall_clock_timeout_seconds=3600,
        reserve_bytes=FREE_FLOOR_BYTES, abort_threshold_bytes=FREE_FLOOR_BYTES,
    )
    for key in ('db_writes_performed', 'canonical_writes_performed',
                'pointer_changes_performed', 'publication_performed', 'service_changes_performed',
                'filesystem_reclamation_performed', 'migration_execution_performed',
                'application_deployment_performed'):
        result[key] = False
    return result


def authenticated_plan(path, expected_sha, *, now=None, require_fresh=True):
    if not isinstance(expected_sha, str) or re.fullmatch('[0-9a-f]{64}', expected_sha) is None:
        raise ValueError('plan_expected_sha256_invalid')
    try:
        if Path(path).stat().st_size > MAX_OUTPUT:
            raise ValueError('plan_size_exceeded')
        plan = evidence.load_sealed(path)
    except ValueError:
        raise ValueError('plan_seal_invalid') from None
    if plan['content_sha256'] != expected_sha:
        raise ValueError('plan_expected_sha256_mismatch')
    if plan.get('phase') != 'plan' or plan.get('status') != 'success':
        raise ValueError('plan_not_successful')
    try:
        created = datetime.fromisoformat(plan['created_at'])
        age = ((now or datetime.now(timezone.utc)) - created).total_seconds()
    except (KeyError, TypeError, ValueError):
        raise ValueError('plan_timestamp_invalid') from None
    if age < 0 or (require_fresh and age > MAX_PLAN_AGE_SECONDS):
        raise ValueError('plan_expired_or_future')
    if not isinstance(plan.get('reviewed_plan'), dict):
        raise ValueError('plan_database_contract_missing')
    return plan


def check_wrapper(expected_path=WRAPPER, installed_path=INSTALLED_WRAPPER):
    expected = hashlib.sha256(Path(expected_path).read_bytes()).hexdigest()
    actual = hashlib.sha256(Path(installed_path).read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError('installed_backup_wrapper_hash_mismatch')
    return expected, actual


def authenticated_verification(path, expected_sha):
    """Authenticate durable proof; ledger binding is checked when it is used."""
    if not isinstance(expected_sha, str) or re.fullmatch('[0-9a-f]{64}', expected_sha) is None:
        raise ValueError('verification_expected_sha256_invalid')
    if Path(path).stat().st_size > MAX_OUTPUT:
        raise ValueError('verification_size_exceeded')
    proof = evidence.load_sealed(path)
    if proof['content_sha256'] != expected_sha:
        raise ValueError('verification_expected_sha256_mismatch')
    if (proof.get('operation') != 'v3-derived-generation-purge'
            or proof.get('phase') != 'verify-system-archetype-empty'
            or proof.get('status') != 'success'
            or evidence.canonical_json(proof.get('result')) != evidence.canonical_json({'empty': True, 'counts': dict.fromkeys(
                ('cluster_run', 'cluster', 'cluster_member', 'system_archetype'), 0),
                'database_writes': False})):
        raise ValueError('verification_not_successful')
    return proof


def verification_gate(proof, requests):
    if proof is None:
        return {'status': 'not_proven', 'reason': 'sealed_verification_path_and_sha256_required'}
    if (len(requests) != 2 or len({row['plan_sha256'] for row in requests}) != 1
            or proof.get('reviewed_plan_sha256') != requests[0]['plan_sha256']
            or not isinstance(proof.get('purge_id'), list) or len(proof['purge_id']) != 2
            or set(proof['purge_id']) != {row['purge_id'] for row in requests}):
        raise ValueError('verification_request_plan_mismatch')
    return {'status': 'proven', 'content_sha256': proof['content_sha256'],
            'reviewed_plan_sha256': proof['reviewed_plan_sha256'], 'purge_ids': proof['purge_id']}


def check_placement(data_device, objects, temp_devices, wal_device):
    if (not objects or not temp_devices or data_device is None or
            any(obj.get('device') != data_device for obj in objects) or
            any(device != data_device for device in temp_devices) or wal_device != data_device):
        raise ValueError('tablespace_or_wal_filesystem_mismatch')
    return True


def read_sql(body):
    return ("SET ROLE v3_derived_purge_executor; SET default_transaction_read_only=off; "
            "BEGIN READ ONLY; SET LOCAL lock_timeout='5s'; "
            "SET LOCAL statement_timeout='45min'; " + body + '; COMMIT;')


MIGRATION_LEDGER_SQL = read_sql("""
SELECT COALESCE(jsonb_agg(jsonb_build_object(
 'ledger_name',migration_name,'sha256',encode(migration_sha256,'hex'))
 ORDER BY applied_at,migration_name),'[]'::jsonb) FROM v3_meta.schema_migration
""")


IDENTITY_SQL = read_sql("""
SELECT jsonb_build_object(
 'database',current_database(),'session_user',session_user,'current_user',current_user,
 'version',current_setting('server_version_num')::int,
 'postmaster_started_epoch',floor(extract(epoch FROM pg_postmaster_start_time()))::bigint,
 'data_directory',NULL,
 'temp_tablespaces',current_setting('temp_tablespaces'),
 'database_tablespace',(SELECT t.spcname FROM pg_database d JOIN pg_tablespace t ON t.oid=d.dattablespace
  WHERE d.datname=current_database()),
 'tablespaces',(SELECT jsonb_agg(jsonb_build_object('name',spcname,'location',pg_tablespace_location(oid))) FROM pg_tablespace),
 'migration_sha256',(SELECT encode(migration_sha256,'hex') FROM v3_meta.schema_migration
  WHERE migration_name='016_v3_governed_derived_purge.sql'),
 'application_role', 'edfinder_v3',
 'role_defaults', COALESCE((SELECT jsonb_agg(v) FROM pg_db_role_setting s CROSS JOIN unnest(s.setconfig) v
  WHERE s.setrole='edfinder_v3'::regrole AND s.setdatabase IN (0,(SELECT oid FROM pg_database WHERE datname=current_database()))
  AND v LIKE 'default_transaction_read_only=%'),'[]'::jsonb),
 'writer_fence_owner',(SELECT r.rolname FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner
  WHERE p.oid='v3_meta.purge_set_writer_fence(uuid,boolean)'::regprocedure AND p.prosecdef),
 'writer_fence_owner_permitted',(SELECT r.rolname='edfinder_v3' OR (r.rolcreaterole AND EXISTS(
  SELECT 1 FROM pg_auth_members m WHERE m.roleid='edfinder_v3'::regrole AND m.member=r.oid AND m.admin_option))
  FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner
  WHERE p.oid='v3_meta.purge_set_writer_fence(uuid,boolean)'::regprocedure AND p.prosecdef))
""")

# Fixed relation list includes every payload heap, its indexes, TOAST and TOAST
# indexes. File paths are values supplied by PostgreSQL, never SQL identifiers.
OBJECTS_SQL = read_sql("""
WITH heaps AS (
 SELECT c.oid,c.reltoastrelid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE (n.nspname='v3_derived' AND c.relname IN
 ('system_search','economy_opportunity','body_mechanics','system_rating_vector','system_archetype'))
 OR (n.nspname='v3_spatial' AND c.relname IN ('cluster_run','cluster','cluster_member'))
), tables AS (
 SELECT oid FROM heaps UNION SELECT reltoastrelid FROM heaps WHERE reltoastrelid<>0
), objects AS (
 SELECT oid FROM tables UNION SELECT indexrelid FROM pg_index WHERE indrelid IN (SELECT oid FROM tables)
)
SELECT jsonb_agg(jsonb_build_object('oid',c.oid,'relation',c.oid::regclass::text,
 'kind',c.relkind,'path',pg_relation_filepath(c.oid),'tablespace',c.reltablespace,
 'heap_bytes',pg_relation_size(c.oid),'index_bytes',CASE WHEN c.relkind='r' THEN pg_indexes_size(c.oid) ELSE 0 END,
 'total_bytes',pg_total_relation_size(c.oid),'relfilenode',c.relfilenode,
 'valid',NOT EXISTS(SELECT 1 FROM pg_index i WHERE i.indexrelid=c.oid AND (NOT indisvalid OR NOT indisready))))
FROM objects o JOIN pg_class c ON c.oid=o.oid
""")

AGES_SQL = read_sql("""
WITH heaps AS (SELECT oid,relname,reltoastrelid FROM pg_class
 WHERE oid IN ('v3_derived.system_search'::regclass,'v3_derived.economy_opportunity'::regclass,
 'v3_derived.body_mechanics'::regclass,'v3_derived.system_rating_vector'::regclass)), objects AS (
 SELECT relname AS relation_code,'heap' AS scope,oid FROM heaps UNION ALL
 SELECT relname,'toast',reltoastrelid FROM heaps WHERE reltoastrelid<>0)
SELECT jsonb_build_object('xid_next',pg_snapshot_xmax(pg_current_snapshot())::text,
 'objects',(SELECT jsonb_agg(jsonb_build_object('relation_code',o.relation_code,'scope',o.scope,
 'oid',c.oid,'relminmxid',c.relminmxid::text,'xid_age',age(c.relfrozenxid)::bigint,
 'mxid_age',mxid_age(c.relminmxid)::bigint,
 'xid_limit',least(current_setting('autovacuum_freeze_max_age')::bigint,COALESCE(
 (SELECT option_value::bigint FROM pg_options_to_table(c.reloptions) WHERE option_name='autovacuum_freeze_max_age'),9223372036854775807)),
 'mxid_limit',least(current_setting('autovacuum_multixact_freeze_max_age')::bigint,COALESCE(
 (SELECT option_value::bigint FROM pg_options_to_table(c.reloptions) WHERE option_name='autovacuum_multixact_freeze_max_age'),9223372036854775807))))
 FROM objects o JOIN pg_class c ON c.oid=o.oid))
""")

WAL_SQL = read_sql("""
SELECT jsonb_build_object('lsn',pg_current_wal_lsn()::text,
 'bytes',NULL,
 'archiver',(SELECT to_jsonb(a) FROM pg_stat_archiver a),
 'archive_mode',current_setting('archive_mode'),
 'slots',COALESCE((SELECT jsonb_agg(jsonb_build_object('slot_name',slot_name,'active',active,
 'wal_status',wal_status,'retained_bytes',pg_wal_lsn_diff(pg_current_wal_lsn(),restart_lsn))) FROM pg_replication_slots),'[]'::jsonb),
 'replication',COALESCE((SELECT jsonb_agg(jsonb_build_object('pid',pid,'state',state,
 'write_lag',write_lag,'flush_lag',flush_lag,'replay_lag',replay_lag)) FROM pg_stat_replication),'[]'::jsonb),
 'checkpoints',(SELECT to_jsonb(c) FROM pg_stat_checkpointer c),
 'temp_bytes',(SELECT temp_bytes FROM pg_stat_database WHERE datname=current_database()))
""")

WAL_LSN_DIFF_SQL = read_sql("""
SELECT jsonb_build_object('wal_byte_delta',
 pg_wal_lsn_diff(%(after_lsn)s::pg_lsn,%(before_lsn)s::pg_lsn)::bigint)
""")


def finalize_wal_delta(runtime, report):
    """Use server LSN arithmetic; directory growth is not WAL generated."""
    before = (report.get('wal_before') or {}).get('lsn')
    after = runtime.query(WAL_SQL)
    if not isinstance(after, dict):
        raise ValueError('wal_byte_delta_unavailable')
    after_lsn = after.get('lsn')
    if any(not isinstance(value, str) or re.fullmatch('[0-9A-Fa-f]+/[0-9A-Fa-f]+', value) is None
           for value in (before, after_lsn)):
        raise ValueError('wal_byte_delta_unavailable')
    result = runtime.query(WAL_LSN_DIFF_SQL, {'before_lsn': before, 'after_lsn': after_lsn})
    delta = result.get('wal_byte_delta') if isinstance(result, dict) else None
    if type(delta) is not int or delta < 0:
        raise ValueError('wal_byte_delta_unavailable')
    # WAL_SQL deliberately leaves directory bytes unmeasured. Retain the
    # phase's final filesystem measurement while refreshing its server LSN.
    measured = report.get('wal_after') or {}
    report.update(wal_after={**measured, **{key: value for key, value in after.items()
                                         if key != 'bytes'}}, wal_byte_delta=delta)

# Like the P2a probe, this fixed owner read is needed to see the recorded
# backend's full identity; SET ROLE masks other sessions' backend_start.
PROGRESS_SQL = "BEGIN READ ONLY; SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='10s'; " + """
SELECT jsonb_build_object('requests',COALESCE((SELECT jsonb_agg(to_jsonb(r)) FROM
 (SELECT purge_id,derived_generation_id,generation_key,plan_sha256,created_at FROM v3_meta.derived_generation_purge_request) r),'[]'::jsonb),
 'relation_progress',COALESCE((SELECT jsonb_agg(to_jsonb(p)) FROM (
 SELECT purge_id,relation_code,
 count(*) FILTER (WHERE event_kind='BATCH_COMMITTED') AS committed_batches,
 COALESCE(sum(rows_affected) FILTER (WHERE event_kind='BATCH_COMMITTED'),0) AS rows_affected_cumulative,
 bool_or(event_kind='REWRITE_VERIFIED') AS rewrite_verified
 FROM v3_meta.derived_generation_purge_event WHERE relation_code IS NOT NULL
 GROUP BY purge_id,relation_code) p),'[]'::jsonb),
 'events',COALESCE((SELECT jsonb_agg(to_jsonb(e)) FROM (
 SELECT DISTINCT ON (purge_id,relation_code,event_kind) purge_id,relation_code,event_kind,event_sequence,
 rows_affected,rows_remaining,created_at,operational_payload,failure_evidence,backend_pid,backend_start
 FROM v3_meta.derived_generation_purge_event ORDER BY purge_id,relation_code,event_kind,event_sequence DESC) e),'[]'::jsonb),
 'backends',COALESCE((SELECT jsonb_agg(jsonb_build_object('pid',pid,'backend_start',backend_start,
 'backend_type',backend_type,'state',state,'backend_xid',backend_xid::text)) FROM pg_stat_activity
 WHERE datname=current_database() AND pid<>pg_backend_pid()),'[]'::jsonb))
""" + '; COMMIT;'

POINTER_IDENTITIES_SQL = read_sql("""
SELECT jsonb_build_object(
 'canonical',(SELECT to_jsonb(p)||jsonb_build_object('generation_key',g.generation_key)
 FROM v3_meta.current_canonical_generation p JOIN v3_meta.canonical_generation g USING(generation_id) WHERE p.singleton),
 'derived',(SELECT to_jsonb(p)||jsonb_build_object('generation_key',g.generation_key)
 FROM v3_meta.current_derived_generation p JOIN v3_meta.derived_generation g USING(derived_generation_id) WHERE p.singleton),
 'spatial',(SELECT to_jsonb(p)||jsonb_build_object('canonical_generation_id',g.canonical_generation_id,
 'pyramid_version',g.pyramid_version) FROM v3_spatial.current_spatial_generation p
 JOIN v3_spatial.spatial_generation g USING(spatial_generation_id) WHERE p.singleton))
""")

EXTRA_COUNTS_SQL = read_sql("""
WITH ids AS (SELECT unnest(ARRAY['49a0c00d-e722-4209-afd8-9d62b877e30a'::uuid,
 '403b2d43-820c-414a-ad57-0d4de0ca3e82'::uuid,'cfc25d36-3bc7-4011-a465-d6460eaaf826'::uuid]) AS id)
SELECT jsonb_object_agg(id::text,jsonb_build_object(
 'cluster_run',(SELECT count(*) FROM v3_spatial.cluster_run WHERE derived_generation_id=id),
 'cluster',(SELECT count(*) FROM v3_spatial.cluster WHERE derived_generation_id=id),
 'cluster_member',(SELECT count(*) FROM v3_spatial.cluster_member WHERE derived_generation_id=id),
 'system_archetype',(SELECT count(*) FROM v3_derived.system_archetype WHERE derived_generation_id=id))) FROM ids
""")

# Status never calls purge_snapshot(): that function scans all payload heaps.
# Catalog/ledger metadata is available even while a heap is being rewritten.
STATUS_METADATA_SQL = read_sql("""
SELECT jsonb_build_object('targets',(SELECT jsonb_agg(jsonb_build_object(
 'id',derived_generation_id,'key',generation_key,'state',lifecycle_state,
 'manifest_sha256',encode(manifest_sha256,'hex')) ORDER BY derived_generation_id)
 FROM v3_meta.derived_generation WHERE derived_generation_id IN
 ('49a0c00d-e722-4209-afd8-9d62b877e30a','403b2d43-820c-414a-ad57-0d4de0ca3e82')),
 'snapshot',jsonb_build_object(
 'canonical',(SELECT to_jsonb(p) FROM v3_meta.current_canonical_generation p WHERE singleton),
 'derived',(SELECT to_jsonb(p) FROM v3_meta.current_derived_generation p WHERE singleton),
 'spatial',(SELECT to_jsonb(p) FROM v3_spatial.current_spatial_generation p WHERE singleton),
 'retained',NULL,'survivors',NULL,
 'schema_ledger_sha256',(SELECT encode(sha256(convert_to(COALESCE(jsonb_agg(
 jsonb_build_array(migration_name,encode(migration_sha256,'hex')) ORDER BY migration_name)::text,'[]'),'UTF8')),'hex')
 FROM v3_meta.schema_migration)))
""")
# Identifiers come exclusively from the committed enum, never request text.
# Acquire the heap lock before invoking size functions (which can otherwise
# wait independently of lock_timeout), then release it after this one probe.
STATUS_RELATION_SQL = {code: read_sql(
    f"LOCK TABLE v3_derived.{code} IN ACCESS SHARE MODE; "
    "SELECT jsonb_build_object('targets',(SELECT jsonb_object_agg(id::text,"
    f"(SELECT count(*) FROM v3_derived.{code} WHERE derived_generation_id=id)) "
    "FROM unnest(ARRAY['49a0c00d-e722-4209-afd8-9d62b877e30a'::uuid,"
    "'403b2d43-820c-414a-ad57-0d4de0ca3e82'::uuid]) id),"
    f"'survivors',(SELECT count(*) FROM v3_derived.{code} WHERE "
    "derived_generation_id='cfc25d36-3bc7-4011-a465-d6460eaaf826'),"
    f"'total_bytes',pg_total_relation_size('v3_derived.{code}'::regclass))"
) for code in RELATIONS.values()}


class Runtime:
    def __init__(self, report):
        self.report = report
        self.lease_fd = None
        self.deadline = time.monotonic() + 3600
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('PG', 'DOCKER_'))}
        self.env['DOCKER_HOST'] = 'unix:///var/run/docker.sock'

    def run(self, argv, *, input=None, timeout=30, allow_failure=False):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError('wall_clock_timeout')
        timeout = min(timeout, remaining)
        try:
            result = subprocess.run(argv, input=input, capture_output=True, text=True,
                                    env=self.env, check=False, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError('bounded_command_failed') from None
        if result.returncode and not allow_failure:
            # psql's SQLSTATE-only diagnostics allow a bounded, safe recovery
            # signal without exposing server errors or command output.
            if '--no-psqlrc' in argv and re.search(r'\bERROR:\s+(23503|XX001|XX002)\b', result.stderr):
                raise RuntimeError('delete_fk_or_index_failure')
            if '--no-psqlrc' in argv and re.search(r'\bERROR:\s+55P03\b', result.stderr):
                raise RuntimeError('database_lock_timeout')
            raise RuntimeError('bounded_command_failed')
        if len(result.stdout.encode()) > MAX_OUTPUT:
            raise RuntimeError('command_output_bound_exceeded')
        return result.stdout.strip()

    def docker(self, *argv, **kwargs):
        return self.run(['docker', '--context', 'default', *argv], **kwargs)

    def query(self, sql, params=None, *, write=False):
        # psql variable quoting is a data binding layer. Values are hex-encoded
        # UTF-8, decoded inside PostgreSQL; neither SQL nor identifiers come from
        # request text. --file=- is essential: -c does not expand psql variables.
        is_batch = sql == _load('v3_purge_transactions').BATCH_SQL
        assignments = []
        for key, value in (params or {}).items():
            if re.fullmatch('[a-z][a-z0-9_]*', key) is None:
                raise ValueError('invalid_parameter_name')
            value = evidence.canonical_json(value) if not isinstance(value, str) else value
            assignments.append('\\set ' + key + " '" + value.encode().hex() + "'")
            sql = sql.replace('%(' + key + ')s', "convert_from(decode(:'" + key + "','hex'),'UTF8')")
        if '%(' in sql:
            raise ValueError('unbound_parameter')
        if write:
            self.report['read_only'] = False
            self.report['db_writes_performed'] = None
            self.report['transaction_outcome'] = None
        body = self.docker('exec', '-i', CONTAINER, 'psql', '-X', '--no-psqlrc', '--no-password',
                           '--username', USER, '--dbname', DATABASE, '--host', '/var/run/postgresql',
                           '--tuples-only', '--no-align', '--quiet', '--set', 'ON_ERROR_STOP=1',
                           '--set', 'VERBOSITY=sqlstate',
                           '--file=-', input='\n'.join(assignments) + '\n' + sql,
                           timeout=2 if "'competing_writers'" in sql else 2760)
        try:
            if is_batch:
                parts = [json.loads(line) for line in body.splitlines() if line]
                if (len(parts) != 2 or any(not isinstance(part, dict) for part in parts)
                        or type(parts[0].get('start_event')) is not int
                        or parts[0]['start_event'] <= 0):
                    raise ValueError('batch_result_invalid')
                value = {**parts[0], **parts[1]}
            else:
                value = json.loads(body)
        except ValueError:
            raise RuntimeError('database_result_invalid') from None
        if write:
            self.report['db_writes_performed'] = True
            self.report['transaction_outcome'] = 'committed'
        return value

    def guard(self):
        if self.run(['hostname', '-s']) != HOST or self.run(['hostname', '-f']) != FQDN:
            raise ValueError('unexpected_host_identity')
        if self.run(['docker', 'context', 'show']) != 'default':
            raise ValueError('unexpected_docker_context')
        context = json.loads(self.docker('context', 'inspect', 'default'))
        if len(context) != 1 or context[0]['Endpoints']['docker']['Host'] != 'unix:///var/run/docker.sock':
            raise ValueError('unexpected_docker_endpoint')
        if self.docker('inspect', '-f', '{{.State.Running}}', CONTAINER) != 'true':
            raise ValueError('postgres_container_unavailable')
        self.report.update(host=HOST, fqdn=FQDN, container=CONTAINER, database=DATABASE)
        sha = self.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'])
        if re.fullmatch('[0-9a-f]{40}', sha) is None:
            raise ValueError('source_identity_invalid')
        self.report['source_git_sha'] = sha
        wrapper_relative = 'deploy/v3-production/backup/pgbackrest-operation.sh'
        committed_blob = self.run(['git', '-C', str(ROOT), 'rev-parse', sha + ':' + wrapper_relative])
        local_blob = self.run(['git', '-C', str(ROOT), 'hash-object', '--no-filters', '--',
                               str(ROOT / wrapper_relative)])
        # Compare Git's byte-exact blob identities: Runtime.run strips stdout,
        # so hashing `git show` text would lose the source's trailing newline.
        if re.fullmatch('[0-9a-f]{40}', committed_blob) is None or local_blob != committed_blob:
            raise ValueError('backup_wrapper_committed_source_mismatch')
        self.report['workflow_run_id'] = os.environ.get('GITHUB_RUN_ID') or None
        self.report['script_sha256'] = evidence.canonical_sha256({
            relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in sorted((
                'deploy/v3-production/backup/pgbackrest-operation.sh',
                'scripts/operator/actions/v3-derived-generation-purge.sh',
                'scripts/operator/actions/v3-derived-lifecycle-status.sh',
                'scripts/operator/lib/f2d_evidence.py',
                'scripts/operator/lib/v3_generation_purge.py',
                'scripts/operator/lib/v3_purge_delete.py',
                'scripts/operator/lib/v3_purge_state.py',
                'scripts/operator/lib/v3_purge_transactions.py',
                'scripts/operator/v3_schema_identity.py',
            ))})

    @contextmanager
    def backup_lock(self):
        """Exclude scheduled and manually started pgBackRest backup/verify."""
        fd = os.open(BACKUP_SCHEDULE_LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('backup_schedule_lock_not_regular')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('backup_schedule_lock_held') from None
            processes = self.docker('top', CONTAINER, '-eo', 'pid,args')
            if not processes or not re.search(r'\bPID\b', processes.splitlines()[0]):
                raise ValueError('backup_process_state_unknown')
            active = sum(bool(re.search(r'\bpgbackrest\b', line, re.I) and
                              re.search(r'\b(?:backup|verify)\b', line, re.I))
                         for line in processes.splitlines()[1:])
            self.report['backup_processes'] = active
            if active:
                raise ValueError('backup_or_verify_process_active')
            yield
        finally:
            os.close(fd)

    @contextmanager
    def lease(self):
        fd = os.open(LEASE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('purge_host_lease_not_regular')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('purge_host_lease_held') from None
            self.lease_fd = fd
            yield
        finally:
            self.lease_fd = None
            os.close(fd)

    def state(self, *, allow_unresolved=False):
        # Existing P2a query is BEGIN READ ONLY as the owner: 016 does not grant
        # purge_open_event to executor. No action mutation uses this connection.
        try:
            report = purge_state.check(lambda sql: self.owner_read(sql),
                                       lease_held_by_caller=self.lease_fd is not None)
        except purge_state.PurgeStateError as exc:
            report = exc.report
            self.report['purge_state'] = report
            if not allow_unresolved or any(failure in report['failures'] for failure in
                    ('purge_state_query_failed', 'purge_ledger_absent', 'purge_host_lease_query_failed')):
                raise ValueError(','.join(report['failures'])) from None
        self.report['purge_state'] = report
        return report

    def owner_read(self, sql):
        return self.docker('exec', CONTAINER, 'psql', '-X', '--no-psqlrc', '--no-password',
                           '--username', USER, '--dbname', DATABASE, '--host', '/var/run/postgresql',
                           '--tuples-only', '--no-align', '--quiet', '--set', 'ON_ERROR_STOP=1',
                           '--command', sql)

    def workers(self):
        # Reuse the authoritative action, including its full named-container
        # list and its unknown-state refusal, rather than maintaining a copy.
        result = json.loads(self.run(['bash', str(ROOT / 'scripts/operator/actions/v3-derived-lifecycle-status.sh')], timeout=300, allow_failure=True))
        workers = result.get('workers')
        if not isinstance(workers, list) or not workers or any(w.get('running') is None for w in workers):
            raise ValueError('worker_state_unknown')
        self.report['workers'] = workers
        return result.get('all_named_workers_stopped') is True

    def status_workers(self):
        # The lifecycle action also probes relation sizes, which can block on
        # VACUUM FULL. Status needs only Docker's worker observation here.
        names = ('edfinder-ratings-v4-prod-p4', 'edfinder-ratings-v4-prod-p4-opt1',
                 'edfinder-ratings-v4-prod-p4-parallel-v1', 'edfinder-v3-system-search-p4-opt1',
                 'edfinder-v3-system-search-p4-parallel-v1', 'edfinder-v3-system-archetype-p4-parallel-v1')
        rows = self.docker('container', 'ls', '--all', '--format', '{{json .}}')
        containers = [json.loads(row) for row in rows.splitlines() if row]
        indexed = {row['Names']: row for row in containers}
        self.report['workers'] = [dict(name=name, exists=name in indexed,
                                       running=indexed[name]['State'] == 'running' if name in indexed else False)
                                  for name in names]

    def device(self, path):
        if not isinstance(path, str) or not path.startswith('/') or '\x00' in path:
            raise ValueError('database_path_invalid')
        value = self.docker('exec', CONTAINER, 'stat', '-L', '-c', '%d', '--', path)
        if not value.isdecimal():
            raise ValueError('filesystem_device_unknown')
        return int(value)

    def data_directory(self):
        # data_directory is a GUC_SUPERUSER_ONLY setting. Read PostgreSQL's
        # own startup PID file through the pinned container instead of granting
        # extra SQL capabilities to 016's executor. No credential file is read.
        value = self.docker('exec', CONTAINER, 'sh', '-c',
                            'test -n "$PGDATA" && test -f "$PGDATA/postmaster.pid" || exit 1; '
                            'pid="$(sed -n "1p" "$PGDATA/postmaster.pid")"; '
                            'case "$pid" in ""|*[!0-9]*) exit 1;; esac; '
                            'directory="$(sed -n "2p" "$PGDATA/postmaster.pid")"; '
                            'test "$(readlink -f -- "/proc/$pid/cwd")" = "$directory" || exit 1; '
                            'sed -n "2,3p" "$PGDATA/postmaster.pid"')
        parts = value.splitlines()
        if (len(parts) != 2 or not parts[0].startswith('/') or '..' in parts[0].split('/')
                or not parts[1].isdecimal() or int(parts[1]) != self.report.get('postmaster_started_epoch')):
            raise ValueError('data_directory_unresolved')
        return parts[0]

    def storage(self, identity, objects):
        directory = identity['data_directory']
        device = self.device(directory)
        for obj in objects:
            path = obj['path']
            if not isinstance(path, str) or path.startswith('/') or '..' in path.split('/'):
                raise ValueError('relation_path_invalid')
            obj['device'] = self.device(directory + '/' + path)
        temps = next(csv.reader([identity['temp_tablespaces']], skipinitialspace=True))
        # An empty setting (or list entry) uses this database's default
        # tablespace, which can live outside the data directory.
        spaces = {item['name']: item['location'] for item in identity['tablespaces']}
        temp_devices = []
        for name in temps or ['']:
            name = name or identity.get('database_tablespace')
            location = directory if name in ('pg_default', 'pg_global') else spaces.get(name)
            try:
                temp_devices.append(self.device(location))
            except (ValueError, RuntimeError, OSError):
                raise ValueError('tablespace_or_wal_filesystem_mismatch') from None
        wal_device = self.device(directory + '/pg_wal')
        check_placement(device, objects, temp_devices, wal_device)
        mounts = json.loads(self.docker('inspect', '-f', '{{json .Mounts}}', CONTAINER))
        matches = [m for m in mounts if directory == m['Destination'] or directory.startswith(m['Destination'].rstrip('/') + '/')]
        if not matches:
            raise ValueError('data_mount_unresolved')
        mount = max(matches, key=lambda m: len(m['Destination']))
        source = mount['Source'] + directory[len(mount['Destination']):]
        if os.stat(source).st_dev != device:
            raise ValueError('host_data_mount_device_mismatch')
        disk = os.statvfs(source)
        filesystem = dict(total_bytes=disk.f_blocks * disk.f_frsize,
                          used_bytes=(disk.f_blocks - disk.f_bfree) * disk.f_frsize,
                          free_bytes=disk.f_bavail * disk.f_frsize)
        self.report['data_mount'] = dict(source=source, destination=directory, device=device,
                                         temp_devices=temp_devices, wal_device=wal_device)
        return filesystem


def validate_identity(identity, report, *, runtime=None):
    """Reuse the verified sql/v3/migration-manifest.txt lineage and pin 016."""
    try:
        entries = schema_identity.derive_entries(ROOT)
    except schema_identity.SchemaIdentityError:
        raise ValueError('committed_migration_hash_mismatch') from None
    matching = [entry for entry in entries if entry['ledger_name'] == MIGRATION]
    if matching != [{'ledger_name': MIGRATION, 'sha256': MIGRATION_SHA256, 'mode': 'auto',
                     'path': 'sql/v3/migrations/' + MIGRATION}]:
        raise ValueError('committed_migration_hash_mismatch')
    if runtime is not None:
        require_reviewed_migration_ledger(runtime, entries)
    report['migration_live_sha256'] = identity.get('migration_sha256')
    if (identity.get('database') != DATABASE or identity.get('session_user') != USER or
            identity.get('current_user') != 'v3_derived_purge_executor' or
            not 180000 <= identity.get('version', 0) < 190000 or
            identity.get('migration_sha256') != MIGRATION_SHA256):
        raise ValueError('database_or_guard_migration_identity_mismatch')
    report.update(migration_verified=True, postgresql_version=identity['version'],
                  writer_fence={'application_role': APPLICATION_ROLE,
                                'owner': identity.get('writer_fence_owner'),
                                'owner_permitted': identity.get('writer_fence_owner_permitted'),
                                'role_defaults': identity.get('role_defaults')})
    if identity.get('writer_fence_owner_permitted') is not True:
        raise ValueError('writer_fence_owner_precondition_failed')
    defaults = identity.get('role_defaults')
    if not isinstance(defaults, list) or any(v != 'default_transaction_read_only=off' for v in defaults):
        raise ValueError('application_role_already_read_only_or_unknown')
    return entries


def require_reviewed_migration_ledger(runtime, entries):
    """Require the entire reviewed lineage, in the migration runner's order."""
    expected = [{key: entry[key] for key in ('ledger_name', 'sha256')} for entry in entries]
    if runtime.query(MIGRATION_LEDGER_SQL) != expected:
        raise ValueError('live_migration_ledger_unreviewed')


def age_sample(runtime):
    value = runtime.query(AGES_SQL)
    if (not isinstance(value, dict) or not isinstance(value.get('objects'), list)
            or not value['objects'] or not str(value.get('xid_next', '')).isdecimal()):
        raise ValueError('autovacuum_age_observation_invalid')
    scopes = set()
    for obj in value['objects']:
        scope = (obj.get('relation_code'), obj.get('scope'))
        if scope in scopes or scope[0] not in RELATIONS.values() or scope[1] not in ('heap', 'toast'):
            raise ValueError('autovacuum_age_scope_invalid')
        scopes.add(scope)
        if any(type(obj.get(k)) is not int or obj[k] < 0 for k in
               ('oid', 'xid_age', 'mxid_age', 'xid_limit', 'mxid_limit')):
            raise ValueError('autovacuum_age_observation_invalid')
    if {scope[0] for scope in scopes if scope[1] == 'heap'} != set(RELATIONS.values()):
        raise ValueError('autovacuum_heap_observation_missing')
    return value


def measure_autovacuum(runtime):
    for _attempt in range(MEASUREMENT_ATTEMPTS):
        before = age_sample(runtime)
        started = time.monotonic()
        time.sleep(MEASUREMENT_SECONDS)
        after = age_sample(runtime)
        elapsed = time.monotonic() - started
        previous = {obj['oid']: obj for obj in before['objects']}
        if ({obj['oid'] for obj in after['objects']} != set(previous) or any(
                obj['relminmxid'] != previous[obj['oid']]['relminmxid'] for obj in after['objects'])):
            continue  # A vacuum moved a MultiXact baseline; never use that rate.
        xid_delta = int(after['xid_next']) - int(before['xid_next'])
        if xid_delta < 0 or elapsed < MEASUREMENT_SECONDS:
            raise ValueError('autovacuum_measurement_invalid')
        config = {}
        observations = []
        for obj in after['objects']:
            delta = obj['mxid_age'] - previous[obj['oid']]['mxid_age']
            if delta < 0:
                break
            observations.append({**obj, 'xid_rate': xid_delta / elapsed, 'mxid_rate': delta / elapsed,
                                 'xid_ceiling': obj['xid_limit'] * 4 // 5,
                                 'mxid_ceiling': obj['mxid_limit'] * 4 // 5})
        else:
            for code in RELATIONS.values():
                scopes = [obj for obj in observations if obj['relation_code'] == code]
                config[code] = {
                    'xid_ceiling': min(obj['xid_ceiling'] for obj in scopes),
                    'mxid_ceiling': min(obj['mxid_ceiling'] for obj in scopes),
                    'xid_rate': max(obj['xid_rate'] for obj in scopes),
                    'mxid_rate': max(obj['mxid_rate'] for obj in scopes),
                    'remaining_seconds': PLANNING_HORIZON_SECONDS,
                }
                for obj in scopes:
                    bounds = config[code]
                    if (obj['xid_age'] + bounds['xid_rate'] * PLANNING_HORIZON_SECONDS >= bounds['xid_ceiling']
                            or obj['mxid_age'] + bounds['mxid_rate'] * PLANNING_HORIZON_SECONDS >= bounds['mxid_ceiling']):
                        raise ValueError('autovacuum_fence_deadline_unsafe')
            return {'measurement_seconds': elapsed, 'observations': observations, 'configuration': config,
                    'planning_horizon_seconds': PLANNING_HORIZON_SECONDS,
                    'cadence_requires_p2b2_rehearsal': True}
    raise ValueError('autovacuum_measurement_baseline_changed')


def wal_health(before, after):
    for value in (before, after):
        if (not isinstance(value, dict) or value.get('archive_mode') not in ('on', 'always') or
                not isinstance(value.get('archiver'), dict) or not isinstance(value.get('slots'), list)):
            raise ValueError('wal_health_unknown')
        if any(slot.get('active') is not True or slot.get('wal_status') not in ('reserved',)
               for slot in value['slots']):
            raise ValueError('wal_retention_unhealthy')
        archive = value['archiver']
        if type(archive.get('failed_count')) is not int:
            raise ValueError('archiver_counter_unknown')
        failed = archive.get('last_failed_time')
        archived = archive.get('last_archived_time')
        if failed is not None and (archived is None or datetime.fromisoformat(failed) > datetime.fromisoformat(archived)):
            raise ValueError('archiver_last_failure_newer_than_success')
    if after['archiver']['failed_count'] != before['archiver']['failed_count']:
        raise ValueError('archiver_failed_count_changed')


def status_deadlines(ages, state, progress):
    events = {event['event_sequence']: event for event in progress['events']}
    result = []
    for opened in state['unresolved']:
        if opened['event_kind'] != 'AUTOVACUUM_DISABLED':
            continue
        event = events.get(opened['event_sequence'])
        if event is None:
            raise ValueError('autovacuum_fence_evidence_missing')
        for obj in ages['objects']:
            if obj['relation_code'] != opened['relation_code']:
                continue
            config = event['operational_payload'].get(obj['scope'])
            if not isinstance(config, dict):
                raise ValueError('autovacuum_fence_scope_missing')
            projections = {}
            for kind in ('xid', 'mxid'):
                ceiling = config[kind + '_ceiling']
                rate = config[kind + '_rate']
                age = obj[kind + '_age']
                projections[kind + '_seconds_to_ceiling'] = max(0, (ceiling - age) / rate) if rate > 0 else None
            known = [v for v in projections.values() if v is not None]
            result.append({**config, **obj, **projections,
                           'ages_at_fence': {k: config.get(k) for k in ('xid_age', 'mxid_age')},
                           'nearer_ceiling_seconds': min(known) if known else None,
                           'ceiling_exceeded': obj['xid_age'] >= config['xid_ceiling'] or obj['mxid_age'] >= config['mxid_ceiling']})
    return result


def next_mode(state, progress, counts=None, deadlines=(), *, verification=None):
    def empty(code):
        if counts is None or any(t['payload_counts'].get(code) is None for t in counts['targets']):
            return None
        return all(t['payload_counts'][code] == 0 for t in counts['targets'])

    kinds = {event['event_kind'] for event in state['unresolved']}
    if 'FAILED_STOP' in kinds:
        return {'mode': 'status', 'reason': 'owner_integrity_review_required'}
    if kinds & {'WRITER_FENCE_ENABLED', 'SERVICES_QUIESCED'}:
        return {'mode': 'restore-services', 'implemented': True}
    for kind, prefix in (('BATCH_STARTED', 'delete-'), ('REWRITE_STARTED', 'rewrite-'),
                         ('AUTOVACUUM_DISABLED', 'delete-')):
        rows = [row for row in state['unresolved'] if row['event_kind'] == kind]
        if rows:
            code = rows[0]['relation_code']
            relation = next(name for name, value in RELATIONS.items() if value == code)
            if kind == 'AUTOVACUUM_DISABLED' and empty(code) is True:
                prefix = 'rewrite-'
            elif kind == 'AUTOVACUUM_DISABLED' and any(d['relation_code'] == code and d['ceiling_exceeded'] for d in deadlines):
                prefix = 'abort-relation-'
            elif kind == 'AUTOVACUUM_DISABLED' and empty(code) is None:
                return {'mode': 'status', 'reason': 'relation_counts_not_proven'}
            return {'mode': prefix + relation, 'implemented': prefix != 'rewrite-'}
    if not progress['requests']:
        return {'mode': 'plan', 'reason': 'fresh_plan_before_authorize'}
    if all(any(event['purge_id'] == request['purge_id'] and event['event_kind'] == 'COMPLETED'
               for event in progress['events']) for request in progress['requests']):
        return {'mode': 'status', 'reason': 'completed'}
    if not verification or verification['status'] != 'proven':
        return {'mode': 'verify-system-archetype-empty', 'implemented': True,
                'reason': 'system_archetype_empty_not_proven'}
    verified = {event['relation_code'] for event in progress['events'] if event['event_kind'] == 'REWRITE_VERIFIED'}
    for name, code in RELATIONS.items():
        if code not in verified:
            if empty(code) is None:
                return {'mode': 'status', 'reason': 'relation_counts_not_proven'}
            return {'mode': ('rewrite-' if empty(code) else 'delete-') + name,
                    'implemented': not empty(code)}
    return {'mode': 'complete', 'implemented': True}


def status_counts(runtime, report, state, progress):
    """Independent probes never let one rewritten heap hide recovery evidence."""
    opened = {row['event_sequence'] for row in state['unresolved'] if row['event_kind'] == 'REWRITE_STARTED'}
    live = {event['relation_code']: event for event in progress['events']
            if event['event_sequence'] in opened and any(
                backend['pid'] == event['backend_pid'] and backend['backend_start'] == event['backend_start']
                for backend in progress['backends'])}
    probes = {}
    report['relation_probes'] = probes
    for code, sql in STATUS_RELATION_SQL.items():
        probe = dict(targets=None, survivors=None, total_bytes=None, reason=None)
        probes[code] = probe
        if code in live:
            event = live[code]
            probe.update(reason='open_rewrite_backend', backend_pid=event['backend_pid'],
                         backend_start=event['backend_start'])
            continue
        try:
            probe.update(runtime.query(sql))
        except RuntimeError as exc:
            if str(exc) != 'database_lock_timeout':
                raise
            probe['reason'] = 'lock_timeout'
    return probes


def _snapshot_fields(report, observed):
    snapshot = observed['snapshot']
    report['migration_set_identity'] = snapshot['schema_ledger_sha256']
    report['pointers_before'] = {k: snapshot[k] for k in ('canonical', 'derived', 'spatial')}
    report['survivors_before'] = snapshot['survivors']
    report['targets'] = [{**target, 'original_state': TARGETS[target['key']][1], 'current_state': target['state']}
                         for target in observed['targets']]
    report['rows_remaining'] = {target['id']: target['payload_counts'] for target in observed['targets']}


def execute(mode, runtime, report, plan=None, *, actor='governed-operator', reason='Owner-authorized governed purge',
            verification=None, phase_options=None):
    """Shared gates precede every mutation; P2b2 can extend the mode dispatch."""
    if mode == 'restore-services' or mode.startswith(('delete-', 'abort-relation-')):
        _load('v3_purge_delete').dispatch(argparse.Namespace(**globals()), mode, runtime, report, plan, verification,
                                         **(phase_options or {}))
        return
    transactions = _load('v3_purge_transactions')
    # First observation on mutating modes is P2a admission, before taking lease.
    state = runtime.state(allow_unresolved=mode == 'status')
    report['purge_state'] = state
    if mode == 'status':
        progress = runtime.query(PROGRESS_SQL)
        report['progress'] = progress
        report['backend_state'] = progress['backends']
        # Populate recovery guidance before any payload lock or scan.
        report['next_admissible_mode'] = next_mode(state, progress)
        report['system_archetype_verification'] = verification_gate(verification, progress['requests'])
    identity = runtime.query(IDENTITY_SQL)
    if mode != 'status':
        report['postmaster_started_epoch'] = identity.get('postmaster_started_epoch')
        identity['data_directory'] = runtime.data_directory()
    if mode != 'status':
        entries = validate_identity(identity, report, runtime=runtime)
    else:
        # Status must remain available with an open read-only writer fence.
        modified = {**identity, 'role_defaults': []}
        validate_identity(modified, report)
        report['writer_fence']['role_defaults'] = identity['role_defaults']
    observed = runtime.query(STATUS_METADATA_SQL if mode == 'status' else transactions.PLAN_SQL)
    if mode == 'status':
        probes = status_counts(runtime, report, state, progress)
        for target in observed['targets']:
            target['payload_counts'] = {code: probe['targets'].get(target['id']) if probe['targets'] is not None else None
                                        for code, probe in probes.items()}
        observed['snapshot']['survivors'] = {code: probe['survivors'] for code, probe in probes.items()}
        report['relation_bytes_before'] = {code: probe['total_bytes'] for code, probe in probes.items()}
    _snapshot_fields(report, observed)
    if observed['snapshot']['derived'].get('derived_generation_id') != PUBLISHED_ID:
        raise ValueError('published_generation_identity_mismatch')
    # The UUID alone is insufficient: also authenticate the retained manifest.
    published = runtime.query(read_sql("SELECT jsonb_build_object('key',generation_key,'state',lifecycle_state,'manifest_sha256',encode(manifest_sha256,'hex')) FROM v3_meta.derived_generation WHERE derived_generation_id='cfc25d36-3bc7-4011-a465-d6460eaaf826'"))
    report['published_generation'] = published
    if published.get('key') != PUBLISHED_KEY or published.get('state') != 'PUBLISHED':
        raise ValueError('published_generation_identity_mismatch')
    if mode == 'status':
        ages = age_sample(runtime)
        report['autovacuum_ages'] = ages
        report['autovacuum'] = status_deadlines(ages, state, progress)
        report['next_admissible_mode'] = next_mode(state, progress, observed, report['autovacuum'],
                                                 verification=report['system_archetype_verification'])
        report['pointer_identities'] = runtime.query(POINTER_IDENTITIES_SQL)
        report['rows_affected_cumulative'] = progress.get('relation_progress')
        runtime.status_workers()
        try:
            journal = runtime.run(['journalctl', '--no-pager', '--output=json', '--since=-7days', '--lines=1000',
                                   '--unit=edfinder-v3-pgbackrest@full.service', '--unit=edfinder-v3-pgbackrest@diff.service',
                                   '--unit=edfinder-v3-pgbackrest@verify.service'])
            messages = [json.loads(line) for line in journal.splitlines() if line]
            report['skipped_scheduled_backups'] = {'window': 'last_7_days_up_to_1000_entries', 'records': [
                {'message': item['MESSAGE'], 'timestamp': item.get('__REALTIME_TIMESTAMP'),
                 'unit': item.get('_SYSTEMD_UNIT')}
                for item in messages if isinstance(item.get('MESSAGE'), str) and item['MESSAGE'].startswith('SKIP:')]}
        except (RuntimeError, ValueError):
            report['skipped_scheduled_backups'] = None
        report['result'] = 'unresolved_state_first' if state['unresolved'] else 'status_observed'
        report['status'] = 'success'
        return
    objects = runtime.query(OBJECTS_SQL)
    report['relation_bytes_before'] = objects
    if not isinstance(objects, list) or not objects or any(obj.get('valid') is not True for obj in objects):
        raise ValueError('relation_or_index_evidence_invalid')
    filesystem = runtime.storage(identity, objects)
    report['filesystem_before'] = filesystem
    if filesystem['free_bytes'] < FREE_FLOOR_BYTES:
        raise ValueError('filesystem_free_space_floor')
    expected_wrapper, installed_wrapper = check_wrapper()
    report.update(expected_wrapper_sha256=expected_wrapper, installed_wrapper_sha256=installed_wrapper)
    if runtime.workers() is not True:
        raise ValueError('named_workers_not_stopped')
    first_wal = runtime.query(WAL_SQL)
    first_wal['bytes'] = int(runtime.docker('exec', CONTAINER, 'du', '--bytes', '--summarize',
                                           '--dereference', '--', identity['data_directory'] + '/pg_wal').split()[0])
    report['wal_before'] = first_wal
    auto = measure_autovacuum(runtime)
    report['autovacuum'] = auto
    last_wal = runtime.query(WAL_SQL)
    # The directory is already proved to be on the measured filesystem. Avoid
    # pg_ls_waldir, a privilege deliberately not given to the executor by 016.
    wal_size = runtime.docker('exec', CONTAINER, 'du', '--bytes', '--summarize', '--dereference', '--', identity['data_directory'] + '/pg_wal')
    wal_bytes = int(wal_size.split()[0])
    last_wal['bytes'] = wal_bytes
    wal_health(first_wal, last_wal)
    report.update(wal_after=last_wal, archive_status=last_wal['archiver'], replication_slots=last_wal['slots'],
                  checkpoint_counters=last_wal['checkpoints'], temp_bytes=last_wal['temp_bytes'])
    def refresh_phase_gates():
        # Exact row-count scans can be long. Re-observe the host gates only
        # after those scans, immediately before a single transaction starts.
        nonlocal filesystem, wal_bytes
        fresh_objects = runtime.query(OBJECTS_SQL)
        if not fresh_objects or any(obj.get('valid') is not True for obj in fresh_objects):
            raise ValueError('relation_or_index_evidence_invalid')
        filesystem = runtime.storage(identity, fresh_objects)
        report['filesystem_after'] = filesystem
        report['relation_bytes_after'] = fresh_objects
        if filesystem['free_bytes'] < FREE_FLOOR_BYTES:
            raise ValueError('filesystem_free_space_floor')
        check_wrapper()
        if runtime.workers() is not True:
            raise ValueError('named_workers_not_stopped')
        fresh_wal = runtime.query(WAL_SQL)
        wal_bytes = int(runtime.docker('exec', CONTAINER, 'du', '--bytes', '--summarize', '--dereference',
                                      '--', identity['data_directory'] + '/pg_wal').split()[0])
        fresh_wal['bytes'] = wal_bytes
        wal_health(first_wal, fresh_wal)
        report.update(wal_after=fresh_wal, archive_status=fresh_wal['archiver'],
                      replication_slots=fresh_wal['slots'], checkpoint_counters=fresh_wal['checkpoints'],
                      temp_bytes=fresh_wal['temp_bytes'])
        require_reviewed_migration_ledger(runtime, entries)

    if mode != 'plan':
        if plan is None:
            raise ValueError('authenticated_plan_required')
        reviewed = plan['reviewed_plan']
        report['reviewed_plan_sha256'] = reviewed['plan_sha256']
        if published != plan.get('published_generation'):
            raise ValueError('published_generation_manifest_changed')
        if mode == 'authorize' and (plan.get('source_git_sha') != report['source_git_sha'] or
                                    plan.get('script_sha256') != report['script_sha256']):
            raise ValueError('plan_source_or_script_changed')
    extra_counts = runtime.query(EXTRA_COUNTS_SQL)
    report['extra_payload_counts'] = extra_counts
    pointer_identities = runtime.query(POINTER_IDENTITIES_SQL)
    report['pointer_identities'] = pointer_identities
    if mode == 'plan':
        transactions.verify_empty(runtime.query)
        reviewed = transactions.collect_plan(runtime.query, report['source_git_sha'], actor, reason)
        if reviewed['snapshot'] != observed['snapshot'] or reviewed['targets'] != observed['targets']:
            raise ValueError('plan_snapshot_changed_during_measurement')
        reviewed.update(autovacuum=auto['configuration'], extra_payload_counts=extra_counts,
                        delete={code: {'batch_limit': 1000} for code in RELATIONS.values()},
                        pointer_identities=pointer_identities)
        require_reviewed_migration_ledger(runtime, entries)
        report['reviewed_plan'] = transactions.seal_plan(runtime.query, reviewed)
        report['reviewed_plan_sha256'] = report['reviewed_plan']['plan_sha256']
        refresh_phase_gates()
        _snapshot_fields(report, reviewed)
        after_snapshot = reviewed['snapshot']
        report['result'] = 'sealed_plan_ready_for_review'
    else:
        if (pointer_identities != reviewed.get('pointer_identities') or
                extra_counts.get(PUBLISHED_ID) != reviewed.get('extra_payload_counts', {}).get(PUBLISHED_ID)):
            raise ValueError('plan_pointer_identity_or_survivor_count_drift')
        if mode == 'authorize':
            result = transactions.authorize(runtime.query, reviewed, before_write=refresh_phase_gates)
            for target in report['targets']:
                target['current_state'] = 'FAILED'
        else:
            ids = transactions.get_purge_ids(runtime.query, reviewed['plan_sha256'])
            report['purge_id'] = ids
            if mode == 'verify-system-archetype-empty':
                result = transactions.verify_empty(runtime.query, purge_ids=ids)
            else:
                report['system_archetype_verification'] = verification_gate(verification, [
                    {'purge_id': purge_id, 'plan_sha256': reviewed['plan_sha256']} for purge_id in ids])
                if report['system_archetype_verification']['status'] != 'proven':
                    raise ValueError('sealed_verification_required')
                completion = {}
                def fresh_completion():
                    refresh_phase_gates()
                    body = {'reviewed_plan_sha256': reviewed['plan_sha256'],
                            'filesystem_free_bytes': filesystem['free_bytes'], 'wal_bytes': wal_bytes,
                            'observed_at': datetime.now(timezone.utc).isoformat()}
                    completion.update(body, receipt_sha256=evidence.canonical_sha256(body))
                # Validate an initial complete receipt; the callback refreshes it
                # once the potentially long exact database scans have finished.
                body = {'reviewed_plan_sha256': reviewed['plan_sha256'],
                        'filesystem_free_bytes': filesystem['free_bytes'], 'wal_bytes': wal_bytes,
                        'observed_at': datetime.now(timezone.utc).isoformat()}
                completion.update(body, receipt_sha256=evidence.canonical_sha256(body))
                report['completion_receipt'] = completion
                result = transactions.complete(runtime.query, reviewed, completion, purge_ids=ids,
                                               before_write=fresh_completion)
                report['fk_check'] = True
        report['result'] = result
        report['competing_writer_wait'] = result.get('competing_writer_wait')
        if 'purge_ids' in result:
            report['purge_id'] = result['purge_ids']
        after_snapshot = result.get('snapshot')
    if after_snapshot is not None:
        report['pointers_after'] = {k: after_snapshot[k] for k in ('canonical', 'derived', 'spatial')}
        report['survivors_after'] = after_snapshot['survivors']
    finalize_wal_delta(runtime, report)
    report['status'] = 'success'


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError('invalid_arguments')

    report = receipt('unknown')
    try:
        parser = Parser(add_help=False)
        parser.add_argument('mode')
        parser.add_argument('--plan')
        parser.add_argument('--plan-sha256')
        parser.add_argument('--actor', default='governed-operator')
        parser.add_argument('--reason', default='Owner-authorized governed purge')
        parser.add_argument('--verification')
        parser.add_argument('--verification-sha256')
        parser.add_argument('--wall-clock-seconds', type=int, default=300)
        parser.add_argument('--controller-pid', type=int)
        parser.add_argument('--controller-run-id')
        parser.add_argument('--acknowledge-failed-stop', type=int)
        parser.add_argument('--writer-mode', default='read-only')
        args = parser.parse_args(argv)
        report = receipt(args.mode)
        mode = classify_mode(args.mode)
        if platform.python_implementation() != 'CPython' or sys.version_info[:2] != (3, 14):
            raise ValueError('python314_required')
        plan = None
        verification = None
        phase_mode = mode == 'restore-services' or mode.startswith(('delete-', 'abort-relation-'))
        phase_options = dict(wall_clock_seconds=args.wall_clock_seconds, controller_pid=args.controller_pid,
                             controller_run_id=args.controller_run_id, acknowledge_failed_stop=args.acknowledge_failed_stop,
                             writer_mode=args.writer_mode)
        if args.verification or args.verification_sha256:
            if (mode not in ('status', 'complete') and not phase_mode) or not args.verification or not args.verification_sha256:
                raise ValueError('verification_arguments_not_admitted_for_mode')
            verification = authenticated_verification(args.verification, args.verification_sha256)
        if (mode == 'complete' or phase_mode) and verification is None:
            raise ValueError('sealed_verification_required')
        if mode in ('authorize', 'verify-system-archetype-empty', 'complete') or phase_mode:
            if not args.plan or not args.plan_sha256:
                raise ValueError('authenticated_plan_required')
            plan = authenticated_plan(args.plan, args.plan_sha256, require_fresh=mode == 'authorize')
        elif args.plan or args.plan_sha256:
            raise ValueError('plan_arguments_not_admitted_for_mode')
        runtime = Runtime(report)
        runtime.guard()
        if phase_mode:
            runtime.state(allow_unresolved=True)
            with runtime.lease():
                with runtime.backup_lock():
                    execute(mode, runtime, report, plan, actor=args.actor, reason=args.reason,
                            verification=verification, phase_options=phase_options)
        elif mode in ('authorize', 'complete', 'verify-system-archetype-empty'):
            # Check first, then take the lease and recheck under it. The second
            # check knows it owns the lease, so cannot mistake itself for a rival.
            runtime.state()
            with runtime.lease():
                if mode in ('authorize', 'complete'):
                    with runtime.backup_lock():
                        execute(mode, runtime, report, plan, actor=args.actor, reason=args.reason, verification=verification)
                else:
                    execute(mode, runtime, report, plan, actor=args.actor, reason=args.reason, verification=verification)
        else:
            execute(mode, runtime, report, actor=args.actor, reason=args.reason, verification=verification)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        # Only our own finite error codes escape. Commands, SQL diagnostics,
        # environment and arbitrary parser/request text never become receipts.
        code = str(exc)
        if re.fullmatch('[a-zA-Z0-9_]+(,[a-zA-Z0-9_]+)*', code) is None:
            code = 'purge_preflight_or_query_failed'
        report['failures'].append(code)
        extra = getattr(exc, 'evidence', None)
        if extra:
            if 'competing_writer_wait' in extra:
                report['competing_writer_wait'] = extra['competing_writer_wait']
            report['failure_evidence'] = extra
            if 'maximum_seconds' in extra:
                report['competing_writer_wait'] = extra
    print(evidence.canonical_json(evidence.seal(report)))
    return 0 if report['status'] == 'success' else 1


if __name__ == '__main__':
    raise SystemExit(main())
