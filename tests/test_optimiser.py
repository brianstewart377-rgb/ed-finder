
import pytest
from unittest.mock import AsyncMock

from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager

from apps.api.src.models import OptimiserCandidatesRequest, OptimiserCandidatesResponse
from apps.api.src.recommendations.optimiser_generator import generate_optimiser_candidates
from apps.api.src.simulation.build_preview import PreviewContext
from apps.api.src.domain.facilities import FacilityTemplate


class MockConnection:
    async def fetch(self, query, *args):
        if "SELECT * FROM bodies" in query:
            return [
                {
                    "body_id": "body1",
                    "body_name": "Body 1",
                    "system_id64": 123,
                    "body_type": "Planet",
                    "subtype": "Earthlike World",
                    "is_landable": True,
                    "is_terraformable": False,
                    "distance_from_star": 100,
                    "gravity": 1.0,
                    "mass": 1.0,
                    "radius": 1.0,
                    "surface_temp": 200,
                    "orbital_period": 1.0,
                    "rotational_period": 1.0,
                    "orbital_eccentricity": 0.0,
                    "orbital_inclination": 0.0,
                    "arg_of_periapsis": 0.0,
                    "mean_anomaly": 0.0,
                    "mean_anomaly_epoch": 0.0,
                    "periapsis": 0.0,
                    "apoapsis": 0.0,
                    "atmosphere_type": "None",
                    "volcanism_type": "None",
                    "surface_pressure": 0.0,
                    "materials": {"Iron": 100},
                    "bio_signals": [],
                    "geo_signals": [],
                    "is_colony_candidate": True,
                    "colony_candidate_score": 1.0,
                    "colony_candidate_reason": "Good candidate",
                    "colony_candidate_archetypes": ["flexible_multirole", "extraction_refinery", "agriculture_terraforming"],
                    "economy_profile": {
                        "base_economies": ["Agriculture"],
                        "modifier_economies": ["Terraforming"],
                        "weights": {"Agriculture": 1.0},
                        "purity": 1.0,
                        "confidence": 1.0,
                        "caveats": [],
                        "strategic_tags": ["terraforming_candidate"],
                        "source_body_id": "body1",
                        "source_body_name": "Body 1",
                        "inherited": False,
                    },
                },
            ]
        elif "SELECT * FROM facility_templates" in query:
            return [
                {
                    "id": "colony_ship",
                    "name": "Colony Ship",
                    "category": "Colony",
                    "tier": 1,
                    "is_port": False,
                    "is_colony_port": False,
                    "is_support_facility": False,
                    "yellow_cp_generated": 0,
                    "green_cp_generated": 0,
                    "yellow_cp_cost": 10,
                    "green_cp_cost": 10,
                    "strong_link_value": 0.0,
                    "weak_link_value": 0.0,
                    "allowed_location": "orbital_or_surface",
                    "pad_size": None,
                    "prerequisites": [],
                    "economy_effects": {},
                    "stat_effects": {"data_confidence": "confirmed"},
                    "economy": None,
                },
                {
                    "id": "agriculture_support",
                    "name": "Agriculture Support",
                    "category": "Support",
                    "tier": 1,
                    "is_port": False,
                    "is_colony_port": False,
                    "is_support_facility": True,
                    "yellow_cp_generated": 0,
                    "green_cp_generated": 0,
                    "yellow_cp_cost": 5,
                    "green_cp_cost": 5,
                    "strong_link_value": 0.0,
                    "weak_link_value": 0.0,
                    "allowed_location": "orbital_or_surface",
                    "pad_size": None,
                    "prerequisites": [],
                    "economy_effects": {},
                    "stat_effects": {"data_confidence": "confirmed"},
                    "economy": "Agriculture",
                },
                {
                    "id": "orbis_t3",
                    "name": "Orbis T3",
                    "category": "Port",
                    "tier": 3,
                    "is_port": True,
                    "is_colony_port": False,
                    "is_support_facility": False,
                    "yellow_cp_generated": 0,
                    "green_cp_generated": 0,
                    "yellow_cp_cost": 50,
                    "green_cp_cost": 50,
                    "strong_link_value": 0.0,
                    "weak_link_value": 0.0,
                    "allowed_location": "orbital_or_surface",
                    "pad_size": None,
                    "prerequisites": [],
                    "economy_effects": {},
                    "stat_effects": {"data_confidence": "confirmed"},
                    "economy": None,
                },
                {
                    "id": "coriolis_station",
                    "name": "Coriolis Station",
                    "category": "Port",
                    "tier": 2,
                    "is_port": True,
                    "is_colony_port": False,
                    "is_support_facility": False,
                    "yellow_cp_generated": 0,
                    "green_cp_generated": 0,
                    "yellow_cp_cost": 20,
                    "green_cp_cost": 20,
                    "strong_link_value": 0.0,
                    "weak_link_value": 0.0,
                    "allowed_location": "orbital_or_surface",
                    "pad_size": None,
                    "prerequisites": [],
                    "economy_effects": {},
                    "stat_effects": {"data_confidence": "confirmed"},
                    "economy": None,
                },
                {
                    "id": "planetary_port",
                    "name": "Planetary Port",
                    "category": "Port",
                    "tier": 2,
                    "is_port": True,
                    "is_colony_port": False,
                    "is_support_facility": False,
                    "yellow_cp_generated": 0,
                    "green_cp_generated": 0,
                    "yellow_cp_cost": 20,
                    "green_cp_cost": 20,
                    "strong_link_value": 0.0,
                    "weak_link_value": 0.0,
                    "allowed_location": "orbital_or_surface",
                    "pad_size": None,
                    "prerequisites": [],
                    "economy_effects": {},
                    "stat_effects": {"data_confidence": "confirmed"},
                    "economy": None,
                },
                {
                    "id": "asteroid_base",
                    "name": "Asteroid Base",
                    "category": "Port",
                    "tier": 2,
                    "is_port": True,
                    "is_colony_port": False,
                    "is_support_facility": False,
                    "yellow_cp_generated": 0,
                    "green_cp_generated": 0,
                    "yellow_cp_cost": 20,
                    "green_cp_cost": 20,
                    "strong_link_value": 0.0,
                    "weak_link_value": 0.0,
                    "allowed_location": "orbital_or_surface",
                    "pad_size": None,
                    "prerequisites": [],
                    "economy_effects": {},
                    "stat_effects": {"data_confidence": "confirmed"},
                    "economy": None,
                },
            ]
        return []

    async def fetchrow(self, query, *args):
        if "SELECT * FROM systems" in query:
            return {
                "system_id64": 123,
                "estimated_orbital_slots": 10,
                "estimated_ground_slots": 5,
                "slot_confidence": 0.8,
                "has_ringed_body": True,
            }
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockPool:
    def acquire(self):
        return MockConnection()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def close(self):
        pass


