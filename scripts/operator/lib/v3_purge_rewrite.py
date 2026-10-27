"""Fixed rewrite statements and ledger recovery; the caller owns host authority.

The start and VACUUM use one persistent backend. The start's JSON marker comes
after COMMIT, allowing the controller to start its independently lived monitor
before it submits VACUUM. Verification uses a different, short-lived backend.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import time
from uuid import UUID

_spec = importlib.util.spec_from_file_location('v3_purge_transactions', Path(__file__).with_name('v3_purge_transactions.py'))
tx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tx)

FLOOR_BYTES = 100_000_000_000
# The protected workflow's reviewed 120-minute statement envelope.
MAX_RECOVERY_STATEMENT_MS = 7_200_000
BACKEND_SQL = """BEGIN READ ONLY;
SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='5s';
SELECT jsonb_build_object('alive',EXISTS(SELECT 1 FROM pg_stat_activity
 WHERE pid=%(backend_pid)s::integer AND backend_start=%(backend_start)s::timestamptz
 AND datname=current_database())); COMMIT;"""
_RELATION = """CASE %(relation)s
 WHEN 'system_search' THEN 'v3_derived.system_search'::regclass
 WHEN 'economy_opportunity' THEN 'v3_derived.economy_opportunity'::regclass
 WHEN 'body_mechanics' THEN 'v3_derived.body_mechanics'::regclass
 WHEN 'system_rating_vector' THEN 'v3_derived.system_rating_vector'::regclass END"""
START_SQL = tx._session("""SELECT v3_meta.purge_record_event(
 %(purge_id)s::uuid,'REWRITE_STARTED',%(relation)s,%(evidence)s::jsonb || jsonb_build_object(
 'heap_bytes',pg_relation_size(""" + _RELATION + """),
 'index_bytes',pg_indexes_size(""" + _RELATION + """)));""", write=True) + """
SELECT jsonb_build_object('start_event',event_sequence,'backend_pid',backend_pid,
 'backend_start',backend_start,'relation_oid',relation_oid::bigint,
 'relfilenode_before',relfilenode_before::bigint,'relation_bytes',relation_bytes,
 'rewrite_started_at',created_at)
 FROM v3_meta.derived_generation_purge_event
 WHERE purge_id=%(purge_id)s::uuid AND relation_code=%(relation)s
 AND event_kind='REWRITE_STARTED' AND backend_pid=pg_backend_pid()
 ORDER BY event_sequence DESC LIMIT 1;"""
EVENT_SQL = tx._session("""SELECT jsonb_build_object('event_sequence',v3_meta.purge_record_event(
 %(purge_id)s::uuid,%(kind)s,%(relation)s,%(evidence)s::jsonb));""", write=True)
CANCEL_SQL = tx._session("""WITH condition AS MATERIALIZED (
 SELECT set_config('v3.purge_cancel_condition',%(condition)s,true)
) SELECT jsonb_build_object('cancelled',v3_meta.cancel_purge_rewrite(
 %(purge_id)s::uuid,%(relation)s)) FROM condition;""", write=True)
# Recovery deliberately never touches a payload heap while an ACCESS EXCLUSIVE
# rewrite might still be running. PID reuse cannot impersonate the recorded
# backend, and both progress views are checked independently of that identity.
STATE_SQL = """BEGIN READ ONLY;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='10s';
WITH relation AS (SELECT """ + _RELATION + """ AS oid), started AS (
 SELECT * FROM v3_meta.derived_generation_purge_event
 WHERE purge_id=%(purge_id)s::uuid AND event_sequence=%(start_event)s::bigint
 AND event_kind='REWRITE_STARTED' AND relation_code=%(relation)s
)
SELECT jsonb_build_object('relation_oid',r.oid::oid::bigint,'relfilenode',c.relfilenode::bigint,
 'relfilenode_before',e.relfilenode_before::bigint,
 'identity_matches',e.relation_oid=r.oid,
 'backend_alive',EXISTS(SELECT 1 FROM pg_stat_activity a
 WHERE a.pid=e.backend_pid AND a.backend_start=e.backend_start),
 'rewrite_running',EXISTS(SELECT 1 FROM pg_stat_progress_cluster WHERE relid=r.oid),
 'analyze_running',EXISTS(SELECT 1 FROM pg_stat_progress_analyze WHERE relid=r.oid))
 FROM relation r JOIN pg_class c ON c.oid=r.oid CROSS JOIN started e;
