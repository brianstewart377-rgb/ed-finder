from __future__ import annotations

import os

import psycopg2
import pytest

os.environ.setdefault('LOG_FILE', os.devnull)

import import_spansh  # noqa: E402


TEST_SYSTEM_ID = 98_000_000_000_001

SYS_COLS = [
    'id64', 'name', 'x', 'y', 'z',
    'primary_economy', 'secondary_economy',
    'population', 'security', 'allegiance', 'government',
    'controlling_faction', 'galaxy_region_id',
    'updated_at', 'rating_dirty', 'cluster_dirty',
]

# The exact exclusion set import_systems_delta() now applies, confirmed
# by direct inspection of real systems_1day.json.gz/systems_1week.json.gz
# (2026-08-06) - these fields are never present in either file.
DELTA_NEVER_PROVIDES = {
    'primary_economy', 'secondary_economy', 'population',
    'security', 'allegiance', 'government', 'controlling_faction',
}
DELTA_UPDATE_COLS = [
    c for c in SYS_COLS if c != 'id64' and c not in DELTA_NEVER_PROVIDES
]


@pytest.fixture
def pg_conn():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM systems WHERE id64 = %s', (TEST_SYSTEM_ID,))
        conn.commit()
        yield conn
    finally:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM systems WHERE id64 = %s', (TEST_SYSTEM_ID,))
        conn.commit()
        conn.close()


@pytest.mark.db
def test_systems_delta_upsert_preserves_fields_the_delta_never_carries(pg_conn):
    """Regression test for F-014 (docs/audits/round6-report.md), confirmed
    as an active nightly/weekly bug rather than a latent risk: Spansh's
    systems_1day.json.gz and systems_1week.json.gz delta files (verified
    by direct download and inspection) never carry economy, population,
    security, allegiance, government, or controlling_faction - every
    record is just {coords, id64, mainStar, name, updateTime}. Before
    this fix, import_systems_delta() included all of those in
    update_cols, so norm_economy/norm_security/etc.'s missing-input
    fallback to 'Unknown' (and _parse_system_population's fallback to
    None) unconditionally overwrote every touched system's real values
    on every nightly/weekly delta import."""
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO systems (
                id64, name, x, y, z,
                primary_economy, secondary_economy,
                population, security, allegiance, government,
                controlling_faction
            ) VALUES (
                %s, 'Delta Preserve Test System', 1.0, 2.0, 3.0,
                'Industrial', 'Extraction',
                123456, 'High', 'Federation', 'Democracy',
                'Delta Preserve Test Faction'
            )
            """,
            (TEST_SYSTEM_ID,),
        )
    pg_conn.commit()

    now_iso = '2026-08-06T00:00:00+00:00'
    delta_row = (
        TEST_SYSTEM_ID,
        'Delta Preserve Test System',
        1.5, 2.5, 3.5,
        import_spansh.norm_economy(None),
        import_spansh.norm_economy(None),
        import_spansh._parse_system_population({}),
        import_spansh.norm_security(None),
        import_spansh.norm_allegiance(None),
        import_spansh.norm_government(None),
        None,
        None,
        now_iso, True, True,
    )

    count = import_spansh.upsert_via_temp(
        pg_conn, 'systems', SYS_COLS, [delta_row], 'id64',
        update_cols=DELTA_UPDATE_COLS,
    )
    assert count == 1

    with pg_conn.cursor() as cur:
        cur.execute(
            '''
            SELECT x, y, z, primary_economy, secondary_economy,
                   population, security, allegiance, government,
                   controlling_faction
            FROM systems WHERE id64 = %s
            ''',
            (TEST_SYSTEM_ID,),
        )
        row = cur.fetchone()

    # Coordinates: the delta DOES carry these, so they update.
    assert row[0:3] == (1.5, 2.5, 3.5)
    # Everything the delta never carries: untouched, still the real values.
    assert row[3:] == (
        'Industrial', 'Extraction', 123456, 'High', 'Federation',
        'Democracy', 'Delta Preserve Test Faction',
    )
