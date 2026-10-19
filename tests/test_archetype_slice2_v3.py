"""F3 slice 2: `/rerank`, `/system/{id64}`, `/simulate` and `/profiles` read
the published V3 projections (generation-pinned) with the same fail-closed
product gate as slice 1, validate every request before touching the database,
and carry the ranking-identity block.

Fixture/harness mirrors tests/test_archetype_system_v3.py: a disposable PG18
database from `tests.ratings_v4_pg_fixture.canonical_database`, the F1 Search
and F2d wide-row Archetype products built/validated against one Ratings V4
generation, then published so `v3_app.*` exposes them.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import uuid

from fastapi import FastAPI, HTTPException
import httpx
import pytest
import pytest_asyncio


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("CORS_ORIGINS", "https://archetype-slice2-v3-test.invalid")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps/api/src"))

from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.production_generation import (  # noqa: E402
    create_generation,
    seal_source,
    validate_generation,
    write_chunk,
)
import scripts.v3_system_archetype as archetype_builder  # noqa: E402
from scripts.v3_system_search import (  # noqa: E402
    build_available as search_build_available,
    register_product as search_register_product,
    validate_product as search_validate_product,
)
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402

from edfinder_api.config import limiter  # noqa: E402
from edfinder_api.ranking.profile import (  # noqa: E402
    ARCHETYPE_KEYS,
    RANKING_VERSION,
    ranking_sha256,
)
from edfinder_api.ranking.rerank import WEIGHTED_E4_SCALE, equal_weights  # noqa: E402
from edfinder_api.routers import archetypes  # noqa: E402


@pytest.fixture
def database():
    with canonical_database() as (connection, canonical, metadata, payloads):
        for name in (
            "003_ratings_v4_derived.sql",
            "004_v3_search_spatial_clusters.sql",
            "006_v3_derived_product_lifecycle.sql",
            "010_v3_system_search_body_type_counts.sql",
            "011_v3_system_archetype.sql",
            "015_v3_derived_product_publication.sql",
        ):
            connection.execute((ROOT / "sql/v3/migrations" / name).read_text())
        yield connection, canonical, metadata, payloads


def _ratings_generation(database, *, chunk_size: int = 4):
    connection, _, _, payloads = database
    snapshot = CanonicalSnapshot.pin(connection)
    key = "archetype_slice2_v3_test_" + uuid.uuid4().hex
    generation_id = create_generation(connection, snapshot, key)
    records = [payload["system"] for payload in payloads]
    for ordinal, start in enumerate(range(0, len(records), chunk_size)):
        chunk = records[start : start + chunk_size]
        canonical = snapshot.export_chunk(
            connection, [record["id64"] for record in chunk],
        )
        assert write_chunk(
            connection, generation_id, ordinal, canonical, snapshot.metadata, chunk,
        )
    return key, generation_id, snapshot


def _eof_receipt(database):
    _, canonical, metadata, _ = database
    return {
        "consumed_to_eof": True,
        "artifact_sha256": metadata["artifact"]["content_sha256"].removeprefix("\\x"),
        "size_bytes": metadata["artifact"]["size_bytes"],
        "systems": len(canonical["systems"]),
        "bodies": len(canonical["bodies"]),
    }


def _build_ready_generation(database):
    connection, _, _, _ = database
    key, generation_id, snapshot = _ratings_generation(database)
    search_generation, _, search_manifest_sha = search_register_product(connection, key)
    search_build_available(connection, search_generation, search_manifest_sha)
    seal_source(connection, generation_id, _eof_receipt(database))
    assert validate_generation(connection, generation_id)["status"] == "VERIFIED"
    assert search_validate_product(
        connection, search_generation, search_manifest_sha,
    )["status"] == "VERIFIED"
    archetype_generation, _, archetype_manifest_sha = (
        archetype_builder.register_product(connection, key)
    )
    archetype_builder.build_available(
        connection, archetype_generation, archetype_manifest_sha,
    )
    assert archetype_builder.validate_product(
        connection, archetype_generation, archetype_manifest_sha,
    )["status"] == "VERIFIED"
    return generation_id, snapshot


def _publish(connection, generation_id, snapshot):
    return connection.execute(
        "SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            generation_id, None, 0,
            snapshot.generation_id, snapshot.publication_sequence,
            "test", "slice 2 fixture", ["system_search", "system_archetype"],
        ),
    ).fetchone()[0]


async def _asyncpg_pool(connection):
    import asyncpg
    from psycopg.conninfo import conninfo_to_dict

    settings = conninfo_to_dict(os.environ["RATINGS_V4_VALIDATION_DATABASE_URL"])
    return await asyncpg.create_pool(
        host=settings.get("host"),
        port=int(settings.get("port", 5432)),
        user=settings.get("user"),
        password=settings.get("password"),
        database=connection.info.dbname,
        min_size=1,
        max_size=3,
        statement_cache_size=0,
    )


def _test_app() -> FastAPI:
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(archetypes.router)
    return app


def _published_identity(connection, generation_id):
    row = connection.execute(
        """
        SELECT c.publication_sequence,
               p.product_version,
               encode(p.manifest_sha256, 'hex'),
               p.manifest ->> 'archetype_model_sha256'
          FROM v3_meta.current_derived_generation c
          JOIN v3_meta.derived_product p USING (derived_generation_id)
         WHERE c.derived_generation_id = %s
           AND p.product_code = 'system_archetype'
           AND p.lifecycle_state = 'READY'
           AND p.published_at IS NOT NULL
        """,
        (generation_id,),
    ).fetchone()
    return {
        "ranking_version": RANKING_VERSION,
        "ranking_sha256": ranking_sha256(),
        "derived_generation_id": str(generation_id),
        "publication_sequence": row[0],
        "archetype_version": row[1],
        "archetype_manifest_sha256": row[2],
        "archetype_model_sha256": row[3],
    }


def _wide_rows(connection):
    cursor = connection.execute(
        "SELECT * FROM v3_app.system_archetype ORDER BY system_id64"
    )
    columns = [description.name for description in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _search_row(connection, id64):
    cursor = connection.execute(
        "SELECT * FROM v3_app.system_search WHERE system_id64 = %s", (id64,)
    )
    columns = [description.name for description in cursor.description]
    return dict(zip(columns, cursor.fetchone(), strict=True))


@pytest_asyncio.fixture
async def published_client(database, monkeypatch):
    connection, _, _, _ = database
    generation_id, snapshot = _build_ready_generation(database)
    assert _publish(connection, generation_id, snapshot) == 1
    pool = await _asyncpg_pool(connection)
    monkeypatch.setattr(archetypes, "get_pool", lambda: pool)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app()),
            base_url="http://test",
        ) as client:
            yield client, connection, generation_id
    finally:
        await pool.close()


# ---------------------------------------------------------------------------
# POST /api/archetypes/rerank
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rerank_default_blend_matches_stored_keys_and_carries_identity(
    published_client,
):
    client, connection, generation_id = published_client
    stored = _wide_rows(connection)
    assert len(stored) >= 3
    by_id = {row["system_id64"]: row for row in stored}
    unknown = 2**63 - 1
    id64s = [row["system_id64"] for row in stored] + [unknown]

    response = await client.post("/api/archetypes/rerank", json={"id64s": id64s})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["archetype"] is None
    assert body["profile_applied"] is None
    assert body["weights_applied"] == equal_weights()
    assert body["missing_id64s"] == [unknown]
    assert body["ranking"] == _published_identity(connection, generation_id)
    assert len(body["results"]) == len(stored)

    def blend(row):
        return sum(row[f"{key}_weighted_e4"] for key in ARCHETYPE_KEYS) / len(ARCHETYPE_KEYS)

    expected_order = sorted(by_id, key=lambda i: (-blend(by_id[i]), i))
    assert [r["id64"] for r in body["results"]] == expected_order
    for result in body["results"]:
        row = by_id[result["id64"]]
        assert result["reranked_score"] == round(blend(row) / WEIGHTED_E4_SCALE)
        assert result["original_score"] == float(row["best_colony_potential"])
        assert result["completeness"] == pytest.approx(row["completeness_ppm"] / 1e6)
        assert result["primary_archetype"] == row["primary_archetype"]
        assert result["secondary_archetype"] == row["secondary_archetype"]
        assert result["tier"] in ("S", "A", "B", "C", "D")
        assert set(result) == {
            "id64", "reranked_score", "tier", "original_score", "confidence",
            "completeness", "primary_archetype", "secondary_archetype",
        }


@pytest.mark.asyncio
async def test_rerank_picked_archetype_defaults_to_that_fit_and_profile_wins(
    published_client,
):
    client, connection, _ = published_client
    stored = _wide_rows(connection)
    by_id = {row["system_id64"]: row for row in stored}
    id64s = list(by_id)

    picked = await client.post(
        "/api/archetypes/rerank", json={"id64s": id64s, "archetype": "mining_hub"},
    )
    assert picked.status_code == 200, picked.text
    body = picked.json()
    assert body["archetype"] == "mining_hub"
    assert body["weights_applied"]["mining_hub"] == 1.0
    assert sum(body["weights_applied"].values()) == 1.0
    expected = sorted(by_id, key=lambda i: (-by_id[i]["mining_hub_weighted_e4"], i))
    assert [r["id64"] for r in body["results"]] == expected
    for result in body["results"]:
        row = by_id[result["id64"]]
        assert result["original_score"] == float(row["mining_hub_score"])
        assert result["reranked_score"] == round(
            row["mining_hub_weighted_e4"] / WEIGHTED_E4_SCALE
        )
        assert result["confidence"] == pytest.approx(
            row["mining_hub_confidence_ppm"] / 1e6, abs=1e-4,
        )

    # An explicit profile takes precedence over explicit weights, as documented.
    both = await client.post(
        "/api/archetypes/rerank",
        json={
            "id64s": id64s[:1],
            "profile": "generalist",
            "weights": {**{key: 0.0 for key in ARCHETYPE_KEYS}, "paradise": 1.0},
        },
    )
    assert both.status_code == 200, both.text
    assert both.json()["profile_applied"] == "generalist"
    assert both.json()["weights_applied"] == equal_weights()


class _NeverAcquire:
    """A pool stub that fails the test if any route reaches the database."""

    def acquire(self):
        raise AssertionError("database must not be touched for an invalid request")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    (
        {"id64s": [1], "profile": "industrial_empire"},                    # legacy preset id
        {"id64s": [1], "archetype": "refinery_industrial"},                # legacy key
        {"id64s": [1], "weights": {"purity": 1.0}},                        # legacy dimension
        {"id64s": [1], "weights": {key: 0.0 for key in ARCHETYPE_KEYS}},   # all zero
        {"id64s": [1], "weights": {**equal_weights(), "paradise": 1.5}},   # out of range
        {"id64s": []},
        {"id64s": [-1]},
        {"id64s": [2**63]},
        {"id64s": list(range(501))},
        {"id64s": [1], "profile": ""},
    ),
)
async def test_rerank_rejects_invalid_requests_before_database(monkeypatch, payload):
    monkeypatch.setattr(archetypes, "get_pool", lambda: _NeverAcquire())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_test_app()), base_url="http://test",
    ) as client:
        response = await client.post("/api/archetypes/rerank", json=payload)
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# GET /api/archetypes/system/{id64}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_system_detail_matches_wide_row_and_search_facts(published_client):
    client, connection, generation_id = published_client
    stored = _wide_rows(connection)[0]
    id64 = stored["system_id64"]
    search = _search_row(connection, id64)

    response = await client.get(f"/api/archetypes/system/{id64}")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["id64"] == id64
    assert body["name"] == search["name"]
    assert body["coords"] == {"x": search["x_ly"], "y": search["y_ly"], "z": search["z_ly"]}
    assert body["distance_to_sol"] == pytest.approx(
        (search["x_ly"] ** 2 + search["y_ly"] ** 2 + search["z_ly"] ** 2) ** 0.5, abs=0.01,
    )
    assert body["main_star_class"] == search["main_star_class"]
    assert body["galaxy_region_id"] == search["galaxy_region_id"]
    assert body["galaxy_region"] == search["region_name"]
    assert body["confidence"] == search["confidence"]
    assert body["completeness"] == search["completeness"]
    assert set(body["archetypes"]) == set(ARCHETYPE_KEYS)
    for key, entry in body["archetypes"].items():
        assert entry["score"] == stored[f"{key}_score"]
        assert entry["tier"] == stored[f"{key}_tier"]
        assert entry["confidence"] == pytest.approx(stored[f"{key}_confidence_ppm"] / 1e6)
        assert entry["weighted_e4"] == stored[f"{key}_weighted_e4"]
        assert entry["label"] == archetypes._V3_ARCHETYPE_LABELS[key]
        assert "rationale" not in entry
    assert body["primary_archetype"] == stored["primary_archetype"]
    assert body["secondary_archetype"] == stored["secondary_archetype"]
    assert body["archetype_confidence"] == pytest.approx(
        stored["archetype_confidence_ppm"] / 1e6,
    )
    assert body["overall_development_potential"] == stored["best_colony_potential"]
    assert body["best_tier"] == stored["best_tier"]
    assert body["weighted_potential"] == stored["weighted_potential"]
    assert body["facts"]["body_count"] == search["body_count"]
    assert body["facts"]["landable_count"] == search["landable_count"]
    assert body["facts"]["elw_count"] == search["elw_count"]
    assert body["facts"]["has_rings"] == search["has_rings"]
    assert body["ranking"] == _published_identity(connection, generation_id)
    # Retired V2-only fields must not be present at all (not null-degraded).
    for retired in ("topology", "economy_pairs", "tags", "buildability_score",
                    "purity_score", "contamination_risk", "main_star_type"):
        assert retired not in body


@pytest.mark.asyncio
async def test_system_detail_unknown_system_is_404(published_client):
    client, _, _ = published_client
    response = await client.get(f"/api/archetypes/system/{2**63 - 1}")
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("id64", (-1, 2**63))
async def test_system_detail_path_bounds_precede_database(monkeypatch, id64):
    monkeypatch.setattr(archetypes, "get_pool", lambda: _NeverAcquire())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_test_app()), base_url="http://test",
    ) as client:
        response = await client.get(f"/api/archetypes/system/{id64}")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/archetypes/simulate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_simulate_scores_planned_archetype_from_stored_fit(published_client):
    client, connection, generation_id = published_client
    stored = _wide_rows(connection)[0]
    id64 = stored["system_id64"]
    primary = stored["primary_archetype"]
    planned = next(key for key in ARCHETYPE_KEYS if key != primary)

    response = await client.post(
        "/api/archetypes/simulate",
        json={
            "id64": id64,
            "planned_archetype": planned,
            "planned_facilities": [{"type": "StarPort", "tier": 3}],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["simulation_score"] == stored[f"{planned}_score"]
    assert body["tier"] == stored[f"{planned}_tier"]
    assert body["confidence"] == pytest.approx(stored[f"{planned}_confidence_ppm"] / 1e6)
    assert body["primary_archetype"] == primary
    assert body["best_colony_potential"] == stored["best_colony_potential"]
    assert body["disclaimer"] == archetypes._SIMULATE_DISCLAIMER
    assert any(archetypes._V3_ARCHETYPE_LABELS[primary] in rec for rec in body["recommendations"])
    assert any("1 T3 facilities" in rec for rec in body["recommendations"])
    assert body["ranking"] == _published_identity(connection, generation_id)
    for retired in ("contamination_risk", "purity_score", "buildability_score"):
        assert retired not in body

    aligned = await client.post(
        "/api/archetypes/simulate", json={"id64": id64, "planned_archetype": primary},
    )
    assert aligned.status_code == 200, aligned.text
    assert aligned.json()["simulation_score"] == stored[f"{primary}_score"]
    assert not any("rates this system strongest" in rec for rec in aligned.json()["recommendations"])

    missing = await client.post(
        "/api/archetypes/simulate", json={"id64": 2**63 - 1, "planned_archetype": planned},
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    (
        {"id64": 1, "planned_archetype": "agriculture_terraforming"},   # legacy key
        {"id64": -1, "planned_archetype": "paradise"},
        {"id64": 2**63, "planned_archetype": "paradise"},
        {"id64": 1, "planned_archetype": "paradise",
         "planned_facilities": [{"type": "StarPort", "tier": 4}]},
        {"id64": 1},
    ),
)
async def test_simulate_rejects_invalid_requests_before_database(monkeypatch, payload):
    monkeypatch.setattr(archetypes, "get_pool", lambda: _NeverAcquire())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_test_app()), base_url="http://test",
    ) as client:
        response = await client.post("/api/archetypes/simulate", json=payload)
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# GET /api/archetypes/profiles
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_profiles_are_v3_presets_and_each_resolves_in_rerank(published_client):
    client, connection, _ = published_client
    id64 = _wide_rows(connection)[0]["system_id64"]

    response = await client.get("/api/archetypes/profiles")
    assert response.status_code == 200, response.text
    profiles = response.json()["profiles"]
    assert [p["id"] for p in profiles] == [*ARCHETYPE_KEYS, "generalist"]
    for profile in profiles:
        assert set(profile["weights"]) == set(ARCHETYPE_KEYS)
        assert profile["archetype"] in (*ARCHETYPE_KEYS, None)
        reranked = await client.post(
            "/api/archetypes/rerank", json={"id64s": [id64], "profile": profile["id"]},
        )
        assert reranked.status_code == 200, reranked.text
        assert reranked.json()["profile_applied"] == profile["id"]
        assert reranked.json()["weights_applied"] == profile["weights"]


# ---------------------------------------------------------------------------
# Fail-closed availability
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_slice2_routes_are_404_without_a_published_generation(database, monkeypatch):
    connection, _, _, _ = database
    _build_ready_generation(database)   # READY but never published
    pool = await _asyncpg_pool(connection)
    monkeypatch.setattr(archetypes, "get_pool", lambda: pool)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app()), base_url="http://test",
        ) as client:
            rerank = await client.post("/api/archetypes/rerank", json={"id64s": [1]})
            detail = await client.get("/api/archetypes/system/1")
            simulate = await client.post(
                "/api/archetypes/simulate", json={"id64": 1, "planned_archetype": "paradise"},
            )
    finally:
        await pool.close()
    for response in (rerank, detail, simulate):
        assert response.status_code == 404, response.text
        assert response.json()["detail"] == "No published Ratings V4 generation"


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _UnpublishedProductConnection:
    """A published generation whose archetype product is not yet published."""

    def transaction(self, *, isolation=None, readonly=True):
        return _FakeTransaction()

    async def fetchrow(self, *_args, **_kwargs):
        return {
            "derived_generation_id": "00000000-0000-0000-0000-000000000001",
            "publication_sequence": 1,
        }

    async def fetch(self, *_args, **_kwargs):
        return [{
            "product_code": "system_search",
            "lifecycle_state": "READY",
            "published_at": "2026-10-13T00:00:00+00:00",
        }]


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_exc):
        return False


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)


@pytest.mark.asyncio
async def test_slice2_read_is_503_until_both_finder_products_are_published():
    with pytest.raises(HTTPException) as excinfo:
        await archetypes._read_system_archetype_rows(
            _Pool(_UnpublishedProductConnection()), [1], surface="Archetype rerank",
        )
    assert excinfo.value.status_code == 503
    assert "system_archetype=MISSING" in excinfo.value.detail


# ---------------------------------------------------------------------------
# OpenAPI contract
# ---------------------------------------------------------------------------

def test_openapi_exposes_v3_archetype_keys_and_response_models():
    spec = _test_app().openapi()
    schemas = spec["components"]["schemas"]
    weights = schemas["ArchetypeRerankWeights"]["properties"]
    assert set(weights) == set(ARCHETYPE_KEYS)
    for legacy in ("purity", "buildability", "slots", "expansion", "logistics"):
        assert legacy not in weights
    request_archetype = schemas["ArchetypeRerankRequest"]["properties"]["archetype"]
    assert any(
        option.get("enum") == list(ARCHETYPE_KEYS)
        for option in request_archetype.get("anyOf", [request_archetype])
    )
    assert schemas["BuildSimulateRequest"]["properties"]["planned_archetype"] == {
        "$ref": "#/components/schemas/ArchetypeKey",
    } or schemas["BuildSimulateRequest"]["properties"]["planned_archetype"].get("enum") == list(
        ARCHETYPE_KEYS
    )
    for path, method, model in (
        ("/api/archetypes/rerank", "post", "ArchetypeRerankResponse"),
        ("/api/archetypes/system/{id64}", "get", "SystemArchetypeResponse"),
        ("/api/archetypes/simulate", "post", "BuildSimulateResponse"),
        ("/api/archetypes/profiles", "get", "ArchetypesProfilesResponse"),
    ):
        operation = spec["paths"][path][method]
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{model}",
        }
        assert "ranking" in schemas[model]["properties"] or model == "ArchetypesProfilesResponse"
    id64 = {p["name"]: p for p in spec["paths"]["/api/archetypes/system/{id64}"]["get"]["parameters"]}["id64"]
    assert id64["schema"]["minimum"] == 0 and id64["schema"]["maximum"] == 2**63 - 1
