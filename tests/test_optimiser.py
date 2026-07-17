import os

os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')
os.environ.setdefault('ENVIRONMENT', 'test')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('DATABASE_URL', 'postgresql://user:password@localhost:5432/ed_finder_test')

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from edfinder_api.domain.facilities import FacilityTemplate
from edfinder_api.models import OptimiserCandidatesRequest, OptimiserCandidatesResponse
from edfinder_api.optimiser.candidate_generator import generate_candidates
from edfinder_api.optimiser.dedupe import placement_fingerprint
from edfinder_api.optimiser.models import (
    CandidateGenerationRequest,
    CandidatePlacement,
    CandidatePreviewSummary,
    OptimiserCandidate,
    candidate_placement_to_preview_placement,
    candidate_to_dict,
    ranking_result_to_dict,
)
from edfinder_api.optimiser.ranker import rank_candidates
from edfinder_api.routers.optimiser import post_optimiser_candidates


class MockConnection:
    def __init__(self, body_rows=None, system_row=None):
        self.body_rows = body_rows if body_rows is not None else body_rows_default()
        self.system_row = system_row if system_row is not None else {
            'system_id64': 123,
            'estimated_orbital_slots': 8,
            'estimated_ground_slots': 4,
            'slot_confidence': 0.9,
            'has_ringed_body': True,
        }

    async def fetch(self, query, *args):
        if 'SELECT * FROM bodies' in query:
            return self.body_rows
        if 'SELECT * FROM facility_templates' in query:
            return []
        return []

    async def fetchrow(self, query, *args):
        if 'SELECT * FROM systems' in query:
            return self.system_row
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class MockPool:
    def __init__(self, body_rows=None, system_row=None):
        self.connection = MockConnection(body_rows=body_rows, system_row=system_row)

    def acquire(self):
        return self.connection


@pytest.fixture
def catalogue():
    return {
        'generic_port_alpha': facility('generic_port_alpha', 'Generic Port Alpha', 'Port', 2, None, is_port=True, yellow_cp_cost=20, green_cp_cost=20),
        'generic_port_beta': facility('generic_port_beta', 'Generic Port Beta', 'Port', 1, None, is_port=True, yellow_cp_cost=10, green_cp_cost=10),
        'agri_support_a': facility('agri_support_a', 'Agriculture Support A', 'Support', 1, 'Agriculture', is_support_facility=True),
        'agri_support_b': facility('agri_support_b', 'Agriculture Support B', 'Support', 2, 'Agriculture', is_support_facility=True),
        'refinery_support': facility('refinery_support', 'Refinery Support', 'Support', 1, 'Refinery', is_support_facility=True),
        'industrial_support': facility('industrial_support', 'Industrial Support', 'Support', 1, 'Industrial', is_support_facility=True),
        'service_support': facility(
            'service_support',
            'Service Unlock Support',
            'Support',
            1,
            'Agriculture',
            is_support_facility=True,
            stat_effects={'data_confidence': 'confirmed', 'unlocks': [{'type': 'service', 'description': 'market'}]},
        ),
    }


def facility(
    id,
    name,
    category,
    tier,
    economy,
    *,
    is_port=False,
    is_colony_port=False,
    is_support_facility=False,
    yellow_cp_cost=5,
    green_cp_cost=5,
    stat_effects=None,
):
    return FacilityTemplate(
        id=id,
        name=name,
        category=category,
        tier=tier,
        economy=economy,
        is_port=is_port,
        is_colony_port=is_colony_port,
        is_support_facility=is_support_facility,
        yellow_cp_generated=0,
        green_cp_generated=0,
        yellow_cp_cost=yellow_cp_cost,
        green_cp_cost=green_cp_cost,
        strong_link_value=0.0,
        weak_link_value=0.0,
        allowed_location='orbital_or_surface',
        pad_size=None,
        prerequisites=[],
        economy_effects={},
        stat_effects=stat_effects or {'data_confidence': 'confirmed'},
    )


