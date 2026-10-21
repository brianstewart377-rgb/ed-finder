"""F3 slice 2b: `POST /api/search/galaxy` and `POST /api/search/cluster` — the
last two Finder routes — read only the V3 relations behind the same
fail-closed product gate as slices 1 and 2, validate every request before
touching the database, and never reference a legacy relation.

- Galaxy search is the galaxy-wide Any-mode window of the ranked search
  (`local_search.local_db_galaxy_search_v3`): same ordering, same envelope,
  same ranking identity as `/api/local/search` with `galaxy_wide=true`.
  Legacy features with no V3 projection (concrete economy, `min_score > 0`,
  uncolonised-only, region) answer 422, never a silently unfiltered page.
- Cluster search (`local_search.local_db_cluster_search_v3`) pins the
  published generation, reads the Finder-owned `v3_spatial.cluster_run`
  state for it, and fails closed with 503 naming the gap — no Finder cluster
  run exists yet and the viability summary contract is undefined.

Fixture/harness mirrors tests/test_archetype_slice2_v3.py: a disposable PG18
database from `tests.ratings_v4_pg_fixture.canonical_database`, the F1 Search
and F2d wide-row Archetype products built/validated against one Ratings V4
generation, then published so `v3_app.*` exposes them.
"""

from __future__ import annotations

import ast
import inspect
import os
from pathlib import Path
import sys
import uuid

from fastapi import FastAPI, HTTPException
import httpx
import pytest
import pytest_asyncio


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("CORS_ORIGINS", "https://search-slice2b-v3-test.invalid")
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

from edfinder_api import deps  # noqa: E402
from edfinder_api import local_search  # noqa: E402
from edfinder_api.config import limiter  # noqa: E402
from edfinder_api.ranking.profile import (  # noqa: E402
    LOCAL_SEARCH_GALAXY_WIDE_FILTER_REJECTION_REASON,
    RANKING_VERSION,
    ranking_sha256,
)
from edfinder_api.routers import search as search_router  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

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
    key = "search_slice2b_v3_test_" + uuid.uuid4().hex
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


def _build_ready_generation(database, *, while_building=None):
    """Build + validate both Finder products on one Ratings generation.

    `while_building(connection, generation_id)` runs while the generation is
    still BUILDING, which is the only state the shared immutability guard
    lets a test attach rows (e.g. a `v3_spatial.cluster_run`) to it.
    """
    connection, _, _, _ = database
    key, generation_id, snapshot = _ratings_generation(database)
    if while_building is not None:
        while_building(connection, generation_id)
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
            "test", "slice 2b fixture", ["system_search", "system_archetype"],
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


def _test_app(pool) -> FastAPI:
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(search_router.router)

    async def _pool():
        return pool

    async def _no_redis():
        return None

    app.dependency_overrides[deps.get_pool] = _pool
    app.dependency_overrides[deps.get_redis] = _no_redis
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


@pytest_asyncio.fixture
async def published_client(database):
    connection, _, _, _ = database
    generation_id, snapshot = _build_ready_generation(database)
    assert _publish(connection, generation_id, snapshot) == 1
    pool = await _asyncpg_pool(connection)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app(pool)),
            base_url="http://test",
        ) as client:
            yield client, connection, generation_id, pool
    finally:
        await pool.close()


# ---------------------------------------------------------------------------
# Galaxy search — pure request validation (no database)
# ---------------------------------------------------------------------------

def _never_touched_pool():
    class _Pool:
        def acquire(self):  # pragma: no cover - reaching here is the failure
            raise AssertionError("database must not be touched for a 422")
    return _Pool()


