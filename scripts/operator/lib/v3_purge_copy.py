"""Fixed SQL and pure helpers for the copy-and-drop purge route (migration 019).

The owner-accepted design is docs/development/v3-purge-copy-and-drop-design.md.
Every 019 call runs inside a transaction that first sets ``SET LOCAL
statement_timeout`` and ``SET LOCAL lock_timeout`` from the closed, reviewed
PHASES table: a function-level ``SET statement_timeout`` never bounds the
function's own call (measured on PostgreSQL 18.4; tests prove it), so the bound
must come from the caller. 019 pins ``lock_timeout='2s'`` on swap, swap-back,
drop and abandon and that function-level value wins over the caller's
``SET LOCAL`` (also measured); the caller's statement timeout still caps every
attempt, so one swap attempt can stall Finder reads for at most that long.

No caller text enters SQL. Relation names come from a closed mapping; numbers
come from this module's tables; identifiers in the planner-statistics step are
fixed literals. Only the outer controller owns host authority and the lease.
"""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import re
import urllib.error
import urllib.request
from uuid import UUID

_spec = importlib.util.spec_from_file_location('v3_purge_transactions', Path(__file__).with_name('v3_purge_transactions.py'))
tx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tx)

RELATIONS = tx.RELATIONS
ORDER = RELATIONS  # children before parents: Search, opportunity, body, vector
PUBLISHED_ID = tx.PUBLISHED_ID
FLOOR_BYTES = 100_000_000_000
CHUNK_ROWS = 100_000                      # 019's own upper bound
DEFAULT_CHUNK_RESERVATION_BYTES = 900_000_000  # before any chunk growth is measured
MAX_LONG_PHASE_MS = 7_200_000             # the workflow's reviewed 120-minute statement envelope
MAX_WALL_CLOCK_SECONDS = 9_000            # chunk-loop budget; the 180-minute job keeps >=30 min for cleanup
LONG_PHASE_MARGIN_SECONDS = 300
TEMP_FILE_LIMIT_KB = 32 * 1024 * 1024      # 32 GB per long-phase session (SUSET: needs GRANT SET ON PARAMETER)
WAL_SOFT_FRACTION = 0.9                   # throttle while WAL since the last checkpoint REDO >= 0.9 x max_wal_size
WAL_CEILING_MULTIPLIER = 2                # watchdog cancels a long phase when pg_wal on disk reaches 2 x max_wal_size
ARCHIVE_LAG_CHUNK_SEGMENTS = 256          # 4 GB of 16 MB segments while chunks run
ARCHIVE_LAG_PHASE_SEGMENTS = 16           # 256 MB before a long phase starts
ARCHIVE_WAIT_SECONDS = 1_800
THROTTLE_POLL_SECONDS = 5
FREEZE_AGE_FRACTION = 0.8                 # live age(relfrozenxid) must stay under 80% of its limit
MAX_STAGING_FROZEN_AGE = 1_000_000        # after VACUUM (FREEZE): absolute bound on age(relfrozenxid)
FREEZE_SLACK_XIDS = 10_000                # plus the XIDs consumed while the VACUUM itself ran
SWAP_MAX_ATTEMPTS = 12
SWAP_BACKOFF_SECONDS = (2, 4, 8, 15, 30, 30, 60, 60, 60, 60, 60, 60)
SWAP_LOCK_TIMEOUT_MS = 400                 # F4: effective only once 019 stops pinning 2s (see module doc)
VACUUM_COST_DELAY_MS = 10
VACUUM_COST_LIMIT = 1000                  # ~125 GB/h of frozen pages, under the ~245 GB/h archive rate
API_ORIGIN = 'http://127.0.0.1:58080'     # the active production origin the deployer smokes
MAX_SMOKE = 1_048_576
RETRYABLE_SQLSTATES = frozenset(('55P03', '57014'))          # lock timeout, statement timeout / cancel
INTEGRITY_SQLSTATES = frozenset(('P0001', '23514', '23502', '23503', '23505'))
RESOURCE_SQLSTATES = frozenset(('53100', '53200', '53400'))   # disk full, out of memory, config limit
PHASES = {
    # name: (statement_timeout_ms, lock_timeout_ms, temp_file_limit_kb or None, long)
    'prepare': (60_000, 5_000, None, False),
    'chunk': (300_000, 5_000, None, False),
    'index_build': (MAX_LONG_PHASE_MS, 5_000, TEMP_FILE_LIMIT_KB, True),
    'vacuum_freeze': (MAX_LONG_PHASE_MS, 5_000, None, True),
    'verify': (MAX_LONG_PHASE_MS, 5_000, TEMP_FILE_LIMIT_KB, True),
    'validate_fks': (MAX_LONG_PHASE_MS, 5_000, TEMP_FILE_LIMIT_KB, True),
    'swap': (8_000, SWAP_LOCK_TIMEOUT_MS, None, False),
    'swap_back': (8_000, SWAP_LOCK_TIMEOUT_MS, None, False),
    'drop': (8_000, SWAP_LOCK_TIMEOUT_MS, None, False),
    'abandon': (8_000, SWAP_LOCK_TIMEOUT_MS, None, False),
    'record_failure': (60_000, 5_000, None, False),
    'complete': (300_000, 5_000, None, False),
    'recalibrate_count': (MAX_LONG_PHASE_MS, 5_000, TEMP_FILE_LIMIT_KB, True),
    'recalibrate_alter': (60_000, 5_000, None, False),
    'recalibrate_analyze': (MAX_LONG_PHASE_MS, 5_000, None, True),
    'read': (45 * 60_000, 5_000, None, False),
    'preflight_scan': (MAX_LONG_PHASE_MS, 5_000, None, True),  # owner session; a count scan sorts nothing
}
MODE_PREFIXES = ('preflight-', 'copy-', 'swap-back-', 'swap-', 'drop-', 'abandon-')
DISABLED_PREFIXES = ('delete-', 'rewrite-')
DISABLED_REASON = 'delete_rewrite_modes_disabled_by_copy_and_drop_design'
_LIVE = """CASE %(relation)s
 WHEN 'system_search' THEN 'v3_derived.system_search'::regclass
 WHEN 'economy_opportunity' THEN 'v3_derived.economy_opportunity'::regclass
 WHEN 'body_mechanics' THEN 'v3_derived.body_mechanics'::regclass
 WHEN 'system_rating_vector' THEN 'v3_derived.system_rating_vector'::regclass END"""