@pytest.fixture
def mock_pool():
    return MockPool()


@pytest.fixture
async def client(mock_pool: MockPool, monkeypatch):
    # Set environment variables for Pydantic Settings
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@host:port/database")

    from apps.api.src.main import app
    from apps.api.src.deps import get_pool
    from apps.api.src.main import lifespan
    import asyncpg
    import redis.asyncio as aioredis

    # Mock asyncpg.create_pool to return our mock_pool
    monkeypatch.setattr(asyncpg, "create_pool", AsyncMock(return_value=mock_pool))

    # Mock aioredis.from_url to return a mock redis client
    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True
    monkeypatch.setattr(aioredis, "from_url", AsyncMock(return_value=mock_redis))

    async with LifespanManager(app):
        # Override the get_pool dependency to return our mock_pool after lifespan has run
        app.dependency_overrides[get_pool] = lambda: mock_pool
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.mark.asyncio
async def test_generate_optimiser_candidates_simple_case(mock_pool: MockPool):
    system_id64 = 123
    target_archetype_key = 'agriculture_terraforming'
    cat = {
        "colony_ship": FacilityTemplate(
            id="colony_ship", name="Colony Ship", category="Colony", tier=1, is_port=False, is_colony_port=False, is_support_facility=False, yellow_cp_generated=0, green_cp_generated=0, yellow_cp_cost=10, green_cp_cost=10, strong_link_value=0.0, weak_link_value=0.0, allowed_location="orbital_or_surface", pad_size=None, prerequisites=[], economy_effects={}, stat_effects={"data_confidence": "confirmed"}, economy=None
        ),
        "agriculture_support": FacilityTemplate(
            id="agriculture_support", name="Agriculture Support", category="Support", tier=1, is_port=False, is_colony_port=False, is_support_facility=True, yellow_cp_generated=0, green_cp_generated=0, yellow_cp_cost=5, green_cp_cost=5, strong_link_value=0.0, weak_link_value=0.0, allowed_location="orbital_or_surface", pad_size=None, prerequisites=[], economy_effects={}, stat_effects={"data_confidence": "confirmed"}, economy="Agriculture"
        ),
        "orbis_t3": FacilityTemplate(
            id="orbis_t3", name="Orbis T3", category="Port", tier=3, is_port=True, is_colony_port=False, is_support_facility=False, yellow_cp_generated=0, green_cp_generated=0, yellow_cp_cost=50, green_cp_cost=50, strong_link_value=0.0, weak_link_value=0.0, allowed_location="orbital_or_surface", pad_size=None, prerequisites=[], economy_effects={}, stat_effects={"data_confidence": "confirmed"}, economy=None
        ),
        "coriolis_station": FacilityTemplate(
            id="coriolis_station", name="Coriolis Station", category="Port", tier=2, is_port=True, is_colony_port=False, is_support_facility=False, yellow_cp_generated=0, green_cp_generated=0, yellow_cp_cost=20, green_cp_cost=20, strong_link_value=0.0, weak_link_value=0.0, allowed_location="orbital_or_surface", pad_size=None, prerequisites=[], economy_effects={}, stat_effects={"data_confidence": "confirmed"}, economy=None
        ),
        "planetary_port": FacilityTemplate(
            id="planetary_port", name="Planetary Port", category="Port", tier=2, is_port=True, is_colony_port=False, is_support_facility=False, yellow_cp_generated=0, green_cp_generated=0, yellow_cp_cost=20, green_cp_cost=20, strong_link_value=0.0, weak_link_value=0.0, allowed_location="orbital_or_surface", pad_size=None, prerequisites=[], economy_effects={}, stat_effects={"data_confidence": "confirmed"}, economy=None
        ),
        "asteroid_base": FacilityTemplate(
            id="asteroid_base", name="Asteroid Base", category="Port", tier=2, is_port=True, is_colony_port=False, is_support_facility=False, yellow_cp_generated=0, green_cp_generated=0, yellow_cp_cost=20, green_cp_cost=20, strong_link_value=0.0, weak_link_value=0.0, allowed_location="orbital_or_surface", pad_size=None, prerequisites=[], economy_effects={}, stat_effects={"data_confidence": "confirmed"}, economy=None
        ),
    }
    max_candidates = 1

    candidates, warnings = await generate_optimiser_candidates(
        system_id64=system_id64,
        target_archetype_key=target_archetype_key,
        catalogue=cat,
        pool=mock_pool,
        max_candidates=max_candidates,
    )

    assert not warnings
    assert len(candidates) == 1
    assert candidates[0]["id"] == "agriculture_terraforming-body1-simple"
    assert candidates[0]["label"] == "Simple recommended build for Body 1"
    assert candidates[0]["archetype"] == "agriculture_terraforming"
    assert len(candidates[0]["placements"]) == 2
    assert candidates[0]["preview_summary"].score >= 0.0


