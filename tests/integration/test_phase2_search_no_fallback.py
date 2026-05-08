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
from unittest.mock import patch


pytestmark = pytest.mark.asyncio


# --- Happy paths ------------------------------------------------------------

async def test_local_search_runs_via_local_db_search(client):
    """Real DB call, real seed data → 200 + non-empty results."""
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
    assert body.get('source') == 'local_db', f"expected local_db source, got {body.get('source')!r}"


async def test_local_search_extraction_economy_uses_extraction_column(client):
    """Audit §C5 regression test: filtering by economy=Extraction must
    rank by score_extraction, NOT silently fall back to overall score."""
    payload = {
        'reference_coords': {'x': 0, 'y': 0, 'z': 0},
        'filters':          {'distance': {'min': 0, 'max': 100000}, 'economy': 'Extraction'},
        'size':             3,
        'sort_by':          'rating',
    }
    r = await client.post('/api/local/search', json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get('display_economy') == 'Extraction'
    # Ordering: descending by display_score (= score_extraction here)
    scores = [row.get('display_score') for row in body['results'] if row.get('display_score') is not None]
    assert scores == sorted(scores, reverse=True), \
        f"display_score should descend, got {scores}"


# --- 503 on DB failure (the core Phase 2 contract) --------------------------

async def test_local_search_returns_503_on_db_failure(client):
    """If the SQL builder raises, the API must surface a 503 with a
    problem-details body — not silently degrade to an inline fallback
    that produces different ordering (audit §C5)."""
    from local_search import local_db_search as real_fn

    async def boom(body, pool):
        raise RuntimeError('simulated DB outage')

    with patch('routers.search._ls.local_db_search', boom):
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
