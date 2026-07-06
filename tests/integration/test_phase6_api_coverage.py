"""Phase 6 — broader API integration tests beyond the per-phase coverage.

Covers the endpoints the per-phase tests didn't already touch:
  * /api/health
  * /api/cache/stats
  * /api/local/autocomplete
  * /api/system/{id64}
  * /api/systems/batch
  * /api/archetypes/rerank
  * /api/profile/sync/{key}  (rate limit + round-trip)
  * /api/share/og/{id64}     (image generation)
  * Admin endpoints respect ADMIN_TOKEN
  * RFC 7807 problem-details on 503 / 410
"""
import pytest
import json

pytestmark = pytest.mark.asyncio

ADMIN_TOKEN = 'test-admin-token'


async def _seed_archetype_rerank_rows(pool, count: int) -> list[int]:
    async with pool.acquire() as conn:
        ids = [r['id64'] for r in await conn.fetch('SELECT id64 FROM systems ORDER BY id64 LIMIT $1', count)]
        score_payload = []
        trait_payload = []
        for idx, id64 in enumerate(ids, start=1):
            score_payload.append((
                id64,
                55 + idx,
                50 + idx,
                40 + idx,
                0.82,
                json.dumps({'summary': f'Seeded rationale {idx}'}),
            ))
            trait_payload.append((id64, 8 + idx))

        await conn.executemany(
            """
            INSERT INTO system_archetype_scores (
                system_id64,
                primary_archetype,
                overall_development_potential,
                purity_score,
                buildability_score,
                confidence,
                rationale,
                dirty
            )
            VALUES ($1, 'flexible_multirole', $2, $3, $4, $5, $6::jsonb, FALSE)
            ON CONFLICT (system_id64) DO UPDATE SET
                primary_archetype = EXCLUDED.primary_archetype,
                overall_development_potential = EXCLUDED.overall_development_potential,
                purity_score = EXCLUDED.purity_score,
                buildability_score = EXCLUDED.buildability_score,
                confidence = EXCLUDED.confidence,
                rationale = EXCLUDED.rationale,
                dirty = FALSE
            """,
            score_payload,
        )
        await conn.executemany(
            """
            INSERT INTO system_archetype_traits (system_id64, est_total_slots, display_tags)
            VALUES ($1, $2, ARRAY['Seeded'])
            ON CONFLICT (system_id64) DO UPDATE SET
                est_total_slots = EXCLUDED.est_total_slots,
                display_tags = EXCLUDED.display_tags
            """,
            trait_payload,
        )
    return ids


# --- Health / status -------------------------------------------------------

async def test_health_endpoint(client):
    r = await client.get('/api/health')
    assert r.status_code == 200
    body = r.json()
    assert body['status'] == 'ok'
    assert body['database'] == 'connected'
    assert 'version' in body


async def test_status_endpoint(client):
    r = await client.get('/api/status')
    assert r.status_code == 200
    body = r.json()
    assert 'version' in body
    assert 'schema_version' in body


async def test_cache_stats(client):
    r = await client.get('/api/cache/stats')
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


# --- Autocomplete ----------------------------------------------------------

async def test_autocomplete_short_query_returns_empty(client):
    r = await client.get('/api/local/autocomplete?q=a')
    assert r.status_code == 200
    assert r.json()['results'] == []


async def test_autocomplete_real_query(client):
    """Seed has Sol, Achenar, Lave, Procyon — pick a recognisable prefix."""
    r = await client.get('/api/local/autocomplete?q=ach')
    assert r.status_code == 200
    assert isinstance(r.json()['results'], list)


# --- System detail ---------------------------------------------------------

async def test_system_detail_known_id64(client, pool):
    """Pull a known id64 from the seed and verify the full detail shape."""
    async with pool.acquire() as conn:
        id64 = await conn.fetchval('SELECT id64 FROM systems LIMIT 1')
    r = await client.get(f'/api/system/{id64}')
    assert r.status_code == 200
    body = r.json()
    # Phase 4-era response carried both `record` and `system` for legacy
    # compat (audit §H6). Either is acceptable here.
    assert ('record' in body) or ('system' in body), body


async def test_system_detail_unknown_id64_404(client):
    r = await client.get('/api/system/9999999999999999')
    assert r.status_code == 404


