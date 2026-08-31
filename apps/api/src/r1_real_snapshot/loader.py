from __future__ import annotations
from dataclasses import asdict
from collections.abc import Mapping
import re
from r1_evidence_bridge.candidate_projection import project_candidate,project_system
from r1_evidence_bridge.types import CanonicalBodyRow,CanonicalRingRow,CanonicalSystemRow
from r1_finder_compare.evidence import sha256_id
from .types import SnapshotBundle,SnapshotSelector
MAX_SYSTEMS=20
SHOW_READ_ONLY_SQL='SHOW transaction_read_only'
DB_IDENTITY_SQL='SELECT current_database() AS current_database, current_user AS current_user'
SYSTEMS_SQL='''SELECT id64::text AS id64, name, has_body_data, body_count, updated_at::text AS updated_at FROM systems WHERE id64 = ANY(%s::bigint[]) OR name = ANY(%s::text[]) ORDER BY id64'''
BODIES_SQL='''SELECT id::text AS id, system_id64::text AS system_id64, name, body_type::text AS body_type, subtype, distance_from_star, is_tidal_lock, radius, gravity, surface_temp, atmosphere_type, volcanism, terraforming_state, is_terraformable, is_landable, bio_signal_count, geo_signal_count, updated_at::text AS updated_at, is_ammonia_world FROM bodies WHERE system_id64 = ANY(%s::bigint[]) ORDER BY system_id64, id'''
RINGS_SQL='''SELECT body_id::text AS body_id, source_body_id::text AS source_body_id, body_name, ring_name, source, confidence, association_status, updated_at::text AS updated_at, system_id64::text AS system_id64 FROM body_rings WHERE system_id64 = ANY(%s::bigint[]) ORDER BY system_id64, body_id NULLS LAST, ring_name NULLS LAST, source'''
class SnapshotSafetyError(RuntimeError): pass
def _row_value(row,key,index=0):
    if isinstance(row,Mapping): return row[key]
    return row[index]
def assert_read_only(conn):
    with conn.cursor() as cur:
        cur.execute(SHOW_READ_ONLY_SQL); row=cur.fetchone(); value=str(_row_value(row,'transaction_read_only')).lower()
    if value!='on': raise SnapshotSafetyError('STOP: database transaction is not read-only')
def read_db_identity(conn):
    with conn.cursor() as cur:
        cur.execute(DB_IDENTITY_SQL); row=cur.fetchone()
    if isinstance(row,Mapping): return {'current_database':str(row['current_database']),'current_user':str(row['current_user'])}
    return {'current_database':str(row[0]),'current_user':str(row[1])}
def _normalize_selectors(selectors):
    selectors=tuple(selectors)
    if not selectors: raise ValueError('at least one explicit selector is required')
    if len(selectors)>MAX_SYSTEMS: raise ValueError(f'maximum {MAX_SYSTEMS} systems per snapshot')
    ids=tuple(sorted({s.value for s in selectors if s.kind=='id64'})); names=tuple(sorted({s.value for s in selectors if s.kind=='name'})); return ids,names
def _system(row): return CanonicalSystemRow(str(row['id64']),str(row['name']),bool(row['has_body_data']),int(row['body_count']),row.get('updated_at'))
def _body(row): return CanonicalBodyRow(str(row['id']),str(row['system_id64']),str(row['name']),str(row['body_type']),row.get('subtype'),row.get('distance_from_star'),row.get('is_tidal_lock'),row.get('radius'),row.get('gravity'),row.get('surface_temp'),row.get('atmosphere_type'),row.get('volcanism'),row.get('terraforming_state'),bool(row.get('is_terraformable')),bool(row.get('is_landable')),int(row.get('bio_signal_count') or 0),int(row.get('geo_signal_count') or 0),row.get('updated_at'),bool(row.get('is_ammonia_world')))
def _ring(row): return CanonicalRingRow(str(row['body_id']) if row.get('body_id') is not None else None,str(row['source_body_id']) if row.get('source_body_id') is not None else None,row.get('body_name'),row.get('ring_name'),str(row['source']),str(row['confidence']),str(row['association_status']),row.get('updated_at'))
def load_snapshots(conn,selectors):
    assert_read_only(conn); ids,names=_normalize_selectors(selectors)
    with conn.cursor() as cur:
        cur.execute(SYSTEMS_SQL,(list(ids),list(names))); systems=tuple(_system(r) for r in cur.fetchall())
    if len(systems)>MAX_SYSTEMS: raise SnapshotSafetyError('selector result exceeded bounded system limit')
    system_ids=tuple(s.id64 for s in systems)
    if not system_ids:return ()
    with conn.cursor() as cur:
        cur.execute(BODIES_SQL,(list(system_ids),)); bodies=tuple(_body(r) for r in cur.fetchall())
    with conn.cursor() as cur:
        cur.execute(RINGS_SQL,(list(system_ids),)); ring_rows=tuple((str(r['system_id64']),_ring(r)) for r in cur.fetchall())
    out=[]
    for s in systems:
        sb=tuple(b for b in bodies if b.system_id64==s.id64); sr=tuple(r for sid,r in ring_rows if sid==s.id64)
        projected=project_system(s,sb,sr,()); candidate=project_candidate(projected)
        digest=sha256_id({'system':asdict(s),'bodies':[asdict(b) for b in sb],'rings':[asdict(r) for r in sr],'projection_revision':projected.projection_revision})
        out.append(SnapshotBundle(s,sb,sr,projected,candidate,digest))
    return tuple(sorted(out,key=lambda x:(x.system.name,x.system.id64)))
def sql_is_select_only():
    allowed=(SHOW_READ_ONLY_SQL,DB_IDENTITY_SQL,SYSTEMS_SQL,BODIES_SQL,RINGS_SQL)
    forbidden=re.compile(r'\b(INSERT|UPDATE|DELETE|ALTER|DROP|CREATE|TRUNCATE|COPY)\b',re.IGNORECASE)
    return all(q.lstrip().upper().startswith(('SELECT','SHOW')) and forbidden.search(q) is None for q in allowed)