@pytest.mark.parametrize(
    "body, fragment",
    [
        ({"economy": "Tourism"}, "economy"),
        ({"economy": "any", "min_score": 50}, "min_score"),
        ({"economy": "any", "include_colonised": False}, "include_colonised"),
        ({"economy": "any", "galaxy_region_id": 31}, "galaxy_region"),
        ({"economy": "any", "limit": 0}, "size"),
        ({"economy": "any", "limit": 501}, "limit"),
        ({"economy": "any", "offset": -1}, "from"),
        ({"economy": "any", "limit": 500, "offset": 9_501}, "from + size"),
        ({"economy": "any", "min_score": -1}, "min_score"),
        ({"economy": "any", "limit": "lots"}, "limit"),
    ],
)
def test_prepare_galaxy_search_v3_rejects_unsupported_features_with_422(body, fragment):
    with pytest.raises(HTTPException) as excinfo:
        local_search.prepare_galaxy_search_v3(body)
    assert excinfo.value.status_code == 422
    assert fragment in str(excinfo.value.detail)


def test_prepare_galaxy_search_v3_min_score_names_the_galaxy_wide_reason():
    with pytest.raises(HTTPException) as excinfo:
        local_search.prepare_galaxy_search_v3({"economy": "any", "min_score": 1})
    assert LOCAL_SEARCH_GALAXY_WIDE_FILTER_REJECTION_REASON in excinfo.value.detail


def test_prepare_galaxy_search_v3_maps_any_request_onto_galaxy_wide_local_body():
    body = local_search.prepare_galaxy_search_v3(
        {"economy": "any", "min_score": 0, "limit": 25, "offset": 50},
    )
    assert body["galaxy_wide"] is True
    assert body["reference_coords"] is None
    assert body["economy"] == "any"
    assert body["sort_by"] == "development"
    assert body["size"] == 25 and body["from"] == 50
    assert body["min_development_score"] == 0
    # Defaults match the public GalaxySearchRequest model.
    defaults = local_search.prepare_galaxy_search_v3({})
    assert defaults["size"] == local_search.GALAXY_SEARCH_LIMIT_DEFAULT == 100
    assert defaults["from"] == 0


@pytest.mark.asyncio
async def test_galaxy_search_v3_validates_before_any_database_access():
    with pytest.raises(HTTPException) as excinfo:
        await local_search.local_db_galaxy_search_v3(
            {"economy": "Agriculture"}, _never_touched_pool(),
        )
    assert excinfo.value.status_code == 422


# ---------------------------------------------------------------------------
# Galaxy search — against the published fixture
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_galaxy_search_v3_is_the_galaxy_wide_any_window(published_client):
    client, connection, generation_id, pool = published_client

    expected_order = [
        system_id64 for system_id64, _ in sorted(
            connection.execute(
                "SELECT system_id64, weighted_potential FROM v3_app.system_archetype_summary"
            ).fetchall(),
            key=lambda row: (-row[1], row[0]),
        )
    ]
    assert len(expected_order) == 12  # authoritative fixture: 12 systems

    direct = await local_search.local_db_galaxy_search_v3(
        {"economy": "any", "min_score": 0, "limit": 100, "offset": 0}, pool,
    )
    assert [row["id64"] for row in direct["results"]] == expected_order
    assert direct["source"] == f"v3:{RANKING_VERSION}"
    assert direct["total"] == len(expected_order)
    assert direct["total_is_capped"] is False
    assert direct["ranking"] == _published_identity(connection, generation_id)
    for row in direct["results"]:
        assert row["source"] == "v3_app"
        assert "confidence" in row and "completeness" in row

    # Byte-for-byte the same page as the local-search route in galaxy-wide
    # Any mode: one access path, one ranking profile, one envelope.
    via_local = await local_search.local_db_search_v3(
        {"galaxy_wide": True, "size": 100, "from": 0}, pool,
    )
    assert via_local["results"] == direct["results"]
    assert via_local["ranking"] == direct["ranking"]

    # Through the route, with the default request body.
    response = await client.post("/api/search/galaxy", json={})
    assert response.status_code == 200, response.text
    envelope = response.json()
    assert [row["id64"] for row in envelope["results"]] == expected_order
    assert envelope["ranking"] == direct["ranking"]

    # Paging stays inside the window and is honoured.
    page = await client.post("/api/search/galaxy", json={"limit": 5, "offset": 5})
    assert page.status_code == 200, page.text
    assert [row["id64"] for row in page.json()["results"]] == expected_order[5:10]


