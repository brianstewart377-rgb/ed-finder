"""F2d PR3: version-pinned on-demand V3 archetype explanations."""

from __future__ import annotations

import hashlib
import inspect
import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock
import uuid

from fastapi import FastAPI
import httpx
import pytest
import pytest_asyncio


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("CORS_ORIGINS", "https://archetype-system-v3-test.invalid")
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
from edfinder_api.routers import archetypes  # noqa: E402


LEGACY_HANDLER_SHA256 = (
    "70eb954d12bb320ed211ec160145740d68ee834b942510978e1cbb512eacd8ba"
)


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
    key = "archetype_system_v3_test_" + uuid.uuid4().hex
    generation_id = create_generation(connection, snapshot, key)
    records = [payload["system"] for payload in payloads]
    for ordinal, start in enumerate(range(0, len(records), chunk_size)):
        chunk = records[start : start + chunk_size]
        canonical = snapshot.export_chunk(
            connection,
            [record["id64"] for record in chunk],
        )
        assert write_chunk(
            connection,
            generation_id,
            ordinal,
            canonical,
            snapshot.metadata,
            chunk,
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
    archetype_generation, _, archetype_manifest_sha = (
        archetype_builder.register_product(connection, key)
    )
    archetype_builder.build_available(
        connection,
        archetype_generation,
        archetype_manifest_sha,
    )

    seal_source(connection, generation_id, _eof_receipt(database))
    assert validate_generation(connection, generation_id)["status"] == "VERIFIED"
    assert (
        search_validate_product(
            connection,
            search_generation,
            search_manifest_sha,
        )["status"]
        == "VERIFIED"
    )
    assert (
        archetype_builder.validate_product(
            connection,
            archetype_generation,
            archetype_manifest_sha,
        )["status"]
        == "VERIFIED"
    )
    return generation_id, snapshot


def _publish(
    connection,
    generation_id,
    snapshot,
    *,
    expected_current=None,
    expected_sequence: int = 0,
):
    return connection.execute(
        "SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            generation_id,
            expected_current,
            expected_sequence,
            snapshot.generation_id,
            snapshot.publication_sequence,
            "test",
            "archetype explanation fixture",
            ["system_search", "system_archetype"],
        ),
    ).fetchone()[0]


def _build_published_generation(database):
    connection, _, _, _ = database
    generation_id, snapshot = _build_ready_generation(database)
    assert _publish(connection, generation_id, snapshot) == 1
    return generation_id, snapshot


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


def _valid_response(id64: int) -> dict:
    return {
        "id64": id64,
        "archetypes": [
            {
                "key": key,
                "score": 0,
                "tier": "D",
                "confidence": 0.0,
                "weighted_e4": 0,
                "explanation": {},
            }
            for key in ARCHETYPE_KEYS
        ],
        "summary": {
            "primary_archetype": "paradise",
            "secondary_archetype": None,
            "best_colony_potential": 0,
            "best_tier": "D",
            "archetype_confidence": 0.0,
            "weighted_potential": 0.0,
        },
        "completeness": 0.0,
        "ranking": {
            "ranking_version": RANKING_VERSION,
            "ranking_sha256": ranking_sha256(),
            "derived_generation_id": str(uuid.UUID(int=1)),
            "publication_sequence": 1,
            "archetype_version": "v3-archetype-4",
            "archetype_manifest_sha256": "a" * 64,
            "archetype_model_sha256": "b" * 64,
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("id64", "expected_status"),
    ((-1, 422), (2**63, 422), (0, 200), (2**63 - 1, 200)),
)
async def test_explanation_path_bigint_bounds(
    monkeypatch,
    id64,
    expected_status,
):
    helper = AsyncMock(side_effect=lambda **kwargs: _valid_response(kwargs["id64"]))
    monkeypatch.setattr(archetypes, "_system_archetype_explanation_v3", helper)
    monkeypatch.setattr(archetypes, "get_pool", lambda: object())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_test_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/archetypes/system/{id64}/explanation")
    assert response.status_code == expected_status
    assert helper.await_count == (1 if expected_status == 200 else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ("", "x" * 129))
async def test_expected_archetype_version_validation(monkeypatch, value):
    helper = AsyncMock()
    monkeypatch.setattr(archetypes, "_system_archetype_explanation_v3", helper)
    monkeypatch.setattr(archetypes, "get_pool", lambda: object())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_test_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/archetypes/system/0/explanation",
            params={"expected_archetype_version": value},
        )
    assert response.status_code == 422
    helper.assert_not_awaited()


