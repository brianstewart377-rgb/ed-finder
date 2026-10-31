"""Database-free HTTP contracts for the V3 colony planner's pure core."""

from __future__ import annotations

from dataclasses import asdict, fields
import json
import os
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.routing import APIRoute
import httpx
import pytest


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'http://test')
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from edfinder_api.config import limiter  # noqa: E402
from edfinder_api.cpe import Body, Plan, Site, evaluate_plan  # noqa: E402
from edfinder_api.cpe.budget import StepResult  # noqa: E402
from edfinder_api.cpe.catalogue import planner_facilities, prerequisites_for  # noqa: E402
from edfinder_api.cpe.explain import explain_rule  # noqa: E402
from edfinder_api.cpe.plan import validate_plan  # noqa: E402
from edfinder_api.cpe.rules import RULEBOOK_RELEASE  # noqa: E402
from edfinder_api.mechanics import cp_rules  # noqa: E402
from edfinder_api.routers import plan  # noqa: E402


pytestmark = pytest.mark.unit
SITE_FIELDS = ('site_id', 'facility_id', 'body_ref', 'slot_kind', 'status', 'name')


def _test_app() -> FastAPI:
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(plan.router)
    return app


@pytest.fixture(autouse=True)
def reset_rate_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_test_app()),
        base_url='http://test',
    ) as client:
        yield client


def _site(site_id='primary', facility_id='orbital_outpost_civilian', **overrides):
    return {
        'site_id': site_id,
        'facility_id': facility_id,
        'body_ref': None,
        'slot_kind': 'orbital',
        'status': 'complete',
        'name': None,
        **overrides,
    }


def _request(**overrides):
    return {'system_id64': '1', 'sites': [_site()], **overrides}


def _body(**overrides):
    return {
        'body_ref': 'A',
        'orbital_slots': 64,
        'surface_slots': 64,
        'is_landable': True,
        'is_ringed': True,
        **overrides,
    }


def _core_plan(body):
    return Plan(
        system_id64=int(body['system_id64']),
        bodies=tuple(Body(**item) for item in body.get('bodies', [])),
        sites=tuple(Site(**item) for item in body['sites']),
    )


async def test_catalogue_is_complete_static_and_matches_core_rules(client):
    response = await client.get('/api/v1/plan/catalogue')
    assert response.status_code == 200, response.text
    catalogue = response.json()
    assert catalogue['rulebook_release'] == RULEBOOK_RELEASE
    entries = catalogue['facilities']
    ids = [item['id'] for item in entries]
    assert ids == sorted(set(ids))
    assert 'colony_ship' not in ids
    assert len(entries) == len(planner_facilities())
    by_id = {item['id']: item for item in entries}
    assert by_id['coriolis_station']['escalating_port_tier'] == 2
    assert by_id['coriolis_station']['rule_ids'] == ['RB-0003', 'RB-0005', 'RB-0006']
    assert by_id['orbital_installation_space_farm']['rule_ids'] == ['RB-0002']
    assert by_id['industrial_facility']['prerequisites'] == [
        ['orbital_installation_mining_outpost'],
    ]
    assert by_id['surface_settlement_tourism_t2_l']['prerequisites'] == [
        ['orbital_installation_satellite'],
    ]
    for facility_id, template in planner_facilities().items():
        entry = by_id[facility_id]
        for field_name in (
            'id', 'name', 'category', 'tier', 'allowed_location', 'economy',
            'is_port', 'yellow_cp_cost', 'green_cp_cost',
            'yellow_cp_generated', 'green_cp_generated',
        ):
            assert entry[field_name] == getattr(template, field_name), facility_id
        assert entry['escalating_port_tier'] == cp_rules.escalating_port_tier(template)
        assert entry['prerequisites'] == [
            sorted(requirement) for requirement in prerequisites_for(facility_id)
        ]
        request = _request(
            bodies=[_body()],
            sites=[
                _site(body_ref='A'),
                _site(
                    'candidate', facility_id, body_ref='A', status='planned',
                    slot_kind='orbital' if template.can_go_orbital else 'surface',
                ),
            ],
        )
        evaluated = evaluate_plan(_core_plan(request))
        assert entry['rule_ids'] == list(evaluated.steps[1].rule_ids), facility_id
    assert (await client.get('/api/v1/plan/catalogue')).json() == catalogue