def body_rows_default():
    return [
        body_row('body1', 'Body One', ['Agriculture'], ['terraforming_candidate']),
        body_row('body2', 'Body Two', ['Agriculture'], ['terraforming_candidate']),
    ]


def body_row(body_id, name, base_economies, strategic_tags):
    return {
        'body_id': body_id,
        'body_name': name,
        'system_id64': 123,
        'body_type': 'Planet',
        'subtype': 'Earthlike World',
        'is_landable': True,
        'is_terraformable': 'terraforming_candidate' in strategic_tags,
        'distance_from_star': 100,
        'gravity': 1.0,
        'mass': 1.0,
        'radius': 1.0,
        'surface_temp': 290,
        'atmosphere_type': 'None',
        'volcanism_type': 'None',
        'surface_pressure': 0.0,
        'materials': {},
        'bio_signals': [],
        'geo_signals': [],
        'economy_profile': {
            'base_economies': base_economies,
            'modifier_economies': [],
            'weights': {economy: 1.0 for economy in base_economies},
            'purity': 1.0,
            'confidence': 1.0,
            'caveats': [],
            'strategic_tags': strategic_tags,
            'source_body_id': body_id,
            'source_body_name': name,
            'inherited': False,
        },
    }


def preview_response(**overrides):
    response = {
        'final_score': 82.4,
        'composition_score': 85.0,
        'buildability_score': 78.0,
        'confidence': 0.72,
        'build_complexity': 'moderate',
        'warnings': ['example warning'],
        'cp': {'yellow_cp_final': 1, 'green_cp_final': 1},
        'top_two_alignment': 'strong',
    }
    response.update(overrides)
    return response


async def generate(catalogue, *, body_rows=None, max_candidates=5, target='agriculture_terraforming', run_preview=False, preferred_body_ids=None, preview_runner=None):
    kwargs = {}
    if preview_runner is not None:
        kwargs['preview_runner'] = preview_runner
    return await generate_candidates(
        CandidateGenerationRequest(
            system_id64=123,
            target_archetype=target,
            max_candidates=max_candidates,
            preferred_body_ids=preferred_body_ids or [],
            run_preview=run_preview,
        ),
        catalogue=catalogue,
        pool=MockPool(body_rows=body_rows),
        **kwargs,
    )


async def endpoint_payload(
    catalogue,
    monkeypatch,
    *,
    system_id64=123,
    target_archetype='agriculture_terraforming',
    target_archetype_key=None,
    max_candidates=5,
    run_preview=False,
    include_ranking=False,
):
    async def fake_catalogue(pool):
        return catalogue

    monkeypatch.setattr('edfinder_api.routers.optimiser._catalogue_or_db', fake_catalogue)
    response = await post_optimiser_candidates(
        OptimiserCandidatesRequest(
            system_id64=system_id64,
            target_archetype=target_archetype,
            target_archetype_key=target_archetype_key,
            max_candidates=max_candidates,
            run_preview=run_preview,
            include_ranking=include_ranking,
        ),
        MockPool(),
    )
    return response.model_dump()


@pytest.mark.asyncio
async def test_generate_candidates_respects_max_candidates(catalogue):
    result = await generate(catalogue, max_candidates=2)
    assert result.candidate_count == 2
    assert len(result.candidates) == 2


@pytest.mark.asyncio
async def test_candidate_ids_are_deterministic(catalogue):
    first = await generate(catalogue, max_candidates=4)
    second = await generate(catalogue, max_candidates=4)
    assert [c.candidate_id for c in first.candidates] == [c.candidate_id for c in second.candidates]


@pytest.mark.asyncio
async def test_candidate_build_orders_are_sequential(catalogue):
    result = await generate(catalogue, max_candidates=3)
    for candidate in result.candidates:
        assert [p.build_order for p in candidate.placements] == list(range(1, len(candidate.placements) + 1))


@pytest.mark.asyncio
async def test_candidate_has_at_most_one_primary_port(catalogue):
    result = await generate(catalogue, max_candidates=5)
    for candidate in result.candidates:
        assert sum(1 for p in candidate.placements if p.is_primary_port) <= 1