@pytest.mark.asyncio
async def test_galaxy_route_answers_422_before_the_product_gate(monkeypatch):
    """A disallowed request never reaches the generation pin."""
    async def _boom(_pool):
        raise AssertionError("resolve_published_generation must not run for a 422")

    monkeypatch.setattr(local_search, "resolve_published_generation", _boom)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_test_app(object())), base_url="http://test",
    ) as client:
        concrete = await client.post("/api/search/galaxy", json={"economy": "High Tech"})
        floored = await client.post("/api/search/galaxy", json={"min_score": 60})
    assert concrete.status_code == 422, concrete.text
    assert "economy" in concrete.text
    assert floored.status_code == 422, floored.text
    assert "min_score" in floored.text


@pytest.mark.asyncio
async def test_galaxy_route_is_404_without_a_published_generation(database):
    connection, _, _, _ = database
    _build_ready_generation(database)   # READY but never published
    pool = await _asyncpg_pool(connection)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app(pool)), base_url="http://test",
        ) as client:
            response = await client.post("/api/search/galaxy", json={})
    finally:
        await pool.close()
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "No published Ratings V4 generation"


# ---------------------------------------------------------------------------
# Cluster search — pure request validation (no database)
# ---------------------------------------------------------------------------

_SLOT = {"economies": ["Agriculture"], "min_score": 65}
_REQ = {"economy": "Agriculture", "min_count": 1, "min_score": 40}


@pytest.mark.parametrize(
    "body, fragment",
    [
        ({}, "exactly one of requirements or slots"),
        ({"requirements": [_REQ], "slots": [_SLOT]}, "exactly one of requirements or slots"),
        ({"requirements": [_REQ] * 7}, "at most 6"),
        ({"slots": [_SLOT] * 11}, "at most 10"),
        ({"requirements": [{"economy": "Banking"}]}, "unknown economy"),
        ({"requirements": [{"economy": "Agriculture", "min_count": 0}]}, "min_count"),
        ({"requirements": [{"economy": "Agriculture", "min_score": 101}]}, "min_score"),
        ({"slots": [{"economies": []}]}, "at least one economy"),
        ({"slots": [{"economies": ["Agriculture", "Tourism", "Military"]}]}, "at most 2"),
        ({"slots": [{"economies": ["Agriculture"], "min_score": -5}]}, "min_score"),
        ({"requirements": [_REQ], "limit": 0}, "limit"),
        ({"requirements": [_REQ], "limit": 201}, "limit"),
        ({"requirements": [_REQ], "offset": -1}, "offset"),
        ({"requirements": [_REQ], "reference_coords": {"x": 1, "y": 2}}, "reference_coords"),
        ({"requirements": [_REQ], "reference_coords": {"x": 1, "y": 2, "z": float("inf")}}, "finite"),
        ({"requirements": [_REQ], "galaxy_region_id": 43}, "galaxy_region_id"),
        ({"requirements": [_REQ], "galaxy_region_id": 0}, "galaxy_region_id"),
    ],
)
def test_prepare_cluster_search_v3_rejects_malformed_requests_with_422(body, fragment):
    with pytest.raises(HTTPException) as excinfo:
        local_search.prepare_cluster_search_v3(body)
    assert excinfo.value.status_code == 422
    assert fragment in str(excinfo.value.detail)


def test_prepare_cluster_search_v3_normalises_a_valid_request():
    spec = local_search.prepare_cluster_search_v3({
        "requirements": [
            {"economy": "High Tech", "min_count": 2},
            {"economy": "extraction"},
        ],
        "limit": 10,
        "reference_coords": {"x": 1, "y": 2, "z": 3},
        "galaxy_region_id": 31,
    })
    assert spec["requirements"] == [
        {"economy": "hightech", "min_count": 2, "min_score": 40},
        {"economy": "extraction", "min_count": 1, "min_score": 40},
    ]
    assert spec["slots"] == []
    assert spec["limit"] == 10 and spec["offset"] == 0
    assert spec["reference_coords"] == (1.0, 2.0, 3.0)
    assert spec["galaxy_region_id"] == 31

    slots = local_search.prepare_cluster_search_v3({
        "slots": [{"economies": ["Agriculture", "Tourism"], "label": "Paradise"}],
    })
    assert slots["slots"] == [
        {"economies": ["agriculture", "tourism"], "min_score": 65, "label": "Paradise"},
    ]
    assert slots["reference_coords"] is None and slots["galaxy_region_id"] is None