async def test_evaluate_raven_answer_key_preserves_budget_and_citations(client):
    answer = json.loads((
        ROOT / 'tests/fixtures/cpe/raven_answer_key_praea_euq_rev174.json'
    ).read_text(encoding='utf-8'))
    system_id64 = str(answer['source']['system_id64'])
    request = _request(
        system_id64=system_id64,
        sites=[
            {key: item[key] for key in SITE_FIELDS}
            for item in answer['sites_in_raven_order']
        ],
    )
    response = await client.post('/api/v1/plan/evaluate', json=request)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['rulebook_release'] == RULEBOOK_RELEASE
    assert body['system_id64'] == system_id64
    assert body['now'] == {'t2': 1, 't3': -17}
    assert body['after_plan'] == {'t2': 5, 't3': -16}
    assert len(body['steps']) == 13
    assert body['summary'] == {
        'OK': 0, 'BLOCKED': 0, 'NEEDS_INFO': 0, 'COUNTED': 13, 'IGNORED': 0,
    }
    expected = json.loads(json.dumps(asdict(evaluate_plan(_core_plan(request)))))
    assert {key: body[key] for key in expected} == expected
    step_fields = {field.name for field in fields(StepResult)}
    assert all(set(step) == step_fields for step in body['steps'])
    cited = {rule_id for step in body['steps'] for rule_id in step['rule_ids']}
    assert set(body['explanations']) == cited
    for rule_id in cited:
        assert body['explanations'][rule_id] == explain_rule(rule_id)
        assert body['explanations'][rule_id]['quote']


async def test_evaluate_blocked_orbis_has_affordable_payers_and_next_port_cost(client):
    response = await client.post('/api/v1/plan/evaluate', json=_request(
        bodies=[_body(surface_slots=0)],
        sites=[
            _site(body_ref='A'),
            _site('orbis', 'orbis_t3', body_ref='A', status='planned'),
        ],
    ))
    assert response.status_code == 200, response.text
    body = response.json()
    orbis = body['steps'][1]
    assert orbis['result'] == 'BLOCKED'
    assert orbis['reasons'] == ['INSUFFICIENT_T3']
    assert orbis['payers'] == [
        'orbital_installation_government',
        'orbital_installation_medical',
        'orbital_installation_space_bar',
    ]
    assert body['next_port_cost'] == {'t2': 3, 't3': 6}


@pytest.mark.parametrize(('facility_id', 'code'), (
    ('orbital_installation_space_farm', 'PRIMARY_NOT_PORT'),
    ('not_a_facility', 'UNKNOWN_FACILITY'),
))
async def test_core_invalid_plan_returns_plan_issue_shape(client, facility_id, code):
    response = await client.post('/api/v1/plan/evaluate', json=_request(
        sites=[_site('invalid', facility_id)],
    ))
    assert response.status_code == 422
    body = response.json()
    assert body['error'] == 'plan_invalid'
    assert any(
        issue['code'] == code and issue['site_id'] == 'invalid'
        for issue in body['issues']
    )


async def test_core_validation_preserves_all_issues_in_core_order(client):
    request = _request(
        system_id64='0', bodies=[_body(), _body()],
        sites=[
            _site('same', 'orbital_installation_space_farm', body_ref='missing'),
            _site('same', 'not_a_facility'),
        ],
    )
    expected_issues = [asdict(issue) for issue in validate_plan(_core_plan(request))]
    response = await client.post('/api/v1/plan/evaluate', json=request)
    assert response.status_code == 422
    assert response.json() == {'error': 'plan_invalid', 'issues': expected_issues}
    assert len(expected_issues) >= 5


