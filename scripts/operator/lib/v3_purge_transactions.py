"""Fixed SQL for the P2b1 purge phases; no connection or host authority here.

The query adapter accepts SQL, a mapping of bound values, and ``write=False``.
It returns the one JSON result only after COMMIT succeeds. All mutations go
through 016's public functions. The outer operator owns host gates and the lease.
"""
from __future__ import annotations

import json
import re
import time
from uuid import UUID


RELATIONS = ('system_search', 'economy_opportunity', 'body_mechanics', 'system_rating_vector')
TARGET_IDS = ('49a0c00d-e722-4209-afd8-9d62b877e30a', '403b2d43-820c-414a-ad57-0d4de0ca3e82')
TARGET_IDENTITIES = (
    (TARGET_IDS[0], 'ratings_v4_prod_p4', 'BUILDING'),
    (TARGET_IDS[1], 'ratings_v4_prod_p4_opt1', 'VALIDATING'),
)
PUBLISHED_ID = 'cfc25d36-3bc7-4011-a465-d6460eaaf826'
WRITER_WAIT_SECONDS = 30
WRITER_POLL_SECONDS = 1
_PREFIX = """SET ROLE v3_derived_purge_executor;
SET default_transaction_read_only=off;
"""
# Exact boundary scans include the published galaxy; use the same bounded
# maintenance allowance as the controller. 016's own function-level 60-second
# settings remain untouched and still constrain those definer invocations.
_BOUNDS = """SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='45min';
"""


def _session(sql: str, *, write: bool = False) -> str:
    return _PREFIX + ('BEGIN;\n' if write else 'BEGIN READ ONLY;\n') + _BOUNDS + sql + '\nCOMMIT;'


# Counts are intentionally fixed SQL, not caller-derived identifiers. Internal
# purge_counts is not executable by the executor; purge_snapshot is public.
_TARGET_COUNTS = """SELECT d.derived_generation_id::text AS id,d.generation_key AS key,
 encode(d.manifest_sha256,'hex') AS manifest_sha256,d.lifecycle_state AS state,
 jsonb_build_object(
  'system_search',(SELECT count(*) FROM v3_derived.system_search x WHERE x.derived_generation_id=d.derived_generation_id),
  'economy_opportunity',(SELECT count(*) FROM v3_derived.economy_opportunity x WHERE x.derived_generation_id=d.derived_generation_id),
  'body_mechanics',(SELECT count(*) FROM v3_derived.body_mechanics x WHERE x.derived_generation_id=d.derived_generation_id),
  'system_rating_vector',(SELECT count(*) FROM v3_derived.system_rating_vector x WHERE x.derived_generation_id=d.derived_generation_id)
 ) AS payload_counts
 FROM v3_meta.derived_generation d
 WHERE d.derived_generation_id IN
 ('49a0c00d-e722-4209-afd8-9d62b877e30a','403b2d43-820c-414a-ad57-0d4de0ca3e82')"""
PLAN_SQL = _session("""SELECT jsonb_build_object('snapshot',v3_meta.purge_snapshot(),
 'targets',(SELECT jsonb_agg(t ORDER BY id) FROM (""" + _TARGET_COUNTS + ') t));')
PLAN_HASH_SQL = _session("""SELECT jsonb_build_object('plan_sha256',
 encode(sha256(convert_to((%(plan)s::jsonb)::text,'UTF8')),'hex'));""")
# As with the shared P2a ledger admission query, this strictly read-only
# observation uses the pinned connection owner. The executor lacks stats-role
# membership: SET ROLE masks application state and backend_type. PostgreSQL 18
# exposes backend_xid to every caller, including background-worker XIDs; the
# owner also sees its application sessions' remaining fields. 016's
# actual mutation functions repeat this predicate as their SECURITY DEFINER owner.
COMPETING_WRITER_SQL = """BEGIN READ ONLY;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='1s';
SELECT jsonb_build_object('competing_writers',count(*),
 'background_writers',count(*) FILTER (WHERE backend_type<>'client backend'))
 FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()
 AND (backend_xid IS NOT NULL OR (backend_type='client backend' AND state IS NULL));
COMMIT;"""
_EXCLUSIONS = """WITH targets AS (
 SELECT unnest(ARRAY['49a0c00d-e722-4209-afd8-9d62b877e30a'::uuid,
                    '403b2d43-820c-414a-ad57-0d4de0ca3e82'::uuid]) AS id
)
SELECT jsonb_build_object(
 'cluster_run',(SELECT count(*) FROM v3_spatial.cluster_run WHERE derived_generation_id IN (SELECT id FROM targets)),
 'cluster',(SELECT count(*) FROM v3_spatial.cluster WHERE derived_generation_id IN (SELECT id FROM targets)),
 'cluster_member',(SELECT count(*) FROM v3_spatial.cluster_member WHERE derived_generation_id IN (SELECT id FROM targets)),
 'system_archetype',(SELECT count(*) FROM v3_derived.system_archetype WHERE derived_generation_id IN (SELECT id FROM targets)))"""
# The summary is a v3_app view; 016 deliberately grants this executor access
# only to v3_meta/v3_derived/v3_spatial. The direct target-row check above proves
# the underlying archetype payload is empty without broadening those grants.
EXCLUSIONS_SQL = _session(_EXCLUSIONS + ';')
AUTHORIZE_SQL = _session("""WITH authorized AS MATERIALIZED (
 SELECT v3_meta.begin_derived_generation_purge(%(plan)s::jsonb) AS ids
), checked AS MATERIALIZED (
 SELECT ids,v3_meta.purge_snapshot() AS snapshot FROM authorized
)
SELECT jsonb_build_object('purge_ids',to_jsonb(ids),'snapshot',snapshot,
 'verified',1 / CASE WHEN snapshot=%(snapshot)s::jsonb THEN 1 ELSE 0 END)
 FROM checked;""", write=True)
