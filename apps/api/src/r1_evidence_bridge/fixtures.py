from .types import BodyEvidenceHints,CanonicalBodyRow,CanonicalRingRow,CanonicalSystemRow
def system(sid='2001',name='Canonical Test',count=1,has=True): return CanonicalSystemRow(sid,name,has,count,'2026-08-31T00:00:00Z')
def body(bid='b1',sid='2001',subtype='High metal content world',**kw):
    d=dict(distance_from_star=1000.0,is_tidal_lock=False,radius=3200.0,gravity=1.0,surface_temp=300.0,atmosphere_type='No atmosphere',volcanism='No volcanism',terraforming_state='Not terraformable',is_terraformable=False,is_landable=True,bio_signal_count=0,geo_signal_count=0,updated_at='2026-08-31T00:00:00Z',is_ammonia_world=False)
    d.update(kw); return CanonicalBodyRow(bid,sid,bid,'Planet',subtype,**d)
def hint(bid='b1',**kw): return BodyEvidenceHints(bid,**kw)
def ring(body_id='b1',status='local_matched',body_name='b1'): return CanonicalRingRow(body_id if status=='local_matched' else None,None,body_name,'A Ring','spansh_dump','source_ring_payload',status,'2026-08-31T00:00:00Z')