@pytest.mark.asyncio
async def test_candidates_only_use_catalogue_facilities(catalogue):
    result = await generate(catalogue, max_candidates=5)
    catalogue_ids = set(catalogue)
    for candidate in result.candidates:
        assert {p.facility_template_id for p in candidate.placements} <= catalogue_ids


@pytest.mark.asyncio
async def test_trivial_port_only_candidates_are_rejected():
    port_only_catalogue = {
        'generic_port_only': facility('generic_port_only', 'Generic Port Only', 'Port', 1, None, is_port=True),
    }
    result = await generate(port_only_catalogue, body_rows=[body_row('body1', 'Body One', ['Agriculture'], ['terraforming_candidate'])], max_candidates=5)
    assert result.candidate_count == 0


@pytest.mark.asyncio
async def test_unknown_archetype_falls_back_to_flexible_multirole_with_warning(catalogue):
    result = await generate(catalogue, target='unknown_specialisation', max_candidates=1)
    assert result.target_archetype == 'flexible_multirole'
    assert result.warnings == ['Unknown archetype unknown_specialisation; using flexible_multirole fallback.']


@pytest.mark.asyncio
async def test_generation_works_without_body_data(catalogue):
    result = await generate(catalogue, body_rows=[], max_candidates=1)
    assert result.candidate_count == 1
    assert result.candidates[0].placements[0].local_body_id is None
    assert 'No body data available; generated system-level candidates only.' in result.warnings


@pytest.mark.asyncio
async def test_preferred_body_ids_are_used_when_supplied(catalogue):
    result = await generate(catalogue, max_candidates=1, preferred_body_ids=['body2'])
    assert result.candidates[0].placements[0].local_body_id == 'body2'
    assert any('preferred' in item for item in result.candidates[0].rationale)


@pytest.mark.asyncio
async def test_useful_industrial_archetype_candidate_appears(catalogue):
    result = await generate(
        catalogue,
        target='refinery_industrial',
        body_rows=[body_row('body1', 'Rocky Industrial', ['Refinery'], [])],
        max_candidates=4,
    )

    assert result.candidate_count > 0
    assert any(
        {'refinery_support', 'industrial_support'} & {placement.facility_template_id for placement in candidate.placements}
        for candidate in result.candidates
    )
    assert all(len(candidate.placements) >= 2 for candidate in result.candidates)


@pytest.mark.asyncio
async def test_default_candidates_are_scaled_beyond_bootstrap_when_data_allows(catalogue):
    result = await generate(
        catalogue,
        target='agriculture_terraforming',
        body_rows=body_rows_default(),
        max_candidates=5,
        run_preview=False,
    )

    assert result.candidate_count > 0
    assert any(len(candidate.placements) > 4 for candidate in result.candidates)
    assert any(any(tag.startswith('scale_') for tag in candidate.tags) for candidate in result.candidates)


@pytest.mark.asyncio
async def test_scaled_candidates_use_multiple_bodies_when_available(catalogue):
    result = await generate(
        catalogue,
        target='agriculture_terraforming',
        body_rows=body_rows_default(),
        max_candidates=5,
        run_preview=False,
    )

    assert any(
        len({placement.local_body_id for placement in candidate.placements if placement.local_body_id}) > 1
        for candidate in result.candidates
        if len(candidate.placements) >= 5
    )


