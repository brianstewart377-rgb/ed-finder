"""V3 planner catalogue, stateless evaluation and canonical body facts."""

from __future__ import annotations

from dataclasses import asdict
from functools import cache
from typing import Literal

import asyncpg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from edfinder_api.config import limiter
from edfinder_api.cpe import RULEBOOK_RELEASE, Body, Plan, Site, evaluate_plan
from edfinder_api.cpe.budget import _cost
from edfinder_api.cpe.catalogue import planner_facilities, prerequisites_for
from edfinder_api.cpe.explain import explain_rule
from edfinder_api.cpe.plan import PlanInvalid
from edfinder_api.deps import get_readonly_pool
from edfinder_api.mechanics.cp_rules import escalating_port_tier
from edfinder_api.routers.v3 import (
    SystemId,
    _bounded,
    _numeric_system_id,
    current_canonical_generation,
)

router = APIRouter(prefix="/api/v1/plan", tags=["v3-plan"])


class PlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PlanFacilityV1(PlanModel):
    id: str
    name: str
    category: str
    tier: int
    allowed_location: str
    economy: str | None
    is_port: bool
    escalating_port_tier: int | None
    yellow_cp_cost: int
    green_cp_cost: int
    yellow_cp_generated: int
    green_cp_generated: int
    prerequisites: list[list[str]]
    rule_ids: list[str]


class PlanCatalogueV1(PlanModel):
    rulebook_release: str
    facilities: list[PlanFacilityV1]


class PlanSystemBodyV1(PlanModel):
    body_id: str
    name: str
    direct_parent_body_id: str | None
    body_type: str | None
    is_main_star: bool | None
    is_landable: bool | None
    radius_km: float | None
    surface_gravity_g: float | None
    surface_temperature_k: float | None
    atmosphere: str | None
    terraforming_state: str | None
    volcanism: str | None
    distance_from_arrival_ls: float | None
    has_rings: bool
    geological_signals: int
    biological_signals: int
    signals_complete: bool | None
    lifecycle_state: str


class PlanBodiesV1(PlanModel):
    generation_id: str
    publication_sequence: str
    system_id64: str
    bodies: list[PlanSystemBodyV1]


class PlanBodyV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body_ref: str = Field(min_length=1, max_length=64, strict=True)
    orbital_slots: int | None = Field(default=None, ge=0, le=64, strict=True)
    surface_slots: int | None = Field(default=None, ge=0, le=64, strict=True)
    is_landable: bool | None = Field(default=None, strict=True)
    is_ringed: bool | None = Field(default=None, strict=True)


class PlanSiteV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: str = Field(min_length=1, max_length=64, strict=True)
    facility_id: str = Field(min_length=1, max_length=64, strict=True)
    body_ref: str | None = Field(default=None, min_length=1, max_length=64, strict=True)
    slot_kind: Literal["orbital", "surface"]
    status: Literal["planned", "building", "complete", "demolished"]
    name: str | None = Field(default=None, max_length=64, strict=True)


class PlanRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_id64: str = Field(pattern=r"^[0-9]{1,19}$", strict=True)
    bodies: list[PlanBodyV1] = Field(default_factory=list, max_length=1000)
    sites: list[PlanSiteV1] = Field(min_length=1, max_length=300)


class PlanTotalsV1(PlanModel):
    t2: int
    t3: int


class PlanStepV1(PlanModel):
    site_id: str
    facility_id: str
    status: str
    view: Literal["now", "after_plan", "ignored"]
    result: Literal["OK", "BLOCKED", "NEEDS_INFO", "COUNTED", "IGNORED"]
    counted_port_number: int | None
    cost_t2: int
    cost_t3: int
    reward_t2: int
    reward_t3: int
    t2_before: int
    t3_before: int
    t2_after: int
    t3_after: int
    reasons: list[str]
    rule_ids: list[str]
    payers: list[str]


class PlanCheckV1(PlanModel):
    code: str
    message: str
    rule_ids: list[str]


class PlanSummaryV1(PlanModel):
    OK: int
    BLOCKED: int
    NEEDS_INFO: int
    COUNTED: int
    IGNORED: int