@pytest.mark.asyncio
async def test_generate_optimiser_candidates_multiple_plans(mock_pool: MockPool):
    system_id64 = 123
    target_archetype_key = 'agriculture_terraforming'
    cat = {
        "colony_ship": FacilityTemplate(
            id="colony_ship", name="Colony Ship", category="Colony", tier=1, is_port=False, is_colony_port=False, is_support_facility=False, yellow_cp_generated=0, green_cp_generated=0, yellow_cp_cost=10, green_cp_cost=10, strong_link_value=0.0, weak_link_value=0.0, allowed_location="orbital_or_surface", pad_size=None, prerequisites=[], economy_effects={}, stat_effects={"data_confidence": "confirmed"}, economy=None
        ),
        "agriculture_support": FacilityTemplate(
            id="agriculture_support", name="Agriculture Support", category="Support", tier=1, is_port=False, is_colony_port=False, is_support_facility=True, yellow_cp_generated=0, green_cp_generated=0, yellow_cp_cost=5, green_cp_cost=5, strong_link_value=0.0, weak_link_value=0.0, allowed_location="orbital_or_surface", pad_size=None, prerequisites=[], economy_effects={}, stat_effects={"data_confidence": "confirmed"}, economy="Agriculture"
        ),
        "orbis_t3": FacilityTemplate(
            id="orbis_t3", name="Orbis T3", category="Port", tier=3, is_port=True, is_colony_port=False, is_support_facility=False, yellow_cp_generated=0, green_cp_generated=0, yellow_cp_cost=50, green_cp_cost=50, strong_link_value=0.0, weak_link_value=0.0, allowed_location="orbital_or_surface", pad_size=None, prerequisites=[], economy_effects={}, stat_effects={"data_confidence": "confirmed"}, economy=None
        ),
        "coriolis_station": FacilityTemplate(
            id="coriolis_station", name="Coriolis Station", category="Port", tier=2, is_port=True, is_colony_port=False, is_support_facility=False, yellow_cp_generated=0, green_cp_generated=0, yellow_cp_cost=20, green_cp_cost=20, strong_link_value=0.0, weak_link_value=0.0, allowed_location="orbital_or_surface", pad_size=None, prerequisites=[], economy_effects={}, stat_effects={"data_confidence": "confirmed"}, economy=None
        ),
        "planetary_port": FacilityTemplate(
            id="planetary_port", name="Planetary Port", category="Port", tier=2, is_port=True, is_colony_port=False, is_support_facility=False, yellow_cp_generated=0, green_cp_generated=0, yellow_cp_cost=20, green_cp_cost=20, strong_link_value=0.0, weak_link_value=0.0, allowed_location="orbital_or_surface", pad_size=None, prerequisites=[], economy_effects={}, stat_effects={"data_confidence": "confirmed"}, economy=None
        ),
        "asteroid_base": FacilityTemplate(
            id="asteroid_base", name="Asteroid Base", category="Port", tier=2, is_port=True, is_colony_port=False, is_support_facility=False, yellow_cp_generated=0, green_cp_generated=0, yellow_cp_cost=20, green_cp_cost=20, strong_link_value=0.0, weak_link_value=0.0, allowed_location="orbital_or_surface", pad_size=None, prerequisites=[], economy_effects={}, stat_effects={"data_confidence": "confirmed"}, economy=None
        ),
    }
    max_candidates = 3

    candidates, warnings = await generate_optimiser_candidates(
        system_id64=system_id64,
        target_archetype_key=target_archetype_key,
        catalogue=cat,
        pool=mock_pool,
        max_candidates=max_candidates,
    )

    assert not warnings
    assert len(candidates) == 3
    assert candidates[0]["id"] == "agriculture_terraforming-body1-simple"
    assert candidates[1]["id"] == "agriculture_terraforming-body1-balanced"
    assert candidates[2]["id"] == "agriculture_terraforming-body1-advanced"