@pytest.mark.asyncio
async def test_bootstrap_candidate_is_marked_and_ranks_below_strategic_options(catalogue):
    bootstrap = OptimiserCandidate(
        candidate_id='bootstrap',
        label='Bootstrap candidate',
        target_archetype='agriculture_terraforming',
        strategy='primary_port_bootstrap',
        placements=[
            CandidatePlacement('generic_port_alpha', local_body_id='body1', is_primary_port=True, build_order=1),
            CandidatePlacement('agri_support_a', local_body_id='body1', is_primary_port=False, build_order=2),
            CandidatePlacement('agri_support_b', local_body_id='body2', is_primary_port=False, build_order=3),
        ],
        tags=['scale_bootstrap', 'bootstrap'],
        preview_summary=CandidatePreviewSummary(final_score=80, composition_score=80, buildability_score=80, confidence=0.8),
    )
    expansion = OptimiserCandidate(
        candidate_id='expansion',
        label='Expansion candidate',
        target_archetype='agriculture_terraforming',
        strategy='balanced_expansion',
        placements=[
            CandidatePlacement('generic_port_alpha', local_body_id='body1', is_primary_port=True, build_order=1),
            CandidatePlacement('agri_support_a', local_body_id='body1', is_primary_port=False, build_order=2),
            CandidatePlacement('agri_support_b', local_body_id='body2', is_primary_port=False, build_order=3),
            CandidatePlacement('service_support', local_body_id='body2', is_primary_port=False, build_order=4),
            CandidatePlacement('agri_support_a', local_body_id='body1', is_primary_port=False, build_order=5),
        ],
        tags=['scale_starter'],
        preview_summary=CandidatePreviewSummary(final_score=80, composition_score=80, buildability_score=80, confidence=0.8),
    )

    ranking = rank_candidates([bootstrap, expansion], target_archetype='agriculture_terraforming')
    scores = {item.candidate_id: item.rank_score for item in ranking.ranked_candidates}
    assert 'scale_bootstrap' in bootstrap.tags
    assert scores['bootstrap'] < scores['expansion']


@pytest.mark.asyncio
async def test_colony_ship_bootstrap_is_not_returned_as_strategic_candidate(catalogue):
    with_colony_ship = {
        **catalogue,
        'colony_ship': facility('colony_ship', 'Colony Ship', 'Port', 0, 'Colony', is_port=True, is_colony_port=True, yellow_cp_cost=0, green_cp_cost=0),
    }

    result = await generate(
        with_colony_ship,
        target='agriculture_terraforming',
        body_rows=[body_row('body1', 'Body One', ['Agriculture'], ['terraforming_candidate'])],
        max_candidates=5,
    )

    assert result.candidate_count > 0
    assert all(
        placement.facility_template_id != 'colony_ship'
        for candidate in result.candidates
        for placement in candidate.placements
    )


@pytest.mark.asyncio
async def test_run_preview_false_omits_preview_summary(catalogue):
    result = await generate(catalogue, max_candidates=1, run_preview=False)
    assert result.candidates[0].preview_summary is None


@pytest.mark.asyncio
async def test_run_preview_true_adds_lightweight_preview_summary(catalogue):
    result = await generate(catalogue, max_candidates=1, run_preview=True, preview_runner=lambda **kwargs: preview_response())
    summary = result.candidates[0].preview_summary
    assert summary is not None
    assert summary.final_score == 82.4
    assert summary.buildability_score == 78.0
    assert summary.warnings_count == 1
    assert summary.cp_negative is False


@pytest.mark.asyncio
async def test_preview_failure_is_captured_per_candidate(catalogue):
    def failing_preview(**kwargs):
        raise RuntimeError('preview unavailable')

    result = await generate(catalogue, max_candidates=1, run_preview=True, preview_runner=failing_preview)
    assert result.candidates[0].preview_summary is None
    assert result.candidates[0].warnings == ['Preview failed for candidate: preview unavailable']


def test_candidate_placement_converts_to_preview_placement():
    placement = CandidatePlacement('generic_support', local_body_id='body1', is_primary_port=True, build_order=2)
    preview = candidate_placement_to_preview_placement(placement)
    assert preview.facility_template_id == 'generic_support'
    assert preview.local_body_id == 'body1'
    assert preview.is_primary_port is True
    assert preview.build_order == 2


@pytest.mark.asyncio
async def test_endpoint_returns_clean_candidate_response_shape(catalogue, monkeypatch):
    payload = await endpoint_payload(catalogue, monkeypatch, max_candidates=1)
    response_data = OptimiserCandidatesResponse.model_validate(payload)
    assert payload['system_id64'] == 123
    assert payload['target_archetype'] == 'agriculture_terraforming'
    assert payload['candidate_count'] == 1
    assert set(payload['candidates'][0]) == {
        'candidate_id', 'label', 'target_archetype', 'strategy', 'placements',
        'rationale', 'warnings', 'assumptions', 'tags', 'preview_summary'
    }
    assert response_data.candidates[0].candidate_id


