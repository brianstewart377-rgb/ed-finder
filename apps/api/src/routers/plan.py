"""Database-free V3 planner catalogue and stateless budget evaluation."""

from __future__ import annotations

from dataclasses import asdict
from functools import cache
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from edfinder_api.config import limiter
from edfinder_api.cpe import RULEBOOK_RELEASE, Body, Plan, Site, evaluate_plan
from edfinder_api.cpe.budget import _cost
from edfinder_api.cpe.catalogue import planner_facilities, prerequisites_for
from edfinder_api.cpe.explain import explain_rule
from edfinder_api.cpe.plan import PlanInvalid
from edfinder_api.mechanics.cp_rules import escalating_port_tier

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


@router.post(
    "/evaluate",
    response_model=PlanEvaluationV1,
    operation_id="evaluateV3Plan",
    responses={422: {"model": PlanInvalidV1}},
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
        return JSONResponse(status_code=422, content=invalid.model_dump())

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
