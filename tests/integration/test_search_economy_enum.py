"""Regression test — `/api/local/search` and `/api/search/galaxy` must
accept *any* shape of the economy filter without raising
``InvalidTextRepresentationError``.

Background (production incident, post-Phase-2 refactor)
------------------------------------------------------
The frontend's ``ECONOMY_OPTIONS`` dropdown ships ``'High Tech'`` (with a
space) as the wire value, and the ``High-Tech R&D`` quick-preset shipped
the same. The PostgreSQL ``economy_type`` enum literal is ``'HighTech'``
(no space) — see ``sql/001_schema.sql``. After the audit's Phase-2
refactor removed the inline-SQL fallback, casting the raw user input
``'High Tech'::economy_type`` raised
``asyncpg.exceptions.InvalidTextRepresentationError`` which the new
``routers/search.py`` correctly surfaces as HTTP 503 problem-details.

The fix maps any input form (lowercase / Title / spaced / aliased) to
the canonical PG enum literal via
``apps/api/src/search_economies.py::economy_enum_value`` before the SQL
cast. This test pins that contract.
"""
import pytest


pytestmark = pytest.mark.asyncio


# Every form a real client has been observed to send for HighTech.
HIGHTECH_FORMS = ['High Tech', 'high tech', 'high-tech', 'hightech', 'HighTech']

# Every form a real client has been observed to send for Extraction.
EXTRACTION_FORMS = ['extraction', 'Extraction']


@pytest.mark.parametrize('economy', HIGHTECH_FORMS)
async def test_local_search_accepts_every_hightech_form(client, economy):
    """All wire shapes of HighTech must return 200, not 503."""
    r = await client.post('/api/local/search', json={
        'reference_coords': {'x': 0, 'y': 0, 'z': 0},
        'filters':          {'distance': {'min': 0, 'max': 100000},
                             'economy':  economy},
        'size':             3,
        'sort_by':          'development',
    })
    assert r.status_code == 200, (
        f"economy={economy!r} returned {r.status_code}: {r.text}"
    )
    body = r.json()
    assert body.get('source') == 'local_db'
    # All results must actually be HighTech systems
    for row in body['results']:
        assert row.get('primaryEconomy') == 'HighTech', row


@pytest.mark.parametrize('economy', EXTRACTION_FORMS)
async def test_local_search_accepts_extraction_forms(client, economy):
    """Extraction (the audit's §C5 economy) must work in any case."""
    r = await client.post('/api/local/search', json={
        'reference_coords': {'x': 0, 'y': 0, 'z': 0},
        'filters':          {'distance': {'min': 0, 'max': 100000},
                             'economy':  economy},
        'size':             3,
        'sort_by':          'development',
    })
    assert r.status_code == 200, r.text


async def test_galaxy_search_accepts_spaced_high_tech(client):
    """The /api/search/galaxy endpoint shares the same code path."""
    r = await client.post('/api/search/galaxy', json={
        'economy':   'High Tech',
        'min_score': 0,
        'limit':     3,
        'offset':    0,
    })
    assert r.status_code == 200, r.text


async def test_unknown_economy_returns_422_not_503(client):
    """After Phase-2.1 (Literal-typed economy on request models), unknown
    inputs that the BeforeValidator can't resolve fall through Pydantic's
    union check and return a 422 with a clear 'input should be …' message
    instead of the previous 503-from-PostgreSQL.

    This is *better* than the old 'silently skip filter' semantics:
      * The frontend gets an immediate, structured error pointing at
        the bad field.
      * The TS codegen union types the field as `Agriculture | Refinery
        | Industrial | HighTech | Military | Tourism | Extraction |
        'any'`, so this case is unreachable from the typed path.
      * Old untyped consumers (curl, Postman, scripts) get an
        actionable 422 rather than a confusing 503.
    """
    r = await client.post('/api/local/search', json={
        'reference_coords': {'x': 0, 'y': 0, 'z': 0},
        'filters':          {'distance': {'min': 0, 'max': 1000},
                             'economy':  'NotAnEconomy'},
        'size':             3,
    })
    assert r.status_code == 422, r.text
    body = r.json()
    # FastAPI / Pydantic 2 error envelope
    assert any('economy' in str(e.get('loc', '')) for e in body['detail']), body


# Pure-function unit coverage of `economy_enum_value` lives in
# tests/test_search_economies_unit.py — outside the integration
# directory so the module-wide `pytestmark = pytest.mark.asyncio`
# doesn't apply to a sync helper test.