@pytest.mark.asyncio
async def test_endpoint_returns_safe_error_without_raw_exception(catalogue, monkeypatch):
    async def fake_catalogue(pool):
        return catalogue

    class BrokenPool:
        def acquire(self):
            raise RuntimeError('database schema exploded with private details')

    monkeypatch.setattr('edfinder_api.routers.optimiser._catalogue_or_db', fake_catalogue)
    with pytest.raises(HTTPException) as exc_info:
        await post_optimiser_candidates(
            OptimiserCandidatesRequest(
                system_id64=123,
                target_archetype='agriculture_terraforming',
                max_candidates=1,
                run_preview=False,
            ),
            BrokenPool(),
        )

    assert exc_info.value.status_code == 503
    detail = exc_info.value.detail
    assert detail['message'] == 'Suggested Builds are temporarily unavailable. You can still edit your Build Plan manually or try again.'
    assert detail['error_code'] == 'optimiser_candidates_unavailable'
    assert 'technical_detail' in detail


@pytest.mark.asyncio
async def test_context_query_uses_systems_id64_column(catalogue):
    class QueryAssertingConnection(MockConnection):
        async def fetchrow(self, query, *args):
            assert 'WHERE id64 = $1' in query
            assert 'system_id64 = $1' not in query
            return await super().fetchrow(query, *args)

    class QueryAssertingPool(MockPool):
        def __init__(self):
            self.connection = QueryAssertingConnection()

    result = await generate_candidates(
        CandidateGenerationRequest(
            system_id64=123,
            target_archetype='agriculture_terraforming',
            max_candidates=1,
            run_preview=False,
        ),
        catalogue=catalogue,
        pool=QueryAssertingPool(),
    )

    assert result.candidate_count == 1


@pytest.mark.asyncio
async def test_endpoint_respects_max_candidates(catalogue, monkeypatch):
    payload = await endpoint_payload(
        catalogue,
        monkeypatch,
        target_archetype=None,
        target_archetype_key='agriculture_terraforming',
        max_candidates=2,
    )
    assert payload['candidate_count'] == 2
    assert len(payload['candidates']) == 2


@pytest.mark.asyncio
async def test_generate_candidates_zero_max_candidates_returns_empty_defensively(catalogue):
    result = await generate(catalogue, max_candidates=0)
    assert result.candidate_count == 0
    assert result.candidates == []


def test_optimiser_request_rejects_zero_max_candidates():
    with pytest.raises(ValidationError):
        OptimiserCandidatesRequest(
            system_id64=123,
            target_archetype='agriculture_terraforming',
            max_candidates=0,
        )


def test_public_optimiser_response_model_matches_clean_contract():
    payload = {
        'system_id64': 123,
        'target_archetype': 'agriculture_terraforming',
        'candidate_count': 1,
        'candidates': [
            {
                'candidate_id': 'agriculture_terraforming_body1_balanced',
                'label': 'Balanced Agriculture / Terraforming candidate',
                'target_archetype': 'agriculture_terraforming',
                'strategy': 'balanced',
                'placements': [
                    {
                        'facility_template_id': 'generic_port_alpha',
                        'local_body_id': 'body1',
                        'is_primary_port': True,
                        'build_order': 1,
                    }
                ],
                'rationale': ['Body supports target economies: Agriculture.'],
                'warnings': [],
                'assumptions': [],
                'tags': ['balanced', 'agriculture_terraforming'],
                'preview_summary': {
                    'final_score': 82.4,
                    'composition_score': 85.0,
                    'buildability_score': 78.0,
                    'confidence': 0.72,
                    'build_complexity': 'moderate',
                    'warnings_count': 2,
                    'cp_negative': False,
                    'top_two_alignment': 'strong',
                },
            }
        ],
        'warnings': [],
        'assumptions': ['Stage 5A generates bounded heuristic candidates only; Simulation Preview remains the source of truth.'],
    }

    response = OptimiserCandidatesResponse.model_validate(payload)
    candidate_payload = response.model_dump()['candidates'][0]
    assert set(candidate_payload) == {
        'candidate_id',
        'label',
        'target_archetype',
        'strategy',
        'placements',
        'rationale',
        'warnings',
        'assumptions',
        'tags',
        'preview_summary',
    }
    assert set(candidate_payload['preview_summary']) == {
        'final_score',
        'composition_score',
        'buildability_score',
        'confidence',
        'build_complexity',
        'warnings_count',
        'cp_negative',
        'top_two_alignment',
    }
    assert 'id' not in candidate_payload
    assert 'archetype' not in candidate_payload
    assert 'description' not in candidate_payload
    assert 'tradeoffs' not in candidate_payload