@pytest.mark.asyncio
async def test_post_optimiser_candidates_endpoint(client: AsyncClient, mock_pool: MockPool, monkeypatch):
    request_body = OptimiserCandidatesRequest(
        system_id64=123,
        target_archetype_key='agriculture_terraforming',
        max_candidates=1,
    )

    async def mock_generate_optimiser_candidates(**kwargs):
        assert kwargs['system_id64'] == 123
        assert kwargs['target_archetype_key'] == 'agriculture_terraforming'
        assert kwargs['max_candidates'] == 1
        return [
            {
                'id': 'agriculture_terraforming-body1-simple',
                'label': 'Simple recommended build for Body 1',
                'description': 'Deterministic test candidate.',
                'archetype': 'agriculture_terraforming',
                'placements': [
                    {'facility_template_id': 'colony_ship', 'local_body_id': 'body1', 'is_primary_port': True, 'build_order': 1},
                    {'facility_template_id': 'agriculture_support', 'local_body_id': 'body1', 'is_primary_port': False, 'build_order': 2},
                ],
                'preview_summary': {'source': 'computed', 'slot_confidence': 1.0, 'note': 'Test summary'},
                'tradeoffs': [],
            }
        ], []

    monkeypatch.setattr('routers.optimiser.generate_optimiser_candidates', mock_generate_optimiser_candidates)

    response = await client.post('/api/optimiser/candidates', json=request_body.model_dump())

    assert response.status_code == 200
    response_data = OptimiserCandidatesResponse.model_validate(response.json())

    assert not response_data.warnings
    assert len(response_data.candidates) == 1
    assert response_data.candidates[0].id == 'agriculture_terraforming-body1-simple'
    assert response_data.candidates[0].label == 'Simple recommended build for Body 1'
    assert response_data.candidates[0].archetype == 'agriculture_terraforming'
    assert len(response_data.candidates[0].placements) == 2
    assert response_data.candidates[0].preview_summary.slot_confidence == 1.0