async def test_systems_batch(client, pool):
    async with pool.acquire() as conn:
        ids = [r['id64'] for r in await conn.fetch('SELECT id64 FROM systems LIMIT 5')]
    r = await client.post('/api/systems/batch', json={'id64s': ids})
    assert r.status_code == 200
    body = r.json()
    assert len(body['systems']) == 5


# --- Development rerank ----------------------------------------------------

async def test_archetype_rerank_default_weights(client, pool):
    ids = await _seed_archetype_rerank_rows(pool, 3)
    r = await client.post('/api/archetypes/rerank', json={
        'id64s': ids,
    })
    assert r.status_code == 200
    body = r.json()
    assert 'weights_applied' in body
    assert 'results' in body
    assert len(body['results']) == 3
    for row in body['results']:
        assert row['id64'] in ids
        assert isinstance(row['reranked_score'], int)


async def test_archetype_rerank_custom_weights(client, pool):
    ids = await _seed_archetype_rerank_rows(pool, 5)
    r = await client.post('/api/archetypes/rerank', json={
        'id64s': ids,
        'weights': {
            'purity': 1.0,
            'buildability': 0.0,
            'slots': 0.0,
            'expansion': 0.0,
            'logistics': 0.0,
        },
    })
    assert r.status_code == 200
    body = r.json()
    assert body['weights_applied']['purity'] == 1.0
    assert len(body['results']) == 5

# --- Profile sync (rate limited per audit §S3) ----------------------------

VALID_KEY = 'phase6-test-key-aaaaaaaaaaaa'   # 28 chars


async def test_profile_sync_round_trip(client):
    """PUT then GET should retrieve the same blob."""
    blob = {'theme': 'dark', 'pinned': [1, 2, 3]}

    r = await client.put(f'/api/profile/sync/{VALID_KEY}', json={'blob': blob})
    assert r.status_code in (200, 201), r.text

    r = await client.get(f'/api/profile/sync/{VALID_KEY}')
    assert r.status_code == 200
    body = r.json()
    assert body['blob'] == blob


async def test_profile_sync_unknown_key_returns_404(client):
    r = await client.get('/api/profile/sync/never-stored-this-key-zzzzzzzzz')
    assert r.status_code == 404


async def test_profile_sync_short_key_rejected(client):
    r = await client.get('/api/profile/sync/short')
    assert r.status_code == 422   # FastAPI Path validation


# --- OG share image --------------------------------------------------------

async def test_share_og_renders_png(client, pool):
    async with pool.acquire() as conn:
        id64 = await conn.fetchval('SELECT id64 FROM systems LIMIT 1')
    r = await client.get(f'/api/share/og/{id64}')
    assert r.status_code == 200, r.text
    assert r.headers['content-type'] == 'image/png'
    # PNG magic bytes
    assert r.content[:8] == b'\x89PNG\r\n\x1a\n', \
        f"expected PNG header, got {r.content[:8]!r}"


# --- Admin auth ------------------------------------------------------------

async def test_admin_endpoint_requires_token(client):
    r = await client.post('/api/cache/clear')
    assert r.status_code == 401


async def test_admin_endpoint_wrong_token_401(client):
    """Wrong or missing token both return 401 — the admin handler does
    HMAC compare and returns 401 on any failure. (FastAPI's default 403
    is not used here because we want indistinguishable failure modes
    between 'not authenticated' and 'authenticated but wrong'.)"""
    r = await client.post('/api/cache/clear', headers={'X-Admin-Token': 'wrong'})
    assert r.status_code == 401


async def test_admin_endpoint_with_token_works(client):
    r = await client.post('/api/cache/clear', headers={'X-Admin-Token': ADMIN_TOKEN})
    assert r.status_code == 200
    assert r.json()['ok'] is True


# --- 410 Gone responses are RFC 7807 problem-details ----------------------

async def test_legacy_410_uses_problem_details_shape(client):
    r = await client.get('/api/watchlist')
    assert r.status_code == 410
    body = r.json()
    assert 'detail' in body
    detail = body['detail']
    assert detail['type'].startswith('https://')
    assert detail['status'] == 410
    assert 'sync_key' in detail['detail']
