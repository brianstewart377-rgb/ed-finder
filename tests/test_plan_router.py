"""Database-free HTTP and dependency contracts for the V3 colony planner."""

from __future__ import annotations

import ast
from dataclasses import asdict, fields
import json
import os
from pathlib import Path
import re
import sys
from uuid import UUID

from fastapi import FastAPI
from fastapi.routing import APIRoute
import httpx
import pytest
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'http://test')
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from edfinder_api.config import limiter  # noqa: E402
from edfinder_api.cpe import Body, Plan, Site, evaluate_plan  # noqa: E402
from edfinder_api.cpe.budget import StepResult  # noqa: E402
from edfinder_api.cpe.catalogue import planner_facilities, prerequisites_for  # noqa: E402
from edfinder_api.cpe.economy import (  # noqa: E402
    Economy, EconomyBody, EconomyItem, EconomyNote, EconomySystem, PortEconomy,
    evaluate_economies,
)
from edfinder_api.cpe.explain import explain_rule  # noqa: E402
from edfinder_api.cpe.plan import validate_plan  # noqa: E402
from edfinder_api.cpe.rules import RULEBOOK_RELEASE  # noqa: E402
from edfinder_api.deps import get_readonly_pool  # noqa: E402
from edfinder_api.mechanics import cp_rules  # noqa: E402
from edfinder_api.routers import plan  # noqa: E402
from edfinder_api.routers.v3 import GenerationV1  # noqa: E402


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
        bodies=tuple(Body(**{key: value for key, value in item.items() if key != 'economy'})
                     for item in body.get('bodies', [])),
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
    cited.update(
        rule_id for view in ('now', 'after_plan') for port in body['economies'][view]
        for economy in port['economies'] for item in economy['items'] for rule_id in item['rule_ids']
    )
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
    assert response.status_code == 400
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
    assert response.status_code == 400
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


@pytest.mark.parametrize('lifecycle_state', ('ACTIVE', 'MISSING_CANDIDATE', 'RETIRED'))
def test_plan_belt_lifecycle_is_required_and_preserved(lifecycle_state):
    belt = {
        'belt_id': '1', 'name': 'Test A Belt', 'parent_body_id': '2',
        'ring_type': None, 'reserve': None, 'mass_mt': None,
        'inner_radius_km': None, 'outer_radius_km': None,
    }
    with pytest.raises(ValidationError, match='lifecycle_state'):
        plan.PlanSystemBeltV1(**belt)
    parsed = plan.PlanSystemBeltV1(**belt, lifecycle_state=lifecycle_state)
    assert parsed.model_dump()['lifecycle_state'] == lifecycle_state


def test_openapi_documents_operations_invalid_response_and_database_dependencies():
    app = _test_app()
    operations = app.openapi()['paths']
    assert operations['/api/v1/plan/catalogue']['get']['operationId'] == 'getV3PlanCatalogue'
    bodies = operations['/api/v1/plan/systems/{system_id}/bodies']['get']
    assert bodies['operationId'] == 'listV3PlanBodies'
    assert bodies['responses']['200']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/PlanBodiesV1',
    }
    assert 'belts' in app.openapi()['components']['schemas']['PlanBodiesV1']['properties']
    belt_schema = app.openapi()['components']['schemas']['PlanSystemBeltV1']
    assert belt_schema['properties']['lifecycle_state']['type'] == 'string'
    assert 'lifecycle_state' in belt_schema['required']
    system_id = next(parameter for parameter in bodies['parameters'] if parameter['name'] == 'system_id')
    assert system_id['in'] == 'path'
    assert system_id['required'] is True
    assert system_id['schema']['type'] == 'string'
    assert system_id['schema']['pattern'] == '^[0-9]{1,19}$'
    evaluate = operations['/api/v1/plan/evaluate']['post']
    assert evaluate['operationId'] == 'evaluateV3Plan'
    assert evaluate['responses']['400']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/PlanInvalidV1',
    }
    # Malformed bodies keep FastAPI's own 422 shape, documented separately.
    assert evaluate['responses']['422']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/HTTPValidationError',
    }
    # FastAPI includes routers lazily; inspect their concrete API routes.
    routes = [route for route in plan.router.routes if isinstance(route, APIRoute)]
    assert {route.path for route in routes} == {
        '/api/v1/plan/catalogue', '/api/v1/plan/evaluate',
        '/api/v1/plan/systems/{system_id}/bodies',
    }
    for route in routes:
        pending = list(route.dependant.dependencies)
        dependency_calls = []
        while pending:
            dependency = pending.pop()
            dependency_calls.append(dependency.call)
            pending.extend(dependency.dependencies)
        if route.path == '/api/v1/plan/systems/{system_id}/bodies':
            assert dependency_calls == [get_readonly_pool]
        else:
            # Catalogue/evaluate remain strictly dependency-free, including
            # indirect dependencies that could accidentally acquire a pool.
            assert not dependency_calls
            assert not route.dependant.dependencies