COMMIT;"""
VERIFY_SQL = tx._session("""WITH relation AS (SELECT """ + _RELATION + """ AS oid), started AS (
 SELECT e.*,p.frozen_snapshot FROM v3_meta.derived_generation_purge_event e
 JOIN v3_meta.derived_generation_purge_request p USING(purge_id)
 WHERE e.purge_id=%(purge_id)s::uuid AND e.event_sequence=%(start_event)s::bigint
 AND e.event_kind='REWRITE_STARTED' AND e.relation_code=%(relation)s
)
SELECT jsonb_build_object('relation_oid',r.oid::oid::bigint,'relfilenode',c.relfilenode::bigint,
 'relfilenode_before',e.relfilenode_before::bigint,'identity_matches',e.relation_oid=r.oid,
 'analyze_verified',EXISTS(SELECT 1 FROM pg_stat_user_tables
 WHERE relid=r.oid AND last_analyze>e.created_at),
 'snapshot_verified',v3_meta.purge_snapshot()=e.frozen_snapshot,
 'target_counts_zero',NOT EXISTS(SELECT 1 FROM v3_meta.derived_generation_purge_request p
 WHERE p.plan_sha256=(SELECT plan_sha256 FROM v3_meta.derived_generation_purge_request
 WHERE purge_id=%(purge_id)s::uuid) AND CASE %(relation)s
 WHEN 'system_search' THEN (SELECT count(*) FROM v3_derived.system_search x WHERE x.derived_generation_id=p.derived_generation_id)
 WHEN 'economy_opportunity' THEN (SELECT count(*) FROM v3_derived.economy_opportunity x WHERE x.derived_generation_id=p.derived_generation_id)
 WHEN 'body_mechanics' THEN (SELECT count(*) FROM v3_derived.body_mechanics x WHERE x.derived_generation_id=p.derived_generation_id)
 WHEN 'system_rating_vector' THEN (SELECT count(*) FROM v3_derived.system_rating_vector x WHERE x.derived_generation_id=p.derived_generation_id)
 END<>0),
 'invalid_foreign_keys',(SELECT count(*) FROM pg_constraint k JOIN pg_namespace n ON n.oid=k.connamespace
 WHERE n.nspname IN ('v3_meta','v3_derived','v3_spatial') AND k.contype='f' AND NOT k.convalidated),
 'invalid_indexes',(SELECT count(*) FROM pg_index WHERE indrelid=r.oid AND (NOT indisvalid OR NOT indisready)),
 'invalid_triggers',(SELECT count(*) FROM pg_trigger WHERE tgrelid=r.oid AND tgenabled<>'O'),
 'heap_bytes',pg_relation_size(r.oid),'index_bytes',pg_indexes_size(r.oid),
 'relation_bytes',pg_total_relation_size(r.oid))
 FROM relation r JOIN pg_class c ON c.oid=r.oid CROSS JOIN started e;""")


def rewrite_configuration(plan: dict, relation: str) -> dict:
    tx._relation(relation)
    configurations = plan.get('rewrite', {})
    config = configurations.get(relation, {}) if isinstance(configurations, dict) else {}
    if not isinstance(config, dict):
        raise tx.PurgeTransactionError('purge_rewrite_plan_configuration_invalid')
    peak = config.get('rewrite_peak_bytes')
    if type(peak) is not int or not 0 <= peak < 2**63:
        raise tx.PurgeTransactionError('rewrite_peak_not_measured')
    timeout = config.get('statement_timeout_ms')
    if type(timeout) is not int or not 1 <= timeout <= 2_147_483_647:
        raise tx.PurgeTransactionError('rewrite_statement_timeout_not_measured')
    return {'rewrite_peak_bytes': peak, 'statement_timeout_ms': timeout}


def session_setup(statement_timeout_ms: int) -> str:
    if type(statement_timeout_ms) is not int or not 1 <= statement_timeout_ms <= 2_147_483_647:
        raise tx.PurgeTransactionError('rewrite_statement_timeout_not_measured')
    # An integer validated above is a session setting, never an identifier.
    return (tx._PREFIX + "SET lock_timeout='5s';\nSET statement_timeout='"
            + str(statement_timeout_ms) + "ms';\n")


def rewrite_command(relation: str) -> str:
    # Closed mapping: relation text is never interpolated into identifiers.
    return {
        'system_search': 'VACUUM (FULL, ANALYZE) v3_derived.system_search;',
        'economy_opportunity': 'VACUUM (FULL, ANALYZE) v3_derived.economy_opportunity;',
        'body_mechanics': 'VACUUM (FULL, ANALYZE) v3_derived.body_mechanics;',
        'system_rating_vector': 'VACUUM (FULL, ANALYZE) v3_derived.system_rating_vector;',
    }[tx._relation(relation)]


def analyze_command(relation: str) -> str:
    return {
        'system_search': 'ANALYZE v3_derived.system_search;',
        'economy_opportunity': 'ANALYZE v3_derived.economy_opportunity;',
        'body_mechanics': 'ANALYZE v3_derived.body_mechanics;',
        'system_rating_vector': 'ANALYZE v3_derived.system_rating_vector;',
    }[tx._relation(relation)]


def start_evidence(measured: dict, rewrite_peak_bytes: int, competing_writer_wait) -> dict:
    """Fresh host evidence for REWRITE_STARTED.

    016's shared freshness check (purge_check_measurements) bounds
    batch_peak_bytes to one delete batch (< 1 GB). A rewrite has no delete
    batch, so it reports 0 there. The rewrite's own peak travels as
    rewrite_peak_bytes, which REWRITE_STARTED checks against the 100 GB floor
    separately; the controller has already enforced the same headroom.
    """
    if type(rewrite_peak_bytes) is not int or not 0 <= rewrite_peak_bytes < 2**63:
        raise tx.PurgeTransactionError('rewrite_peak_not_measured')
    return {**measured, 'batch_peak_bytes': 0, 'rewrite_peak_bytes': rewrite_peak_bytes,
            'competing_writer_wait': competing_writer_wait}


def start_rewrite(query, purge_ids, relation: str, receipt: dict) -> dict:
    ids = tx._ids(purge_ids)
    tx._relation(relation)
    peak, free = receipt.get('rewrite_peak_bytes'), receipt.get('filesystem_free_bytes')
    if type(peak) is not int or not 0 <= peak < 2**63:
        raise tx.PurgeTransactionError('rewrite_peak_not_measured')
    required = FLOOR_BYTES + (3 * peak + 1) // 2
    if type(free) is not int or free < required:
        raise tx.PurgeTransactionError('rewrite_projected_headroom_insufficient', {'required_bytes': required})
    result = tx._result(query, START_SQL, {'purge_id': ids[0], 'relation': relation,
                                        'evidence': tx._json(receipt)}, write=True)
    if (type(result.get('start_event')) is not int or result['start_event'] <= 0
            or type(result.get('backend_pid')) is not int or result['backend_pid'] <= 0
            or not result.get('backend_start')
            or type(result.get('relfilenode_before')) is not int):
        raise tx.PurgeTransactionError('purge_rewrite_start_outcome_unknown', {'transaction_outcome': None})
    return result


def cancel_rewrite(query, purge_id: str, relation: str, condition='owner_cancel') -> dict:
    if condition not in ('owner_cancel', 'controller_loss', 'free_space_floor',
                         'wal_archiver_failure', 'wal_retention', 'wal_filesystem'):
        raise tx.PurgeTransactionError('purge_cancel_condition_invalid')
    return tx._result(query, CANCEL_SQL, {'purge_id': str(UUID(purge_id)),
                      'relation': tx._relation(relation), 'condition': condition}, write=True)


def _params(event: dict) -> dict:
    return {'purge_id': str(UUID(event['purge_id'])),
            'relation': tx._relation(event['relation_code']),
            'start_event': str(event['event_sequence'])}


def _state(query, event: dict) -> dict:
    state = tx._result(query, STATE_SQL, _params(event))
    if (state.get('identity_matches') is not True
            or any(type(state.get(k)) is not bool for k in ('backend_alive', 'rewrite_running', 'analyze_running'))
            or any(type(state.get(k)) is not int for k in ('relfilenode', 'relfilenode_before'))):
        raise tx.PurgeTransactionError('purge_rewrite_identity_invalid')
    return state


def verify_rewrite(query, purge_ids, relation: str, receipt: dict, *, recovered=False, event=None) -> dict:
    tx._relation(relation)
    if event is None:
        opened = tx.metadata_state(query, purge_ids)['open_rewrites']
        matching = [e for e in opened if e['relation_code'] == relation]
        if len(matching) != 1:
            raise tx.PurgeTransactionError('purge_rewrite_start_missing')
        event = matching[0]
    observed = tx._result(query, VERIFY_SQL, _params(event))
    changed = (type(observed.get('relfilenode')) is int
               and type(observed.get('relfilenode_before')) is int
               and observed['relfilenode'] != observed['relfilenode_before'])
    if (not changed or observed.get('identity_matches') is not True
            or any(observed.get(key) is not True for key in ('analyze_verified', 'snapshot_verified', 'target_counts_zero'))
            or any(observed.get(key) != 0 for key in ('invalid_foreign_keys', 'invalid_indexes', 'invalid_triggers'))
            or any(type(observed.get(key)) is not int or observed[key] < 0
                   for key in ('heap_bytes', 'index_bytes', 'relation_bytes'))):
        failure = {'condition': 'rewrite_verification_failed', 'rewrite_committed': changed,
                   'integrity_failed': changed, 'start_event': event['event_sequence'], 'verification': observed}
        tx.record_failed_stop(query, purge_ids, failure, relation)
        raise tx.PurgeTransactionError('rewrite_verification_failed', failure)
    evidence = {**receipt, 'recovered': recovered, 'start_event': event['event_sequence'], 'verification': observed}
    result = tx._result(query, EVENT_SQL, {**_params(event), 'kind': 'REWRITE_VERIFIED',
                                        'evidence': tx._json(evidence)}, write=True)
    return {**result, 'recovered': recovered, 'verification': observed}


def resolve_rewrites(query, purge_ids, relation=None, *, cancel=True, analyze=None, receipt=None,
                     statement_timeout_ms=None,
                     clock=time.monotonic, sleep=time.sleep, maximum_seconds=65) -> dict:
    """Resolve from durable filenodes; a changed node is never rewritten twice.

    ``receipt`` can be a fresh-measurement callback. ``analyze`` must execute the
    supplied fixed SQL under the executor role and close its backend afterward.
    The default uses the same JSON query adapter, with a standalone ANALYZE.
    """
    if relation is not None:
        tx._relation(relation)
    events = tx.metadata_state(query, purge_ids)['open_rewrites']
    result = {'resolved_rewrite_events': [], 'verified_relations': [], 'rolled_back_relations': []}
    for event in events:
        code = tx._relation(event['relation_code'])
        if relation is not None and code != relation:
            raise tx.PurgeTransactionError('different_relation_rewrite_open')
        started, attempted = clock(), False
        while True:
            state = _state(query, event)
            if not any(state[k] for k in ('backend_alive', 'rewrite_running', 'analyze_running')):
                break
            if not cancel:
                raise tx.PurgeTransactionError('purge_rewrite_backend_still_active', state)
            if state['backend_alive'] and not attempted:
                attempted = True
                try:
                    cancel_rewrite(query, event['purge_id'], code)
                except Exception:
                    # The backend can finish between observation and cancel;
                    # only a fresh observation can decide whether it departed.
                    pass
            if clock() - started >= maximum_seconds:
                raise tx.PurgeTransactionError('purge_rewrite_backend_did_not_exit', state)
            sleep(0.25)
        if state['relfilenode'] == state['relfilenode_before']:
            resolved = tx._result(query, EVENT_SQL, {**_params(event), 'kind': 'REWRITE_ROLLED_BACK',
                'evidence': tx._json({'recovered': True, 'start_event': event['event_sequence'],
                                      'backend_departed': True, 'relfilenode_unchanged': True})}, write=True)
            result['rolled_back_relations'].append(code)
        else:
            try:
                command = analyze_command(code)
                if analyze is not None:
                    analyze(command)
                else:
                    tx._result(query, session_setup(statement_timeout_ms) + command
                               + "\nSELECT jsonb_build_object('analyzed',true);", write=True)
                measured = receipt() if callable(receipt) else receipt
                if not isinstance(measured, dict):
                    raise tx.PurgeTransactionError('purge_rewrite_recovery_measurements_missing')
                resolved = verify_rewrite(query, purge_ids, code, measured, recovered=True, event=event)
            except Exception as exc:
                if getattr(exc, 'code', '') != 'rewrite_verification_failed':
                    failure = {'condition': 'rewrite_recovery_verification_failed', 'rewrite_committed': True,
                               'integrity_failed': True, 'start_event': event['event_sequence']}
                    tx.record_failed_stop(query, purge_ids, failure, code)
                    raise tx.PurgeTransactionError('rewrite_recovery_verification_failed', failure) from exc
                raise
            result['verified_relations'].append(code)
        result['resolved_rewrite_events'].append(resolved['event_sequence'])
    return result