@pytest.mark.asyncio
async def test_run_preview_true_does_not_embed_full_simulation_preview_response(catalogue):
    large_preview_response = preview_response(
        mechanics_trace={'cp_effects': []},
        port_economy_states=[],
        service_unlock_ledger=[],
        prediction_observation_diffs=[],
        very_large_field={'should_not': 'leak'},
    )
    result = await generate(
        catalogue,
        max_candidates=1,
        run_preview=True,
        preview_runner=lambda **kwargs: large_preview_response,
    )
    summary = result.candidates[0].preview_summary
    assert summary is not None

    payload = {'candidates': [candidate_to_dict(result.candidates[0])]}
    preview_summary = payload['candidates'][0]['preview_summary']
    assert set(preview_summary) == {
        'final_score',
        'composition_score',
        'buildability_score',
        'confidence',
        'build_complexity',
        'warnings_count',
        'cp_negative',
        'top_two_alignment',
    }
    assert 'mechanics_trace' not in preview_summary
    assert 'port_economy_states' not in preview_summary
    assert 'service_unlock_ledger' not in preview_summary
    assert 'prediction_observation_diffs' not in preview_summary
    assert 'very_large_field' not in preview_summary


def test_candidate_fingerprint_is_order_sensitive_because_cp_timing_matters():
    port_then_support = [
        CandidatePlacement('generic_port_alpha', local_body_id='body1', is_primary_port=True, build_order=1),
        CandidatePlacement('agri_support_a', local_body_id='body1', is_primary_port=False, build_order=2),
    ]
    support_then_port = [
        CandidatePlacement('agri_support_a', local_body_id='body1', is_primary_port=False, build_order=1),
        CandidatePlacement('generic_port_alpha', local_body_id='body1', is_primary_port=True, build_order=2),
    ]
    assert placement_fingerprint(port_then_support) != placement_fingerprint(support_then_port)


def ranked_test_candidate(
    candidate_id: str,
    *,
    final_score: float | None = 80.0,
    composition_score: float | None = 80.0,
    buildability_score: float | None = 80.0,
    confidence: float | None = 0.8,
    warnings_count: int = 0,
    cp_negative: bool | None = False,
    top_two_alignment: str | None = 'strong',
    warnings: list[str] | None = None,
    strategy: str = 'balanced',
    preview: bool = True,
) -> OptimiserCandidate:
    summary = None
    if preview:
        summary = CandidatePreviewSummary(
            final_score=final_score,
            composition_score=composition_score,
            buildability_score=buildability_score,
            confidence=confidence,
            build_complexity='moderate',
            warnings_count=warnings_count,
            cp_negative=cp_negative,
            top_two_alignment=top_two_alignment,
        )
    return OptimiserCandidate(
        candidate_id=candidate_id,
        label=f'{candidate_id} label',
        target_archetype='agriculture_terraforming',
        strategy=strategy,
        placements=[CandidatePlacement('generic_port_alpha', local_body_id='body1', is_primary_port=True, build_order=1)],
        rationale=[],
        warnings=warnings or [],
        assumptions=[],
        tags=[],
        preview_summary=summary,
    )