REQUESTS_SQL = _session("""SELECT jsonb_build_object('requests',COALESCE(jsonb_agg(
 jsonb_build_object('purge_id',purge_id,'plan_sha256',plan_sha256,
 'derived_generation_id',derived_generation_id,'frozen_snapshot',frozen_snapshot)
 ORDER BY derived_generation_id),'[]'::jsonb))
 FROM v3_meta.derived_generation_purge_request WHERE purge_id IN
 (SELECT value::uuid FROM jsonb_array_elements_text(%(purge_ids)s::jsonb));""")
PLAN_REQUEST_IDS_SQL = _session("""SELECT jsonb_build_object('purge_ids',COALESCE(
 jsonb_agg(purge_id::text ORDER BY derived_generation_id),'[]'::jsonb))
 FROM v3_meta.derived_generation_purge_request WHERE plan_sha256=%(plan_sha256)s;""")
FAILED_STOP_SQL = _session("""WITH recorded AS MATERIALIZED (
 SELECT v3_meta.purge_record_event(value::uuid,'FAILED_STOP',NULL,%(evidence)s::jsonb) AS event
 FROM jsonb_array_elements_text(%(purge_ids)s::jsonb)
)
SELECT jsonb_build_object('failed_stop_events',jsonb_agg(event)) FROM recorded;""", write=True)
COMPLETION_STATE_SQL = _session("""SELECT jsonb_build_object(
 'snapshot',v3_meta.purge_snapshot(),
 'targets',(SELECT jsonb_agg(t ORDER BY id) FROM (""" + _TARGET_COUNTS + """) t),
 'invalid_foreign_keys',(SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace
   WHERE n.nspname IN ('v3_meta','v3_derived','v3_spatial') AND c.contype='f' AND NOT c.convalidated),
 'invalid_indexes',(SELECT count(*) FROM pg_index WHERE indrelid IN
   ('v3_derived.system_search'::regclass,'v3_derived.economy_opportunity'::regclass,
    'v3_derived.body_mechanics'::regclass,'v3_derived.system_rating_vector'::regclass)
   AND (NOT indisvalid OR NOT indisready)),
 'invalid_triggers',(SELECT count(*) FROM pg_trigger WHERE tgrelid IN
   ('v3_derived.system_search'::regclass,'v3_derived.economy_opportunity'::regclass,
    'v3_derived.body_mechanics'::regclass,'v3_derived.system_rating_vector'::regclass) AND tgenabled<>'O'),
 'rewrites',COALESCE((SELECT jsonb_agg(DISTINCT relation_code) FROM v3_meta.derived_generation_purge_event e
   JOIN v3_meta.derived_generation_purge_request p USING(purge_id)
   WHERE p.plan_sha256=%(plan_sha256)s AND e.event_kind='REWRITE_VERIFIED'),'[]'::jsonb));""")
COMPLETE_SQL = _session("""WITH completed AS MATERIALIZED (
 SELECT value AS purge_id,v3_meta.complete_derived_generation_purge(value::uuid,%(receipt)s::jsonb) AS done
 FROM jsonb_array_elements_text(%(purge_ids)s::jsonb)
)
SELECT jsonb_build_object('completed_ids',jsonb_agg(purge_id),'verified',count(done),
 'snapshot',v3_meta.purge_snapshot(),
 'snapshot_verified',1 / CASE WHEN v3_meta.purge_snapshot()=%(snapshot)s::jsonb THEN 1 ELSE 0 END)
 FROM completed;""", write=True)

# Every identifier is fixed here. The relation code is only a bound value;
# 016 owns its translation into the physical relation and all payload writes.
PHASE_STATE_SQL = _session("""WITH requests AS (
 SELECT * FROM v3_meta.derived_generation_purge_request WHERE purge_id IN
 (SELECT value::uuid FROM jsonb_array_elements_text(%(purge_ids)s::jsonb))
), events AS (
 SELECT e.* FROM v3_meta.derived_generation_purge_event e JOIN requests p USING(purge_id)
), opened AS (
 SELECT e.* FROM events e WHERE e.event_kind IN
 ('BATCH_STARTED','REWRITE_STARTED','AUTOVACUUM_DISABLED','SERVICES_QUIESCED')
 AND NOT EXISTS (SELECT 1 FROM events z WHERE z.purge_id=e.purge_id
 AND z.relation_code IS NOT DISTINCT FROM e.relation_code AND z.event_sequence>e.event_sequence
 AND ((e.event_kind='BATCH_STARTED' AND z.event_kind IN ('BATCH_COMMITTED','BATCH_ROLLED_BACK'))
 OR (e.event_kind='REWRITE_STARTED' AND z.event_kind IN ('REWRITE_VERIFIED','REWRITE_ROLLED_BACK'))
 OR (e.event_kind='AUTOVACUUM_DISABLED' AND z.event_kind='AUTOVACUUM_RESTORED')
 OR (e.event_kind='SERVICES_QUIESCED' AND z.event_kind='SERVICES_RESTORED')))
), relation AS (
 SELECT CASE %(relation)s WHEN 'system_search' THEN 'v3_derived.system_search'::regclass
 WHEN 'economy_opportunity' THEN 'v3_derived.economy_opportunity'::regclass
 WHEN 'body_mechanics' THEN 'v3_derived.body_mechanics'::regclass
 WHEN 'system_rating_vector' THEN 'v3_derived.system_rating_vector'::regclass END AS oid
)
SELECT jsonb_build_object(
 'open_events',COALESCE((SELECT jsonb_agg(to_jsonb(e) || jsonb_build_object('backend_alive',
 EXISTS(SELECT 1 FROM pg_stat_activity a WHERE a.pid=e.backend_pid AND a.backend_start=e.backend_start)))
 FROM opened e),'[]'::jsonb),
 'writer_fence',(SELECT to_jsonb(e) FROM events e WHERE event_kind IN
 ('WRITER_FENCE_ENABLED','WRITER_FENCE_RESTORED') ORDER BY event_sequence DESC LIMIT 1),
 'integrity_failures',COALESCE((SELECT jsonb_agg(to_jsonb(e)) FROM events e
 WHERE event_kind='FAILED_STOP' AND failure_evidence->'integrity_failed'='true'::jsonb),'[]'::jsonb),
 'target_counts',(SELECT jsonb_object_agg(p.derived_generation_id::text,CASE %(relation)s
 WHEN 'system_search' THEN (SELECT count(*) FROM v3_derived.system_search x WHERE x.derived_generation_id=p.derived_generation_id)
 WHEN 'economy_opportunity' THEN (SELECT count(*) FROM v3_derived.economy_opportunity x WHERE x.derived_generation_id=p.derived_generation_id)
 WHEN 'body_mechanics' THEN (SELECT count(*) FROM v3_derived.body_mechanics x WHERE x.derived_generation_id=p.derived_generation_id)
 WHEN 'system_rating_vector' THEN (SELECT count(*) FROM v3_derived.system_rating_vector x WHERE x.derived_generation_id=p.derived_generation_id)
 END) FROM requests p),
 'relation_bytes',(SELECT pg_total_relation_size(oid) FROM relation),
 'vacuum_running',EXISTS(SELECT 1 FROM pg_stat_progress_vacuum WHERE relid IN
 ((SELECT oid FROM relation),(SELECT reltoastrelid FROM pg_class WHERE oid=(SELECT oid FROM relation)))),
 'ages',(SELECT jsonb_agg(jsonb_build_object('scope',CASE WHEN c.oid=r.oid THEN 'heap' ELSE 'toast' END,
 'xid_age',age(c.relfrozenxid)::bigint,'mxid_age',mxid_age(c.relminmxid)::bigint))
 FROM relation r JOIN pg_class c ON c.oid IN (r.oid,(SELECT reltoastrelid FROM pg_class WHERE oid=r.oid))));""")