@pytest.mark.asyncio
async def test_expected_generation_id_validation_precedes_database(monkeypatch):
    helper = AsyncMock()
    monkeypatch.setattr(archetypes, "_system_archetype_explanation_v3", helper)
    monkeypatch.setattr(archetypes, "get_pool", lambda: object())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_test_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/archetypes/system/0/explanation",
            params={"expected_generation_id": "not-a-uuid"},
        )
    assert response.status_code == 422
    helper.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    ("a" * 63, "a" * 65, "A" * 64, "g" * 64),
)
async def test_expected_manifest_sha256_validation(monkeypatch, value):
    helper = AsyncMock()
    monkeypatch.setattr(archetypes, "_system_archetype_explanation_v3", helper)
    monkeypatch.setattr(archetypes, "get_pool", lambda: object())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_test_app()),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/archetypes/system/0/explanation",
            params={"expected_manifest_sha256": value},
        )
    assert response.status_code == 422
    helper.assert_not_awaited()


def test_shared_model_sql_is_converted_mechanically_to_fixed_asyncpg_slots():
    for psycopg_sql, asyncpg_sql in (
        (archetypes.VECTOR_READ_SQL, archetypes._VECTOR_READ_ASYNCPG_SQL),
        (archetypes.OPPORTUNITY_READ_SQL, archetypes._OPPORTUNITY_READ_ASYNCPG_SQL),
    ):
        expected = psycopg_sql
        for index, name in enumerate(archetypes._MODEL_SQL_PARAMETER_ORDER, 1):
            expected = expected.replace(f"%({name})s", f"${index}")
        assert asyncpg_sql == expected
        assert "%(" not in asyncpg_sql
    assert archetypes._VECTOR_READ_ASYNCPG_SQL in (
        archetypes._SYSTEM_ARCHETYPE_READ_SQL
    )
    assert archetypes._OPPORTUNITY_READ_ASYNCPG_SQL in (
        archetypes._SYSTEM_ARCHETYPE_READ_SQL
    )


def test_explanation_openapi_declares_bounds_identity_and_response_model():
    operation = _test_app().openapi()["paths"][
        "/api/archetypes/system/{id64}/explanation"
    ]["get"]
    parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}
    assert parameters["id64"]["schema"]["minimum"] == 0
    assert parameters["id64"]["schema"]["maximum"] == 2**63 - 1
    assert (
        parameters["expected_generation_id"]["schema"]["anyOf"][0]["format"] == "uuid"
    )
    version_schema = parameters["expected_archetype_version"]["schema"]["anyOf"][0]
    assert version_schema["minLength"] == 1
    assert version_schema["maxLength"] == 128
    manifest_schema = parameters["expected_manifest_sha256"]["schema"]["anyOf"][0]
    assert manifest_schema["pattern"] == "^[0-9a-f]{64}$"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SystemArchetypeExplanationResponse",
    }


@pytest_asyncio.fixture
async def published_client(database, monkeypatch):
    connection, _, _, _ = database
    generation_id, _ = _build_published_generation(database)
    pool = await _asyncpg_pool(connection)
    monkeypatch.setattr(archetypes, "get_pool", lambda: pool)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app()),
            base_url="http://test",
        ) as client:
            yield client, pool, connection, generation_id
    finally:
        await pool.close()


