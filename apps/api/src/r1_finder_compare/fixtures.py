from __future__ import annotations

from .programmes import PROGRAMME_ID, TEMPLATE_REVISION
from .types import (
    AllocationClaim,
    BodyFact,
    CandidateEvidence,
    CandidateProgrammePlan,
    CapacityEvidence,
    RequirementEvidence,
)


def body(
    body_id: str,
    identity: str,
    *,
    distance_ls: float,
    rings: bool = False,
    geo: bool = False,
    landable: bool = True,
) -> BodyFact:
    return BodyFact(
        body_id=body_id,
        base_identity=identity,
        distance_ls=distance_ls,
        is_landable=landable,
        is_terraformable=False,
        has_rings=rings,
        has_geologicals=geo,
        has_biologicals=False,
        volcanism='Minor Metallic Magma' if geo else None,
        atmosphere='No atmosphere',
        surface_temperature_k=280.0,
        gravity_g=0.8,
        radius_km=3200.0,
    )


def req(eid: str, support: float, *, satisfied: bool = True, disposition: str = 'sufficient') -> RequirementEvidence:
    return RequirementEvidence(
        evidence_id=eid,
        disposition=disposition,  # type: ignore[arg-type]
        satisfied=satisfied,
        support=support,
        evidence_refs=(eid,),
    )


def cap(
    eid: str,
    support: float,
    reserve: str,
    *,
    sufficient: bool = True,
    disposition: str = 'sufficient',
    duplicate: bool = False,
) -> CapacityEvidence:
    allocations = (
        AllocationClaim('alloc-extraction', 'slot-A', 'hub-er'),
        AllocationClaim('alloc-refinery', 'slot-A' if duplicate else 'slot-B', 'hub-er'),
    )
    return CapacityEvidence(
        evidence_id=eid,
        disposition=disposition,  # type: ignore[arg-type]
        sufficient=sufficient,
        usable_capacity=support,
        reserve_capacity=reserve,  # type: ignore[arg-type]
        allocations=allocations,
    )