AUTOVACUUM_SQL = _session("""WITH changed AS MATERIALIZED (
 SELECT v3_meta.purge_set_relation_autovacuum(%(purge_id)s::uuid,%(relation)s,%(enabled)s::boolean)
) SELECT jsonb_build_object('autovacuum_enabled',%(enabled)s::boolean) FROM changed;""", write=True)
WRITER_SET_SQL = _session("""WITH changed AS MATERIALIZED (
 SELECT v3_meta.purge_set_writer_fence(%(purge_id)s::uuid,%(enabled)s::boolean)
) SELECT jsonb_build_object('enabled',%(enabled)s::boolean) FROM changed;""", write=True)
WRITER_RECYCLE_SQL = _session("""SELECT jsonb_build_object('sessions_recycled',
 v3_meta.purge_recycle_writer_sessions(%(purge_id)s::uuid,%(enabled)s::boolean));""", write=True)
WRITER_VERIFY_SQL = _session("""WITH verified AS MATERIALIZED (
 SELECT v3_meta.purge_verify_writer_fence(%(purge_id)s::uuid,%(enabled)s::boolean,%(observed)s)
) SELECT jsonb_build_object('enabled',%(enabled)s::boolean,'verified',true) FROM verified;""", write=True)
BATCH_SQL = (_session("""SELECT jsonb_build_object('start_event',v3_meta.purge_start_payload_batch(
 %(purge_id)s::uuid,%(relation)s,%(max_rows)s::integer,%(evidence)s::jsonb));""", write=True)
 + '\n' + _session("""SELECT jsonb_build_object('rows_affected',v3_meta.purge_derived_payload_batch(
 %(purge_id)s::uuid,%(relation)s,%(max_rows)s::integer));""", write=True))
CANCEL_BATCH_SQL = _session("""WITH condition AS MATERIALIZED (
 SELECT set_config('v3.purge_cancel_condition',%(condition)s,true)
) SELECT jsonb_build_object('cancelled',v3_meta.cancel_purge_batch(%(purge_id)s::uuid,%(relation)s))
 FROM condition;""", write=True)
ROLLBACK_BATCH_SQL = _session("""SELECT jsonb_build_object('event_sequence',v3_meta.purge_record_event(
 %(purge_id)s::uuid,'BATCH_ROLLED_BACK',%(relation)s,%(evidence)s::jsonb));""", write=True)
BATCH_RANGE_SQL = _session("""WITH started AS (
 SELECT e.*,p.derived_generation_id FROM v3_meta.derived_generation_purge_event e
 JOIN v3_meta.derived_generation_purge_request p USING(purge_id)
 WHERE e.purge_id=%(purge_id)s::uuid AND e.event_sequence=%(start_event)s::bigint
 AND e.event_kind='BATCH_STARTED' AND e.relation_code=%(relation)s
), bounds AS (
 SELECT *,ARRAY(SELECT value::bigint FROM jsonb_array_elements_text(
 CASE WHEN jsonb_typeof(operational_payload->'low')='array' THEN operational_payload->'low' ELSE '[]'::jsonb END)
 WITH ORDINALITY ORDER BY ordinality) AS low,
 ARRAY(SELECT value::bigint FROM jsonb_array_elements_text(
 CASE WHEN jsonb_typeof(operational_payload->'high')='array' THEN operational_payload->'high' ELSE '[]'::jsonb END)
 WITH ORDINALITY ORDER BY ordinality) AS high FROM started
)
SELECT jsonb_build_object('selected',(b.operational_payload->>'selected')::bigint,
 'range_rows',CASE %(relation)s
 WHEN 'system_search' THEN (SELECT count(*) FROM v3_derived.system_search x
 WHERE x.derived_generation_id=b.derived_generation_id AND x.system_id64>=b.low[1] AND x.system_id64<=b.high[1])
 WHEN 'economy_opportunity' THEN (SELECT count(*) FROM v3_derived.economy_opportunity x
 WHERE x.derived_generation_id=b.derived_generation_id
 AND (x.system_id64,x.body_pk,x.economy_ordinal)>=(b.low[1],b.low[2],b.low[3]::smallint)
 AND (x.system_id64,x.body_pk,x.economy_ordinal)<=(b.high[1],b.high[2],b.high[3]::smallint))
 WHEN 'body_mechanics' THEN (SELECT count(*) FROM v3_derived.body_mechanics x
 WHERE x.derived_generation_id=b.derived_generation_id
 AND (x.system_id64,x.body_pk)>=(b.low[1],b.low[2])
 AND (x.system_id64,x.body_pk)<=(b.high[1],b.high[2]))
 WHEN 'system_rating_vector' THEN (SELECT count(*) FROM v3_derived.system_rating_vector x
 WHERE x.derived_generation_id=b.derived_generation_id AND x.system_id64>=b.low[1] AND x.system_id64<=b.high[1])
 END) FROM bounds b;""")