@pytest.mark.asyncio
async def test_cluster_search_v3_validates_before_any_database_access():
    with pytest.raises(HTTPException) as excinfo:
        await local_search.local_db_cluster_search_v3({}, _never_touched_pool())
    assert excinfo.value.status_code == 422


# ---------------------------------------------------------------------------
# Cluster search — fail-closed product gate against the fixture
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cluster_search_is_503_naming_the_missing_cluster_product(published_client):
    client, connection, generation_id, pool = published_client

    with pytest.raises(HTTPException) as excinfo:
        await local_search.local_db_cluster_search_v3({"requirements": [_REQ]}, pool)
    assert excinfo.value.status_code == 503
    detail = excinfo.value.detail
    assert "Finder cluster product is not published" in detail
    assert str(generation_id) in detail
    assert "v3_spatial.cluster_run" in detail
    assert "owner_domain=finder" in detail and ": none)" in detail

    # Through the route: the deliberate 503 is surfaced as-is, not re-wrapped
    # as the generic RFC 7807 "search unavailable" problem.
    response = await client.post(
        "/api/search/cluster",
        json={"requirements": [{"economy": "Agriculture", "min_count": 1}], "limit": 5},
    )
    assert response.status_code == 503, response.text
    assert response.json()["detail"] == detail

    # The slot form takes the same gate.
    slot_response = await client.post(
        "/api/search/cluster",
        json={"slots": [{"economies": ["Agriculture", "Tourism"]}], "limit": 5},
    )
    assert slot_response.status_code == 503, slot_response.text
    assert slot_response.json()["detail"] == detail


def _attach_runs(*rows):
    """Insert `v3_spatial.cluster_run` rows while the generation is BUILDING —
    the only state the shared immutability guard lets a test attach them in;
    once published, cluster_run rows are immutable."""
    def _hook(conn, generation_id):
        for owner_domain, algorithm, version, state in rows:
            conn.execute(
                """
                INSERT INTO v3_spatial.cluster_run
                    (derived_generation_id, cluster_run_id, owner_domain, algorithm,
                     algorithm_version, parameters, lifecycle_state, validation_receipt,
                     published_at)
                VALUES (%s, %s, %s, %s, %s, '{}'::jsonb, %s,
                        CASE WHEN %s = 'PUBLISHED' THEN '{}'::jsonb END,
                        CASE WHEN %s = 'PUBLISHED' THEN now() END)
                """,
                (generation_id, uuid.uuid4(), owner_domain, algorithm, version,
                 state, state, state),
            )
    return _hook


@pytest.mark.asyncio
async def test_cluster_search_reports_unpublished_finder_run_state(database):
    """An unpublished Finder run is reported by state; another domain's
    published run is not a Finder cluster product and is not reported."""
    connection, _, _, _ = database
    generation_id, snapshot = _build_ready_generation(
        database,
        while_building=_attach_runs(
            ("finder", "economy_bubble", "v0", "BUILDING"),
            ("other_domain", "dbscan", "v1", "PUBLISHED"),
        ),
    )
    assert _publish(connection, generation_id, snapshot) == 1
    pool = await _asyncpg_pool(connection)
    try:
        with pytest.raises(HTTPException) as excinfo:
            await local_search.local_db_cluster_search_v3({"requirements": [_REQ]}, pool)
    finally:
        await pool.close()
    assert excinfo.value.status_code == 503
    assert "Finder cluster product is not published" in excinfo.value.detail
    assert "economy_bubble@v0=BUILDING" in excinfo.value.detail
    assert "dbscan" not in excinfo.value.detail


