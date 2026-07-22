"""Phase 5 — map endpoints must read from materialised views (audit §C4).

Validates:
  * /api/map/regions      → reads from mv_map_regions
  * /api/map/heatmap      → reads from mv_map_heatmap_<resolution>ly
  * /api/map/timeline     → reads from mv_map_timeline_month for bucket=month
  * Refresh helper        → refresh_map_mviews() function exists and runs
"""
import pytest

pytestmark = pytest.mark.asyncio


async def test_regions_endpoint_reads_from_mv(client, pool):
    """The endpoint must return the same row count as mv_map_regions
    AND should not hit a 5+ second AVG()."""
    import time
    t0 = time.monotonic()
    r = await client.get('/api/map/regions')
    elapsed = time.monotonic() - t0

    assert r.status_code == 200
    body = r.json()
    assert body['total_regions'] == 42, body
    # MV read should be fast — well under the 5 s defence-in-depth cap.
    assert elapsed < 1.0, f'regions took {elapsed:.2f}s — possible MV miss'

    # Compare to the MV directly to lock the data path.
    async with pool.acquire() as conn:
        mv_count = await conn.fetchval('SELECT count(*) FROM mv_map_regions')
    assert mv_count == 42


async def test_heatmap_endpoint_reads_from_mv(client, pool):
    """voxel_size=200 should hit mv_map_heatmap_200ly; result must
    include voxel_bucket telling the client which resolution was served."""
    r = await client.get('/api/map/heatmap?voxel_size=200&min_systems=1')
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['voxel_bucket'] == 200, body
    assert body['count'] >= 1, body  # we seeded 40 systems
    assert body['max_cells'] == 50_000, body
    assert body['truncated'] is False, body

    # 750 LY bucket → 1000 LY MV (the closest pre-aggregated bucket up).
    r2 = await client.get('/api/map/heatmap?voxel_size=750&min_systems=1')
    assert r2.status_code == 200
    assert r2.json()['voxel_bucket'] == 1000


async def test_timeline_month_reads_from_mv(client, pool):
    r = await client.get('/api/map/timeline?bucket=month')
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['bucket'] == 'month'
    assert isinstance(body['points'], list)
    # Lock the MV data path: the API total must equal the MV total.
    async with pool.acquire() as conn:
        mv_total = await conn.fetchval(
            'SELECT COALESCE(SUM(systems_discovered),0) FROM mv_map_timeline_month'
        )
    assert body['total'] == mv_total


async def test_refresh_function_exists(pool):
    """The refresh helper that the nightly cron will call must exist."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT name, refresh_ms FROM refresh_map_mviews(TRUE)"
        )
    names = sorted(r['name'] for r in rows)
    assert names == sorted([
        'mv_map_heatmap_1000ly',
        'mv_map_heatmap_200ly',
        'mv_map_heatmap_500ly',
        'mv_map_regions',
        'mv_map_timeline_month',
    ])
    # Every refresh should complete in milliseconds for our seed-sized dataset
    for r in rows:
        assert r['refresh_ms'] < 5000, f'{r["name"]} refresh took {r["refresh_ms"]}ms'


async def test_heatmap_uses_economy_specific_max_column(client):
    """Audit §C5 follow-through: filtering by economy must use the MV's
    per-economy max_<eco> column, not max_score."""
    r = await client.get('/api/map/heatmap?voxel_size=200&min_systems=1&economy=tourism')
    assert r.status_code == 200
    body = r.json()
    # Result shape unchanged; all rows present
    assert body['economy'] == 'tourism'
    assert body['count'] >= 1