class PlanRuleExplanationV1(PlanModel):
    id: str
    title: str
    status: str
    statement: str
    quote: str
    page: int | None


class PlanEvaluationV1(PlanModel):
    rulebook_release: str
    system_id64: str
    now: PlanTotalsV1
    after_plan: PlanTotalsV1
    next_port_cost: PlanTotalsV1
    steps: list[PlanStepV1]
    plan_checks: list[PlanCheckV1]
    summary: PlanSummaryV1
    explanations: dict[str, PlanRuleExplanationV1]


class PlanIssueV1(PlanModel):
    code: str
    site_id: str | None
    message: str


class PlanInvalidV1(PlanModel):
    error: Literal["plan_invalid"]
    issues: list[PlanIssueV1]


@cache
def _catalogue_response() -> PlanCatalogueV1:
    return PlanCatalogueV1(
        rulebook_release=RULEBOOK_RELEASE,
        facilities=[
            PlanFacilityV1(
                id=template.id,
                name=template.name,
                category=template.category,
                tier=template.tier,
                allowed_location=template.allowed_location,
                economy=template.economy,
                is_port=template.is_port,
                escalating_port_tier=escalating_port_tier(template),
                yellow_cp_cost=template.yellow_cp_cost,
                green_cp_cost=template.green_cp_cost,
                yellow_cp_generated=template.yellow_cp_generated,
                green_cp_generated=template.green_cp_generated,
                prerequisites=[sorted(entry) for entry in prerequisites_for(template.id)],
                # The first non-primary port's position affects its cost, but
                # never its citations. Reuse the evaluator's citation source.
                rule_ids=list(_cost(template, False, 1)[2]),
            )
            for _, template in sorted(planner_facilities().items())
        ],
    )


@router.get("/catalogue", response_model=PlanCatalogueV1, operation_id="getV3PlanCatalogue")
async def get_catalogue() -> PlanCatalogueV1:
    return _catalogue_response()


@router.get(
    "/systems/{system_id}/bodies",
    response_model=PlanBodiesV1,
    operation_id="listV3PlanBodies",
)
async def bodies(
    system_id: SystemId, pool: asyncpg.Pool = Depends(get_readonly_pool),
) -> PlanBodiesV1:
    numeric_id = _numeric_system_id(system_id)
    schema, generation = await current_canonical_generation(pool)
    rows = await _bounded(pool.fetch(
        f"""SELECT body.body_pk,body.name,body.direct_parent_body_pk,
                   body_type.public_code AS body_type,body.is_main_star,body.is_landable,
                   body.radius_km,body.surface_gravity_g,body.surface_temperature_k,
                   atmosphere.display_name AS atmosphere,
                   terraforming.display_name AS terraforming_state,
                   volcanism.display_name AS volcanism,body.distance_from_arrival_ls,
                   body.signals_complete,body.lifecycle_state
              FROM {schema}.bodies body
              LEFT JOIN v3_vocab.body_type body_type USING(body_type_id)
              LEFT JOIN v3_vocab.atmosphere_classification atmosphere
                     USING(atmosphere_classification_id)
              LEFT JOIN v3_vocab.terraforming_state terraforming USING(terraforming_state_id)
              LEFT JOIN v3_vocab.volcanism_type volcanism USING(volcanism_type_id)
             WHERE body.system_id64=$1 ORDER BY body.body_pk""",
        numeric_id,
    ))
    ring_rows = await _bounded(pool.fetch(
        f"""SELECT ring.body_pk
              FROM {schema}.rings ring
             WHERE ring.system_id64=$1 AND ring.kind='RING'
             GROUP BY ring.body_pk""",
        numeric_id,
    ))
    signal_rows = await _bounded(pool.fetch(
        f"""SELECT signal.body_pk,
                   COALESCE(SUM(signal.signal_count) FILTER
                       (WHERE signal_type.display_name='Geological'),0) AS geological_signals,
                   COALESCE(SUM(signal.signal_count) FILTER
                       (WHERE signal_type.display_name='Biological'),0) AS biological_signals
              FROM {schema}.body_signal_current signal
              JOIN {schema}.bodies body USING(body_pk)
              JOIN v3_vocab.signal_type signal_type USING(signal_type_id)
             WHERE body.system_id64=$1
               AND signal_type.display_name IN ('Geological','Biological')
             GROUP BY signal.body_pk""",
        numeric_id,
    ))
    ringed_bodies = {row["body_pk"] for row in ring_rows}
    signals_by_body = {row["body_pk"]: row for row in signal_rows}
    result = []
    for row in rows:
        signal = signals_by_body.get(row["body_pk"])
        result.append(PlanSystemBodyV1(
            body_id=str(row["body_pk"]),
            name=row["name"],
            direct_parent_body_id=(
                str(row["direct_parent_body_pk"])
                if row["direct_parent_body_pk"] is not None else None
            ),
            body_type=row["body_type"],
            is_main_star=row["is_main_star"],
            is_landable=row["is_landable"],
            radius_km=row["radius_km"],
            surface_gravity_g=row["surface_gravity_g"],
            surface_temperature_k=row["surface_temperature_k"],
            atmosphere=row["atmosphere"],
            terraforming_state=row["terraforming_state"],
            volcanism=row["volcanism"],
            distance_from_arrival_ls=row["distance_from_arrival_ls"],
            has_rings=row["body_pk"] in ringed_bodies,
            geological_signals=signal["geological_signals"] if signal else 0,
            biological_signals=signal["biological_signals"] if signal else 0,
            signals_complete=row["signals_complete"],
            lifecycle_state=row["lifecycle_state"],
        ))
    return PlanBodiesV1(
        generation_id=generation.generation_id,
        publication_sequence=generation.publication_sequence,
        system_id64=system_id,
        bodies=result,
    )


