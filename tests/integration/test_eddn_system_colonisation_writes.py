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
    92_000_000_000_006,
    92_000_000_000_007,
    92_000_000_000_008,
    92_000_000_000_009,
)

TEST_BODY_IDS = (
    920_000_004,
    920_000_005,
    920_000_006,
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


@pytest.mark.asyncio
async def test_fss_with_null_system_name_inserts_unknown(
    pool,
    isolated_eddn_system_writes,
):
    system_id = TEST_SYSTEM_IDS[5]
    await eddn_listener.handle_fss_discovery(
        pool,
        {},
        {
            'StarSystem': {
                'SystemAddress': system_id,
                'name': None,
            },
        },
    )

    await eddn_listener.flush_pending(pool)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT name FROM systems WHERE id64 = $1',
            system_id,
        )

    assert row is not None
    assert row['name'] == 'Unknown'


@pytest.mark.asyncio
async def test_fss_with_null_system_name_preserves_existing_real_name(
    pool,
    isolated_eddn_system_writes,
):
    system_id = TEST_SYSTEM_IDS[6]
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO systems (id64, name, population)
            VALUES ($1, 'Existing Real System Name', 1)
            """,
            system_id,
        )

    await eddn_listener.handle_fss_discovery(
        pool,
        {},
        {
            'StarSystem': {
                'SystemAddress': system_id,
                'name': None,
                'Population': 42,
            },
        },
    )

    await eddn_listener.flush_pending(pool)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT name, population FROM systems WHERE id64 = $1',
            system_id,
        )

    assert row is not None
    assert row['name'] == 'Existing Real System Name'
    assert row['population'] == 42


@pytest.mark.asyncio
async def test_scan_with_colliding_body_id_from_other_system_does_not_reparent(
    pool,
    isolated_eddn_system_writes,
):
    """Journal BodyID is unique only within a system, but bodies.id is the
    sole PK with no sequence and no system_id64 component. A scan of a
    colliding BodyID from a different system must be a no-op, not a steal —
    see the 2026-08-04 body_rings association_status drift incident."""
    owner_system_id = TEST_SYSTEM_IDS[7]
    intruder_system_id = TEST_SYSTEM_IDS[8]
    body_id = TEST_BODY_IDS[2]

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO systems (id64, name) VALUES ($1, 'EDDN Guard Owner System')",
            owner_system_id,
        )
        await conn.execute(
            "INSERT INTO systems (id64, name) VALUES ($1, 'EDDN Guard Intruder System')",
            intruder_system_id,
        )

    await eddn_listener.handle_scan(
        pool,
        {},
        {
            'SystemAddress': owner_system_id,
            'BodyID': body_id,
            'BodyName': 'Owner System Body 1 a',
            'PlanetClass': 'Rocky body',
        },
    )
    await eddn_listener.flush_pending(pool)

    await eddn_listener.handle_scan(
        pool,
        {},
        {
            'SystemAddress': intruder_system_id,
            'BodyID': body_id,
            'BodyName': 'Intruder System Body 1 a',
            'PlanetClass': 'Icy body',
        },
    )
    await eddn_listener.flush_pending(pool)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT system_id64, name, subtype FROM bodies WHERE id = $1',
            body_id,
        )

    assert row is not None
    assert row['system_id64'] == owner_system_id
    assert row['name'] == 'Owner System Body 1 a'
    assert row['subtype'] == 'Rocky body'


@pytest.mark.asyncio
async def test_scan_from_owning_system_still_updates_after_guard(
    pool,
    isolated_eddn_system_writes,
):
    """Companion to the collision-guard test: a same-system rescan must
    still update normally, proving the guard scopes to cross-system writes
    only rather than freezing the row."""
    owner_system_id = TEST_SYSTEM_IDS[7]
    body_id = TEST_BODY_IDS[2]

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO systems (id64, name) VALUES ($1, 'EDDN Guard Owner System')",
            owner_system_id,
        )

    await eddn_listener.handle_scan(
        pool,
        {},
        {
            'SystemAddress': owner_system_id,
            'BodyID': body_id,
            'BodyName': 'Owner System Body 1 a',
            'PlanetClass': 'Rocky body',
        },
    )
    await eddn_listener.flush_pending(pool)

    await eddn_listener.handle_scan(
        pool,
        {},
        {
            'SystemAddress': owner_system_id,
            'BodyID': body_id,
            'BodyName': 'Owner System Body 1 a',
            'PlanetClass': 'Icy body',
        },
    )
    await eddn_listener.flush_pending(pool)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT system_id64, subtype FROM bodies WHERE id = $1',
            body_id,
        )

    assert row is not None
    assert row['system_id64'] == owner_system_id
    assert row['subtype'] == 'Icy body'


@pytest.mark.asyncio
async def test_scan_with_rings_writes_locally_matched_body_rings_row(
    pool,
    isolated_eddn_system_writes,
):
    """2026-08-07 Codex Review finding: eddn_listener.py's own body_rings
    write (BODY_RING_UPSERT_SQL, via flush_pending) had no real-Postgres
    test asserting on body_rings content — bodies writes and import_spansh's
    ring writes were both covered, but this specific path wasn't.

    A second Codex Review finding on the first version of this test: the
    original two-flush version only proved rings resolve once a body is
    already committed from a *prior* flush — it didn't cover (and in fact
    sidestepped) the real production case, a single Scan message reporting
    a body and its Rings together for that body's first-ever sighting. That
    case used to lose the ring permanently: resolve_ring_rows_to_local_
    bodies ran before the bodies upsert loop within the same flush_pending
    call, so the ring's lookup missed the body this same flush was about to
    insert, and _pending_rings was cleared regardless. Ring resolution now
    runs after the bodies upsert loop in the same transaction, so this test
    exercises the real single-scan, single-flush path directly."""
    owner_system_id = TEST_SYSTEM_IDS[6]
    body_id = TEST_BODY_IDS[1]

    async def clear_rings():
        async with pool.acquire() as conn:
            await conn.execute('DELETE FROM body_rings WHERE system_id64 = $1', owner_system_id)

    await clear_rings()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO systems (id64, name) VALUES ($1, 'EDDN Ring Test System')",
                owner_system_id,
            )

        # One scan, one flush: the body and its Rings arrive together, as a
        # real Scan journal event reports them — this is the case that used
        # to lose the ring permanently.
        await eddn_listener.handle_scan(
            pool,
            {},
            {
                'SystemAddress': owner_system_id,
                'BodyID': body_id,
                'BodyName': 'Ring Test Body 1 a',
                'PlanetClass': 'Rocky body',
                'Rings': [
                    {
                        'Name': 'Ring Test Body 1 a A Ring',
                        'RingClass': 'eRingClass_Rocky',
                        'MassMT': 123.0,
                        'InnerRad': 1000.0,
                        'OuterRad': 2000.0,
                    },
                ],
            },
        )
        await eddn_listener.flush_pending(pool)

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT body_id, ring_name, ring_class, association_status '
                'FROM body_rings WHERE system_id64 = $1',
                owner_system_id,
            )

        assert row is not None, 'ring should have been written by eddn_listener.flush_pending'
        assert row['body_id'] == body_id
        assert row['ring_name'] == 'Ring Test Body 1 a A Ring'
        assert row['ring_class'] == 'eRingClass_Rocky'
        assert row['association_status'] == 'local_matched'
    finally:
        await clear_rings()