RELATION_BYTES_SQL = _session("""SELECT jsonb_build_object('relation_bytes',pg_total_relation_size(
 CASE %(relation)s WHEN 'system_search' THEN 'v3_derived.system_search'::regclass
 WHEN 'economy_opportunity' THEN 'v3_derived.economy_opportunity'::regclass
 WHEN 'body_mechanics' THEN 'v3_derived.body_mechanics'::regclass
 WHEN 'system_rating_vector' THEN 'v3_derived.system_rating_vector'::regclass END));""")
RELATION_EMPTY_SQL = _session("""WITH verified AS MATERIALIZED (
 SELECT v3_meta.complete_derived_payload_relation(value::uuid,%(relation)s,%(receipt)s::jsonb)
 FROM jsonb_array_elements_text(%(purge_ids)s::jsonb)
) SELECT jsonb_build_object('logically_empty',true,'verified',count(*)) FROM verified;""", write=True)
RELATION_FAILURE_SQL = _session("""WITH recorded AS MATERIALIZED (
 SELECT v3_meta.purge_record_event(value::uuid,'FAILED_STOP',%(relation)s,%(evidence)s::jsonb) AS event
 FROM jsonb_array_elements_text(%(purge_ids)s::jsonb)
) SELECT jsonb_build_object('failed_stop_events',jsonb_agg(event)) FROM recorded;""", write=True)

# pg_stat_activity backend identity is an owner-only observation, matching the
# existing progress/competing-writer read boundary. Recovery must not inspect a
# payload heap: a future rewrite can hold ACCESS EXCLUSIVE while recovery needs
# to authenticate its backend and cancel it. This query is strictly read-only.
_RECOVERY_STATE_READ = """BEGIN READ ONLY;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='45min';
WITH requests AS (
 SELECT purge_id FROM v3_meta.derived_generation_purge_request WHERE purge_id IN
 (SELECT value::uuid FROM jsonb_array_elements_text(%(purge_ids)s::jsonb))
), events AS (
 SELECT e.* FROM v3_meta.derived_generation_purge_event e JOIN requests p USING(purge_id)
), opened AS (
 SELECT e.* FROM events e WHERE e.event_kind IN
 ('BATCH_STARTED','REWRITE_STARTED','AUTOVACUUM_DISABLED','SERVICES_QUIESCED')
 AND NOT EXISTS (SELECT 1 FROM events z WHERE z.purge_id=e.purge_id
 AND z.relation_code IS NOT DISTINCT FROM e.relation_code AND z.event_sequence>e.event_sequence
 AND ((e.event_kind='BATCH_STARTED' AND z.event_kind IN ('BATCH_COMMITTED','BATCH_ROLLED_BACK'))
 OR (e.event_kind='REWRITE_STARTED' AND z.event_kind IN ('REWRITE_VERIFIED','REWRITE_ROLLED_BACK'))
 OR (e.event_kind='AUTOVACUUM_DISABLED' AND z.event_kind='AUTOVACUUM_RESTORED')
 OR (e.event_kind='SERVICES_QUIESCED' AND z.event_kind='SERVICES_RESTORED')))
)
SELECT jsonb_build_object(
 'open_events',COALESCE((SELECT jsonb_agg(to_jsonb(e) || jsonb_build_object('backend_alive',
 EXISTS(SELECT 1 FROM pg_stat_activity a WHERE a.pid=e.backend_pid AND a.backend_start=e.backend_start)))
 FROM opened e),'[]'::jsonb),
 'writer_fence',(SELECT to_jsonb(e) FROM events e WHERE event_kind IN
 ('WRITER_FENCE_ENABLED','WRITER_FENCE_RESTORED') ORDER BY event_sequence DESC LIMIT 1),
 'integrity_failures',COALESCE((SELECT jsonb_agg(to_jsonb(e)) FROM events e
 WHERE event_kind='FAILED_STOP' AND failure_evidence->'integrity_failed'='true'::jsonb),'[]'::jsonb));
COMMIT;"""


class PurgeTransactionError(ValueError):
    """A safe error code and non-secret observations for the outer receipt."""

    def __init__(self, code: str, evidence: dict | None = None):
        self.code = code
        self.evidence = evidence or {}
        super().__init__(code)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _result(query, sql: str, params: dict | None = None, *, write: bool = False) -> dict:
    value = query(sql, params, write=write)
    if not isinstance(value, dict):
        raise PurgeTransactionError('purge_sql_result_invalid')
    return value


def _targets(value: object, *, failed: bool = False) -> list[dict]:
    if not isinstance(value, list) or len(value) != 2 or any(not isinstance(t, dict) for t in value):
        raise PurgeTransactionError('purge_target_identity_mismatch')
    indexed = {t.get('id'): t for t in value}
    if set(indexed) != set(TARGET_IDS):
        raise PurgeTransactionError('purge_target_identity_mismatch')
    for identity, key, state in TARGET_IDENTITIES:
        target = indexed[identity]
        counts = target.get('payload_counts')
        if (target.get('key') != key or target.get('state') != ('FAILED' if failed else state)
                or not re.fullmatch('[0-9a-f]{64}', str(target.get('manifest_sha256', '')))
                or not isinstance(counts, dict) or set(counts) != set(RELATIONS)
                or any(type(n) is not int or n < 0 for n in counts.values())):
            raise PurgeTransactionError('purge_target_identity_mismatch')
    return value