def test_plan_sql_reads_only_body_mechanics_from_derived_and_no_application_or_spatial():
    source = ast.parse((ROOT / 'apps/api/src/routers/plan.py').read_text(encoding='utf-8'))
    sql_texts = []
    for node in ast.walk(source):
        if isinstance(node, ast.JoinedStr):
            text = ''.join(
                part.value for part in node.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
        else:
            continue
        if re.search(r'\b(?:SELECT|FROM|JOIN)\b', text, re.IGNORECASE):
            sql_texts.append(text)
    assert sql_texts, 'The canonical bodies queries must be covered by this guard'
    for text in sql_texts:
        assert not re.search(r'\bv3_(?:app|spatial)\b', text, re.IGNORECASE), text
        derived = re.findall(r'\bv3_derived\.(\w+)', text, re.IGNORECASE)
        assert set(derived) <= {'body_mechanics'}, text
        if derived:
            assert 'derived_generation_id=$1 AND system_id64=$2' in text


def test_economy_openapi_schemas_mirror_core_and_forbid_extra_inputs():
    schemas = _test_app().openapi()['components']['schemas']
    for schema, dataclass in (
        ('PortEconomyV1', PortEconomy), ('EconomyV1', Economy),
        ('EconomyItemV1', EconomyItem), ('EconomyNoteV1', EconomyNote),
    ):
        assert set(schemas[schema]['properties']) == {field.name for field in fields(dataclass)}
    assert set(schemas['EconomyModifierV1']['properties']) == {'condition', 'delta'}
    assert schemas['PlanEvaluationV1']['properties']['economies'] == {
        '$ref': '#/components/schemas/PlanEconomiesV1',
    }
    for name in ('PlanBodyEconomyV1', 'PlanSystemEconomyV1'):
        assert schemas[name]['additionalProperties'] is False
    assert 'economy' in schemas['PlanBodyV1']['properties']
    assert 'system_economy' in schemas['PlanRequestV1']['properties']
    assert {'economy_facts_generation_id', 'reserve_level', 'has_black_hole',
            'has_white_dwarf', 'has_neutron_star', 'economy_notes'} <= set(
        schemas['PlanBodiesV1']['properties'],
    )
    assert {'economy_kind', 'economy_parent_id', 'in_binary_pair', 'tidally_locked',
            'volcanism_present', 'terraformable'} <= set(schemas['PlanSystemBodyV1']['properties'])


@pytest.mark.parametrize('publication', ['matching', 'missing', 'different'])
async def test_bodies_economy_generation_gate_and_active_flags(monkeypatch, publication):
    canonical_id = UUID('00000000-0000-0000-0000-000000000001')
    derived_id = UUID('00000000-0000-0000-0000-000000000002')
    rows = [{
        'body_pk': index, 'name': f'Body {index}', 'direct_parent_body_pk': None,
        'body_type': 'Star', 'is_main_star': index == 1, 'is_landable': False,
        'radius_km': None, 'surface_gravity_g': None, 'surface_temperature_k': None,
        'atmosphere': None, 'terraforming_state': None, 'volcanism': None,
        'distance_from_arrival_ls': None, 'signals_complete': None,
        'lifecycle_state': 'ACTIVE' if index == 1 else 'RETIRED',
    } for index in (1, 2)]
    mechanics = [{
        'body_pk': index, 'body_class': 'Black Hole' if index == 1 else 'Neutron Star',
        'spectral_class': None, 'luminosity_class': None, 'volcanism': False,
        'terraformable': False, 'tidally_locked': None,
        'reserve_level': 'pristine' if index == 1 else 'low',
    } for index in (1, 2)]

    async def canonical(_pool):
        return 'v3_gen_fixture', generation

    # Canonical API identity is a string, while asyncpg returns UUID columns.
    generation = GenerationV1(
        generation_id=str(canonical_id), generation_key='fixture',
        publication_sequence='1', published_at='2026-11-01T00:00:00+00:00',
    )
    monkeypatch.setattr(plan, 'current_canonical_generation', canonical)
    bounded_calls = []

    async def bounded(operation):
        bounded_calls.append(operation)
        return await operation

    monkeypatch.setattr(plan, '_bounded', bounded)

    class Pool:
        mechanics_reads = 0

        async def fetchrow(self, sql):
            assert 'JOIN v3_meta.derived_generation d USING(derived_generation_id)' in sql
            assert "d.lifecycle_state='PUBLISHED'" in sql
            if publication == 'missing':
                return None
            return {'derived_generation_id': derived_id,
                    'canonical_generation_id': canonical_id if publication == 'matching' else derived_id}

        async def fetch(self, sql, *args):
            if 'FROM v3_derived.body_mechanics' in sql:
                assert args == (derived_id, 42)
                self.mechanics_reads += 1
                return mechanics
            assert args == (42,)
            if 'FROM v3_gen_fixture.bodies body' in sql:
                return rows
            return []

    pool = Pool()
    result = (await plan.bodies('42', pool)).model_dump()
    assert result['generation_id'] == str(canonical_id)
    assert [body['name'] for body in result['bodies']] == ['Body 1', 'Body 2']
    if publication == 'matching':
        assert pool.mechanics_reads == 1
        assert len(bounded_calls) == 6
        assert result['economy_facts_generation_id'] == str(derived_id)
        assert result['has_black_hole'] is True
        assert result['has_neutron_star'] is False
        assert result['has_white_dwarf'] is False
        assert result['reserve_level'] == 'pristine'
        assert result['bodies'][0]['economy_kind'] == 'black_hole'
        assert result['bodies'][0]['volcanism_present'] is False
        assert result['bodies'][0]['terraformable'] is False
    else:
        assert pool.mechanics_reads == 0
        assert len(bounded_calls) == 5
        for field in ('economy_facts_generation_id', 'reserve_level', 'has_black_hole',
                      'has_white_dwarf', 'has_neutron_star'):
            assert result[field] is None
        for body in result['bodies']:
            for field in ('economy_kind', 'economy_parent_id', 'in_binary_pair',
                          'tidally_locked', 'volcanism_present', 'terraformable'):
                assert body[field] is None
    assert result['economy_notes'] == []


async def test_economy_wregoe_a5_answer_key_and_citations(client):
    def site(site_id, facility_id, body_ref='A'):
        template = planner_facilities()[facility_id]
        return _site(
            site_id, facility_id, body_ref=body_ref,
            slot_kind='surface' if template.allowed_location == 'surface' else 'orbital',
        )

    weak_facilities = {
        'Extraction': ('orbital_installation_mining_outpost', 7),
        'Industrial': ('surface_settlement_industrial_t1_s', 3),
        'HighTech': ('orbital_installation_relay_station', 5),
        'Military': ('orbital_installation_security_station', 4),
        'Refinery': ('refinery', 1),
        'Agriculture': ('orbital_installation_space_farm', 1),
    }
    sites = [
        site('dodec', 'dodecahedron_t3'), site('planetary', 'planetary_port'),
        site('mine', 'orbital_installation_mining_outpost'),
        site('security', 'orbital_installation_security_station'),
        site('government', 'orbital_installation_government'),
        site('extraction', 'surface_settlement_extraction_t2_l'),
        *(site(f'refinery-{i}', 'refinery') for i in range(3)),
        *(site(f'weak-{name}-{i}', facility, 'remote')
          for name, (facility, count) in weak_facilities.items() for i in range(count)),
    ]
    facts = {
        'kind': 'high_metal_content_world', 'tidally_locked': False,
        'volcanism': False, 'terraformable': False,
        'geological_signals': 0, 'biological_signals': 0,
    }
    bodies = [
        _body(body_ref='star', economy={**facts, 'kind': 'other_star'}),
        _body(economy={**facts, 'parent_ref': 'star', 'tidally_locked': True,
                       'volcanism': True, 'geological_signals': 3}),
        _body(body_ref='remote', economy=facts),
    ]
    payload = _request(sites=sites, bodies=bodies, system_economy={'reserve': 'pristine'})
    response = await client.post('/api/v1/plan/evaluate', json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    dodec, planetary = result['economies']['now']
    assert {item['name']: item['strength'] for item in dodec['economies']} == {
        'Extraction': 6.95, 'Refinery': 3.65, 'Industrial': 3.15,
        'Military': 1.0, 'HighTech': 0.25, 'Agriculture': 0.05,
    }
    assert {item['name']: item['strength'] for item in planetary['economies']} == {
        'Extraction': 3.75, 'Refinery': 3.65, 'Industrial': 1.55,
        'HighTech': 0.25, 'Military': 0.2, 'Agriculture': 0.05,
    }
    assert (dodec['role'], planetary['role']) == ('main', 'remaining_planetary')
    expected = evaluate_economies(
        _core_plan(payload).sites,
        tuple(EconomyBody(item['body_ref'], **item['economy']) for item in bodies),
        EconomySystem('pristine'), 'now',
    )
    # Field-by-field wire parity includes link provenance and tuple modifiers
    # exposed as named objects, rather than losing the engine's explanation.
    expected_ports = json.loads(json.dumps([asdict(port) for port in expected.ports]))
    for port in expected_ports:
        for economy in port['economies']:
            for item in economy['items']:
                item['modifiers'] = [
                    {'condition': condition, 'delta': delta}
                    for condition, delta in item['modifiers']
                ]
    assert result['economies']['now'] == result['economies']['after_plan'] == expected_ports
    cited = {
        rule_id for port in expected_ports for economy in port['economies']
        for item in economy['items'] for rule_id in item['rule_ids']
    }
    assert {'RB-0010', 'RB-0018', 'RB-0029'} <= cited
    for rule_id in cited:
        assert result['explanations'][rule_id] == explain_rule(rule_id)


async def test_economy_views_count_planned_and_building_only_after_plan(client):
    response = await client.post('/api/v1/plan/evaluate', json=_request(
        bodies=[_body(economy={'kind': 'high_metal_content_world'})],
        sites=[
            _site(body_ref='A'),
            _site('mine', 'orbital_installation_mining_outpost', body_ref='A', status='planned'),
            _site('building', 'orbital_outpost_civilian', body_ref='A', status='building'),
            _site('removed', 'orbital_outpost_civilian', body_ref='A', status='demolished'),
        ],
    ))
    assert response.status_code == 200, response.text
    economies = response.json()['economies']
    assert [port['site_id'] for port in economies['now']] == ['primary']
    assert [port['site_id'] for port in economies['after_plan']] == ['primary', 'building']
    now_items = economies['now'][0]['economies'][0]['items']
    after_items = economies['after_plan'][0]['economies'][0]['items']
    assert not any('mine' in item['source_site_ids'] for item in now_items)
    assert any('mine' in item['source_site_ids'] for item in after_items)


async def test_economy_missing_facts_notes_are_unique_in_first_seen_order(client):
    payload = _request(
        bodies=[_body(), _body(body_ref='B')],
        sites=[_site(body_ref='A'), _site('planned', body_ref='B', status='planned')],
    )
    response = await client.post('/api/v1/plan/evaluate', json=payload)
    assert response.status_code == 200, response.text
    sites = _core_plan(payload).sites
    bodies = (EconomyBody('A'), EconomyBody('B'))
    now = evaluate_economies(sites, bodies, EconomySystem(), 'now')
    after = evaluate_economies(sites, bodies, EconomySystem(), 'after_plan')
    notes = response.json()['economies']['notes']
    assert notes == [asdict(note) for note in dict.fromkeys((*now.notes, *after.notes))]
    assert [note['body_ref'] for note in notes if note['code'] == 'unknown_body_kind'] == ['A', 'B']
    assert sum(note['code'] == 'unknown_reserve' for note in notes) == 1


@pytest.mark.parametrize('economy', [
    {}, {field.name: None for field in fields(EconomyBody) if field.name != 'body_ref'},
])
async def test_economy_fields_are_optional_and_nullable(client, economy):
    response = await client.post('/api/v1/plan/evaluate', json=_request(
        bodies=[_body(economy=economy)], sites=[_site(body_ref='A')],
    ))
    assert response.status_code == 200, response.text


@pytest.mark.parametrize('economy', [
    {'kind': 'water_giant'}, {'parent_ref': ''}, {'parent_ref': 'x' * 65},
    {'geological_signals': -1}, {'biological_signals': 1001},
    {'geological_signals': True}, {'biological_signals': '3'},
    {'has_rings': 1}, {'in_binary_pair': 'true'}, {'tidally_locked': 0},
    {'volcanism': 'false'}, {'terraformable': 1}, {'unknown': True},
])
async def test_invalid_economy_body_facts_are_422(client, economy):
    response = await client.post('/api/v1/plan/evaluate', json=_request(
        bodies=[_body(economy=economy)],
    ))
    assert response.status_code == 422, response.text


@pytest.mark.parametrize('economy', [
    {'reserve': 'Pristine'}, {'has_black_hole': 'true'}, {'has_white_dwarf': None},
    {'has_neutron_star': 1}, {'unknown': True},
])
async def test_invalid_economy_system_facts_are_422(client, economy):
    response = await client.post('/api/v1/plan/evaluate', json=_request(system_economy=economy))
    assert response.status_code == 422, response.text


@pytest.mark.parametrize('failing_view', ['now', 'after_plan'])
async def test_economy_value_error_uses_existing_plan_invalid_shape(client, monkeypatch, failing_view):
    def failing_economies(*args, view):
        if view == failing_view:
            raise ValueError('Economy input failed.')
        return evaluate_economies(*args, view=view)

    monkeypatch.setattr(plan, 'evaluate_economies', failing_economies)
    response = await client.post('/api/v1/plan/evaluate', json=_request())
    assert response.status_code == 400
    assert response.json() == {'error': 'plan_invalid', 'issues': [{
        'code': 'ECONOMY_INPUT', 'site_id': None, 'message': 'Economy input failed.',
    }]}


def test_evaluate_has_sixty_per_minute_rate_limit():
    endpoint = next(
        route.endpoint for route in plan.router.routes
        if isinstance(route, APIRoute) and route.path == '/api/v1/plan/evaluate'
    )
    limits = limiter._route_limits[f'{endpoint.__module__}.{endpoint.__name__}']
    assert [str(limit.limit) for limit in limits] == ['60 per 1 minute']
