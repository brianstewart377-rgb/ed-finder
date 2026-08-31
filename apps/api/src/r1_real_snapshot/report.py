from collections import Counter
from .types import SnapshotReport
from r1_evidence_bridge.slot_prediction import predict_orbital_capacity,predict_surface_slots
def build_report(bundle):
    counts=Counter(status.availability for p in bundle.projected_system.bodies for _,status in p.field_status)
    slots=[predict_surface_slots(p) for p in bundle.projected_system.bodies]; known=sum(x.availability=='known_prediction' for x in slots); unknown=len(slots)-known
    gg=tuple(sorted((p.body.body_id,predict_orbital_capacity(p).slots) for p in bundle.projected_system.bodies if predict_orbital_capacity(p).availability=='known_prediction'))
    caveats=[]
    if bundle.projected_system.body_data_completeness!='known_present': caveats.append('body inventory is not confirmed complete')
    if unknown:caveats.append(f'{unknown} body slot predictions remain Unknown')
    return SnapshotReport(bundle.system.id64,bundle.system.name,bundle.projected_system.body_data_completeness,bundle.system.body_count,len(bundle.bodies),tuple(sorted(counts.items())),known,unknown,gg,bundle.candidate.extraction_evidence.satisfied,bundle.candidate.extraction_evidence.disposition,bundle.candidate.refinery_evidence.satisfied,bundle.candidate.refinery_evidence.disposition,bundle.snapshot_digest,tuple(caveats))