def collect_plan(query, source_git_sha: str, actor: str, reason: str) -> dict:
    """Read the exact 016 plan and obtain its PostgreSQL jsonb::text digest.

    This digest differs from f2d_evidence's canonical JSON seal. Both are kept:
    plan_sha256 authenticates 016's reviewed_plan, content_sha256 seals the outer
    receipt used by the operator's path plus expected-SHA authentication.
    """
    if (not re.fullmatch('[0-9a-f]{40}', source_git_sha)
            or not isinstance(actor, str) or not 1 <= len(actor) <= 256 or actor != actor.strip()
            or not isinstance(reason, str) or not 1 <= len(reason) <= 2048 or reason != reason.strip()):
        raise PurgeTransactionError('purge_plan_actor_source_or_reason_invalid')
    observed = _result(query, PLAN_SQL)
    _targets(observed.get('targets'))
    snapshot = observed.get('snapshot')
    if (not isinstance(snapshot, dict) or any(not isinstance(snapshot.get(k), dict)
            for k in ('canonical', 'derived', 'spatial', 'retained', 'survivors'))
            or snapshot['derived'].get('derived_generation_id') != PUBLISHED_ID):
        raise PurgeTransactionError('purge_published_identity_mismatch')
    return seal_plan(query, {**observed, 'workers_stopped': True, 'source_git_sha': source_git_sha,
                             'actor': actor, 'reason': reason})


def seal_plan(query, plan_body: dict) -> dict:
    """Reseal after adding observations such as the autovacuum measurement."""
    body = {k: v for k, v in plan_body.items() if k != 'plan_sha256'}
    digest = _result(query, PLAN_HASH_SQL, {'plan': _json(body)}).get('plan_sha256')
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
        raise PurgeTransactionError('purge_plan_digest_invalid')
    return {**body, 'plan_sha256': digest}


def wait_for_competing_writers(query, *, clock=time.monotonic, sleep=time.sleep) -> dict:
    """Bounded grace for automatic ANALYZE, retaining 016's exact predicate.

    This is never authority to ignore any backend. 016 rechecks within the write
    transaction, so a writer appearing after this observation still refuses.
    """
    started = clock()
    attempts = 0
    observed_background = False
    while True:
        attempts += 1
        try:
            result = _result(query, COMPETING_WRITER_SQL)
        except Exception as exc:
            raise PurgeTransactionError('purge_competing_writer_observation_failed', {
                'maximum_seconds': WRITER_WAIT_SECONDS,
                'elapsed_seconds': round(clock() - started, 3), 'attempts': attempts,
                'background_writer_observed': observed_background,
                'remaining_competing_writers': None,
            }) from exc
        count = result.get('competing_writers')
        background = result.get('background_writers')
        if (type(count) is not int or count < 0 or type(background) is not int
                or not 0 <= background <= count):
            raise PurgeTransactionError('purge_competing_writer_observation_invalid', {
                'maximum_seconds': WRITER_WAIT_SECONDS,
                'elapsed_seconds': round(clock() - started, 3), 'attempts': attempts,
                'background_writer_observed': observed_background,
                'remaining_competing_writers': None,
            })
        observed_background |= background > 0
        elapsed = clock() - started
        evidence = {'maximum_seconds': WRITER_WAIT_SECONDS, 'elapsed_seconds': round(elapsed, 3),
                    'attempts': attempts, 'background_writer_observed': observed_background,
                    'remaining_competing_writers': count}
        if count == 0:
            return evidence
        if elapsed >= WRITER_WAIT_SECONDS or attempts >= WRITER_WAIT_SECONDS + 1:
            raise PurgeTransactionError('purge_competing_writer_wait_exhausted', evidence)
        sleep(min(WRITER_POLL_SECONDS, WRITER_WAIT_SECONDS - elapsed))


def _write_after_wait(query, sql: str, params: dict, waited: dict, phase: str) -> dict:
    """Retain the bounded wait even when transport cannot prove COMMIT.

    Never retry an uncertain mutation. The adapter marks write outcome unknown
    before sending SQL; only a fresh read-only status may resolve that outcome.
    """
    try:
        return _result(query, sql, params, write=True)
    except Exception as exc:
        raise PurgeTransactionError('purge_' + phase + '_write_outcome_unknown',
                                    {**waited, 'transaction_outcome': None}) from exc


def authorize(query, reviewed_plan: dict, *, before_write=None) -> dict:
    _targets(reviewed_plan.get('targets'))
    digest = seal_plan(query, reviewed_plan)['plan_sha256']
    if digest != reviewed_plan.get('plan_sha256'):
        raise PurgeTransactionError('purge_plan_digest_mismatch')
    current = _result(query, PLAN_SQL)
    if (current.get('snapshot') != reviewed_plan.get('snapshot')
            or current.get('targets') != reviewed_plan.get('targets')
            or reviewed_plan.get('workers_stopped') is not True):
        raise PurgeTransactionError('purge_plan_live_identity_mismatch')
    if any(verify_empty(query)['counts'].values()):
        raise PurgeTransactionError('purge_unexpected_excluded_payload')
    if before_write is not None:
        before_write()
    waited = wait_for_competing_writers(query)
    result = _write_after_wait(query, AUTHORIZE_SQL,
                              {'plan': _json(reviewed_plan), 'snapshot': _json(reviewed_plan['snapshot'])},
                              waited, 'authorization')
    try:
        _ids(result.get('purge_ids'))
    except PurgeTransactionError as exc:
        raise PurgeTransactionError('purge_authorization_postcondition_unknown', waited) from exc
    if result.get('snapshot') != reviewed_plan['snapshot'] or result.get('verified') != 1:
        raise PurgeTransactionError('purge_authorization_postcondition_unknown', waited)
    return {**result, 'competing_writer_wait': waited}


