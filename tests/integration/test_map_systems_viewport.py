"""Integration: GET /api/map/systems — the real-star viewport detail lane.

Seeds a few systems at coordinates far outside the real galaxy (~+-50k LY) so
only our rows fall inside the test bounding box, then asserts the endpoint:
  * filters to the box (out-of-box rows excluded),
  * orders notable-first (populated, then brighter spectral class),
  * honors the cap via `truncated`,
  * rejects an over-wide box with `too_wide`,
  * rejects an out-of-range `limit` at the edge (422).
"""
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

BASE = 800_000.0  # far outside the real galaxy so the box is otherwise empty
TEST_IDS = [9_900_000_001, 9_900_000_002, 9_900_000_003, 9_900_000_004]

# (id64, name, x, y, z, population, main_star_type)
SEED = [
    (9_900_000_001, 'VP Test Populated K', BASE,         BASE,       BASE,       12_000, 'K'),
    (9_900_000_002, 'VP Test Bright O',    BASE + 100.0, BASE,       BASE,       0,      'O'),
    (9_900_000_003, 'VP Test Dim M',       BASE + 200.0, BASE,       BASE,       0,      'M'),
    (9_900_000_004, 'VP Test OutOfBox',    900_000.0,    900_000.0,  900_000.0,  0,      'G'),
]

IN_BOX = {
    'min_x': BASE - 1_000, 'max_x': BASE + 1_000,
    'min_y': BASE - 1_000, 'max_y': BASE + 1_000,
    'min_z': BASE - 1_000, 'max_z': BASE + 1_000,
}


@pytest_asyncio.fixture
async def seeded_viewport_systems(pool):
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM systems WHERE id64 = ANY($1::bigint[])', TEST_IDS)
        await conn.executemany(
            'INSERT INTO systems (id64, name, x, y, z, population, main_star_type) '
            'VALUES ($1, $2, $3, $4, $5, $6, $7)',
            SEED,
        )
    yield
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM systems WHERE id64 = ANY($1::bigint[])', TEST_IDS)


async def test_viewport_filters_to_box_and_orders_notable_first(client, seeded_viewport_systems):
    r = await client.get('/api/map/systems', params=IN_BOX)
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [s['id64'] for s in body['systems'] if s['id64'] in TEST_IDS]
    # out-of-box row excluded; exactly the three in-box seeds, notable-first:
    # populated K first, then bright O before dim M.
    assert ids == [9_900_000_001, 9_900_000_002, 9_900_000_003]
    assert body['too_wide'] is False
    assert body['truncated'] is False
    assert all('galaxy_region_id' in system for system in body['systems'])


async def test_viewport_rejects_overwide_box(client):
    params = {'min_x': 0, 'max_x': 100_000, 'min_y': 0, 'max_y': 10, 'min_z': 0, 'max_z': 10}
    r = await client.get('/api/map/systems', params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['too_wide'] is True
    assert body['systems'] == []


async def test_viewport_truncates_at_limit(client, seeded_viewport_systems):
    r = await client.get('/api/map/systems', params={**IN_BOX, 'limit': 2})
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [s['id64'] for s in body['systems'] if s['id64'] in TEST_IDS]
    assert ids == [9_900_000_001, 9_900_000_002]  # notable-first, capped at 2
    assert body['truncated'] is True


async def test_viewport_rejects_out_of_range_limit(client):
    r = await client.get('/api/map/systems', params={**IN_BOX, 'limit': 999_999})
    assert r.status_code == 422