CANDIDATES: tuple[CandidateEvidence, ...] = (
    CandidateEvidence(
        fixture_id='compact_extraction_specialist', fixture_revision='1', system_id64='1001',
        system_name='Compact Prospect', distance_ly=12.0,
        bodies=(body('c1', 'High metal content world', distance_ls=600), body('c2', 'Metal-rich body', distance_ls=900), body('c3', 'Rocky body', distance_ls=1200, rings=True)),
        physical_capacity=cap('cap-compact', 0.95, 'resilient'),
        extraction_evidence=req('ext-compact', 1.0), refinery_evidence=req('ref-compact', 0.92),
        logistics_no_carrier='compact', logistics_carrier='compact',
        evidence_disposition='sufficient', ambiguity_flags=(), conflict_flags=(), provenance_ids=('fixture:compact:1',),
    ),
    CandidateEvidence(
        fixture_id='remote_extraction_abundance', fixture_revision='1', system_id64='1002',
        system_name='Far Abundance', distance_ly=35.0,
        bodies=tuple(body(f'r{i}', 'High metal content world' if i < 5 else 'Metal-rich body', distance_ls=110000 + i * 5000, geo=i % 2 == 0) for i in range(1, 8)),
        physical_capacity=cap('cap-remote', 1.0, 'expandable'),
        extraction_evidence=req('ext-remote', 1.0), refinery_evidence=req('ref-remote', 0.95),
        logistics_no_carrier='extreme', logistics_carrier='moderate',
        evidence_disposition='sufficient', ambiguity_flags=(), conflict_flags=(), provenance_ids=('fixture:remote:1',),
    ),
    CandidateEvidence(
        fixture_id='geo_hmc_composable', fixture_revision='1', system_id64='1003',
        system_name='Geo HMC', distance_ly=18.0,
        bodies=(body('g1', 'High metal content world', distance_ls=1800, geo=True), body('g2', 'Rocky body', distance_ls=2200, rings=True)),
        physical_capacity=cap('cap-geo', 1.0, 'sufficient'),
        extraction_evidence=req('ext-geo', 0.93), refinery_evidence=req('ref-geo', 0.70),
        logistics_no_carrier='compact', logistics_carrier='compact',
        evidence_disposition='sufficient', ambiguity_flags=(), conflict_flags=(), provenance_ids=('fixture:geo:1',),
    ),
    CandidateEvidence(
        fixture_id='refinery_heavy_weak_extraction', fixture_revision='1', system_id64='1004',
        system_name='Refinery First', distance_ly=6.0,
        bodies=(body('f1', 'Rocky body', distance_ls=500), body('f2', 'Rocky body', distance_ls=700), body('f3', 'Rocky body', distance_ls=900)),
        physical_capacity=cap('cap-refinery', 0.9, 'resilient'),
        extraction_evidence=req('ext-refinery', 0.25, satisfied=False), refinery_evidence=req('ref-refinery', 1.0),
        logistics_no_carrier='compact', logistics_carrier='compact',
        evidence_disposition='sufficient', ambiguity_flags=(), conflict_flags=(), provenance_ids=('fixture:refinery:1',),
    ),
    CandidateEvidence(
        fixture_id='incomplete_material_evidence', fixture_revision='1', system_id64='1005',
        system_name='Incomplete Promise', distance_ly=9.0,
        bodies=(body('i1', 'High metal content world', distance_ls=1000), body('i2', 'Rocky body', distance_ls=1300, rings=True)),
        physical_capacity=cap('cap-incomplete', 0.9, 'sufficient', disposition='missing'),
        extraction_evidence=req('ext-incomplete', 0.9), refinery_evidence=req('ref-incomplete', 0.9),
        logistics_no_carrier=None, logistics_carrier=None,
        evidence_disposition='conflicting', ambiguity_flags=('capacity_unknown',), conflict_flags=('pair_conflict',), provenance_ids=('fixture:incomplete:1',),
    ),
    CandidateEvidence(
        fixture_id='plateau_sufficient_30', fixture_revision='1', system_id64='1006',
        system_name='Plateau Thirty', distance_ly=14.0,
        bodies=(body('p30-1', 'High metal content world', distance_ls=800), body('p30-2', 'Metal-rich body', distance_ls=1000), body('p30-3', 'Rocky body', distance_ls=1200, rings=True)),
        physical_capacity=cap('cap-p30', 1.0, 'sufficient'),
        extraction_evidence=req('ext-p30', 1.0), refinery_evidence=req('ref-p30', 1.0),
        logistics_no_carrier='moderate', logistics_carrier='compact',
        evidence_disposition='sufficient', ambiguity_flags=(), conflict_flags=(), provenance_ids=('fixture:p30:1',),
    ),
    CandidateEvidence(
        fixture_id='plateau_surplus_60', fixture_revision='1', system_id64='1007',
        system_name='Plateau Sixty', distance_ly=15.0,
        bodies=(
            body('p60-1', 'High metal content world', distance_ls=800), body('p60-2', 'Metal-rich body', distance_ls=1000), body('p60-3', 'Rocky body', distance_ls=1200, rings=True),
            *tuple(body(f'p60-x{i}', 'Icy body', distance_ls=2000 + i * 100) for i in range(20)),
        ),
        physical_capacity=cap('cap-p60', 1.0, 'expandable'),
        extraction_evidence=req('ext-p60', 1.0), refinery_evidence=req('ref-p60', 1.0),
        logistics_no_carrier='moderate', logistics_carrier='compact',
        evidence_disposition='sufficient', ambiguity_flags=(), conflict_flags=(), provenance_ids=('fixture:p60:1',),
    ),
)


def _plan(resilience: str, *refs: str) -> CandidateProgrammePlan:
    return CandidateProgrammePlan(
        programme_id=PROGRAMME_ID,
        template_revision=TEMPLATE_REVISION,
        pair_resilience=resilience,  # type: ignore[arg-type]
        allocation_trace_ids=('alloc-extraction', 'alloc-refinery'),
        resilience_evidence_refs=tuple(sorted(refs)),
    )


P_ER_01_PLANS: dict[str, CandidateProgrammePlan] = {
    'compact_extraction_specialist': _plan('robust', 'plan:compact:pair'),
    'remote_extraction_abundance': _plan('robust', 'plan:remote:pair'),
    'geo_hmc_composable': _plan('robust', 'plan:geo:pair'),
    'refinery_heavy_weak_extraction': _plan('mixed', 'plan:refinery:pair'),
    'incomplete_material_evidence': _plan('unknown', 'plan:incomplete:pair'),
    'plateau_sufficient_30': _plan('robust', 'plan:p30:pair'),
    'plateau_surplus_60': _plan('robust', 'plan:p60:pair'),
}


def get_candidate(fixture_id: str) -> CandidateEvidence:
    for candidate in CANDIDATES:
        if candidate.fixture_id == fixture_id:
            return candidate
    raise KeyError(fixture_id)


def get_p_er_01_plan(fixture_id: str) -> CandidateProgrammePlan:
    try:
        return P_ER_01_PLANS[fixture_id]
    except KeyError as exc:
        raise KeyError(f'no P-ER-01 plan fixture for {fixture_id}') from exc