def _ids(purge_ids: object) -> list[str]:
    if not isinstance(purge_ids, (list, tuple)) or len(purge_ids) != 2:
        raise PurgeTransactionError('purge_two_request_ids_required')
    try:
        result = [str(UUID(value)) for value in purge_ids]
    except (ValueError, TypeError, AttributeError) as exc:
        raise PurgeTransactionError('purge_request_id_invalid') from exc
    if len(set(result)) != 2:
        raise PurgeTransactionError('purge_two_distinct_request_ids_required')
    return result


def _requests(query, purge_ids, reviewed_plan: dict | None = None) -> list[dict]:
    ids = _ids(purge_ids)
    rows = _result(query, REQUESTS_SQL, {'purge_ids': _json(ids)}).get('requests')
    if (not isinstance(rows, list) or len(rows) != 2
            or any(not isinstance(r, dict) for r in rows)
            or {r.get('purge_id') for r in rows} != set(ids)
            or {r.get('derived_generation_id') for r in rows} != set(TARGET_IDS)
            or len({r.get('plan_sha256') for r in rows}) != 1):
        raise PurgeTransactionError('purge_request_plan_mismatch')
    if reviewed_plan is not None and any(
            r.get('plan_sha256') != reviewed_plan.get('plan_sha256')
            or r.get('frozen_snapshot') != reviewed_plan.get('snapshot') for r in rows):
        raise PurgeTransactionError('purge_request_plan_mismatch')
    return rows


def get_purge_ids(query, plan_sha256: str) -> list[str]:
    if not isinstance(plan_sha256, str) or not re.fullmatch('[0-9a-f]{64}', plan_sha256):
        raise PurgeTransactionError('purge_plan_digest_invalid')
    result = _result(query, PLAN_REQUEST_IDS_SQL, {'plan_sha256': plan_sha256})
    return _ids(result.get('purge_ids'))


def verify_empty(query, *, purge_ids=()) -> dict:
    if purge_ids:
        _requests(query, purge_ids)
    counts = _result(query, EXCLUSIONS_SQL)
    if (set(counts) != {'cluster_run', 'cluster', 'cluster_member', 'system_archetype'}
            or any(type(n) is not int or n < 0 for n in counts.values())):
        raise PurgeTransactionError('purge_exclusion_count_invalid')
    if any(counts.values()):
        evidence = {'integrity_failed': True, 'condition': 'unexpected_cluster_or_archetype_payload',
                    'counts': counts}
        if purge_ids:
            try:
                recorded = _result(query, FAILED_STOP_SQL,
                                   {'purge_ids': _json(_ids(purge_ids)), 'evidence': _json(evidence)}, write=True)
            except Exception as exc:
                raise PurgeTransactionError('purge_failed_stop_outcome_unknown',
                                            {**evidence, 'failed_stop_events': None}) from exc
            evidence.update(recorded)
        raise PurgeTransactionError('purge_unexpected_excluded_payload', evidence)
    return {'empty': True, 'counts': counts, 'database_writes': False}


def complete(query, reviewed_plan: dict, completion_receipt: dict, *, purge_ids, before_write=None) -> dict:
    _requests(query, purge_ids, reviewed_plan)
    verify_empty(query, purge_ids=purge_ids)
    state = _result(query, COMPLETION_STATE_SQL, {'plan_sha256': reviewed_plan['plan_sha256']})
    _targets(state.get('targets'), failed=True)
    if (state.get('snapshot') != reviewed_plan.get('snapshot')
            or any(any(t['payload_counts'].values()) for t in state['targets'])
            or any(state.get(k) != 0 for k in ('invalid_foreign_keys', 'invalid_indexes', 'invalid_triggers'))
            or not isinstance(state.get('rewrites'), list) or set(state['rewrites']) != set(RELATIONS)):
        raise PurgeTransactionError('purge_completion_preconditions_failed', state)
    planned = {t['id']: t for t in reviewed_plan['targets']}
    if any(t['manifest_sha256'] != planned[t['id']]['manifest_sha256'] for t in state['targets']):
        raise PurgeTransactionError('purge_completion_target_manifest_mismatch')
    if (type(completion_receipt.get('filesystem_free_bytes')) is not int
            or completion_receipt['filesystem_free_bytes'] < 100_000_000_000
            or type(completion_receipt.get('wal_bytes')) is not int or completion_receipt['wal_bytes'] < 0
            or not re.fullmatch('[0-9a-f]{64}', str(completion_receipt.get('receipt_sha256', '')))):
        raise PurgeTransactionError('purge_completion_receipt_invalid')
    if before_write is not None:
        before_write()
    waited = wait_for_competing_writers(query)
    result = _write_after_wait(query, COMPLETE_SQL,
                              {'purge_ids': _json(_ids(purge_ids)), 'receipt': _json(completion_receipt),
                               'snapshot': _json(reviewed_plan['snapshot'])},
                              waited, 'completion')
    if (set(result.get('completed_ids', ())) != set(purge_ids) or result.get('verified') != 2
            or result.get('snapshot') != reviewed_plan['snapshot'] or result.get('snapshot_verified') != 1):
        raise PurgeTransactionError('purge_completion_postcondition_unknown', waited)
    return {**result, 'competing_writer_wait': waited}


def _relation(relation: str) -> str:
    if relation not in RELATIONS:
        raise PurgeTransactionError('purge_relation_invalid')
    return relation


def phase_state(query, purge_ids, relation: str) -> dict:
    result = _result(query, PHASE_STATE_SQL,
                     {'purge_ids': _json(_ids(purge_ids)), 'relation': _relation(relation)})
    if (not isinstance(result.get('open_events'), list)
            or not isinstance(result.get('integrity_failures'), list)
            or not isinstance(result.get('ages'), list)
            or not isinstance(result.get('target_counts'), dict)
            or set(result['target_counts']) != set(TARGET_IDS)
            or any(type(n) is not int or n < 0 for n in result['target_counts'].values())
            or type(result.get('relation_bytes')) is not int or result['relation_bytes'] < 0
            or type(result.get('vacuum_running')) is not bool):
        raise PurgeTransactionError('purge_phase_state_invalid')
    return {**result, **metadata_state(query, purge_ids)}


