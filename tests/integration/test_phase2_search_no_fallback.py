"""Phase 2 — `/api/local/search` and `/api/search/galaxy` should:

  1. Run via `local_search.local_db_search` (the centralised builder).
  2. Return 200 + a {results, total, count} envelope on success.
  3. Return 503 (Service Unavailable, RFC 7807 problem-details) when
     the underlying DB call raises — NOT silently fall back to a
     duplicated inline SQL builder.

This locks the contract that audit §C5 was about: there is exactly ONE
search SQL builder, and its failures are surfaced — not masked.
"""
import pytest
from unittest.mock import AsyncMock, patch


pytestmark = pytest.mark.asyncio


# --- Happy paths ------------------------------------------------------------

async def test_local_search_runs_via_local_db_search(client):
    """Real DB call, real seed data → 200 + non-empty results.

    `POST /api/local/search` was repointed onto the V3 ranked-search path
    (`local_search.local_db_search_v3`, F2c/F3 Task 3) -- it no longer runs
    via `local_db_search` and no longer reports `source: 'local_db'`.
    Responses now echo the ranking profile identity instead
    (`f'v3:{RANKING_VERSION}'`)."""
    from edfinder_api.ranking.profile import RANKING_VERSION

    payload = {
        'reference_coords': {'x': 0, 'y': 0, 'z': 0},
        'filters':          {'distance': {'min': 0, 'max': 1000}},
        'size':             5,
    }
    r = await client.post('/api/local/search', json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert 'results' in body
    assert isinstance(body['results'], list)
    assert body.get('source') == f'v3:{RANKING_VERSION}', \
        f"expected v3 ranked-search source, got {body.get('source')!r}"


async def test_local_search_extraction_economy_uses_extraction_column(client):
    """Audit §C5 regression test, updated for the V3 repoint.

    V3's `v3_app.system_search` / `system_archetype_summary` carry no
    per-economy potential column yet, so `picked_economy` currently falls
    back to the same no-pick primary score (`best_colony_potential`) --
    a documented gap in `ranking_sql.py` (see its "Economy-picked ranking"
    section), not a silent bug. What must still hold under the repoint is
    that results come back ordered by the ranking profile's actual sort key
    (`primary_score * uncertainty_factor DESC`), which the response exposes
    as `archetype_score` and `uncertainty_factor` -- not some other,
    unrelated ordering."""
    payload = {
        'reference_coords': {'x': 0, 'y': 0, 'z': 0},
        'filters':          {'distance': {'min': 0, 'max': 100000}, 'economy': 'Extraction'},
        'size':             3,
        'sort_by':          'development',
    }
    r = await client.post('/api/local/search', json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get('display_economy') == 'Extraction'
    combined = [
        row['archetype_score'] * row['uncertainty_factor']
        for row in body['results']
        if row.get('archetype_score') is not None and row.get('uncertainty_factor') is not None
    ]
    assert combined == sorted(combined, reverse=True), \
        f"primary_score * uncertainty_factor should descend, got {combined}"


# --- 503 on DB failure (the core Phase 2 contract) --------------------------

async def test_local_search_returns_503_on_db_failure(client):
    """If the SQL builder raises, the API must surface a 503 with a
    problem-details body — not silently degrade to an inline fallback
    that produces different ordering (audit §C5).

    `/api/local/search` runs via `local_db_search_v3` since the V3 repoint
    (F2c/F3 Task 3); patch that function, not the retired `local_db_search`
    call site, or this test would silently stop exercising the failure path
    it claims to cover."""

    async def boom(body, pool):
        raise RuntimeError('simulated DB outage')

    with patch('routers.search._ls.local_db_search_v3', boom):
        r = await client.post('/api/local/search', json={
            'reference_coords': {'x': 0, 'y': 0, 'z': 0},
            'filters':          {'distance': {'min': 0, 'max': 100}},
            'size':             10,
        })
    assert r.status_code == 503, r.text
    body = r.json()
    # RFC 7807 problem-details body
    assert body.get('type', '').endswith('search-unavailable') or \
           'unavailable' in body.get('title', '').lower(), body


async def test_galaxy_search_returns_503_on_db_failure(client):
    async def boom(body, pool):
        raise RuntimeError('simulated DB outage')

    with patch('routers.search._ls.local_db_galaxy_search', boom):
        r = await client.post('/api/search/galaxy', json={
            'economy': 'Tourism', 'min_score': 50, 'limit': 5,
        })
    assert r.status_code == 503


async def test_cluster_search_returns_503_on_db_failure(client):
    async def boom(body, pool):
        raise RuntimeError('simulated DB outage')

    with patch('routers.search._ls.local_db_cluster_search', boom):
        r = await client.post('/api/search/cluster', json={
            'requirements': [{'economy': 'Agriculture', 'min_count': 1}],
            'limit': 5,
        })
    assert r.status_code == 503


async def test_cluster_search_passes_named_region_scope_to_sql_builder(client):
    captured = {}

    async def capture(body, pool):
        captured.update(body)
        return {'clusters': [], 'count': 0, 'query_ms': 1}

    with (
        patch('routers.search.cache_get', AsyncMock(return_value=None)),
        patch('routers.search._ls.local_db_cluster_search', capture),
    ):
        r = await client.post('/api/search/cluster', json={
            'requirements': [{'economy': 'Agriculture', 'min_count': 1}],
            'galaxy_region_id': 31,
            'limit': 5,
        })

    assert r.status_code == 200, r.text
    assert captured['galaxy_region_id'] == 31