@pytest.mark.asyncio
async def test_cluster_search_refuses_a_published_finder_run_without_a_read_contract(database):
    """A PUBLISHED Finder run still fails closed: no read contract exists for
    it, so the route answers 503 naming the run rather than a fabricated 200."""
    connection, _, _, _ = database
    generation_id, snapshot = _build_ready_generation(
        database,
        while_building=_attach_runs(("finder", "economy_bubble", "v0", "PUBLISHED")),
    )
    assert _publish(connection, generation_id, snapshot) == 1
    pool = await _asyncpg_pool(connection)
    try:
        with pytest.raises(HTTPException) as excinfo:
            await local_search.local_db_cluster_search_v3({"requirements": [_REQ]}, pool)
    finally:
        await pool.close()
    assert excinfo.value.status_code == 503
    assert "economy_bubble@v0" in excinfo.value.detail
    assert str(generation_id) in excinfo.value.detail
    assert "no Finder cluster read contract exists" in excinfo.value.detail


@pytest.mark.asyncio
async def test_cluster_route_is_404_without_a_published_generation(database):
    connection, _, _, _ = database
    _build_ready_generation(database)   # READY but never published
    pool = await _asyncpg_pool(connection)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_test_app(pool)), base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/search/cluster",
                json={"requirements": [{"economy": "Agriculture", "min_count": 1}]},
            )
    finally:
        await pool.close()
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
async def test_slice2b_reads_are_503_until_both_finder_products_are_published():
    pool = _Pool(_UnpublishedProductConnection())
    for call in (
        local_search.local_db_galaxy_search_v3({"economy": "any"}, pool),
        local_search.local_db_cluster_search_v3({"requirements": [_REQ]}, pool),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await call
        assert excinfo.value.status_code == 503
        assert "system_archetype=MISSING" in excinfo.value.detail


# ---------------------------------------------------------------------------
# Static guards
# ---------------------------------------------------------------------------

_FORBIDDEN_LEGACY_TERMS = (
    "cluster_summary",
    "grid_cell_id",
    "mv_archetype_rankings",
    "system_archetype_scores",
    " from systems ",
    " from ratings ",
    "join ratings",
    "public.",
)


def test_slice2b_paths_read_no_legacy_relation():
    for fn in (
        local_search.prepare_galaxy_search_v3,
        local_search.local_db_galaxy_search_v3,
        local_search.prepare_cluster_search_v3,
        local_search._finder_cluster_runs,
        local_search.local_db_cluster_search_v3,
        search_router.galaxy_search,
        search_router.cluster_search,
    ):
        src = inspect.getsource(fn).lower()
        for term in _FORBIDDEN_LEGACY_TERMS:
            assert term not in src, f"{fn.__qualname__} unexpectedly contains {term!r}"
    cluster_src = inspect.getsource(local_search._finder_cluster_runs)
    assert "v3_spatial.cluster_run" in cluster_src

    # The legacy galaxy/cluster readers are gone, not merely unreferenced.
    for retired in ("local_db_galaxy_search", "local_db_cluster_search", "_resolve_slot_matches"):
        assert not hasattr(local_search, retired), retired


def test_search_router_has_no_legacy_relation_in_any_string_literal():
    """Walk every string constant in `routers/search.py` (SQL text lives in
    string literals) except the module docstring, which may name the retired
    relations when describing their retirement."""
    source = (ROOT / "apps/api/src/routers/search.py").read_text()
    tree = ast.parse(source)
    docstring = ast.get_docstring(tree, clean=False)
    literals = [
        node.value.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node.value != docstring
    ]
    assert any("local_db_galaxy_search_v3" in literal for literal in literals)
    assert any("local_db_cluster_search_v3" in literal for literal in literals)
    for literal in literals:
        for term in _FORBIDDEN_LEGACY_TERMS:
            assert term not in literal, f"search.py literal contains {term!r}: {literal[:80]!r}"
    # No pre-cutover galaxy/cluster cache namespace can be served again.
    assert "GALAXY_CACHE_VERSION = 'v5'" in source
    assert "CLUSTER_CACHE_VERSION" not in source
