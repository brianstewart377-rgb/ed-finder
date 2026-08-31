from r1_real_snapshot.loader import *
from r1_real_snapshot.report import build_report
from r1_real_snapshot.types import SnapshotSelector
class Cur:
    def __init__(self,c):self.c=c;self.rows=[]
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def execute(self,sql,params=None):
        self.c.calls.append((sql,params)); u=sql.upper()
        if u.startswith('SHOW'):self.rows=[{'transaction_read_only':self.c.readonly}]
        elif 'CURRENT_DATABASE()' in u:self.rows=[{'current_database':'edfinder','current_user':'readonly'}]
        elif "TO_REGCLASS('PUBLIC.BODY_RINGS')" in u:self.rows=[{'body_rings_present':self.c.ring_table}]
        elif 'FROM SYSTEMS' in u:self.rows=self.c.systems
        elif 'FROM BODIES' in u:self.rows=self.c.bodies
        elif 'FROM BODY_RINGS' in u:self.rows=self.c.rings
        else:raise AssertionError(sql)
    def fetchone(self):return self.rows[0] if self.rows else None
    def fetchall(self):return list(self.rows)
class Conn:
    def __init__(self,readonly='on',systems=None,bodies=None,rings=None,ring_table=True):self.readonly=readonly;self.systems=systems or [];self.bodies=bodies or [];self.rings=rings or [];self.ring_table=ring_table;self.calls=[]
    def cursor(self):return Cur(self)
def sysrow(id='1',name='Alpha',count=1,has=True):return {'id64':id,'name':name,'has_body_data':has,'body_count':count,'updated_at':'2026-08-31'}
def brow(id='10',sid='1',name='Alpha 1',sub='High metal content world',**kw):
    d={'id':id,'system_id64':sid,'name':name,'body_type':'Planet','subtype':sub,'distance_from_star':1000.0,'is_tidal_lock':False,'radius':3200.0,'gravity':1.0,'surface_temp':300.0,'atmosphere_type':'No atmosphere','volcanism':'No volcanism','terraforming_state':None,'is_terraformable':False,'is_landable':False,'bio_signal_count':0,'geo_signal_count':0,'updated_at':'2026-08-31','is_ammonia_world':False};d.update(kw);return d
def rrow(sid='1',bid='10'):return {'system_id64':sid,'body_id':bid,'source_body_id':None,'body_name':'Alpha 1','ring_name':'A Ring','source':'spansh_dump','confidence':'source_ring_payload','association_status':'local_matched','updated_at':'2026-08-31'}
def test_refuses_more_than_20():
    import pytest
    with pytest.raises(ValueError):load_snapshots(Conn(),[SnapshotSelector('id64',str(i)) for i in range(21)])
def test_refuses_non_readonly_session():
    import pytest
    with pytest.raises(SnapshotSafetyError):load_snapshots(Conn(readonly='off'),[SnapshotSelector('id64','1')])
def test_identity_read_is_select_only(): assert read_db_identity(Conn())=={'current_database':'edfinder','current_user':'readonly'}
def test_parameterized_selector_query():
    c=Conn(systems=[sysrow()],bodies=[brow()]);load_snapshots(c,[SnapshotSelector('name','Alpha')]); q,p=c.calls[1];assert '%s' in q and p==([],['Alpha'])
def test_deterministic_system_order():
    c=Conn(systems=[sysrow('2','Zulu'),sysrow('1','Alpha')],bodies=[brow('20','2','Zulu 1'),brow('10','1','Alpha 1')]);b=load_snapshots(c,[SnapshotSelector('id64','2'),SnapshotSelector('id64','1')]);assert [x.system.name for x in b]==['Alpha','Zulu']
def test_maps_default_false_to_unknown_via_bridge():
    b=load_snapshots(Conn(systems=[sysrow()],bodies=[brow()]),[SnapshotSelector('id64','1')])[0];p=b.projected_system.bodies[0];assert p.body.is_landable is None and p.body.has_geologicals is None
def test_ring_association_preserved():
    b=load_snapshots(Conn(systems=[sysrow()],bodies=[brow()],rings=[rrow()]),[SnapshotSelector('id64','1')])[0];assert b.ring_source_available is True and b.projected_system.bodies[0].body.has_rings is True
def test_missing_ring_table_does_not_block_snapshot_and_keeps_ring_unknown():
    c=Conn(systems=[sysrow()],bodies=[brow()],ring_table=False);b=load_snapshots(c,[SnapshotSelector('id64','1')])[0]
    assert b.ring_source_available is False and b.projected_system.bodies[0].body.has_rings is None
    assert not any('FROM BODY_RINGS' in q.upper() for q,_ in c.calls)
def test_missing_ring_table_is_reported_as_caveat():
    b=load_snapshots(Conn(systems=[sysrow()],bodies=[brow()],ring_table=False),[SnapshotSelector('id64','1')])[0];r=build_report(b)
    assert r.ring_source_available is False and any('body_rings source unavailable' in x for x in r.caveats)
def test_ring_source_availability_changes_digest():
    a=load_snapshots(Conn(systems=[sysrow()],bodies=[brow()],ring_table=True),[SnapshotSelector('id64','1')])[0]
    b=load_snapshots(Conn(systems=[sysrow()],bodies=[brow()],ring_table=False),[SnapshotSelector('id64','1')])[0]
    assert a.snapshot_digest!=b.snapshot_digest
def test_snapshot_digest_deterministic():
    c1=Conn(systems=[sysrow()],bodies=[brow()]);c2=Conn(systems=[sysrow()],bodies=[brow()]);assert load_snapshots(c1,[SnapshotSelector('id64','1')])[0].snapshot_digest==load_snapshots(c2,[SnapshotSelector('id64','1')])[0].snapshot_digest
def test_no_plan_resilience_or_fit_emitted():
    c=load_snapshots(Conn(systems=[sysrow()],bodies=[brow()]),[SnapshotSelector('id64','1')])[0].candidate;assert not hasattr(c,'pair_resilience') and c.extraction_evidence.support is None
def test_report_counts_unknowns_and_slots():
    r=build_report(load_snapshots(Conn(systems=[sysrow()],bodies=[brow()]),[SnapshotSelector('id64','1')])[0]);assert r.surface_slots_unknown==1 and dict(r.availability_counts)['unknown']>0
def test_sql_constants_select_show_only(): assert sql_is_select_only()
def test_no_mutation_sql_observed():
    c=Conn(systems=[sysrow()],bodies=[brow()]);load_snapshots(c,[SnapshotSelector('id64','1')]); assert all(q.lstrip().upper().startswith(('SELECT','SHOW')) for q,_ in c.calls)
def test_missing_selector_returns_empty(): assert load_snapshots(Conn(),[SnapshotSelector('name','Missing')])==()
def test_body_count_mismatch_surfaces_conflict():
    b=load_snapshots(Conn(systems=[sysrow(count=2)],bodies=[brow()]),[SnapshotSelector('id64','1')])[0];assert b.projected_system.body_data_completeness=='conflicting'
def test_selector_requires_explicit_value():
    import pytest
    with pytest.raises(ValueError):load_snapshots(Conn(),[])