def metadata_state(query, purge_ids) -> dict:
    result = _result(query, _RECOVERY_STATE_READ, {'purge_ids': _json(_ids(purge_ids))})
    if (not isinstance(result.get('open_events'), list)
            or not isinstance(result.get('integrity_failures'), list)
            or any(not isinstance(event, dict) for event in result['open_events'])):
        raise PurgeTransactionError('purge_recovery_state_invalid')
    for key, kind in (('open_batches', 'BATCH_STARTED'), ('open_rewrites', 'REWRITE_STARTED'),
                      ('autovacuum_fences', 'AUTOVACUUM_DISABLED'), ('quiesced_services', 'SERVICES_QUIESCED')):
        result[key] = [event for event in result['open_events'] if event.get('event_kind') == kind]
    return result


def autovacuum_fence(query, purge_ids, relation: str) -> dict:
    """Adopt the existing physical fence only after checking its ledgered ages."""
    ids = _ids(purge_ids)
    state = phase_state(query, ids, relation)
    if any(e['relation_code'] != relation for e in state['autovacuum_fences']):
        raise PurgeTransactionError('different_relation_autovacuum_fence_open')
    if state['vacuum_running']:
        raise PurgeTransactionError('purge_relation_autovacuum_running')
    existing = state['autovacuum_fences']
    if existing:
        options = existing[-1]['operational_payload']
        for age in state['ages']:
            recorded = options.get(age['scope'], {})
            if any(type(age.get(key + '_age')) is not int
                   or type(recorded.get(key + '_ceiling')) is not int
                   or age[key + '_age'] >= recorded[key + '_ceiling'] for key in ('xid', 'mxid')):
                raise PurgeTransactionError('purge_autovacuum_age_ceiling_exceeded', {'ages': state['ages']})
        return {'adopted': True, 'event': existing[-1], 'ages': state['ages']}
    result = _result(query, AUTOVACUUM_SQL,
                     {'purge_id': ids[0], 'relation': _relation(relation), 'enabled': 'false'}, write=True)
    return {**result, 'adopted': False}


def writer_fence(query, purge_id: str, enabled: bool, probe, *, purge_ids=None) -> dict:
    """Each adapter call commits: catalog change, recycle, fresh login, verify.

    probe must create a fresh application-role login and return its observed
    default_transaction_read_only. SET ROLE is never an application login.
    """
    if type(enabled) is not bool:
        raise PurgeTransactionError('purge_writer_fence_enable_invalid')
    if purge_ids is not None:
        state = metadata_state(query, purge_ids)
        event = state['writer_fence']
        expected_kind = 'WRITER_FENCE_ENABLED' if enabled else 'WRITER_FENCE_RESTORED'
        if (event and event['event_kind'] == expected_kind
                and event['operational_payload'].get('verified') is True):
            return {'enabled': enabled, 'verified': True, 'adopted': True}
        if not enabled and event is None:
            return {'enabled': False, 'verified': True, 'already_restored': True}
    params = {'purge_id': str(UUID(purge_id)), 'enabled': str(enabled).lower()}
    _result(query, WRITER_SET_SQL, params, write=True)
    recycled = _result(query, WRITER_RECYCLE_SQL, params, write=True)
    observed = probe()
    if observed != ('on' if enabled else 'off'):
        raise PurgeTransactionError('purge_writer_fence_fresh_probe_failed')
    verified = _result(query, WRITER_VERIFY_SQL, {**params, 'observed': observed}, write=True)
    return {**verified, **recycled, 'adopted': False}


def payload_batch(query, purge_id: str, relation: str, max_rows: int, evidence: dict) -> dict:
    if type(max_rows) is not int or not 1 <= max_rows <= 100_000:
        raise PurgeTransactionError('purge_batch_limit_invalid')
    waited = evidence.get('competing_writer_wait')
    if waited is None:
        waited = wait_for_competing_writers(query)
    elif (not isinstance(waited, dict) or waited.get('maximum_seconds') != WRITER_WAIT_SECONDS
          or type(waited.get('elapsed_seconds')) not in (int, float)
          or not 0 <= waited['elapsed_seconds'] <= WRITER_WAIT_SECONDS
          or type(waited.get('attempts')) is not int or not 1 <= waited['attempts'] <= WRITER_WAIT_SECONDS + 1
          or type(waited.get('background_writer_observed')) is not bool
          or type(waited.get('remaining_competing_writers')) is not int
          or waited['remaining_competing_writers'] != 0):
        raise PurgeTransactionError('purge_batch_competing_writer_wait_invalid')
    result = _write_after_wait(query, BATCH_SQL, {
        'purge_id': str(UUID(purge_id)), 'relation': _relation(relation), 'max_rows': str(max_rows),
        'evidence': _json({**evidence, 'competing_writer_wait': waited}),
    }, waited, 'batch')
    if type(result.get('rows_affected')) is not int or not 0 <= result['rows_affected'] <= max_rows:
        raise PurgeTransactionError('purge_batch_postcondition_unknown', waited)
    return {**result, 'competing_writer_wait': waited}


def cancel_batch(query, purge_id: str, relation: str, condition='owner_cancel') -> dict:
    if condition not in ('owner_cancel', 'controller_loss', 'free_space_floor',
                         'wal_archiver_failure', 'wal_retention', 'wal_filesystem'):
        raise PurgeTransactionError('purge_cancel_condition_invalid')
    return _result(query, CANCEL_BATCH_SQL, {'purge_id': str(UUID(purge_id)),
                   'relation': _relation(relation), 'condition': condition}, write=True)


