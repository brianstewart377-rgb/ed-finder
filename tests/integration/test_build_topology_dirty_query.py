from __future__ import annotations

import os
import re
from pathlib import Path

import psycopg2
import pytest

os.environ.setdefault('LOG_FILE', os.devnull)

import build_topology  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
NIGHTLY_UPDATE_SH = ROOT / 'scripts' / 'nightly_update.sh'

TEST_SYSTEM_IDS = (
    96_000_000_000_001,  # dirty rating, has topology row -> included
    96_000_000_000_002,  # clean rating, has topology row -> excluded
    96_000_000_000_003,  # clean rating, no topology row -> included
    96_000_000_000_004,  # no ratings row at all -> excluded (not in ratings)
)


def _populate_fixture(pg_conn):
    dirty_with_topo, clean_with_topo, clean_no_topo, _no_ratings_row = TEST_SYSTEM_IDS
    with pg_conn.cursor() as cur:
        for system_id in TEST_SYSTEM_IDS:
            cur.execute(
                "INSERT INTO systems (id64, name, rating_dirty) VALUES (%s, %s, %s)",
                (system_id, f'Topology Dirty Test {system_id}', system_id == dirty_with_topo),
            )
        for system_id in (dirty_with_topo, clean_with_topo, clean_no_topo):
            cur.execute(
                "INSERT INTO ratings (system_id64) VALUES (%s)",
                (system_id,),
            )
        for system_id in (dirty_with_topo, clean_with_topo):
            cur.execute(
                "INSERT INTO system_slot_topology (system_id64) VALUES (%s)",
                (system_id,),
            )
    pg_conn.commit()


def _extract_topo_dirty_inner_query() -> str:
    """Pull the inner row-selecting subquery out of nightly_update.sh's
    TOPO_DIRTY pg_count_into call (the part between `SELECT COUNT(*) FROM
    (` and `) topo_dirty`), so this test executes precisely what ships —
    as a plain row-returning SELECT, so it can check exactly which systems
    get selected — rather than a hand-copied approximation that could
    silently drift from the real script. A failed match here means the
    query's shape changed and this extraction needs updating to match."""
    source = NIGHTLY_UPDATE_SH.read_text(encoding='utf-8')
    match = re.search(
        r'pg_count_into TOPO_DIRTY "SELECT COUNT\(\*\) FROM \((?P<inner>.*?)\) topo_dirty"\n',
        source,
        re.DOTALL,
    )
    assert match is not None, (
        'Could not find TOPO_DIRTY pg_count_into in the expected '
        '"SELECT COUNT(*) FROM (...) topo_dirty" shape in nightly_update.sh — '
        'has it changed? Update this extraction pattern to match.'
    )
    return match.group('inner')


@pytest.fixture
def pg_conn():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = False

    def _cleanup():
        with conn.cursor() as cur:
            cur.execute(
                'DELETE FROM system_slot_topology WHERE system_id64 = ANY(%s)',
                (list(TEST_SYSTEM_IDS),),
            )
            cur.execute(
                'DELETE FROM ratings WHERE system_id64 = ANY(%s)',
                (list(TEST_SYSTEM_IDS),),
            )
            cur.execute(
                'DELETE FROM systems WHERE id64 = ANY(%s)',
                (list(TEST_SYSTEM_IDS),),
            )
        conn.commit()

    _cleanup()
    try:
        yield conn
    finally:
        _cleanup()
        conn.close()


@pytest.mark.db
def test_fetch_system_ids_dirty_mode_uses_systems_rating_dirty(pg_conn):
    """GitHub review / production incident 2026-08-05: rating_dirty lives on
    systems, not ratings. The previous `FROM ratings r ... WHERE
    r.rating_dirty = TRUE` errored on every real invocation (confirmed live
    in production: 'column "rating_dirty" does not exist', dating to the
    2026-05-10 commit that introduced this query) — meaning --dirty mode
    could never have actually selected a rating_dirty system by that path,
    only ever the "missing topology row" half of the OR. This proves the
    fixed query correctly includes both cases and correctly excludes a
    clean, already-topology-covered system."""
    dirty_with_topo, clean_with_topo, clean_no_topo, no_ratings_row = TEST_SYSTEM_IDS
    _populate_fixture(pg_conn)

    result = build_topology._fetch_system_ids(pg_conn, 'dirty', None)

    assert dirty_with_topo in result
    assert clean_no_topo in result
    assert clean_with_topo not in result
    assert no_ratings_row not in result


@pytest.mark.db
def test_nightly_update_topo_dirty_query_matches_fetch_system_ids(pg_conn):
    """Companion to the build_topology test above, for the separate
    bash-embedded SQL string in scripts/nightly_update.sh (Step 3.5's
    TOPO_DIRTY gate) — same production incident, same wrong-table bug, but
    build_topology.py's own fix does not touch this file. The comment above
    that query explicitly claims it uses "the same dirty signal as
    build_topology.py" — worth verifying directly rather than trusting the
    comment (see CLAUDE.md's own note on verifying same-name-same-thing
    claims), since these are two independently-maintained SQL strings that
    could silently drift apart again."""
    dirty_with_topo, _clean_with_topo, clean_no_topo, _no_ratings_row = TEST_SYSTEM_IDS
    _populate_fixture(pg_conn)

    fetched = set(build_topology._fetch_system_ids(pg_conn, 'dirty', None)) & set(TEST_SYSTEM_IDS)

    inner_sql = _extract_topo_dirty_inner_query()
    with pg_conn.cursor() as cur:
        cur.execute(inner_sql)
        selected = {row[0] for row in cur.fetchall()} & set(TEST_SYSTEM_IDS)

    assert selected == fetched
    assert selected == {dirty_with_topo, clean_no_topo}
