from dataclasses import replace
from pathlib import Path
from r1_evidence_bridge.body_projection import project_body
from r1_evidence_bridge.candidate_projection import project_candidate,project_system
from r1_evidence_bridge.fixtures import body,hint,ring,system
from r1_evidence_bridge.slot_prediction import predict_orbital_capacity,predict_surface_slots
from r1_finder_compare.evaluator import evaluate_p_er_01
from r1_finder_compare.types import CandidateProgrammePlan

def st(p,n): return p.status(n).availability
def known_hints(bid='b1'): return hint(bid,geo_signal_scan_complete=True,bio_signal_scan_complete=True,terraformable_negative_confirmed=True)
def test_geo_hmc_projects_composable_identity_and_modifier():
    p=project_body(body(geo_signal_count=2),hints=known_hints()); assert p.body.base_identity=='High metal content world' and p.body.has_geologicals is True
def test_ringed_geo_rocky_keeps_identity_ring_and_geo_separate():
    p=project_body(body(subtype='Rocky body',geo_signal_count=1),rings=(ring(),),hints=known_hints()); assert p.body.base_identity=='Rocky body' and p.body.has_rings and p.body.has_geologicals
def test_terraformable_true_survives_projection(): assert project_body(body(terraforming_state='Terraformable',is_terraformable=True),hints=known_hints()).body.is_terraformable is True
def test_terraformable_false_without_source_confirmation_is_unknown():
    p=project_body(body(terraforming_state=None,is_terraformable=False)); assert p.body.is_terraformable is None and st(p,'is_terraformable')=='unknown'
def test_landable_false_without_source_confirmation_is_unknown():
    p=project_body(body(is_landable=False)); assert p.body.is_landable is None and st(p,'is_landable')=='unknown'
def test_zero_geo_without_complete_scan_is_unknown(): assert project_body(body(geo_signal_count=0)).body.has_geologicals is None
def test_zero_geo_with_complete_scan_is_known_negative(): assert project_body(body(geo_signal_count=0),hints=hint(geo_signal_scan_complete=True)).body.has_geologicals is False
def test_zero_bio_without_complete_scan_is_unknown(): assert project_body(body(bio_signal_count=0)).body.has_biologicals is None
def test_volcanism_does_not_imply_geologicals():
    p=project_body(body(volcanism='Minor Metallic Magma',geo_signal_count=0)); assert p.body.has_geologicals is None
def test_true_ammonia_world_requires_exact_identity(): assert project_body(body(subtype='Ammonia world',is_ammonia_world=True)).true_ammonia_world is True
def test_ammonia_life_gas_giant_is_not_true_ammonia_world(): assert project_body(body(subtype='Gas giant with ammonia-based life')).true_ammonia_world is False
def test_conflicting_ammonia_flag_and_subtype_withholds_true_identity():
    p=project_body(body(subtype='Gas giant with ammonia-based life',is_ammonia_world=True)); assert p.true_ammonia_world is None and st(p,'true_ammonia_world')=='conflicting'
def test_local_matched_ring_row_is_known_positive(): assert project_body(body(),rings=(ring(),)).body.has_rings is True
def test_missing_ring_rows_are_unknown_not_false(): assert project_body(body()).body.has_rings is None
def test_conflicting_ring_row_is_conflicting():
    p=project_body(body(),rings=(ring(status='conflict'),)); assert p.body.has_rings is None and st(p,'has_rings')=='conflicting'
def test_no_body_data_is_unknown_not_zero_complete(): assert project_system(system(has=False,count=0),()).body_data_completeness=='unknown'
def test_has_body_data_true_with_zero_rows_is_conflicting(): assert project_system(system(has=True,count=1),()).body_data_completeness=='conflicting'
def _slot_body(**kw):
    b=body(**kw); h=known_hints(); return project_body(b,hints=h)
def test_surface_slot_unknown_if_required_input_unknown(): assert predict_surface_slots(project_body(body(atmosphere_type=None),hints=known_hints())).availability=='unknown'
def test_surface_slot_threshold_700_k_is_allowed(): assert predict_surface_slots(_slot_body(surface_temp=700.0)).slots>0
def test_surface_slot_threshold_2_7_g_is_allowed(): assert predict_surface_slots(_slot_body(gravity=2.7)).slots>0
def test_surface_slot_radius_boundaries_1500_3750_6000():
    vals=[predict_surface_slots(_slot_body(radius=r)).slots for r in (1499,1500,3749,3750,5999,6000)]; assert vals==[2,3,3,4,4,5]
def test_surface_slot_modifiers_are_independent_and_cap_at_7():
    p=_slot_body(radius=6000,terraforming_state='Terraformable',is_terraformable=True,geo_signal_count=1,volcanism='Minor Metallic Magma',atmosphere_type='Thin atmosphere'); assert predict_surface_slots(p).slots==7
def test_surface_slot_geo_and_volcanism_together_add_only_one():
    a=predict_surface_slots(_slot_body(geo_signal_count=1,volcanism='No volcanism')).slots; b=predict_surface_slots(_slot_body(geo_signal_count=1,volcanism='Minor Metallic Magma')).slots; assert a==b
def test_surface_slot_prediction_is_labelled_prediction_not_observation(): assert predict_surface_slots(_slot_body()).evidence_class=='prediction'
def test_gas_giant_orbital_capacity_is_one(): assert predict_orbital_capacity(project_body(body(subtype='Class I gas giant'))).slots==1
def test_non_gas_giant_orbital_capacity_remains_unknown_in_first_slice(): assert predict_orbital_capacity(project_body(body(subtype='Rocky body'))).availability=='unknown'
def test_candidate_projection_has_no_plan_pair_resilience():
    s=project_system(system(),(body(),),hints=(known_hints(),)); c=project_candidate(s); assert not hasattr(c,'pair_stability') and not hasattr(c,'pair_resilience')
def test_bridge_does_not_construct_candidate_programme_plan():
    c=project_candidate(project_system(system(),(body(),),hints=(known_hints(),))); assert c.__class__.__name__=='CandidateEvidence'
def test_candidate_projection_does_not_invent_numeric_support():
    c=project_candidate(project_system(system(),(body(),),hints=(known_hints(),))); assert c.extraction_evidence.support is None and c.refinery_evidence.support is None
def test_downstream_candidate_evidence_shape_is_compatible(): project_candidate(project_system(system(),(body(),),hints=(known_hints(),)))
def test_external_unknown_plan_keeps_downstream_p_er_not_assessable():
    c=project_candidate(project_system(system(),(body(),),hints=(known_hints(),))); p=CandidateProgrammePlan('P-ER-01','p-er-01-finder-proof-2026-08-31.1','unknown',()); assert evaluate_p_er_01(c,p,'no_carrier',None).state=='not_assessable'
def test_projection_is_deterministic():
    args=(system(),(body(),)); assert project_system(*args,hints=(known_hints(),))==project_system(*args,hints=(known_hints(),))
def test_source_boundary_has_no_db_network_or_legacy_scorer_imports():
    root=Path(__file__).resolve().parents[1]/'apps'/'api'/'src'/'r1_evidence_bridge'; forbidden=('asyncpg','psycopg','redis','fastapi','requests','httpx','build_ratings','build_topology','build_archetype_scores','local_search','search_economies')
    for p in root.glob('*.py'):
        t=p.read_text().lower()
        for x in forbidden: assert x not in t
