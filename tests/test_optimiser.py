import os

os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')
os.environ.setdefault('ENVIRONMENT', 'test')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('DATABASE_URL', 'postgresql://user:password@localhost:5432/ed_finder_test')

import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from httpx import ASGITransport, AsyncClient

from deps import get_pool
from domain.facilities import FacilityTemplate
from models import OptimiserCandidatesRequest, OptimiserCandidatesResponse
from optimiser.candidate_generator import generate_candidates
from optimiser.dedupe import placement_fingerprint
from optimiser.models import (
    CandidateGenerationRequest,
    CandidatePlacement,
    candidate_placement_to_preview_placement,
    candidate_to_dict,
)
from routers.optimiser import router as optimiser_router


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
        is_colony_port=False,
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
async def test_duplicate_candidate_fingerprints_are_deduped():
    port_only_catalogue = {
        'generic_port_only': facility('generic_port_only', 'Generic Port Only', 'Port', 1, None, is_port=True),
    }
    result = await generate(port_only_catalogue, body_rows=[body_row('body1', 'Body One', ['Agriculture'], ['terraforming_candidate'])], max_candidates=5)
    assert result.candidate_count == 1


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
    async def fake_catalogue(pool):
        return catalogue

    monkeypatch.setattr('routers.optimiser._catalogue_or_db', fake_catalogue)
    app = FastAPI()
    app.include_router(optimiser_router)
    app.dependency_overrides[get_pool] = lambda: MockPool()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post('/api/optimiser/candidates', json={
            'system_id64': 123,
            'target_archetype': 'agriculture_terraforming',
            'max_candidates': 1,
            'run_preview': False,
        })

    assert response.status_code == 200
    payload = response.json()
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
async def test_endpoint_respects_max_candidates(catalogue, monkeypatch):
    async def fake_catalogue(pool):
        return catalogue

    monkeypatch.setattr('routers.optimiser._catalogue_or_db', fake_catalogue)
    app = FastAPI()
    app.include_router(optimiser_router)
    app.dependency_overrides[get_pool] = lambda: MockPool()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post('/api/optimiser/candidates', json={
            'system_id64': 123,
            'target_archetype_key': 'agriculture_terraforming',
            'max_candidates': 2,
            'run_preview': False,
        })

    assert response.status_code == 200
    payload = response.json()
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
