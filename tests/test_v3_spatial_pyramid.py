"""Tests for the V3 spatial density pyramid cell-level registry + source resolver.

Reuses the `db_conn` fixture pattern from
`tests/test_journal_commander_association.py`: a real, disposable-DB-only
connection routed through `tests/helpers/db_isolation`, wrapped in a rolled
back transaction so nothing persists between tests. Skips (rather than fails)
when no local disposable Postgres is reachable.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
import pytest

os.environ.setdefault('CORS_ORIGINS', 'http://testserver')

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.helpers import db_isolation  # noqa: E402


@pytest.fixture
def db_conn():
    """A real, disposable-DB-only connection wrapped in a rolled-back transaction.

    Reuses the repo's fail-closed DB isolation helpers (tests/helpers/db_isolation.py)
    so this never targets a production-looking host/database. Skips (rather than
    fails) when no local disposable Postgres is reachable, per the project's
    "real-service tests must skip explicitly when the service is absent" rule.
    """
    target = db_isolation.default_target(os.environ)
    try:
        conn = psycopg.connect(target.dsn)
    except psycopg.OperationalError as exc:
        pytest.skip(f'disposable test Postgres unreachable at {target.redacted_dsn}: {exc}')
        return
    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def test_cell_levels_registered(db_conn):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, CELL_LEVELS, register_cell_levels
    register_cell_levels(db_conn, PYRAMID_VERSION)
    rows = db_conn.execute(
        "SELECT level, cell_size_ly FROM v3_spatial.cell_level WHERE spatial_pyramid_version=%s ORDER BY level",
        (PYRAMID_VERSION,),
    ).fetchall()
    assert [r[0] for r in rows] == [lvl.level for lvl in CELL_LEVELS]
    # sizes strictly decrease as level increases (coarse -> fine)
    sizes = [r[1] for r in rows]
    assert sizes == sorted(sizes, reverse=True)


def test_register_cell_levels_is_idempotent(db_conn):
    from scripts.v3_spatial_pyramid import PYRAMID_VERSION, register_cell_levels
    register_cell_levels(db_conn, PYRAMID_VERSION)
    register_cell_levels(db_conn, PYRAMID_VERSION)  # must not raise or duplicate
    n = db_conn.execute(
        "SELECT count(*) FROM v3_spatial.cell_level WHERE spatial_pyramid_version=%s",
        (PYRAMID_VERSION,),
    ).fetchone()[0]
    from scripts.v3_spatial_pyramid import CELL_LEVELS
    assert n == len(CELL_LEVELS)