def test_rank_candidates_orders_by_rank_score():
    weaker = ranked_test_candidate('weak_candidate', final_score=40, composition_score=40, buildability_score=40, confidence=0.4)
    stronger = ranked_test_candidate('strong_candidate', final_score=90, composition_score=90, buildability_score=90, confidence=0.9)
    result = rank_candidates([weaker, stronger], target_archetype='agriculture_terraforming')
    assert [item.candidate_id for item in result.ranked_candidates] == ['strong_candidate', 'weak_candidate']
    assert result.ranked_candidates[0].rank == 1
    assert result.ranked_candidates[0].rank_score >= result.ranked_candidates[1].rank_score


def test_rank_candidates_is_deterministic_for_equal_inputs():
    candidates = [
        ranked_test_candidate('candidate_b', final_score=80),
        ranked_test_candidate('candidate_a', final_score=80),
    ]
    first = rank_candidates(candidates, target_archetype='agriculture_terraforming')
    second = rank_candidates(candidates, target_archetype='agriculture_terraforming')
    assert [item.candidate_id for item in first.ranked_candidates] == ['candidate_a', 'candidate_b']
    assert ranking_result_to_dict(first) == ranking_result_to_dict(second)


def test_rank_candidates_handles_missing_preview_summary():
    result = rank_candidates([
        ranked_test_candidate('unpreviewed', preview=False),
    ], target_archetype='agriculture_terraforming')
    ranked = result.ranked_candidates[0]
    assert 0.0 <= ranked.rank_score <= 100.0
    assert ranked.rank_tier in {'weak', 'risky', 'viable', 'strong', 'excellent'}


def test_missing_preview_summary_includes_explanatory_reason():
    result = rank_candidates([
        ranked_test_candidate('unpreviewed', preview=False),
    ], target_archetype='agriculture_terraforming')
    reasons = result.ranked_candidates[0].rank_breakdown.reasons
    assert any('not been preview-scored' in reason for reason in reasons)


def test_rank_candidates_penalizes_candidate_warnings():
    clean = ranked_test_candidate('clean')
    warned = ranked_test_candidate('warned', warnings=['Candidate warning'])
    result = rank_candidates([clean, warned], target_archetype='agriculture_terraforming')
    scores = {item.candidate_id: item.rank_score for item in result.ranked_candidates}
    assert scores['clean'] > scores['warned']


def test_rank_candidates_penalizes_cp_negative():
    ok = ranked_test_candidate('cp_ok', cp_negative=False)
    negative = ranked_test_candidate('cp_negative', cp_negative=True)
    result = rank_candidates([ok, negative], target_archetype='agriculture_terraforming')
    scores = {item.candidate_id: item.rank_score for item in result.ranked_candidates}
    assert scores['cp_ok'] > scores['cp_negative']


def test_rank_candidates_uses_confidence_component():
    high = ranked_test_candidate('high_confidence', confidence=0.9)
    low = ranked_test_candidate('low_confidence', confidence=0.2)
    result = rank_candidates([low, high], target_archetype='agriculture_terraforming')
    scores = {item.candidate_id: item.rank_score for item in result.ranked_candidates}
    assert scores['high_confidence'] > scores['low_confidence']
    high_breakdown = next(item.rank_breakdown for item in result.ranked_candidates if item.candidate_id == 'high_confidence')
    assert high_breakdown.confidence_component > 0


def test_rank_candidates_assigns_rank_tiers():
    candidates = [
        ranked_test_candidate('excellent', final_score=100, composition_score=100, buildability_score=100, confidence=1.0),
        ranked_test_candidate('weak', final_score=10, composition_score=10, buildability_score=10, confidence=0.1, top_two_alignment='poor'),
    ]
    result = rank_candidates(candidates, target_archetype='agriculture_terraforming')
    tiers = {item.candidate_id: item.rank_tier for item in result.ranked_candidates}
    assert tiers['excellent'] == 'excellent'
    assert tiers['weak'] == 'weak'


