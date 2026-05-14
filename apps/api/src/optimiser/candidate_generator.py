"""Bounded deterministic Stage 5A optimiser candidate generation."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Optional

import asyncpg

from domain.colonisation_rules import BodyEconomyProfile, profile_body
from domain.facilities import FacilityTemplate
from optimiser.archetype_rules import ArchetypeRule, resolve_archetype_rule
from optimiser.dedupe import dedupe_candidates, placement_fingerprint
from optimiser.facility_selection import (
    find_service_unlock_support,
    find_support_by_economy,
    select_port_template,
    select_support_templates,
)
from optimiser.models import (
    CandidateGenerationRequest,
    CandidateGenerationResult,
    CandidatePlacement,
    OptimiserCandidate,
    candidate_placement_to_preview_placement,
)
from optimiser.preview_summary import preview_summary_from_response
from simulation.build_preview import PreviewContext, simulate_build_preview

PreviewRunner = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class BodyAnchor:
    body_id: Optional[str]
    body_name: str
    profile: Optional[BodyEconomyProfile]
    score: float
    rationale: list[str]
    tags: list[str]


async def generate_candidates(
    request: CandidateGenerationRequest,
    catalogue: dict[str, FacilityTemplate],
    pool: asyncpg.Pool,
    *,
    preview_runner: PreviewRunner = simulate_build_preview,
) -> CandidateGenerationResult:
    rule, warnings = resolve_archetype_rule(request.target_archetype)
    context, body_rows = await _get_preview_context_and_body_rows(pool, request.system_id64)
    assumptions = [
        'Stage 5A generates bounded heuristic candidates only; Simulation Preview remains the source of truth.',
    ]

    if not catalogue:
        return CandidateGenerationResult(
            system_id64=request.system_id64,
            target_archetype=rule.key,
            candidate_count=0,
            candidates=[],
            warnings=[*warnings, 'No facility catalogue is available for candidate generation.'],
            assumptions=assumptions,
        )

    anchors = _select_body_anchors(
        rows=body_rows,
        rule=rule,
        preferred_body_ids=request.preferred_body_ids,
        limit=max(1, request.max_candidates * 2),
    )
    if not anchors:
        anchors = [BodyAnchor(None, 'system-level plan', None, 0.0, ['No body data is available; generated a system-level candidate.'], ['no_body_data'])]
        warnings.append('No body data available; generated system-level candidates only.')

    candidates: list[OptimiserCandidate] = []
    seen_fingerprints: set[tuple[tuple[str, str | None, bool, int], ...]] = set()

    for anchor in anchors:
        for strategy in rule.strategies:
            candidate = _build_candidate(
                rule=rule,
                strategy=strategy,
                anchor=anchor,
                catalogue=catalogue,
                allow_estimated_data=request.allow_estimated_data,
            )
            if candidate is None:
                continue

            fingerprint = placement_fingerprint(candidate.placements)
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)

            if request.run_preview:
                candidate = _attach_preview_summary(
                    candidate=candidate,
                    request=request,
                    catalogue=catalogue,
                    base_context=context,
                    anchor=anchor,
                    preview_runner=preview_runner,
                )

            candidates.append(candidate)
            if len(candidates) >= max(0, request.max_candidates):
                break
        if len(candidates) >= max(0, request.max_candidates):
            break

    candidates = dedupe_candidates(candidates)[:max(0, request.max_candidates)]
    return CandidateGenerationResult(
        system_id64=request.system_id64,
        target_archetype=rule.key,
        candidate_count=len(candidates),
        candidates=candidates,
        warnings=warnings,
        assumptions=assumptions,
    )


async def _get_preview_context_and_body_rows(pool: asyncpg.Pool, system_id64: int) -> tuple[PreviewContext, list[dict[str, Any]]]:
    async with pool.acquire() as conn:
        system_row = await conn.fetchrow(
            """SELECT * FROM systems WHERE system_id64 = $1""",
            system_id64,
        )
        if not system_row:
            return PreviewContext(system_id64=system_id64), []

        body_rows = await conn.fetch(
            """SELECT * FROM bodies WHERE system_id64 = $1""",
            system_id64,
        )

    local_body_profiles: dict[str, dict[str, Any]] = {}
    clean_rows = [dict(row) for row in body_rows]
    for row in clean_rows:
        profile = profile_body(row)
        if profile.body_id:
            local_body_profiles[profile.body_id] = profile.to_context_profile()

    return PreviewContext(
        system_id64=system_id64,
        estimated_orbital_slots=system_row.get('estimated_orbital_slots'),
        estimated_ground_slots=system_row.get('estimated_ground_slots'),
        slot_confidence=system_row.get('slot_confidence'),
        has_ringed_body=system_row.get('has_ringed_body'),
        local_body_profiles=local_body_profiles,
        mechanics_notes=[],
        observed_facts=[],
    ), clean_rows


def _select_body_anchors(
    *,
    rows: list[dict[str, Any]],
    rule: ArchetypeRule,
    preferred_body_ids: list[str],
    limit: int,
) -> list[BodyAnchor]:
    preferred = {str(body_id) for body_id in preferred_body_ids}
    anchors: list[BodyAnchor] = []
    for row in rows:
        profile = profile_body(row)
        body_id = profile.body_id
        economies = set(profile.base_economies) | set(profile.modifier_economies)
        tags = set(profile.strategic_tags)
        rationale: list[str] = []
        score = profile.confidence + profile.purity

        economy_matches = [economy for economy in rule.expected_economies if economy in economies]
        if economy_matches:
            score += len(economy_matches) * 2.0
            rationale.append(f"Body supports target economies: {', '.join(economy_matches)}.")
        tag_matches = [tag for tag in rule.strategic_tags if tag in tags]
        if tag_matches:
            score += len(tag_matches)
            rationale.append(f"Body has target strategic tags: {', '.join(tag_matches)}.")
        avoid_matches = [economy for economy in rule.avoid_economies if economy in economies]
        if avoid_matches:
            score -= len(avoid_matches)
            rationale.append(f"Body includes non-target economies to watch: {', '.join(avoid_matches)}.")
        if body_id and body_id in preferred:
            score += 10.0
            rationale.append('Body was explicitly preferred in the request.')

        if not economy_matches and not tag_matches and not preferred:
            continue
        if preferred and body_id not in preferred:
            continue

        anchors.append(BodyAnchor(
            body_id=body_id,
            body_name=profile.body_name or f'Body {body_id or "unknown"}',
            profile=profile,
            score=round(score, 3),
            rationale=rationale or ['Body is available as a fallback anchor.'],
            tags=[*profile.strategic_tags, *profile.base_economies, *profile.modifier_economies],
        ))

    anchors.sort(key=lambda anchor: (-anchor.score, anchor.body_id or '', anchor.body_name))
    return anchors[:limit]


def _build_candidate(
    *,
    rule: ArchetypeRule,
    strategy: str,
    anchor: BodyAnchor,
    catalogue: dict[str, FacilityTemplate],
    allow_estimated_data: bool,
) -> Optional[OptimiserCandidate]:
    port = select_port_template(catalogue, strategy, allow_estimated_data=allow_estimated_data)
    if port is None:
        return None

    warnings: list[str] = []
    assumptions: list[str] = []
    tags = [strategy, rule.key, *anchor.tags]
    selected: list[FacilityTemplate] = [port]

    supports = select_support_templates(catalogue, rule, strategy, allow_estimated_data=allow_estimated_data)
    primary_supports = find_support_by_economy(catalogue, rule.primary_economies, allow_estimated_data=allow_estimated_data)

    if strategy == 'balanced':
        selected.extend(_unique_templates(supports[:2]))
        assumptions.append('Balanced strategy uses a compact port plus up to two target-economy supports.')
    elif strategy == 'pure':
        selected.extend(_unique_templates((primary_supports or supports)[:2]))
        assumptions.append('Pure strategy prioritises primary target-economy supports where catalogue data allows.')
    elif strategy == 'services_aware':
        selected.extend(_unique_templates(supports[:1]))
        service_support = find_service_unlock_support(catalogue, allow_estimated_data=allow_estimated_data)
        if service_support:
            selected.append(service_support)
            assumptions.append('Service-aware strategy includes an obvious unlock support; Simulation Preview validates actual effects.')
        else:
            warnings.append('No obvious service-unlocking support was available in the catalogue.')
    elif strategy == 'low_cp':
        selected.extend(_unique_templates(supports[:1]))
        assumptions.append('Low-CP strategy minimises candidate size and favours lower CP-cost templates.')
    elif strategy == 'flexible_multirole':
        selected.extend(_unique_templates(supports[:3]))
        assumptions.append('Flexible multirole strategy samples broad support options without exhaustive search.')
    else:
        return None

    selected = _unique_templates(selected)
    if len(selected) == 1:
        warnings.append('No matching support facilities were available; candidate is port-only.')

    placements = _placements_from_templates(selected, anchor.body_id)
    if not placements:
        return None

    safe_body = anchor.body_id or 'system'
    candidate_id = f'{rule.key}_{safe_body}_{strategy}'
    label = f'{strategy.replace("_", " ").title()} {rule.label} candidate'
    return OptimiserCandidate(
        candidate_id=candidate_id,
        label=label,
        target_archetype=rule.key,
        strategy=strategy,
        placements=placements,
        rationale=[*anchor.rationale, f'Strategy: {strategy.replace("_", " ")}'],
        warnings=warnings,
        assumptions=assumptions,
        tags=_unique_strings(tags),
        preview_summary=None,
    )


def _attach_preview_summary(
    *,
    candidate: OptimiserCandidate,
    request: CandidateGenerationRequest,
    catalogue: dict[str, FacilityTemplate],
    base_context: PreviewContext,
    anchor: BodyAnchor,
    preview_runner: PreviewRunner,
) -> OptimiserCandidate:
    context = replace(
        base_context,
        local_body_profiles=dict(base_context.local_body_profiles),
        mechanics_notes=list(base_context.mechanics_notes),
        observed_facts=list(base_context.observed_facts),
    )
    if anchor.profile and anchor.body_id:
        context.local_body_profiles[anchor.body_id] = anchor.profile.to_context_profile()

    try:
        response = preview_runner(
            system_id64=request.system_id64,
            target_archetype=candidate.target_archetype,
            placements=[candidate_placement_to_preview_placement(p) for p in candidate.placements],
            catalogue=catalogue,
            context=context,
        )
        return replace(candidate, preview_summary=preview_summary_from_response(response))
    except Exception as exc:  # pragma: no cover - exercised through tests with deterministic monkeypatches.
        return replace(candidate, warnings=[*candidate.warnings, f'Preview failed for candidate: {exc}'])


def _placements_from_templates(templates: list[FacilityTemplate], body_id: Optional[str]) -> list[CandidatePlacement]:
    placements: list[CandidatePlacement] = []
    primary_assigned = False
    for template in templates:
        is_primary = bool(template.is_port and not primary_assigned)
        primary_assigned = primary_assigned or is_primary
        placements.append(CandidatePlacement(
            facility_template_id=template.id,
            local_body_id=body_id,
            is_primary_port=is_primary,
            build_order=len(placements) + 1,
        ))
    return placements


def _unique_templates(templates: list[FacilityTemplate]) -> list[FacilityTemplate]:
    seen: set[str] = set()
    result: list[FacilityTemplate] = []
    for template in templates:
        if template.id in seen:
            continue
        seen.add(template.id)
        result.append(template)
    return result


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