def _published_identity(connection, generation_id):
    return connection.execute(
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


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ("generation", "version", "manifest"))
async def test_expected_identity_mismatch_is_exact_409(published_client, field):
    client, _, connection, generation_id = published_client
    identity = _published_identity(connection, generation_id)
    params = {
        "expected_generation_id": (
            str(uuid.uuid4()) if field == "generation" else str(generation_id)
        ),
        "expected_archetype_version": (
            "different-version" if field == "version" else identity[1]
        ),
        "expected_manifest_sha256": ("0" * 64 if field == "manifest" else identity[2]),
    }
    response = await client.get(
        f"/api/archetypes/system/{connection.execute('SELECT min(system_id64) FROM v3_app.system_archetype').fetchone()[0]}/explanation",
        params=params,
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": archetypes._EXPLANATION_UNAVAILABLE_DETAIL,
    }


@pytest.mark.asyncio
async def test_product_version_mismatch_is_409_before_model(
    published_client,
    monkeypatch,
):
    client, _, connection, _ = published_client
    id64 = connection.execute(
        "SELECT min(system_id64) FROM v3_app.system_archetype"
    ).fetchone()[0]
    score_spy = AsyncMock()
    monkeypatch.setattr(archetypes, "ARCHETYPE_VERSION", "different-version")
    monkeypatch.setattr(archetypes, "score_raw_system", score_spy)
    response = await client.get(f"/api/archetypes/system/{id64}/explanation")
    assert response.status_code == 409
    assert response.json() == {
        "detail": archetypes._EXPLANATION_UNAVAILABLE_DETAIL,
    }
    score_spy.assert_not_called()


@pytest.mark.asyncio
async def test_model_file_hash_mismatch_is_409_before_model(
    published_client,
    monkeypatch,
):
    client, _, connection, _ = published_client
    id64 = connection.execute(
        "SELECT min(system_id64) FROM v3_app.system_archetype"
    ).fetchone()[0]
    score_spy = AsyncMock()
    monkeypatch.setattr(
        archetypes,
        "_DEPLOYED_ARCHETYPE_MODEL_FILE_SHA256",
        "0" * 64,
    )
    monkeypatch.setattr(archetypes, "score_raw_system", score_spy)
    response = await client.get(f"/api/archetypes/system/{id64}/explanation")
    assert response.status_code == 409
    assert response.json() == {
        "detail": archetypes._EXPLANATION_UNAVAILABLE_DETAIL,
    }
    score_spy.assert_not_called()