_STAGING = """CASE %(relation)s
 WHEN 'system_search' THEN to_regclass('v3_purge_staging.system_search')
 WHEN 'economy_opportunity' THEN to_regclass('v3_purge_staging.economy_opportunity')
 WHEN 'body_mechanics' THEN to_regclass('v3_purge_staging.body_mechanics')
 WHEN 'system_rating_vector' THEN to_regclass('v3_purge_staging.system_rating_vector') END"""
STAGING_TABLES = {
    'system_search': 'v3_purge_staging.system_search',
    'economy_opportunity': 'v3_purge_staging.economy_opportunity',
    'body_mechanics': 'v3_purge_staging.body_mechanics',
    'system_rating_vector': 'v3_purge_staging.system_rating_vector',
}


COPY_FIGURE_FIELDS = ('copy_peak_bytes', 'required_free_bytes_before_copy', 'copy_rows_per_second',
                      'long_phase_seconds_max', 'long_phase_fits_reviewed_timeout')
BOOTSTRAP_SOURCE = 'disposable_bootstrap_unmeasured'


def plan_block(figures: dict | None, source: str) -> dict:
    """The copy route's reviewed figures for a plan (sealed with it).

    ``figures`` is the reviewed copy-route rehearsal receipt's per-relation
    ``production`` block (schema v3): the free space required before each
    relation's copy is the 100 GB floor plus 1.5 x the measured, extrapolated
    copy peak (design section 1.6). Only the disposable rehearsal may seal a
    figure-less bootstrap block, marked ``disposable_bootstrap_unmeasured``.
    """
    if not isinstance(source, str) or not (source == BOOTSTRAP_SOURCE
                                           or re.fullmatch('reviewed_rehearsal:[0-9a-f]{64}', source)):
        raise tx.PurgeTransactionError('copy_plan_source_invalid')
    relations = {}
    for code in RELATIONS:
        if figures is None:
            if source != BOOTSTRAP_SOURCE:
                raise tx.PurgeTransactionError('copy_plan_figures_missing')
            measured = {'copy_peak_bytes': 0, 'required_free_bytes_before_copy': FLOOR_BYTES}
        else:
            measured = figures.get(code) if isinstance(figures, dict) else None
            if (not isinstance(measured, dict) or any(key not in measured for key in COPY_FIGURE_FIELDS)
                    or type(measured['copy_peak_bytes']) is not int or not 0 <= measured['copy_peak_bytes'] < 2**63
                    or measured['required_free_bytes_before_copy'] != FLOOR_BYTES + (3 * measured['copy_peak_bytes'] + 1) // 2):
                raise tx.PurgeTransactionError('copy_plan_peak_not_measured')
        relations[code] = {'chunk_rows': CHUNK_ROWS, 'copy_peak_bytes': measured['copy_peak_bytes'],
                           'copy_peak_source': source,
                           'required_free_bytes_before_copy': measured['required_free_bytes_before_copy']}
        if figures is not None:
            relations[code]['rehearsal'] = {key: measured[key] for key in COPY_FIGURE_FIELDS}
    return {'relations': relations, 'phase_timeouts': {name: phase_settings(name) for name in sorted(PHASES)},
            'floor_bytes': FLOOR_BYTES, 'chunk_reservation_fallback_bytes': DEFAULT_CHUNK_RESERVATION_BYTES,
            'wal_soft_fraction': WAL_SOFT_FRACTION, 'wal_ceiling_multiplier': WAL_CEILING_MULTIPLIER,
            'swap_max_attempts': SWAP_MAX_ATTEMPTS, 'swap_backoff_seconds': list(SWAP_BACKOFF_SECONDS),
            'source': source}


def required_before_copy(reviewed: dict, relation: str) -> int:
    block = reviewed.get('copy') if isinstance(reviewed, dict) else None
    value = ((block or {}).get('relations') or {}).get(relation, {}).get('required_free_bytes_before_copy')
    if type(value) is not int or value < FLOOR_BYTES:
        raise tx.PurgeTransactionError('copy_plan_figures_missing')
    return value


def phase_settings(phase: str) -> dict:
    if phase not in PHASES:
        raise tx.PurgeTransactionError('purge_copy_phase_invalid')
    statement, lock, temp, long = PHASES[phase]
    return {'phase': phase, 'statement_timeout_ms': statement, 'lock_timeout_ms': lock,
            'temp_file_limit_kb': temp, 'long': long}


def _locals(phase: str) -> str:
    settings = phase_settings(phase)
    text = ("SET LOCAL statement_timeout='" + str(settings['statement_timeout_ms']) + "ms';\n"
            "SET LOCAL lock_timeout='" + str(settings['lock_timeout_ms']) + "ms';\n")
    if settings['temp_file_limit_kb'] is not None:
        text += "SET LOCAL temp_file_limit='" + str(settings['temp_file_limit_kb']) + "kB';\n"
    return text


def phase_sql(phase: str, body: str, *, write: bool = True) -> str:
    """Executor session, one transaction, the phase's SET LOCAL bounds, one JSON row."""
    return tx._PREFIX + ('BEGIN;\n' if write else 'BEGIN READ ONLY;\n') + _locals(phase) + body + '\nCOMMIT;'


def owner_sql(phase: str, body: str) -> str:
    """Owner read-only transaction (no SET ROLE), for catalog/stat observations
    that 019 did not grant to the executor; mirrors the P2a owner-read exception."""
    return 'BEGIN READ ONLY;\n' + _locals(phase) + body + '\nCOMMIT;'


PREPARE_SQL = phase_sql('prepare', "SELECT jsonb_build_object('event',v3_meta.purge_copy_prepare(%(purge_id)s::uuid,%(relation)s));")
CHUNK_SQL = phase_sql('chunk', """SELECT jsonb_build_object('rows',v3_meta.purge_copy_chunk(%(purge_id)s::uuid,%(relation)s,%(max_rows)s::integer),
 'wal_lsn',pg_current_wal_lsn()::text,'staging_bytes',pg_total_relation_size(""" + _STAGING + '));')
BUILD_INDEXES_SQL = phase_sql('index_build', "SELECT jsonb_build_object('event',v3_meta.purge_copy_build_indexes(%(purge_id)s::uuid,%(relation)s));")
VERIFY_SQL = phase_sql('verify', "SELECT jsonb_build_object('event',v3_meta.purge_copy_verify(%(purge_id)s::uuid,%(relation)s));")
SWAP_SQL = phase_sql('swap', "SELECT jsonb_build_object('event',v3_meta.purge_copy_swap(%(purge_id)s::uuid,%(relation)s));")
SWAP_BACK_SQL = phase_sql('swap_back', "SELECT jsonb_build_object('event',v3_meta.purge_copy_swap_back(%(purge_id)s::uuid,%(relation)s));")
VALIDATE_FKS_SQL = phase_sql('validate_fks', "SELECT jsonb_build_object('event',v3_meta.purge_copy_validate_fks(%(purge_id)s::uuid,%(relation)s));")
DROP_SQL = phase_sql('drop', "SELECT jsonb_build_object('event',v3_meta.purge_copy_drop(%(purge_id)s::uuid,%(relation)s));")
ABANDON_SQL = phase_sql('abandon', "SELECT jsonb_build_object('event',v3_meta.purge_copy_abandon(%(purge_id)s::uuid,%(relation)s,%(evidence)s::jsonb));")
RECORD_FAILURE_SQL = phase_sql('record_failure', "SELECT jsonb_build_object('event',v3_meta.purge_copy_record_failure(%(purge_id)s::uuid,%(relation)s,%(evidence)s::jsonb));")
COMPLETE_SQL = phase_sql('complete', "SELECT jsonb_build_object('event',v3_meta.purge_copy_complete(%(purge_id)s::uuid));")
STATUS_SQL = phase_sql('read', 'SELECT v3_meta.purge_copy_status();', write=False)
BACKUP_SKIP_SQL = phase_sql('read', "SELECT jsonb_build_object('backup_skip',v3_meta.purge_copy_backup_skip());", write=False)
# The copy request's frozen counts and every relation's latest event time.
REQUEST_SQL = phase_sql('read', """SELECT COALESCE((SELECT jsonb_build_object('copy_id',q.copy_id,'purge_id',q.purge_id,
 'frozen_survivors',q.frozen_survivors,'published_search_survivors',q.published_search_survivors,
 'survivor_generation_id',q.survivor_generation_id,'created_at',q.created_at,
 'latest_events',(SELECT COALESCE(jsonb_object_agg(relation_code,jsonb_build_object('event_kind',event_kind,
   'event_sequence',event_sequence,'created_at',created_at)),'{}'::jsonb) FROM (
   SELECT DISTINCT ON (relation_code) relation_code,event_kind,event_sequence,created_at
   FROM v3_meta.derived_purge_copy_event WHERE copy_id=q.copy_id AND relation_code IS NOT NULL
   ORDER BY relation_code,event_sequence DESC) e),
 'completed_at',(SELECT created_at FROM v3_meta.derived_purge_copy_event WHERE copy_id=q.copy_id AND event_kind='COMPLETED'))
 FROM v3_meta.derived_purge_copy_request q WHERE q.plan_sha256=%(plan_sha256)s),'null'::jsonb);""", write=False)
# Staging maintenance and freeze evidence (F12), live/staging sizes for gate 2.
# live_index_bytes is the live indexes the index build will still create: 021's
# build_indexes skips (after checking) every live index whose name already
# exists on the staging table -- the GiST index prepare created empty and the
# chunk inserts filled -- so its bytes are already on disk, inside the copy.
# Before prepare (no staging table) it equals pg_indexes_size(live).
STAGING_SQL = phase_sql('read', """SELECT jsonb_build_object(
 'staging_present',""" + _STAGING + """ IS NOT NULL,
 'staging_bytes',pg_total_relation_size(""" + _STAGING + """),
 'staging_heap_bytes',pg_relation_size(""" + _STAGING + """),
 'last_vacuum',(SELECT last_vacuum FROM pg_stat_user_tables WHERE relid=""" + _STAGING + """),
 'last_analyze',(SELECT last_analyze FROM pg_stat_user_tables WHERE relid=""" + _STAGING + """),
 'staging_xid_age',(SELECT age(relfrozenxid) FROM pg_class WHERE oid=""" + _STAGING + """),
 'staging_mxid_age',(SELECT mxid_age(relminmxid) FROM pg_class WHERE oid=""" + _STAGING + """),
 'xid_next',pg_snapshot_xmax(pg_current_snapshot())::text::bigint,
 'live_reltuples',(SELECT reltuples::bigint FROM pg_class WHERE oid=""" + _LIVE + """),
 'live_heap_bytes',pg_relation_size(""" + _LIVE + """),
 'live_index_bytes',(SELECT COALESCE(sum(pg_total_relation_size(x.indexrelid)),0)::bigint FROM pg_index x
   JOIN pg_class i ON i.oid=x.indexrelid WHERE x.indrelid=""" + _LIVE + """
   AND NOT EXISTS (SELECT 1 FROM pg_index y JOIN pg_class s ON s.oid=y.indexrelid
     WHERE y.indrelid=""" + _STAGING + """ AND s.relname=i.relname)),
 'live_total_bytes',pg_total_relation_size(""" + _LIVE + """),
 'max_wal_size_bytes',pg_size_bytes(current_setting('max_wal_size')),
 'wal_segment_bytes',pg_size_bytes(current_setting('wal_segment_size')),
 'wal_lsn',pg_current_wal_lsn()::text);""", write=False)
WAL_LAG_SQL = phase_sql('read', """SELECT jsonb_build_object(
 'current_segment',(pg_split_walfile_name(pg_walfile_name(pg_current_wal_lsn()))).segment_number,
 'archived_segment',(SELECT (pg_split_walfile_name(last_archived_wal)).segment_number FROM pg_stat_archiver
   WHERE last_archived_wal IS NOT NULL),
 'archive_mode',current_setting('archive_mode'),'wal_lsn',pg_current_wal_lsn()::text);""", write=False)
# temp_file_limit is a superuser-set parameter: the executor can SET LOCAL it
# only after GRANT SET ON PARAMETER temp_file_limit TO v3_derived_purge_executor.
# Long phases refuse without that privilege rather than run unbounded.
TEMP_FILE_LIMIT_PRIVILEGE_SQL = phase_sql('read', """SELECT jsonb_build_object('executor',current_user,
 'can_set_temp_file_limit',has_parameter_privilege(current_user,'temp_file_limit','SET'),
 'temp_file_limit',current_setting('temp_file_limit'));""", write=False)
WAL_DELTA_SQL = phase_sql('read', "SELECT jsonb_build_object('bytes',pg_wal_lsn_diff(%(after_lsn)s::pg_lsn,%(before_lsn)s::pg_lsn)::bigint);", write=False)
# 019 serializes every copy operation with pg_try_advisory_xact_lock(764019001)
# and raises P0001 'competing purge copy operation' while another transaction
# holds it. VERBOSITY=sqlstate reduces that to P0001, which reads as an
# integrity failure, so each mutating dispatch first refuses while another
# backend holds the lock or runs a mutating copy function: an orphaned phase
# backend of an interrupted dispatch keeps running until its statement ends.
COMPETING_COPY_SQL = owner_sql('read', """SELECT jsonb_build_object(
 'lock_holders',(SELECT count(*) FROM pg_locks l WHERE l.locktype='advisory' AND l.granted
   AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
   AND l.classid=0 AND l.objid=764019001 AND l.objsubid=1 AND l.pid<>pg_backend_pid()),
 'copy_statements',(SELECT count(*) FROM pg_stat_activity a WHERE a.datname=current_database()
   AND a.pid<>pg_backend_pid() AND a.state IS DISTINCT FROM 'idle' AND octet_length(a.query)<=65536
   AND a.query ~ 'v3_meta[.]purge_copy_(prepare|chunk|build_indexes|verify|swap|swap_back|validate_fks|drop|abandon|record_failure|complete)[(]'));""")
# Owner session: the backend identity the watchdog pins. SET ROLE would mask
# the session's own backend_start (the executor lacks the stats privilege).
BACKEND_IDENTITY_SQL = """SELECT jsonb_build_object('backend_pid',pg_backend_pid(),
 'backend_start',(SELECT backend_start FROM pg_stat_activity WHERE pid=pg_backend_pid()));"""
BACKEND_ALIVE_SQL = """BEGIN READ ONLY;
SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='5s';
SELECT jsonb_build_object('alive',EXISTS(SELECT 1 FROM pg_stat_activity
 WHERE pid=%(backend_pid)s::integer AND backend_start=%(backend_start)s::timestamptz
 AND datname=current_database())); COMMIT;"""
# Watchdog cancellation (owner session; the phase backend's logged-in role is
# the owner, which PostgreSQL permits to signal its own role's backends). 019
# provides no cancel definer, so the authentication lives here: exact PID and
# backend_start, this database, an active client backend of the owner role, and
# a query that is one of the fixed long-phase statements.
CANCEL_SQL = """BEGIN;
SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='5s';
SELECT jsonb_build_object('cancelled',COALESCE((SELECT pg_cancel_backend(a.pid) FROM pg_stat_activity a
 WHERE a.pid=%(backend_pid)s::integer AND a.backend_start=%(backend_start)s::timestamptz
 AND a.pid<>pg_backend_pid() AND a.datname=current_database() AND a.usename=current_user
 AND a.backend_type='client backend' AND a.state='active' AND octet_length(a.query)<=4096
 AND (a.query ~ 'v3_meta[.]purge_copy_(build_indexes|verify|validate_fks)[(]'
      OR lower(a.query) ~ '^\\s*vacuum [(]freeze, analyze[)] v3_purge_staging[.]'
      OR lower(a.query) ~ '^\\s*analyze v3_derived[.]economy_opportunity [(]system_id64[)]'
      OR a.query ~ 'count[(]DISTINCT system_id64[)]' OR a.query ~ 'query_to_xml[(]')),false));
COMMIT;"""
PROGRESS_SQL = """BEGIN READ ONLY;
SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='5s';
SELECT jsonb_build_object(
 'create_index',(SELECT to_jsonb(p) FROM (SELECT phase,blocks_total,blocks_done,tuples_total,tuples_done,
   lockers_total,lockers_done,partitions_total,partitions_done FROM pg_stat_progress_create_index
   WHERE pid=%(backend_pid)s::integer LIMIT 1) p),
 'vacuum',(SELECT to_jsonb(p) FROM (SELECT phase,heap_blks_total,heap_blks_scanned,heap_blks_vacuumed,
   index_vacuum_count,dead_tuple_bytes,num_dead_item_ids FROM pg_stat_progress_vacuum
   WHERE pid=%(backend_pid)s::integer LIMIT 1) p),
 'activity',(SELECT to_jsonb(a) FROM (SELECT state,wait_event_type,wait_event,
   extract(epoch FROM clock_timestamp()-query_start)::bigint AS query_seconds FROM pg_stat_activity
   WHERE pid=%(backend_pid)s::integer AND backend_start=%(backend_start)s::timestamptz) a));
COMMIT;"""
# Read-only preflight (F6/F9/F10): owner session because 019 revoked the
# dependents/expected helpers from the executor. Catalog only; no payload scan.
PREFLIGHT_SQL = owner_sql('read', """WITH live AS (SELECT """ + _LIVE + """ AS oid)
SELECT jsonb_build_object(
 'relation',%(relation)s,
 'dependents',v3_meta.purge_copy_external_dependents(l.oid),
 'expected_dependents',(SELECT COALESCE(array_agg(x ORDER BY x),'{}') FROM (
   SELECT 'fk:'||c AS x FROM unnest(v3_meta.purge_copy_expected_children(%(relation)s)) c
   UNION SELECT 'view:'||w FROM unnest(v3_meta.purge_copy_expected_views(%(relation)s)) w) e),
 'disabled_triggers',(SELECT COALESCE(jsonb_agg(tgname ORDER BY tgname),'[]'::jsonb) FROM pg_trigger
   WHERE tgrelid=l.oid AND NOT tgisinternal AND tgenabled<>'O'),
 'commented_triggers',(SELECT COALESCE(jsonb_agg(tgname ORDER BY tgname),'[]'::jsonb) FROM pg_trigger
   WHERE tgrelid=l.oid AND NOT tgisinternal AND obj_description(oid,'pg_trigger') IS NOT NULL),
 'dependent_views_with_options',(SELECT COALESCE(jsonb_agg(DISTINCT rw.ev_class::regclass::text),'[]'::jsonb)
   FROM pg_depend d JOIN pg_rewrite rw ON rw.oid=d.objid JOIN pg_class c ON c.oid=rw.ev_class
   WHERE d.classid='pg_rewrite'::regclass AND d.refclassid='pg_class'::regclass AND d.refobjid=l.oid
     AND rw.ev_class<>l.oid AND c.reloptions IS NOT NULL),
 'clustered_indexes',(SELECT COALESCE(jsonb_agg(indexrelid::regclass::text ORDER BY indexrelid::regclass::text),'[]'::jsonb)
   FROM pg_index WHERE indrelid=l.oid AND indisclustered),
 'invalid_indexes',(SELECT count(*) FROM pg_index WHERE indrelid=l.oid AND (NOT indisvalid OR NOT indisready)),
 'live_shape_ok',NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid=l.oid AND attnum>0 AND attacl IS NOT NULL)
   AND EXISTS (SELECT 1 FROM pg_class WHERE oid=l.oid AND relkind='r' AND NOT relispartition
               AND relowner=current_user::regrole AND reltablespace=0),
 'not_valid_checks',(SELECT COALESCE(jsonb_agg(conname ORDER BY conname),'[]'::jsonb) FROM pg_constraint
   WHERE conrelid=l.oid AND contype='c' AND NOT convalidated),
 'staging_exists',""" + _STAGING + """ IS NOT NULL,
 'ages',(WITH heaps AS (SELECT oid,relname,reltoastrelid,reloptions FROM pg_class WHERE oid IN
     ('v3_derived.system_search'::regclass,'v3_derived.economy_opportunity'::regclass,
      'v3_derived.body_mechanics'::regclass,'v3_derived.system_rating_vector'::regclass)),
   objects AS (SELECT relname AS relation_code,'heap' AS scope,oid,reloptions FROM heaps UNION ALL
     SELECT relname,'toast',reltoastrelid,reloptions FROM heaps WHERE reltoastrelid<>0)
   SELECT jsonb_agg(jsonb_build_object('relation_code',o.relation_code,'scope',o.scope,
     'xid_age',age(c.relfrozenxid)::bigint,'mxid_age',mxid_age(c.relminmxid)::bigint,
     'xid_limit',least(current_setting('autovacuum_freeze_max_age')::bigint,COALESCE(
       (SELECT option_value::bigint FROM pg_options_to_table(o.reloptions) WHERE option_name='autovacuum_freeze_max_age'),
       9223372036854775807)),
     'mxid_limit',least(current_setting('autovacuum_multixact_freeze_max_age')::bigint,COALESCE(
       (SELECT option_value::bigint FROM pg_options_to_table(o.reloptions) WHERE option_name='autovacuum_multixact_freeze_max_age'),
       9223372036854775807))) ORDER BY o.relation_code,o.scope)
   FROM objects o JOIN pg_class c ON c.oid=o.oid))
 FROM live l;""")
# Search only: one scan of the published survivors counting rows that violate
# each live NOT VALID check (the staging copy enforces them). The expressions
# come from the catalog, never from a caller; query_to_xml runs the generated
# statement inside this one fixed statement. {} when no NOT VALID check exists:
# HAVING keeps the aggregate from returning its one row over zero checks, which
# would generate a statement selecting every survivor (production validated all
# 18 checks on 2026-10-18; preflight run 41034514200 stopped on it).
SEARCH_VIOLATIONS_SQL = owner_sql('preflight_scan', """SELECT jsonb_build_object(
 'constraints',(SELECT count(*) FROM pg_constraint WHERE conrelid='v3_derived.system_search'::regclass
    AND contype='c' AND NOT convalidated),
 'violations',COALESCE((SELECT ((xpath('/row/j/text()',query_to_xml(format(
    'SELECT jsonb_build_object(%s)::text AS j FROM v3_derived.system_search WHERE derived_generation_id=%L',
    string_agg(format('%L,count(*) FILTER (WHERE NOT (%s))',conname,pg_get_expr(conbin,conrelid)),',' ORDER BY conname),
    'cfc25d36-3bc7-4011-a465-d6460eaaf826'),false,true,'')))[1]::text)::jsonb
  FROM pg_constraint WHERE conrelid='v3_derived.system_search'::regclass AND contype='c' AND NOT convalidated HAVING count(*)>0),'{}'::jsonb));""")
# F7: planner statistics for economy_opportunity.system_id64 after its swap.
RECALIBRATE_COUNT_SQL = phase_sql('recalibrate_count', """SELECT jsonb_build_object('rows',count(*),
 'distinct_systems',count(DISTINCT system_id64)) FROM v3_derived.economy_opportunity;""", write=False)
RECALIBRATE_STATS_SQL = phase_sql('read', """SELECT jsonb_build_object(
 'attoptions',(SELECT to_jsonb(attoptions) FROM pg_attribute WHERE attrelid='v3_derived.economy_opportunity'::regclass AND attname='system_id64'),
 'attstattarget',(SELECT attstattarget FROM pg_attribute WHERE attrelid='v3_derived.economy_opportunity'::regclass AND attname='system_id64'),
 'pg_stats_n_distinct',(SELECT n_distinct FROM pg_stats WHERE schemaname='v3_derived' AND tablename='economy_opportunity' AND attname='system_id64'),
 'reltuples',(SELECT reltuples::bigint FROM pg_class WHERE oid='v3_derived.economy_opportunity'::regclass),
 'last_analyze',(SELECT last_analyze FROM pg_stat_user_tables WHERE relid='v3_derived.economy_opportunity'::regclass),
 'retired_attoptions',(SELECT to_jsonb(attoptions) FROM pg_attribute
   WHERE attrelid=to_regclass('v3_retired.economy_opportunity') AND attname='system_id64'),
 'staging_attoptions',(SELECT to_jsonb(attoptions) FROM pg_attribute
   WHERE attrelid=to_regclass('v3_purge_staging.economy_opportunity') AND attname='system_id64'));""", write=False)
# F4 (Codex 4379797637): 019's swap-back compares attribute options exactly with
# the retired table, and swap-R recalibrated n_distinct on the copy. One owner
# transaction restores the retired table's options on the copy (fixed
# identifiers; values only from the catalog, n_distinct options only) and then
# calls the executor's swap-back, so both commit or neither does. The caller's
# SET LOCAL bounds govern the DO block; 019's own 2 s lock_timeout governs the
# swap-back call.
SWAP_BACK_OPPORTUNITY_SQL = ('SET default_transaction_read_only=off;\nBEGIN;\n' + _locals('swap_back') + """DO $restore$
DECLARE wanted text[]; o record;
BEGIN
    SELECT attoptions INTO wanted FROM pg_attribute
     WHERE attrelid='v3_retired.economy_opportunity'::regclass AND attname='system_id64';
    EXECUTE 'ALTER TABLE v3_derived.economy_opportunity ALTER COLUMN system_id64 RESET (n_distinct, n_distinct_inherited)';
    FOR o IN SELECT option_name,option_value FROM pg_options_to_table(wanted) LOOP
        IF o.option_name NOT IN ('n_distinct','n_distinct_inherited') THEN
            RAISE EXCEPTION 'unsupported attribute option on the retired table';
        END IF;
        EXECUTE format('ALTER TABLE v3_derived.economy_opportunity ALTER COLUMN system_id64 SET (%I = %L)',
                       o.option_name,o.option_value);
    END LOOP;
END $restore$;
SET LOCAL ROLE v3_derived_purge_executor;
SELECT jsonb_build_object('event',v3_meta.purge_copy_swap_back(%(purge_id)s::uuid,'economy_opportunity'),
 'statistics_restored_from','v3_retired.economy_opportunity');
COMMIT;""")
RECALIBRATE_ANALYZE_SQL = (tx._PREFIX + "SET statement_timeout='" + str(PHASES['recalibrate_analyze'][0]) + "ms';\n"
                           "SET lock_timeout='5s';\nANALYZE v3_derived.economy_opportunity (system_id64);\n"
                           "SELECT jsonb_build_object('analyzed',true);")
# The archetype builder's chunk read (shared_contracts OPPORTUNITY_READ_SQL),
# planned for the published generation and chunk 1; it must stay a nested loop
# over economy_opportunity_pkey (docs/operations/v3-postgres-server-settings.md).
# EXPLAIN cannot be nested in an expression; its one JSON document is the
# statement's whole result (a list with one plan object).
CHUNK_READ_PLAN_SQL = phase_sql('read', """EXPLAIN (FORMAT JSON)
 SELECT o.system_id64, o.economy_ordinal, count(*)::int, sum(o.local_score)::bigint
   FROM v3_derived.economy_opportunity o JOIN v3_derived.system_rating_vector v
     ON v.derived_generation_id = o.derived_generation_id AND v.system_id64 = o.system_id64
  WHERE o.derived_generation_id = 'cfc25d36-3bc7-4011-a465-d6460eaaf826'
    AND ((1::bigint IS NOT NULL AND NULL::bigint IS NULL AND v.chunk_ordinal = 1)
         OR (NULL::bigint IS NOT NULL AND 1::bigint IS NULL AND o.system_id64 = NULL::bigint))
  GROUP BY o.system_id64, o.economy_ordinal ORDER BY o.system_id64, o.economy_ordinal;""", write=False)


def vacuum_sql(relation: str) -> str:
    """Outside any transaction block, throttled; the staging name is a closed literal."""
    table = STAGING_TABLES[tx._relation(relation)]
    settings = phase_settings('vacuum_freeze')
    return (tx._PREFIX + "SET statement_timeout='" + str(settings['statement_timeout_ms']) + "ms';\n"
            "SET lock_timeout='" + str(settings['lock_timeout_ms']) + "ms';\n"
            "SET vacuum_cost_delay='" + str(VACUUM_COST_DELAY_MS) + "ms';\n"
            'SET vacuum_cost_limit=' + str(VACUUM_COST_LIMIT) + ';\n'
            'VACUUM (FREEZE, ANALYZE) ' + table + ';\n'
            "SELECT jsonb_build_object('command_completed',true);")


def recalibrate_alter_sql(fraction: float) -> str:
    """Owner session DDL: ALTER TABLE ... SET (n_distinct = -fraction). The
    executor is not the table owner; the value is a validated negative fraction."""
    if type(fraction) is not float or not math.isfinite(fraction) or not 0 < fraction <= 1:
        raise tx.PurgeTransactionError('n_distinct_fraction_invalid')
    literal = format(-fraction, '.6f')
    if re.fullmatch(r'-0\.[0-9]{6}', literal) is None and literal != '-1.000000':
        raise tx.PurgeTransactionError('n_distinct_fraction_invalid')
    return ('BEGIN;\n' + _locals('recalibrate_alter')
            + 'ALTER TABLE v3_derived.economy_opportunity ALTER COLUMN system_id64 SET (n_distinct = ' + literal + ');\n'
            + "SELECT jsonb_build_object('n_distinct'," + literal + ');\nCOMMIT;')


def n_distinct_option(fraction: float) -> str:
    """The attoptions text PostgreSQL stores for recalibrate_alter_sql(fraction)."""
    if type(fraction) is not float or not math.isfinite(fraction) or not 0 < fraction <= 1:
        raise tx.PurgeTransactionError('n_distinct_fraction_invalid')
    return 'n_distinct=' + format(-fraction, '.6f')


def attoptions_list(value) -> list:
    """attoptions as returned by to_jsonb: null or a list of 'name=value' text."""
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise tx.PurgeTransactionError('attoptions_observation_invalid')
    return sorted(value)


def n_distinct_fraction(rows: int, distinct: int) -> float:
    if (type(rows) is not int or type(distinct) is not int or rows <= 0 or distinct <= 0
            or distinct > rows):
        raise tx.PurgeTransactionError('n_distinct_counts_invalid')
    return round(distinct / rows, 6) or 0.000001


def chunk_read_plan_ok(plan: object) -> bool:
    """True when some Nested Loop has an Index Scan on economy_opportunity_pkey below it."""
    def nodes(node, ancestors):
        yield node, ancestors
        for child in node.get('Plans') or []:
            yield from nodes(child, ancestors + [node])
    if not isinstance(plan, list) or not plan or not isinstance(plan[0], dict):
        return False
    root = plan[0].get('Plan')
    if not isinstance(root, dict):
        return False
    for node, ancestors in nodes(root, []):
        if (node.get('Index Name') == 'economy_opportunity_pkey'
                and node.get('Node Type') in ('Index Scan', 'Index Only Scan')
                and any(a.get('Node Type') == 'Nested Loop' for a in ancestors)):
            return True
    return False


def relation_for_mode(mode: str) -> tuple[str, str]:
    """('copy', 'system_search') for 'copy-system-search'; closed prefixes and names."""
    for prefix in MODE_PREFIXES:
        if mode.startswith(prefix):
            name = mode.removeprefix(prefix)
            code = name.replace('-', '_')
            if code in RELATIONS and name == code.replace('_', '-'):
                return prefix.rstrip('-').replace('-', '_'), code
    raise tx.PurgeTransactionError('purge_copy_mode_invalid')


def is_disabled(mode: str) -> bool:
    return mode.startswith(DISABLED_PREFIXES)


def relation_state(status: dict, plan_sha256: str, relation: str) -> dict | None:
    """The 019 ledger state of one relation for the reviewed plan, or None when
    no copy request exists yet (prepare creates it)."""
    requests = status.get('requests') if isinstance(status, dict) else None
    if not isinstance(requests, list):
        raise tx.PurgeTransactionError('purge_copy_status_invalid')
    matching = [q for q in requests if isinstance(q, dict) and q.get('plan_sha256') == plan_sha256]
    if len(matching) > 1:
        raise tx.PurgeTransactionError('purge_copy_status_invalid')
    if not matching:
        return None
    relations = matching[0].get('relations')
    state = relations.get(relation) if isinstance(relations, dict) else None
    if (not isinstance(state, dict) or state.get('copy_position') not in ('none', 'staged', 'swapped', 'dropped')
            or type(state.get('failed')) is not bool):
        raise tx.PurgeTransactionError('purge_copy_status_invalid')
    return {**state, 'completed': matching[0].get('completed') is True}


def next_step(state: dict | None, frozen: int | None, staging: dict | None) -> str:
    """Which copy-R step the ledger admits next. Pure; the dispatcher gates it."""
    if state is None or state['copy_position'] == 'none':
        return 'prepare'
    if state.get('completed'):
        return 'refuse:purge_copy_already_complete'
    if state['failed']:
        return 'refuse:copy_relation_failed_stop_requires_owner_review'
    if state['copy_position'] != 'staged':
        return 'refuse:copy_relation_already_swapped'
    phase = state.get('phase')
    if phase in ('COPY_STARTED', 'CHUNK_COPIED'):
        if type(frozen) is not int:
            return 'refuse:copy_frozen_survivors_unknown'
        return 'chunk' if (state.get('rows_total') or 0) < frozen else 'index_build'
    if phase == 'INDEXES_BUILT':
        if not isinstance(staging, dict) or type(staging.get('staging_present')) is not bool:
            return 'refuse:copy_staging_observation_invalid'
        vacuumed = (staging.get('last_vacuum') is not None and staging.get('last_analyze') is not None
                    and state.get('last_copy_at') is not None
                    and staging['last_vacuum'] > state['last_copy_at'] and staging['last_analyze'] > state['last_copy_at'])
        return 'verify' if vacuumed else 'vacuum_freeze'
    if phase == 'SWAPPED_BACK':
        # A swap-back whose FK validation was interrupted is finished by
        # swap-back-R, never by re-verifying past NOT VALID child FKs.
        if state.get('fk_validated') is None:
            return 'refuse:swap_back_fk_validation_pending'
        return 'verify'
    if phase == 'VERIFIED':
        return 'done'
    return 'refuse:copy_phase_unknown'


def classify_sqlstate(code: str | None) -> str:
    if code in RETRYABLE_SQLSTATES:
        return 'retryable'
    if code in INTEGRITY_SQLSTATES:
        return 'integrity'
    if code in RESOURCE_SQLSTATES:
        return 'resource'
    return 'unknown'


def chunk_gate_required(reservation_bytes: int) -> int:
    if type(reservation_bytes) is not int or reservation_bytes < 0:
        raise tx.PurgeTransactionError('copy_reservation_invalid')
    return FLOOR_BYTES + (3 * reservation_bytes + 1) // 2


def expected_index_bytes(live_index_bytes: int, live_reltuples: int, frozen: int) -> int:
    if any(type(v) is not int or v < 0 for v in (live_index_bytes, live_reltuples, frozen)):
        raise tx.PurgeTransactionError('copy_index_estimate_invalid')
    denominator = max(live_reltuples, frozen, 1)
    return math.ceil(live_index_bytes * frozen / denominator)


def long_phase_required(phase: str, *, index_bytes: int = 0, max_wal_size_bytes: int = 0) -> int:
    settings = phase_settings(phase)
    temp = (settings['temp_file_limit_kb'] or 0) * 1024
    growth = index_bytes if phase == 'index_build' else 0
    return FLOOR_BYTES + (3 * growth + 1) // 2 + temp + max_wal_size_bytes


def wal_throttle_needed(wal_bytes: int, max_wal_size_bytes: int) -> bool:
    if type(wal_bytes) is not int or type(max_wal_size_bytes) is not int or max_wal_size_bytes <= 0:
        raise tx.PurgeTransactionError('wal_measurement_invalid')
    return wal_bytes >= math.floor(max_wal_size_bytes * WAL_SOFT_FRACTION)


def archive_lag_segments(lag: dict) -> int:
    current, archived = lag.get('current_segment'), lag.get('archived_segment')
    if lag.get('archive_mode') not in ('on', 'always') or type(current) is not int or type(archived) is not int:
        raise tx.PurgeTransactionError('wal_archive_lag_unknown')
    return max(0, current - archived)


def staging_frozen(staging: dict, *, xid_before: int | None = None) -> dict:
    """F12: after VACUUM (FREEZE) the staging relfrozenxid must be recent.

    A plain VACUUM leaves relfrozenxid at the first chunk's inserting XID, so
    its age is every XID consumed since the copy started; FREEZE moves it to
    the VACUUM's own cutoff. With ``xid_before`` (the XID horizon read just
    before the VACUUM was issued) the age may exceed the XIDs consumed during
    the VACUUM by at most FREEZE_SLACK_XIDS; the absolute bound always applies.
    """
    age, mage, now = staging.get('staging_xid_age'), staging.get('staging_mxid_age'), staging.get('xid_next')
    evidence = {'staging_xid_age': age, 'staging_mxid_age': mage, 'xid_next': now, 'xid_before': xid_before,
                'maximum': MAX_STAGING_FROZEN_AGE, 'slack': FREEZE_SLACK_XIDS}
    if type(age) is not int or type(mage) is not int or age > MAX_STAGING_FROZEN_AGE or mage > MAX_STAGING_FROZEN_AGE:
        raise tx.PurgeTransactionError('staging_relfrozenxid_not_frozen', evidence)
    if xid_before is not None:
        if type(now) is not int or type(xid_before) is not int or now < xid_before:
            raise tx.PurgeTransactionError('staging_relfrozenxid_not_frozen', evidence)
        if age > (now - xid_before) + FREEZE_SLACK_XIDS:
            raise tx.PurgeTransactionError('staging_relfrozenxid_not_frozen', evidence)
    return evidence


def evaluate_preflight(observed: dict, *, violations: dict | None, relation: str) -> dict:
    """Pure evaluation of the read-only preflight; raises the first refusal."""
    if not isinstance(observed, dict) or observed.get('relation') != relation:
        raise tx.PurgeTransactionError('copy_preflight_observation_invalid')
    result = {'relation': relation, 'checks': {}}
    dependents, expected = observed.get('dependents'), observed.get('expected_dependents')
    if not isinstance(dependents, list) or not isinstance(expected, list):
        raise tx.PurgeTransactionError('copy_preflight_observation_invalid')
    result['checks']['dependents'] = {'observed': dependents, 'expected': expected}
    if sorted(dependents) != sorted(expected):
        raise tx.PurgeTransactionError('copy_preflight_dependents_unexpected', result)
    for key, code in (('disabled_triggers', 'copy_preflight_disabled_trigger'),
                      ('commented_triggers', 'copy_preflight_commented_trigger'),
                      ('dependent_views_with_options', 'copy_preflight_view_options'),
                      ('clustered_indexes', 'copy_preflight_clustered_index')):
        value = observed.get(key)
        if not isinstance(value, list):
            raise tx.PurgeTransactionError('copy_preflight_observation_invalid')
        result['checks'][key] = value
        if value:
            raise tx.PurgeTransactionError(code, result)
    if observed.get('invalid_indexes') != 0 or observed.get('live_shape_ok') is not True:
        raise tx.PurgeTransactionError('copy_preflight_live_shape_outside_contract', result)
    ages = observed.get('ages')
    if not isinstance(ages, list) or not ages:
        raise tx.PurgeTransactionError('copy_preflight_observation_invalid')
    heaps = {a.get('relation_code') for a in ages if a.get('scope') == 'heap'}
    if heaps != set(RELATIONS):
        raise tx.PurgeTransactionError('copy_preflight_observation_invalid')
    result['checks']['ages'] = ages
    for age in ages:
        for kind in ('xid', 'mxid'):
            value, limit = age.get(kind + '_age'), age.get(kind + '_limit')
            if type(value) is not int or type(limit) is not int or limit <= 0:
                raise tx.PurgeTransactionError('copy_preflight_observation_invalid')
            if value >= limit * FREEZE_AGE_FRACTION:
                raise tx.PurgeTransactionError('copy_preflight_freeze_age_unsafe', result)
    checks = observed.get('not_valid_checks')
    if not isinstance(checks, list):
        raise tx.PurgeTransactionError('copy_preflight_observation_invalid')
    result['checks']['not_valid_checks'] = checks
    if relation == 'system_search':
        if violations is None:
            result['checks']['survivor_violations'] = 'not_scanned'
        else:
            counts = violations.get('violations')
            if (not isinstance(counts, dict) or violations.get('constraints') != len(checks)
                    or set(counts) != set(checks) or any(type(n) is not int or n < 0 for n in counts.values())):
                raise tx.PurgeTransactionError('copy_preflight_observation_invalid')
            result['checks']['survivor_violations'] = counts
            if any(counts.values()):
                raise tx.PurgeTransactionError('copy_preflight_survivor_check_violations', result)
    elif checks:
        raise tx.PurgeTransactionError('copy_preflight_not_valid_check_outside_search', result)
    result['passed'] = True
    return result


def failure_evidence(condition: str, phase: str, sqlstate: str | None, extra: dict | None = None) -> dict:
    if re.fullmatch('[a-zA-Z0-9_]+', condition) is None:
        condition = 'copy_phase_failed'
    evidence = {'condition': condition, 'phase': phase, 'integrity_failed': True,
                'sqlstate': sqlstate if isinstance(sqlstate, str) and re.fullmatch('[0-9A-Z]{5}', sqlstate) else None}
    for key, value in (extra or {}).items():
        if key not in evidence and key != 'abandoned':
            evidence[key] = value
    return evidence


def abandon_evidence(reason: str, run_id: str | None, controller: dict | None) -> dict:
    if reason not in ('owner_abandon',):
        raise tx.PurgeTransactionError('purge_copy_abandon_reason_invalid')
    return {'condition': reason, 'integrity_failed': False, 'workflow_run_id': run_id,
            'controller': controller}


def finder_smoke(origin: str = API_ORIGIN, *, opener=None) -> dict:
    """Read-only: /api/health and one ranked call per Finder product. Bodies are
    never retained; only status, size and the health identity fields."""
    if origin != API_ORIGIN:
        raise tx.PurgeTransactionError('finder_smoke_origin_invalid')
    requests = (
        ('GET', '/api/health', None),
        ('GET', '/api/archetypes/rankings?archetype=paradise&offset=0&limit=1', None),
        ('POST', '/api/local/search', {'galaxy_wide': True, 'sort_by': 'development', 'from': 0, 'size': 1}),
    )
    outcomes = {}
    for method, path, body in requests:
        status, payload = _request(origin, method, path, body, opener)
        outcomes[path] = {'status': status, 'bytes': len(payload)}
        if status != 200 or len(payload) > MAX_SMOKE:
            raise tx.PurgeTransactionError('finder_smoke_failed', {'path': path, 'status': status})
        if path == '/api/health':
            try:
                health = json.loads(payload)
            except ValueError:
                raise tx.PurgeTransactionError('finder_smoke_failed', {'path': path}) from None
            if not isinstance(health, dict) or health.get('status') != 'ok' or health.get('database') != 'connected':
                raise tx.PurgeTransactionError('finder_smoke_failed', {'path': path})
            outcomes[path]['database'] = health.get('database')
    return {'origin': origin, 'passed': True, 'requests': outcomes}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(origin, method, path, body, opener):
    data = None if body is None else json.dumps(body).encode()
    headers = {'User-Agent': 'edfinder-v3-purge-copy-smoke/1'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(origin + path, data=data, method=method, headers=headers)
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    try:
        with opener.open(request, timeout=10) as response:
            return response.status, response.read(MAX_SMOKE + 1)
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, exc.read(MAX_SMOKE + 1)
    except (OSError, urllib.error.URLError, TimeoutError):
        raise tx.PurgeTransactionError('finder_smoke_origin_unreachable', {'path': path}) from None


def hours_since(timestamp: str | None, now) -> float | None:
    from datetime import datetime
    if not isinstance(timestamp, str):
        return None
    try:
        then = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    if then.tzinfo is None:
        return None
    return round((now - then).total_seconds() / 3600, 3)


def purge_id_param(purge_id: str) -> str:
    return str(UUID(purge_id))