@pytest.mark.asyncio
async def test_post_optimiser_candidates_endpoint_unsupported_archetype(client: AsyncClient, mock_pool: MockPool, monkeypatch):
    request_body = OptimiserCandidatesRequest(
        system_id64=123,
        target_archetype_key='unsupported_archetype',
        max_candidates=1,
    )

    async def mock_generate_optimiser_candidates(**kwargs):
        assert kwargs['target_archetype_key'] == 'unsupported_archetype'
        return [], ["Recommended build rules are not implemented for this archetype yet."]

    monkeypatch.setattr('routers.optimiser.generate_optimiser_candidates', mock_generate_optimiser_candidates)

    response = await client.post("/api/optimiser/candidates", json=request_body.model_dump())

    assert response.status_code == 200
    response_data = OptimiserCandidatesResponse.model_validate(response.json())

    assert not response_data.candidates
    assert response_data.warnings == ["Recommended build rules are not implemented for this archetype yet."]


@pytest.mark.asyncio
async def test_post_optimiser_candidates_endpoint_no_body_candidates(client: AsyncClient, mock_pool: MockPool, monkeypatch):
    request_body = OptimiserCandidatesRequest(
        system_id64=123,
        target_archetype_key='agriculture_terraforming',
        max_candidates=1,
    )

    async def mock_generate_optimiser_candidates(**kwargs):
        return [], ["No suitable body candidates found for this archetype."]

    monkeypatch.setattr(
        'routers.optimiser.generate_optimiser_candidates',
        mock_generate_optimiser_candidates,
    )

    response = await client.post("/api/optimiser/candidates", json=request_body.model_dump())

    assert response.status_code == 200
    response_data = OptimiserCandidatesResponse.model_validate(response.json())

    assert not response_data.candidates
    assert response_data.warnings == ["No suitable body candidates found for this archetype."]