@pytest.mark.asyncio
async def test_matching_product_returns_verified_eight_explanations(published_client):
    client, _, connection, generation_id = published_client
    cursor = connection.execute(
        "SELECT * FROM v3_app.system_archetype ORDER BY system_id64 LIMIT 1"
    )
    stored = cursor.fetchone()
    stored_columns = [description.name for description in cursor.description]
    stored_by_name = dict(zip(stored_columns, stored, strict=True))
    identity = _published_identity(connection, generation_id)
    response = await client.get(
        f"/api/archetypes/system/{stored_by_name['system_id64']}/explanation",
        params={
            "expected_generation_id": str(generation_id),
            "expected_archetype_version": identity[1],
            "expected_manifest_sha256": identity[2],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id64"] == stored_by_name["system_id64"]
    assert [entry["key"] for entry in body["archetypes"]] == list(ARCHETYPE_KEYS)
    for entry in body["archetypes"]:
        key = entry["key"]
        assert entry["score"] == stored_by_name[f"{key}_score"]
        assert entry["tier"] == stored_by_name[f"{key}_tier"]
        assert entry["confidence"] == (
            stored_by_name[f"{key}_confidence_ppm"] / 1_000_000.0
        )
        assert entry["weighted_e4"] == stored_by_name[f"{key}_weighted_e4"]
        assert entry["explanation"]
    assert body["summary"] == {
        "primary_archetype": stored_by_name["primary_archetype"],
        "secondary_archetype": stored_by_name["secondary_archetype"],
        "best_colony_potential": stored_by_name["best_colony_potential"],
        "best_tier": stored_by_name["best_tier"],
        "archetype_confidence": (
            stored_by_name["archetype_confidence_ppm"] / 1_000_000.0
        ),
        "weighted_potential": stored_by_name["weighted_potential"],
    }
    assert body["completeness"] == stored_by_name["completeness_ppm"] / 1_000_000.0
    assert body["ranking"] == {
        "ranking_version": RANKING_VERSION,
        "ranking_sha256": ranking_sha256(),
        "derived_generation_id": str(generation_id),
        "publication_sequence": identity[0],
        "archetype_version": identity[1],
        "archetype_manifest_sha256": identity[2],
        "archetype_model_sha256": identity[3],
    }


@pytest.mark.asyncio
async def test_missing_wide_row_is_404(published_client):
    client, _, _, _ = published_client
    response = await client.get(f"/api/archetypes/system/{2**63 - 1}/explanation")
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("column", ("completeness_ppm", "paradise_weighted_e4"))
async def test_divergent_stored_value_fails_closed_and_names_column(
    published_client,
    column,
):
    client, _, connection, generation_id = published_client
    id64 = connection.execute(
        "SELECT min(system_id64) FROM v3_derived.system_archetype "
        "WHERE derived_generation_id = %s",
        (generation_id,),
    ).fetchone()[0]
    connection.execute(
        "ALTER TABLE v3_derived.system_archetype DISABLE TRIGGER product_update"
    )
    try:
        if column == "completeness_ppm":
            connection.execute(
                """
                UPDATE v3_derived.system_archetype
                   SET completeness_ppm = CASE WHEN completeness_ppm < 1000000
                                               THEN completeness_ppm + 1
                                               ELSE completeness_ppm - 1 END
                 WHERE derived_generation_id = %s AND system_id64 = %s
                """,
                (generation_id, id64),
            )
        else:
            connection.execute(
                """
                UPDATE v3_derived.system_archetype
                   SET paradise_weighted_e4 =
                       CASE WHEN paradise_weighted_e4 < 1000000
                            THEN paradise_weighted_e4 + 1
                            ELSE paradise_weighted_e4 - 1 END
                 WHERE derived_generation_id = %s AND system_id64 = %s
                """,
                (generation_id, id64),
            )
    finally:
        connection.execute(
            "ALTER TABLE v3_derived.system_archetype ENABLE TRIGGER product_update"
        )
    response = await client.get(f"/api/archetypes/system/{id64}/explanation")
    assert response.status_code == 503
    assert column in response.json()["detail"]


@pytest.mark.asyncio
async def test_publication_mid_request_uses_exactly_one_snapshot(
    database,
    monkeypatch,
):
    connection, _, _, _ = database
    old_generation, old_snapshot = _build_ready_generation(database)
    assert _publish(connection, old_generation, old_snapshot) == 1
    new_generation, new_snapshot = _build_ready_generation(database)
    id64 = connection.execute(
        "SELECT min(system_id64) FROM v3_app.system_archetype"
    ).fetchone()[0]

    original = archetypes._current_derived_generation
    published = False

    async def publish_after_identity(conn):
        nonlocal published
        identity = await original(conn)
        if not published:
            assert (
                _publish(
                    connection,
                    new_generation,
                    new_snapshot,
                    expected_current=old_generation,
                    expected_sequence=1,
                )
                == 2
            )
            published = True
        return identity

    monkeypatch.setattr(
        archetypes,
        "_current_derived_generation",
        publish_after_identity,
    )
    pool = await _asyncpg_pool(connection)
    monkeypatch.setattr(archetypes, "get_pool", lambda: pool)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app()),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/api/archetypes/system/{id64}/explanation")
    finally:
        await pool.close()

    assert response.status_code == 200, response.text
    assert response.json()["ranking"]["derived_generation_id"] == str(old_generation)
    assert (
        connection.execute(
            "SELECT derived_generation_id FROM v3_meta.current_derived_generation"
        ).fetchone()[0]
        == new_generation
    )


def test_legacy_system_archetype_handler_is_byte_for_byte_unchanged():
    source = inspect.getsource(archetypes.get_system_archetypes).encode()
    assert hashlib.sha256(source).hexdigest() == LEGACY_HANDLER_SHA256
