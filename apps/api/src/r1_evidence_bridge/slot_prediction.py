from .types import OrbitalCapacityPrediction,ProjectedBodyEvidence,SlotPrediction
MODEL='surface_slots_nyatto_raven_family'; REV='community-validated-2026-08-31.1'; CAVEAT='Observed validation has two historical +1 residuals; no correction rule is inferred.'
def _present_text(v,no_marker):
    if v is None:return None
    return v.strip().casefold()!=no_marker
def predict_surface_slots(p:ProjectedBodyEvidence):
    names=('is_landable','surface_temperature_k','gravity_g','radius_km','is_terraformable','has_geologicals','volcanism','atmosphere')
    st={n:p.status(n).availability for n in names}; inputs=tuple(sorted(st.items()))
    if any(v!='known' for v in st.values()):return SlotPrediction('unknown',None,MODEL,REV,'prediction',inputs,(CAVEAT,))
    b=p.body; volc=_present_text(b.volcanism,'no volcanism'); atm=_present_text(b.atmosphere,'no atmosphere')
    if b.is_landable is False or b.surface_temperature_k>700 or b.gravity_g>2.7:return SlotPrediction('known_prediction',0,MODEL,REV,'prediction',inputs,(CAVEAT,))
    r=b.radius_km; slots=1 if r<1500 else 2 if r<3750 else 3 if r<6000 else 4
    if b.base_identity.casefold()=='high metal content world':slots+=1
    if b.is_terraformable:slots+=1
    if b.has_geologicals or volc:slots+=1
    if atm:slots+=2
    return SlotPrediction('known_prediction',min(slots,7),MODEL,REV,'prediction',inputs,(CAVEAT,))
def predict_orbital_capacity(p:ProjectedBodyEvidence):
    if 'gas giant' in p.body.base_identity.casefold():return OrbitalCapacityPrediction('known_prediction',1,'orbital_gas_giant_current','post-operations-2026-07-01.1','prediction',())
    return OrbitalCapacityPrediction('unknown',None,'orbital_capacity_first_slice','post-operations-2026-07-01.1','prediction',('Only gas-giant capacity is promoted in this slice.',))
