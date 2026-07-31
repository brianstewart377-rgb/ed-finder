from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio


ROOT = Path(__file__).resolve().parents[2]
EDDN_SRC = ROOT / 'apps' / 'eddn' / 'src'
if str(EDDN_SRC) not in sys.path:
    sys.path.insert(0, str(EDDN_SRC))
os.environ.setdefault('LOG_FILE', os.devnull)

import eddn_listener  # noqa: E402


TEST_SYSTEM_IDS = (
    92_000_000_000_001,
    92_000_000_000_002,
    92_000_000_000_003,
    92_000_000_000_004,
    92_000_000_000_005,
)

TEST_BODY_IDS = (
    920_000_004,
    920_000_005,
)


def _clear_listener_buffers() -> None:
    eddn_listener._pending_systems.clear()
    eddn_listener._pending_bodies.clear()
    eddn_listener._pending_rings.clear()
    eddn_listener._pending_dirty_system_ids.clear()


@pytest_asyncio.fixture
async def isolated_eddn_system_writes(pool, monkeypatch):
    async def clear_test_systems() -> None:
        async with pool.acquire() as conn:
            await conn.execute(
                'DELETE FROM bodies WHERE id = ANY($1::bigint[])',
                list(TEST_BODY_IDS),
            )
            await conn.execute(
                'DELETE FROM systems WHERE id64 = ANY($1::bigint[])',
                list(TEST_SYSTEM_IDS),
            )

    async def skip_evidence_promotion(*_args, **_kwargs):
        return {'warnings': []}

    async def skip_dirty_flush(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(
        eddn_listener,
        'promote_canonical_evidence_for_systems',
        skip_evidence_promotion,
    )
    monkeypatch.setattr(
        eddn_listener,
        'flush_pending_dirty_systems',
        skip_dirty_flush,
    )

    _clear_listener_buffers()
    await clear_test_systems()
    yield
    _clear_listener_buffers()
    await clear_test_systems()


@pytest.mark.asyncio
async def test_fss_system_without_colonisation_keys_uses_false_defaults(
    pool,
    isolated_eddn_system_writes,
):
    system_id = TEST_SYSTEM_IDS[0]
    await eddn_listener.handle_fss_discovery(
        pool,
        {},
        {
            'SystemAddress': system_id,
            'StarSystem': 'EDDN Fix FSS System',
            'StarPos': [10.0, 20.0, 30.0],
        },
    )

    await eddn_listener.flush_pending(pool)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT is_colonised, is_being_colonised FROM systems WHERE id64 = $1',
            system_id,
        )

    assert row is not None
    assert row['is_colonised'] is False
    assert row['is_being_colonised'] is False


@pytest.mark.asyncio
async def test_ordinary_event_updates_existing_system_without_clearing_colonised(
    pool,
    isolated_eddn_system_writes,
):
    system_id = TEST_SYSTEM_IDS[1]
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO systems (id64, name, population, is_colonised, is_being_colonised)
            VALUES ($1, 'EDDN Fix Existing Before', 1, TRUE, FALSE)
            """,
            system_id,
        )

    await eddn_listener.handle_location_or_jump(
        pool,
        {},
        {
            'SystemAddress': system_id,
            'StarSystem': 'EDDN Fix Existing After',
            'Population': 42,
        },
    )

    await eddn_listener.flush_pending(pool)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT name, population, is_colonised, is_being_colonised
            FROM systems
            WHERE id64 = $1
            """,
            system_id,
        )

    assert row is not None
    assert row['name'] == 'EDDN Fix Existing After'
    assert row['population'] == 42
    assert row['is_colonised'] is True
    assert row['is_being_colonised'] is False


@pytest.mark.asyncio
async def test_genuine_colonisation_event_still_updates_status_flags(
    pool,
    isolated_eddn_system_writes,
):
    system_id = TEST_SYSTEM_IDS[2]
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO systems (id64, name, is_colonised, is_being_colonised)
            VALUES ($1, 'EDDN Fix Colonisation Event', FALSE, TRUE)
            """,
            system_id,
        )

    await eddn_listener.handle_colonisation_status(
        pool,
        {},
        {
            'event': 'Colonisation',
            'SystemAddress': system_id,
            'StarSystem': 'EDDN Fix Colonisation Event',
            'ColonisationState': 'Colonised',
        },
    )

    await eddn_listener.flush_pending(pool)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT is_colonised, is_being_colonised FROM systems WHERE id64 = $1',
            system_id,
        )

    assert row is not None
    assert row['is_colonised'] is True
    assert row['is_being_colonised'] is False


@pytest.mark.asyncio
async def test_scan_with_null_body_name_inserts_unknown(
    pool,
    isolated_eddn_system_writes,
):
    system_id = TEST_SYSTEM_IDS[3]
    body_id = TEST_BODY_IDS[0]
    await eddn_listener.handle_scan(
        pool,
        {},
        {
            'SystemAddress': system_id,
            'BodyID': body_id,
            'BodyName': None,
            'PlanetClass': 'Rocky body',
        },
    )

    await eddn_listener.flush_pending(pool)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT name FROM bodies WHERE id = $1',
            body_id,
        )

    assert row is not None
    assert row['name'] == 'Unknown'


@pytest.mark.asyncio
async def test_scan_with_null_body_name_preserves_existing_real_name(
    pool,
    isolated_eddn_system_writes,
):
    system_id = TEST_SYSTEM_IDS[4]
    body_id = TEST_BODY_IDS[1]
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO systems (id64, name)
            VALUES ($1, 'EDDN Body Name Existing System')
            """,
            system_id,
        )
        await conn.execute(
            """
            INSERT INTO bodies (id, system_id64, name, body_type, subtype)
            VALUES ($1, $2, 'Existing Real Body Name', 'Planet', 'Icy body')
            """,
            body_id,
            system_id,
        )

    await eddn_listener.handle_scan(
        pool,
        {},
        {
            'SystemAddress': system_id,
            'BodyID': body_id,
            'BodyName': None,
            'PlanetClass': 'Rocky body',
        },
    )

    await eddn_listener.flush_pending(pool)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT name, subtype FROM bodies WHERE id = $1',
            body_id,
        )

    assert row is not None
    assert row['name'] == 'Existing Real Body Name'
    assert row['subtype'] == 'Rocky body'