def resolve_batches(query, purge_ids, relation=None, *, cancel=True,
                    clock=time.monotonic, sleep=time.sleep, maximum_seconds=65) -> dict:
    """016 atomically records every committed delete with BATCH_COMMITTED.

    Therefore a departed backend with an open start is rollback evidence; its
    recorded key range was never committed. Never synthesize a committed event.
    """
    if relation is not None:
        _relation(relation)
    state = metadata_state(query, purge_ids)
    if state['open_rewrites']:
        raise PurgeTransactionError('rewrite_resolution_requires_p2b2b')
    resolved = []
    for event in state['open_batches']:
        if relation is not None and event['relation_code'] != relation:
            raise PurgeTransactionError('different_relation_batch_open')
        started = clock()
        cancellation_attempted = False
        while event['backend_alive']:
            if cancel and not cancellation_attempted:
                cancellation_attempted = True
                try:
                    cancel_batch(query, event['purge_id'], event['relation_code'])
                except Exception:
                    # A completing batch can win the cancellation race. Only
                    # fresh ledger/backend evidence may resolve that outcome.
                    pass
            if clock() - started >= maximum_seconds:
                raise PurgeTransactionError('purge_batch_backend_did_not_exit')
            sleep(0.25)
            current = metadata_state(query, purge_ids)
            event = next((e for e in current['open_batches']
                          if e['event_sequence'] == event['event_sequence']), None)
            if event is None:
                break
        if event is not None:
            evidence = _result(query, BATCH_RANGE_SQL, {
                'purge_id': event['purge_id'], 'relation': _relation(event['relation_code']),
                'start_event': str(event['event_sequence']),
            })
            if (type(evidence.get('selected')) is not int or evidence['selected'] < 0
                    or type(evidence.get('range_rows')) is not int
                    or evidence['range_rows'] != evidence['selected']):
                failure = {'condition': 'batch_range_evidence_inconsistent', 'integrity_failed': False,
                           'start_event': event['event_sequence'], 'recorded_key_range': {
                               'low': event['operational_payload'].get('low'),
                               'high': event['operational_payload'].get('high')}, **evidence}
                record_failed_stop(query, purge_ids, failure, event['relation_code'])
                raise PurgeTransactionError('batch_range_evidence_inconsistent', failure)
            result = _result(query, ROLLBACK_BATCH_SQL, {
                'purge_id': event['purge_id'], 'relation': event['relation_code'],
                'evidence': _json({'recovered': True, 'start_event': event['event_sequence'],
                                   'low': event['operational_payload'].get('low'),
                                   'high': event['operational_payload'].get('high'),
                                   'backend_departed': True, 'selected': evidence['selected'],
                                   'range_rows': evidence['range_rows'],
                                   'resolution_evidence': 'departed_backend_atomic_commit_receipt_and_intact_key_range'}),
            }, write=True)
            resolved.append(result['event_sequence'])
    return {'resolved_batch_events': resolved}


def record_failed_stop(query, purge_ids, evidence: dict, relation=None) -> dict:
    # The physical phase is shared by both requests. A single event is enough
    # for 016's plan-wide stop and gives the owner one exact acknowledgement.
    ids = [_ids(purge_ids)[0]]
    if relation is None:
        return _result(query, FAILED_STOP_SQL, {'purge_ids': _json(ids),
                       'evidence': _json(evidence)}, write=True)
    _relation(relation)
    return _result(query, RELATION_FAILURE_SQL, {'purge_ids': _json(ids),
                   'relation': relation, 'evidence': _json(evidence)}, write=True)


def acknowledge_failure(query, purge_ids, sequence: int) -> dict:
    if type(sequence) is not int or sequence <= 0:
        raise PurgeTransactionError('purge_failed_stop_acknowledgement_invalid')
    return record_failed_stop(query, purge_ids, {'integrity_failed': False,
                              'acknowledge_failed_stop': sequence, 'recovery_authorized': True})


def abort_relation(query, purge_ids, relation: str, evidence: dict) -> dict:
    ids = _ids(purge_ids)
    _relation(relation)
    state = metadata_state(query, ids)
    if not any(e['relation_code'] == relation for e in state['autovacuum_fences']):
        return {'aborted': True, 'already_restored': True, 'waiting_for_rewrite': True}
    if state['open_batches'] or state['open_rewrites']:
        raise PurgeTransactionError('purge_abort_open_operation')
    size = _result(query, RELATION_BYTES_SQL, {'relation': relation}).get('relation_bytes')
    if type(size) is not int or size < 0:
        raise PurgeTransactionError('purge_relation_bytes_invalid')
    budget = evidence.get('autovacuum_budget_bytes')
    free = evidence.get('filesystem_free_bytes')
    if type(budget) is not int or budget < size or type(free) is not int:
        raise PurgeTransactionError('purge_abort_budget_invalid', {'relation_bytes': size})
    needed = 100_000_000_000 + budget
    if free < needed:
        raise PurgeTransactionError('purge_abort_headroom_insufficient',
                                    {'required_bytes': needed, 'shortfall_bytes': needed - free})
    # 016's dedicated restoration requires this budgeted-abort evidence. Its
    # AUTOVACUUM_RESTORED payload is immutable prior options, so the measured
    # aborted:true receipt necessarily resides on this preceding FAILED_STOP.
    receipt = record_failed_stop(query, ids, {**evidence, 'aborted': True,
                                             'integrity_failed': False}, relation)
    result = _result(query, AUTOVACUUM_SQL, {'purge_id': ids[0], 'relation': relation,
                                            'enabled': 'true'}, write=True)
    return {**result, **receipt, 'aborted': True, 'waiting_for_rewrite': True}


def complete_relation(query, purge_ids, relation: str, receipt: dict) -> dict:
    return _result(query, RELATION_EMPTY_SQL, {'purge_ids': _json(_ids(purge_ids)),
                   'relation': _relation(relation), 'receipt': _json(receipt)}, write=True)


# Stable descriptive aliases for the phase controller.
run_payload_batch = payload_batch
logical_empty = complete_relation