@pytest.mark.parametrize('payload', (
    _request(extra=True),
    _request(system_id64=1),
    _request(system_id64='abc'),
    _request(system_id64='1' * 20),
    _request(sites=[_site(str(index)) for index in range(301)]),
    _request(sites=[]),
    _request(sites=[_site(name='x' * 65)]),
    _request(sites=[_site(slot_kind='ring')]),
    _request(sites=[_site(status='pending')]),
    _request(sites=[_site(extra=True)]),
    _request(sites=[_site(site_id='')]),
    _request(sites=[_site(site_id='x' * 65)]),
    _request(sites=[_site(facility_id='')]),
    _request(sites=[_site(facility_id='x' * 65)]),
    _request(sites=[_site(body_ref='')]),
    _request(sites=[_site(body_ref='x' * 65)]),
    _request(sites=[_site(name=42)]),
    _request(bodies=[_body(extra=True)]),
    _request(bodies=[_body(body_ref='')]),
    _request(bodies=[_body(body_ref='x' * 65)]),
    _request(bodies=[_body(orbital_slots=-1)]),
    _request(bodies=[_body(surface_slots=65)]),
    _request(bodies=[_body(orbital_slots=True)]),
    _request(bodies=[_body(surface_slots='1')]),
    _request(bodies=[_body(is_landable=1)]),
    _request(bodies=[_body(is_ringed='true')]),
    _request(bodies=[_body(body_ref=str(index)) for index in range(1001)]),
), ids=(
    'extra-request-field', 'numeric-id64', 'non-numeric-id64', 'long-id64',
    '301-sites', 'zero-sites', 'long-name', 'bad-slot-kind', 'bad-status',
    'extra-site-field', 'empty-site-id', 'long-site-id', 'empty-facility-id',
    'long-facility-id', 'empty-body-ref', 'long-body-ref', 'numeric-name',
    'extra-body-field', 'empty-body-id', 'long-body-id', 'negative-slots',
    '65-slots', 'bool-slots', 'string-slots', 'numeric-landable',
    'string-ringed', '1001-bodies',
))
async def test_malformed_input_is_rejected_by_pydantic(client, payload):
    response = await client.post('/api/v1/plan/evaluate', json=payload)
    assert response.status_code == 422, response.text
    assert isinstance(response.json()['detail'], list)


async def test_maximum_id64_is_echoed_without_precision_loss(client):
    system_id64 = '9223372036854775807'
    response = await client.post('/api/v1/plan/evaluate', json=_request(
        system_id64=system_id64,
    ))
    assert response.status_code == 200, response.text
    assert response.json()['system_id64'] == system_id64


async def test_explanations_include_plan_check_rules_and_demolished_steps(client):
    response = await client.post('/api/v1/plan/evaluate', json=_request(
        sites=[_site()] + [
            _site(f'building-{index}', 'orbital_installation_comm_station', status='building')
            for index in range(6)
        ] + [_site('removed', status='demolished')],
    ))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['plan_checks'] == [{
        'code': 'MORE_THAN_FIVE_BUILDING',
        'message': 'More than five sites are under construction.',
        'rule_ids': ['RB-0007'],
    }]
    cited = {
        rule_id
        for item in body['steps'] + body['plan_checks']
        for rule_id in item['rule_ids']
    }
    assert set(body['explanations']) == cited
    assert body['explanations']['RB-0007'] == explain_rule('RB-0007')
    assert body['steps'][-1]['result'] == 'IGNORED'
    assert body['steps'][-1]['rule_ids'] == []
    assert body['summary']['IGNORED'] == 1


def test_openapi_documents_operations_invalid_response_and_no_database_dependencies():
    app = _test_app()
    operations = app.openapi()['paths']
    assert operations['/api/v1/plan/catalogue']['get']['operationId'] == 'getV3PlanCatalogue'
    evaluate = operations['/api/v1/plan/evaluate']['post']
    assert evaluate['operationId'] == 'evaluateV3Plan'
    assert evaluate['responses']['422']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/PlanInvalidV1',
    }
    # FastAPI includes routers lazily; inspect their concrete API routes.
    routes = [route for route in plan.router.routes if isinstance(route, APIRoute)]
    assert {route.path for route in routes} == {
        '/api/v1/plan/catalogue', '/api/v1/plan/evaluate',
    }
    for route in routes:
        pending = list(route.dependant.dependencies)
        while pending:
            dependency = pending.pop()
            assert getattr(dependency.call, '__name__', '') not in {
                'get_pool', 'get_readonly_pool',
            }
            pending.extend(dependency.dependencies)
        assert not route.dependant.dependencies


def test_evaluate_has_sixty_per_minute_rate_limit():
    endpoint = next(
        route.endpoint for route in plan.router.routes
        if isinstance(route, APIRoute) and route.path == '/api/v1/plan/evaluate'
    )
    limits = limiter._route_limits[f'{endpoint.__module__}.{endpoint.__name__}']
    assert [str(limit.limit) for limit in limits] == ['60 per 1 minute']