def test_rank_breakdown_exposes_alignment_component_separately():
    result = rank_candidates([
        ranked_test_candidate('candidate', final_score=80, top_two_alignment='strong')
    ], target_archetype='agriculture_terraforming')
    breakdown = result.ranked_candidates[0].rank_breakdown
    assert breakdown.preview_score_component == 28.0
    assert breakdown.alignment_component > 0
    assert breakdown.total_score >= breakdown.preview_score_component + breakdown.alignment_component



def test_rank_breakdown_is_serializable():
    result = rank_candidates([ranked_test_candidate('candidate')], target_archetype='agriculture_terraforming')
    payload = ranking_result_to_dict(result)
    ranked = payload['ranked_candidates'][0]
    assert set(ranked) == {'candidate_id', 'rank', 'rank_score', 'rank_tier', 'rank_breakdown'}
    assert set(ranked['rank_breakdown']) == {
        'preview_score_component',
        'composition_component',
        'buildability_component',
        'confidence_component',
        'alignment_component',
        'warning_penalty',
        'cp_penalty',
        'strategy_modifier',
        'total_score',
        'reasons',
    }


def test_ranking_does_not_mutate_candidates():
    candidate = ranked_test_candidate('candidate')
    before = candidate_to_dict(candidate)
    rank_candidates([candidate], target_archetype='agriculture_terraforming')
    after = candidate_to_dict(candidate)
    assert before == after
    assert 'rank' not in after
    assert 'rank_score' not in after


@pytest.mark.asyncio
async def test_endpoint_without_ranking_preserves_stage5a_shape(catalogue, monkeypatch):
    payload = await endpoint_payload(catalogue, monkeypatch, max_candidates=2)
    assert payload['ranking'] is None
    assert 'rank' not in payload['candidates'][0]
    assert 'rank_score' not in payload['candidates'][0]


@pytest.mark.asyncio
async def test_include_ranking_false_does_not_add_rank_fields_to_candidates(catalogue, monkeypatch):
    payload = await endpoint_payload(catalogue, monkeypatch, max_candidates=1, include_ranking=False)
    candidate = payload['candidates'][0]
    assert 'rank' not in candidate
    assert 'rank_score' not in candidate
    assert 'rank_breakdown' not in candidate


@pytest.mark.asyncio
async def test_include_ranking_false_preserves_candidate_order(catalogue, monkeypatch):
    payload = await endpoint_payload(catalogue, monkeypatch, max_candidates=3, include_ranking=False)
    ids = [candidate['candidate_id'] for candidate in payload['candidates']]
    expected = await generate(catalogue, max_candidates=3, run_preview=False)
    assert ids == [candidate.candidate_id for candidate in expected.candidates]


@pytest.mark.asyncio
async def test_endpoint_with_ranking_returns_top_level_ranking_object(catalogue, monkeypatch):
    payload = await endpoint_payload(catalogue, monkeypatch, max_candidates=2, include_ranking=True)
    ranking = payload['ranking']
    assert ranking is not None
    assert set(ranking) == {'target_archetype', 'ranked_candidates', 'warnings', 'assumptions'}
    assert ranking['target_archetype'] == 'agriculture_terraforming'


@pytest.mark.asyncio
async def test_endpoint_with_ranking_returns_ranked_candidate_ids(catalogue, monkeypatch):
    payload = await endpoint_payload(catalogue, monkeypatch, max_candidates=2, include_ranking=True)
    candidate_ids = {candidate['candidate_id'] for candidate in payload['candidates']}
    ranked_ids = {item['candidate_id'] for item in payload['ranking']['ranked_candidates']}
    assert ranked_ids == candidate_ids


@pytest.mark.asyncio
async def test_endpoint_with_ranking_does_not_duplicate_full_candidates_inside_ranking(catalogue, monkeypatch):
    payload = await endpoint_payload(catalogue, monkeypatch, max_candidates=1, include_ranking=True)
    ranked = payload['ranking']['ranked_candidates'][0]
    assert set(ranked) == {'candidate_id', 'rank', 'rank_score', 'rank_tier', 'rank_breakdown'}
    assert 'placements' not in ranked
    assert 'preview_summary' not in ranked
    assert 'rationale' not in ranked
