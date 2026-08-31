from __future__ import annotations
import math
from r1_finder_compare.types import BodyFact
from .provenance import canonical_body_provenance,ring_provenance,sorted_ids
from .types import BodyEvidenceHints,CanonicalBodyRow,CanonicalRingRow,FactStatus,ProjectedBodyEvidence

def _status(avail,reason,*ids): return FactStatus(avail,tuple(sorted(x for x in ids if x)),reason)
def _finite(v): return v is not None and isinstance(v,(int,float)) and math.isfinite(float(v))
def _ring_status(body,rings):
    rel=[r for r in rings if r.body_id==body.id or (r.body_id is None and r.body_name==body.name)]
    local=[r for r in rel if r.association_status=='local_matched' and r.body_id==body.id]
    ids=tuple(ring_provenance(r) for r in rel)
    if local:return True,_status('known','trusted local_matched ring evidence',*(ring_provenance(r) for r in local))
    if any(r.association_status=='conflict' for r in rel):return None,_status('conflicting','ring association conflict',*ids)
    if any(r.association_status in ('ambiguous_body_identity','unresolved_body_identity') for r in rel):return None,_status('ambiguous','ring association unresolved or ambiguous',*ids)
    return None,_status('unknown','no trusted ring row; absence is not a negative')
def project_body(row:CanonicalBodyRow,rings:tuple[CanonicalRingRow,...]=(),hints:BodyEvidenceHints|None=None):
    h=hints or BodyEvidenceHints(row.id); base_id=(row.subtype or row.body_type or 'Unknown').strip(); baseprov=canonical_body_provenance(row); hp=h.provenance_ids
    statuses={}
    if row.is_landable: land=True; statuses['is_landable']=_status('known','positive canonical landable flag',baseprov)
    elif h.landable_negative_confirmed: land=False; statuses['is_landable']=_status('known','negative landability explicitly confirmed',*hp)
    else: land=None; statuses['is_landable']=_status('unknown','stored false may be importer default',baseprov)
    tfstate=(row.terraforming_state or '').strip()
    if row.is_terraformable or tfstate.lower()=='terraformable': tf=True; statuses['is_terraformable']=_status('known','positive terraformable state/flag',baseprov)
    elif tfstate: tf=False; statuses['is_terraformable']=_status('known','explicit non-terraformable state',baseprov)
    elif h.terraformable_negative_confirmed: tf=False; statuses['is_terraformable']=_status('known','negative terraformability explicitly confirmed',*hp)
    else: tf=None; statuses['is_terraformable']=_status('unknown','stored false has no explicit source-presence evidence',baseprov)
    if row.geo_signal_count>0: geo=True; statuses['has_geologicals']=_status('known','positive geological signal presence',baseprov)
    elif h.geo_signal_scan_complete: geo=False; statuses['has_geologicals']=_status('known','complete geological signal scan confirms zero',*hp)
    else: geo=None; statuses['has_geologicals']=_status('unknown','zero geological count may mean source data absent',baseprov)
    if row.bio_signal_count>0: bio=True; statuses['has_biologicals']=_status('known','positive biological signal presence',baseprov)
    elif h.bio_signal_scan_complete: bio=False; statuses['has_biologicals']=_status('known','complete biological signal scan confirms zero',*hp)
    else: bio=None; statuses['has_biologicals']=_status('unknown','zero biological count may mean source data absent',baseprov)
    ring,rs=_ring_status(row,rings); statuses['has_rings']=rs
    volc=(row.volcanism or '').strip() or None; statuses['volcanism']=_status('known','explicit volcanism value',baseprov) if volc else _status('unknown','volcanism absent from canonical row',baseprov)
    atm=(row.atmosphere_type or '').strip() or None; statuses['atmosphere']=_status('known','explicit atmosphere value',baseprov) if atm else _status('unknown','atmosphere absent from canonical row',baseprov)
    tidal=row.is_tidal_lock; statuses['is_tidal_lock']=_status('known','nullable canonical tidal-lock value supplied',baseprov) if tidal is not None else _status('unknown','tidal-lock value absent',baseprov)
    nums={}
    for name,val in [('distance_ls',row.distance_from_star),('radius_km',row.radius),('gravity_g',row.gravity),('surface_temperature_k',row.surface_temp)]:
        if _finite(val): nums[name]=float(val); statuses[name]=_status('known','finite canonical numeric value',baseprov)
        else: nums[name]=None; statuses[name]=_status('unknown','numeric value absent or non-finite',baseprov)
    norm=base_id.casefold(); exact_ammonia=norm=='ammonia world'; gas='gas giant' in norm
    if row.is_ammonia_world and gas: true_ammonia=None; statuses['true_ammonia_world']=_status('conflicting','canonical flag conflicts with gas-giant subtype',baseprov)
    else: true_ammonia=exact_ammonia; statuses['true_ammonia_world']=_status('known','exact canonical subtype identity',baseprov)
    b=BodyFact(row.id,base_id,nums['distance_ls'],land,tf,ring,geo,bio,volc,atm,nums['surface_temperature_k'],nums['gravity_g'],nums['radius_km'])
    prov=sorted_ids((baseprov,),hp,tuple(x for _,s in statuses.items() for x in s.provenance_ids))
    return ProjectedBodyEvidence(b,tuple(sorted(statuses.items())),true_ammonia,row.bio_signal_count,row.geo_signal_count,prov)