@router.post(
    "/evaluate",
    response_model=PlanEvaluationV1,
    operation_id="evaluateV3Plan",
    # A plan that is well-formed JSON but breaks a planner rule is a 400 with
    # PlanInvalidV1; FastAPI keeps 422 (HTTPValidationError) for malformed
    # bodies, so the OpenAPI contract describes both shapes accurately.
    responses={400: {"model": PlanInvalidV1}},
)
@limiter.limit("60/minute")
async def evaluate(request: Request, body: PlanRequestV1) -> PlanEvaluationV1 | JSONResponse:
    plan = Plan(
        system_id64=int(body.system_id64),
        bodies=tuple(Body(**item.model_dump()) for item in body.bodies),
        sites=tuple(Site(**item.model_dump()) for item in body.sites),
    )
    try:
        evaluation = evaluate_plan(plan)
    except PlanInvalid as exc:
        invalid = PlanInvalidV1(
            error="plan_invalid",
            issues=[PlanIssueV1(**asdict(issue)) for issue in exc.issues],
        )
        return JSONResponse(status_code=400, content=invalid.model_dump())

    cited = {
        rule_id
        for item in (*evaluation.steps, *evaluation.plan_checks)
        for rule_id in item.rule_ids
    }
    return PlanEvaluationV1(
        rulebook_release=evaluation.rulebook_release,
        system_id64=body.system_id64,
        now=PlanTotalsV1(**asdict(evaluation.now)),
        after_plan=PlanTotalsV1(**asdict(evaluation.after_plan)),
        next_port_cost=PlanTotalsV1(**asdict(evaluation.next_port_cost)),
        steps=[
            PlanStepV1(**{
                **asdict(step),
                "reasons": list(step.reasons),
                "rule_ids": list(step.rule_ids),
                "payers": list(step.payers),
            })
            for step in evaluation.steps
        ],
        plan_checks=[
            PlanCheckV1(code=check.code, message=check.message, rule_ids=list(check.rule_ids))
            for check in evaluation.plan_checks
        ],
        summary=PlanSummaryV1(**evaluation.summary),
        explanations={
            rule_id: PlanRuleExplanationV1(**explain_rule(rule_id))
            for rule_id in sorted(cited)
        },
    )
