from __future__ import annotations
from r1_finder_compare.types import CandidateEvidence,CapacityEvidence,RequirementEvidence
from .body_projection import project_body
from .provenance import canonical_system_provenance,sorted_ids
from .slot_prediction import predict_surface_slots
from .types import BodyEvidenceHints,CanonicalBodyRow,CanonicalRingRow,CanonicalSystemRow,ProjectedSystemEvidence
PROJECTION_REVISION='r1-evidence-bridge-2026-08-31.1'
def project_system(system:CanonicalSystemRow,bodies:tuple[CanonicalBodyRow,...],rings:tuple[CanonicalRingRow,...]=(),hints:tuple[BodyEvidenceHints,...]=()):
    hmap={h.body_id:h for h in hints}; projected=tuple(sorted((project_body(b,rings,hmap.get(b.id)) for b in bodies if b.system_id64==system.id64),key=lambda p:p.body.body_id))
    if not system.has_body_data: completeness='unknown'
    elif not projected: completeness='conflicting'
    elif system.body_count!=len(projected): completeness='conflicting'
    else: completeness='known_present'
    prov=sorted_ids((canonical_system_provenance(system),),tuple(x for p in projected for x in p.provenance_ids))
    return ProjectedSystemEvidence(system.id64,system.name,completeness,projected,prov,PROJECTION_REVISION)
def _is_extraction_source(p):
    ident=p.body.base_identity.casefold()
    return ident in ('high metal content world','metal-rich body','metal rich body') or p.body.has_rings is True or p.body.has_geologicals is True
def _is_refinery_source(p):
    ident=p.body.base_identity.casefold()
    return ident in ('rocky body','rocky ice world','rocky ice body','rocky-ice body')
def _req(eid,positive,complete,refs):
    if positive:return RequirementEvidence(eid,'sufficient',True,None,tuple(sorted(refs)),'known canonical source present')
    if complete:return RequirementEvidence(eid,'sufficient',False,None,tuple(sorted(refs)),'complete canonical body inventory contains no known source')
    return RequirementEvidence(eid,'partial',None,None,tuple(sorted(refs)),'source absence cannot be established from incomplete inventory')
def project_candidate(system_ev:ProjectedSystemEvidence):
    complete=system_ev.body_data_completeness=='known_present'; ext=[p for p in system_ev.bodies if _is_extraction_source(p)]; ref=[p for p in system_ev.bodies if _is_refinery_source(p)]
    extrefs=tuple(x for p in ext for x in p.provenance_ids); refrefs=tuple(x for p in ref for x in p.provenance_ids)
    preds=[predict_surface_slots(p) for p in system_ev.bodies]
    all_slots_known=bool(preds) and all(p.availability=='known_prediction' for p in preds)
    cap_disposition='sufficient' if all_slots_known else 'partial'
    cap=CapacityEvidence(f'bridge-cap:{system_ev.system_id64}',cap_disposition,None,None,None,())
    overall='sufficient' if complete and all_slots_known else 'partial'
    return CandidateEvidence(
        fixture_id=f'bridge:{system_ev.system_id64}',fixture_revision=system_ev.projection_revision,system_id64=system_ev.system_id64,system_name=system_ev.system_name,distance_ly=None,
        bodies=tuple(p.body for p in system_ev.bodies),physical_capacity=cap,
        extraction_evidence=_req(f'bridge-ext:{system_ev.system_id64}',bool(ext),complete,extrefs),
        refinery_evidence=_req(f'bridge-ref:{system_ev.system_id64}',bool(ref),complete,refrefs),
        logistics_no_carrier=None,logistics_carrier=None,evidence_disposition=overall,
        ambiguity_flags=(),conflict_flags=('body_data_conflict',) if system_ev.body_data_completeness=='conflicting' else (),provenance_ids=system_ev.provenance_ids,
    )
